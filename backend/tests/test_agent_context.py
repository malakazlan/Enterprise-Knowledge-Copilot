"""Tests for the agent context layer: context packs and knowledge write-back."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.models.user import User, UserRole

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

CONTEXT = "/api/v1/context"
KNOWLEDGE = "/api/v1/knowledge"
DOC = (
    b"# Site Safety\n\nAll workers must wear a helmet on the construction site.\n\n"
    b"High-visibility vests are required in vehicle zones."
)


async def _admin(
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


async def test_context_pack_assembles_with_provenance(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _admin(client, make_user, auth_headers)
    resp = await client.post(
        CONTEXT, headers=headers, json={"task": "helmet rules", "max_tokens": 500}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunks_included"] >= 1
    assert body["tokens_used"] <= 500
    assert "[Source: safety.md" in body["context"]
    assert "helmet" in body["context"].lower()
    assert body["sources"][0]["filename"] == "safety.md"


async def test_context_pack_respects_token_budget(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _admin(client, make_user, auth_headers)
    # A budget too small for any chunk yields an empty (but valid) pack.
    resp = await client.post(
        CONTEXT, headers=headers, json={"task": "helmet rules", "max_tokens": 100}
    )
    body = resp.json()
    assert body["tokens_used"] <= 100
    assert body["chunks_considered"] >= body["chunks_included"]


async def test_context_pack_respects_access_control(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    admin = await _admin(client, make_user, auth_headers)
    created = await client.post("/api/v1/collections", headers=admin, json={"name": "secret"})
    collection_id = created.json()["id"]
    secret = await client.post(
        f"/api/v1/documents?collection_id={collection_id}",
        headers=admin,
        files={"file": ("merger.md", b"# M\n\nProject Neptune acquires Contoso.", "text/markdown")},
    )
    assert secret.status_code == 201

    await make_user("outsider@example.com", role=UserRole.USER)
    outsider = await auth_headers("outsider@example.com")
    resp = await client.post(
        CONTEXT, headers=outsider, json={"task": "Project Neptune Contoso", "max_tokens": 2000}
    )
    assert "merger.md" not in resp.json()["context"]


async def test_knowledge_writeback_is_retrievable_and_attributed(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _admin(client, make_user, auth_headers)

    entry = await client.post(
        KNOWLEDGE,
        headers=headers,
        json={
            "title": "Customer Acme payment terms",
            "content": "Acme Corp prefers net-60 payment terms, confirmed on the last renewal.",
            "source": "billing-agent",
        },
    )
    assert entry.status_code == 201, entry.text
    body = entry.json()
    assert body["status"] == "completed"
    assert body["doc_metadata"]["knowledge_entry"] is True
    assert body["doc_metadata"]["source"] == "billing-agent"
    assert body["filename"] == "customer-acme-payment-terms.md"

    # Instantly retrievable with a citation to the entry.
    answer = await client.post(
        "/api/v1/query",
        headers=headers,
        json={"query": "What payment terms does Acme prefer?"},
    )
    assert answer.json()["answered"] is True
    assert "net-60" in answer.json()["answer"]


async def test_knowledge_requires_writer_role(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    member = await auth_headers("member@example.com")
    resp = await client.post(
        KNOWLEDGE,
        headers=member,
        json={"title": "Sneaky entry", "content": "should not be allowed to write this"},
    )
    assert resp.status_code == 403
