"""Tests for the OpenAI-compatible surface — including the real OpenAI SDK."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx
import openai
from fastapi import FastAPI
from httpx import AsyncClient

from app.models.user import User, UserRole

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

DOC = b"# Safety\n\nAll workers must wear a helmet on the construction site."


async def _api_key(client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders) -> str:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    upload = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("safety.md", DOC, "text/markdown")},
    )
    assert upload.status_code == 201
    created = await client.post(
        "/api/v1/api-keys", headers=headers, json={"name": "compat", "role": "user"}
    )
    return str(created.json()["key"])


async def test_chat_completions_shape_and_grounding(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    key = await _api_key(client, make_user, auth_headers)
    resp = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "general",
            "messages": [{"role": "user", "content": "Who must wear a helmet?"}],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "general"
    message = body["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert "helmet" in message["content"].lower()
    assert "Sources:" in message["content"]
    assert "safety.md" in message["content"]
    assert body["usage"]["total_tokens"] > 0
    # Trust signals ride in the ekc extension.
    assert body["ekc"]["answered"] is True
    assert body["ekc"]["citations"][0]["filename"] == "safety.md"


async def test_refusals_keep_their_semantics(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    key = await _api_key(client, make_user, auth_headers)
    resp = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"messages": [{"role": "user", "content": "quantum banana smoothie recipe"}]},
    )
    body = resp.json()
    assert body["ekc"]["answered"] is False
    assert "can't answer" in body["choices"][0]["message"]["content"]


async def test_streaming_chunks_reassemble(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    key = await _api_key(client, make_user, auth_headers)
    collected: list[str] = []
    finish: str | None = None
    async with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "stream": True,
            "messages": [{"role": "user", "content": "Who must wear a helmet?"}],
        },
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line.removeprefix("data: ")
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            assert chunk["object"] == "chat.completion.chunk"
            choice = chunk["choices"][0]
            if choice["delta"].get("content"):
                collected.append(choice["delta"]["content"])
            if choice["finish_reason"]:
                finish = choice["finish_reason"]
    text = "".join(collected)
    assert "helmet" in text.lower() and "Sources:" in text
    assert finish == "stop"


async def test_models_lists_profiles(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    key = await _api_key(client, make_user, auth_headers)
    resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
    ids = {m["id"] for m in resp.json()["data"]}
    assert {"general", "legal"} <= ids


async def test_bad_key_is_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer ekc_not_a_real_key"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


async def test_real_openai_sdk_works_against_us(
    app: FastAPI, client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    """The actual `openai` package, base_url pointed at our app."""
    key = await _api_key(client, make_user, auth_headers)
    sdk = openai.AsyncOpenAI(
        base_url="http://compat-test/v1",
        api_key=key,
        http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app)),
    )
    try:
        completion = await sdk.chat.completions.create(
            model="general",
            messages=[{"role": "user", "content": "Who must wear a helmet?"}],
        )
    finally:
        await sdk.close()
    assert completion.choices[0].message.role == "assistant"
    assert "helmet" in (completion.choices[0].message.content or "").lower()
    assert completion.model == "general"
