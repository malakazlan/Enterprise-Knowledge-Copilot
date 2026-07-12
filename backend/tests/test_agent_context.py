"""Tests for the agent context layer: context packs and knowledge write-back."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
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


async def test_knowledge_lifecycle_stale_surfacing(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    headers = await _admin(client, make_user, auth_headers)

    entry = await client.post(
        KNOWLEDGE,
        headers=headers,
        json={
            "title": "Quarterly pricing sheet",
            "content": "Standard seat price is 49 dollars per month until further notice.",
            "verify_in_days": 30,
        },
    )
    assert entry.status_code == 201
    assert entry.json()["verify_by"] is not None

    # Not stale yet: verify_by is in the future.
    stale = (await client.get("/api/v1/documents?stale=true", headers=headers)).json()
    assert stale == []

    # Force it past due directly, as time passing would.
    await db_session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(entry.json()["id"]))
        .values(verify_by=datetime(2020, 1, 1, tzinfo=timezone.utc))
    )
    await db_session.commit()

    stale = (await client.get("/api/v1/documents?stale=true", headers=headers)).json()
    assert [d["filename"] for d in stale] == ["quarterly-pricing-sheet.md"]

    stats = (await client.get("/api/v1/admin/stats", headers=headers)).json()
    assert stats["documents_stale"] == 1
