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


async def test_setup_copilot_eval_loop(mcp_env: None) -> None:
    """The copilot's core loop: dataset -> case -> run -> metrics."""
    profiles = await mcp_server.list_profiles()
    names = {p["name"] for p in profiles}
    assert {"legal", "general"} <= names

    dataset = await mcp_server.eval_create_dataset("smoke", profile="general")
    case = await mcp_server.eval_add_case(
        dataset["dataset_id"],
        "Who must wear a helmet?",
        expected_keywords=["helmet"],
    )
    assert case["case_id"]

    run = await mcp_server.eval_run(dataset["dataset_id"])
    assert run["case_count"] == 1
    assert run["metrics"]["keyword_recall"] == 1.0

    queue = await mcp_server.review_queue()
    assert isinstance(queue, list)


async def test_setup_copilot_prompt_registered() -> None:
    prompts = await mcp_server.mcp.list_prompts()
    assert "setup-copilot" in {p.name for p in prompts}
    result = await mcp_server.mcp.get_prompt("setup-copilot")
    text = result.messages[0].content.text
    assert "INTERVIEW" in text and "eval_run" in text


async def test_agent_context_loop(mcp_env: None) -> None:
    """The context-maintainer loop: write knowledge -> get it back as context."""
    written = await mcp_server.write_knowledge(
        "Acme escalation contact",
        "Escalations for Acme Corp go to Jordan Reyes in customer success.",
        source="support-agent",
        verify_in_days=90,
    )
    assert written["status"] == "completed"
    assert written["verify_by"] is not None

    pack = await mcp_server.get_context("Who handles Acme escalations?", max_tokens=800)
    assert "Jordan Reyes" in pack["context"]
    assert pack["tokens_used"] <= 800
    assert pack["sources"][0]["filename"] == "acme-escalation-contact.md"


async def test_new_tools_registered() -> None:
    tools = await mcp_server.mcp.list_tools()
    names = {tool.name for tool in tools}
    assert {"get_context", "write_knowledge"} <= names


async def test_memory_tools_roundtrip(mcp_env: None) -> None:
    """Agent memory over MCP: remember -> recall, scoped to the key."""
    stored = await mcp_server.remember(
        "Customer Globex escalations go to the platinum queue.", kind="fact", ttl_days=30
    )
    assert stored["scope"].startswith("key:")
    assert stored["expires_at"] is not None

    matches = await mcp_server.recall("Where do Globex escalations go?")
    assert matches and "platinum queue" in matches[0]["content"]
