"""End-to-end tests for the grounded /query endpoint."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.querylog import QueryLog
from app.models.user import User, UserRole

QUERY = "/api/v1/query"
DOCUMENTS = "/api/v1/documents"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

SAFETY_DOC = (
    b"# Site Safety Manual\n\n"
    b"All workers must wear a helmet at all times on the construction site. "
    b"Helmets are inspected monthly by the safety officer."
)


async def _upload(client: AsyncClient, headers: dict[str, str], name: str, data: bytes) -> Response:
    resp = await client.post(
        DOCUMENTS, headers=headers, files={"file": (name, data, "text/markdown")}
    )
    assert resp.status_code == 201, resp.text
    return resp


async def _ask(
    client: AsyncClient, headers: dict[str, str], question: str, **kwargs: object
) -> Response:
    return await client.post(QUERY, headers=headers, json={"query": question, **kwargs})


async def test_query_requires_auth(client: AsyncClient) -> None:
    assert (await client.post(QUERY, json={"query": "hi"})).status_code == 401


async def test_query_answers_with_citations_and_confidence(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    await _upload(client, headers, "safety.md", SAFETY_DOC)

    resp = await _ask(client, headers, "Who must wear a helmet on site?")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["answered"] is True
    assert body["answer"] and "helmet" in body["answer"].lower()
    assert body["refusal_reason"] is None
    assert body["model"] == "extractive-v1"
    assert body["query_id"]

    assert body["citations"], "expected at least one citation"
    citation = body["citations"][0]
    assert citation["filename"] == "safety.md"
    assert citation["page_number"] == 1
    assert citation["snippet"]

    assert 0.0 < body["confidence"] <= 1.0
    breakdown = body["confidence_breakdown"]
    assert set(breakdown) == {"retrieval", "groundedness", "citations"}
    assert body["grounded_ratio"] == 1.0  # extractive answers quote sources verbatim


async def test_query_refuses_when_no_documents(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")

    resp = await _ask(client, headers, "anything at all?")
    body = resp.json()
    assert body["answered"] is False
    assert body["answer"] is None
    assert body["refusal_reason"] == "no_relevant_documents"
    assert body["confidence"] == 0.0


async def test_query_refuses_on_irrelevant_question(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    await _upload(client, headers, "safety.md", SAFETY_DOC)

    resp = await _ask(client, headers, "quantum banana smoothie recipe")
    body = resp.json()
    assert body["answered"] is False
    assert body["refusal_reason"] == "insufficient_evidence"
    assert body["citations"] == []


async def test_query_with_unknown_profile_is_404(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    resp = await _ask(client, headers, "hello?", profile="nope")
    assert resp.status_code == 404


async def test_every_query_is_audited(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    user = await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    await _upload(client, headers, "safety.md", SAFETY_DOC)

    answered = await _ask(client, headers, "Who must wear a helmet?")
    refused = await _ask(client, headers, "quantum banana smoothie recipe")
    assert answered.status_code == 200 and refused.status_code == 200

    logs = (
        (await db_session.execute(select(QueryLog).order_by(QueryLog.created_at))).scalars().all()
    )
    assert len(logs) == 2

    answered_log = next(log for log in logs if log.answered)
    refused_log = next(log for log in logs if not log.answered)
    assert answered_log.user_id == user.id
    assert answered_log.profile == "general"
    assert answered_log.citations, "citations must be recorded for audit"
    assert refused_log.refusal_reason == "insufficient_evidence"
    assert str(answered_log.id) == answered.json()["query_id"]


async def test_batch_query(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    upload = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("s.md", b"# Safety\n\nAll workers must wear a helmet.", "text/markdown")},
    )
    assert upload.status_code == 201

    resp = await client.post(
        "/api/v1/query/batch",
        headers=headers,
        json={"queries": ["Who must wear a helmet?", "quantum banana smoothie recipe"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["answered"] == 1 and body["refused"] == 1
    assert body["results"][0]["answered"] is True
    assert body["results"][1]["answered"] is False

    # Bounds: empty and oversized batches are rejected.
    empty = await client.post("/api/v1/query/batch", headers=headers, json={"queries": []})
    assert empty.status_code == 422
    too_many = await client.post(
        "/api/v1/query/batch", headers=headers, json={"queries": ["q"] * 26}
    )
    assert too_many.status_code == 422
