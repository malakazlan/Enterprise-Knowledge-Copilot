"""Tests for the MCP server tools (wired into the app via ASGI transport)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.models.user import User, UserRole

pytest.importorskip("mcp")

from app.mcp import server as mcp_server

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

DOC = b"# Safety\n\nAll workers must wear a helmet on the construction site."


@pytest.fixture
async def mcp_env(
    app: FastAPI,
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[None]:
    """Point the MCP tools at the test app with a real API key."""
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    upload = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("safety.md", DOC, "text/markdown")},
    )
    assert upload.status_code == 201
    created = await client.post(
        "/api/v1/api-keys", headers=headers, json={"name": "mcp", "role": "admin"}
    )
    assert created.status_code == 201

    monkeypatch.setenv("EKC_URL", "http://mcp-test")
    monkeypatch.setenv("EKC_API_KEY", created.json()["key"])
    mcp_server._transport = httpx.ASGITransport(app=app)
    yield
    mcp_server._transport = None


async def test_ask_returns_grounded_answer(mcp_env: None) -> None:
    result = await mcp_server.ask("Who must wear a helmet?")
    assert result["answered"] is True
    assert "helmet" in (result["answer"] or "").lower()
    assert result["citations"] and result["citations"][0]["filename"] == "safety.md"
    assert 0 < result["confidence"] <= 1


async def test_search_returns_passages(mcp_env: None) -> None:
    hits = await mcp_server.search("helmet", top_k=3)
    assert hits and hits[0]["filename"] == "safety.md"
    assert "helmet" in hits[0]["content"].lower()


async def test_list_documents_and_stats(mcp_env: None) -> None:
    docs = await mcp_server.list_documents()
    assert [d["filename"] for d in docs] == ["safety.md"]
    stats = await mcp_server.deployment_stats()
    assert stats["documents_total"] == 1


async def test_missing_config_raises() -> None:
    assert mcp_server._transport is None
    with pytest.raises(RuntimeError, match="EKC_URL"):
        await mcp_server.list_documents()


async def test_tools_registered() -> None:
    tools = await mcp_server.mcp.list_tools()
    names = {tool.name for tool in tools}
    assert {"ask", "search", "list_documents", "deployment_stats"} <= names
