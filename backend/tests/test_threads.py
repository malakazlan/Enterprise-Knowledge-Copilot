"""Tests for chat threads and the SSE streaming endpoint."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.models.user import User, UserRole

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

THREADS = "/api/v1/threads"
DOC = b"# Safety\n\nAll workers must wear a helmet on the construction site."


async def _setup(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> dict[str, str]:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    upload = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("safety.md", DOC, "text/markdown")},
    )
    assert upload.status_code == 201
    return headers


async def test_thread_lifecycle_and_auto_title(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _setup(client, make_user, auth_headers)

    created = await client.post(THREADS, headers=headers, json={})
    assert created.status_code == 201
    thread = created.json()
    assert thread["title"] == "New conversation"

    # Ask into the thread: message persists, title adopts the first question.
    answer = await client.post(
        "/api/v1/query",
        headers=headers,
        json={"query": "Who must wear a helmet?", "thread_id": thread["id"]},
    )
    assert answer.status_code == 200 and answer.json()["answered"] is True

    detail = (await client.get(f"{THREADS}/{thread['id']}", headers=headers)).json()
    assert detail["title"] == "Who must wear a helmet?"
    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["answered"] is True
    assert detail["messages"][0]["citations"]

    listed = (await client.get(THREADS, headers=headers)).json()
    assert [t["id"] for t in listed] == [thread["id"]]

    deleted = await client.delete(f"{THREADS}/{thread['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(THREADS, headers=headers)).json() == []
    # The audit row survives thread deletion.
    logs = await client.get("/api/v1/reviews?status=pending", headers=headers)
    assert logs.status_code == 200


async def test_thread_ownership_enforced(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _setup(client, make_user, auth_headers)
    await make_user("other@example.com", role=UserRole.USER)
    other = await auth_headers("other@example.com")

    thread = (await client.post(THREADS, headers=headers, json={})).json()

    assert (await client.get(f"{THREADS}/{thread['id']}", headers=other)).status_code == 404
    stolen = await client.post(
        "/api/v1/query",
        headers=other,
        json={"query": "anything", "thread_id": thread["id"]},
    )
    assert stolen.status_code == 404


async def test_stream_emits_meta_tokens_result(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _setup(client, make_user, auth_headers)

    events: list[tuple[str, dict[str, object]]] = []
    async with client.stream(
        "POST",
        "/api/v1/query/stream",
        headers=headers,
        json={"query": "Who must wear a helmet?"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        current: str | None = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current = line.removeprefix("event: ")
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line.removeprefix("data: "))))

    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "result"
    assert "token" in names

    result = events[-1][1]
    assert result["answered"] is True
    streamed_text = "".join(str(data["text"]) for name, data in events if name == "token").strip()
    assert streamed_text == str(result["answer"]).strip()
