"""Tests for collections: document access control enforced at retrieval."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.models.user import User, UserRole

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

COLLECTIONS = "/api/v1/collections"
SECRET_DOC = b"# Merger\n\nProject Neptune acquires Contoso for nine billion dollars."
SHARED_DOC = b"# Handbook\n\nThe office closes at six in the evening."


async def _upload(
    client: AsyncClient, headers: dict[str, str], name: str, data: bytes, collection: str | None
) -> str:
    url = "/api/v1/documents" + (f"?collection_id={collection}" if collection else "")
    resp = await client.post(url, headers=headers, files={"file": (name, data, "text/markdown")})
    assert resp.status_code == 201, resp.text
    return resp.json()["document"]["id"]


async def _setup(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> tuple[dict[str, str], dict[str, str], dict[str, str], str, str]:
    """Admin + member + outsider; one secret doc in a collection, one shared."""
    await make_user("admin@example.com", role=UserRole.ADMIN)
    await make_user("member@example.com", role=UserRole.USER)
    await make_user("outsider@example.com", role=UserRole.USER)
    admin = await auth_headers("admin@example.com")
    member = await auth_headers("member@example.com")
    outsider = await auth_headers("outsider@example.com")

    created = await client.post(
        COLLECTIONS, headers=admin, json={"name": "legal", "description": "M&A"}
    )
    assert created.status_code == 201
    collection_id = created.json()["id"]

    added = await client.post(
        f"{COLLECTIONS}/{collection_id}/members",
        headers=admin,
        json={"email": "member@example.com"},
    )
    assert added.status_code == 201

    secret_id = await _upload(client, admin, "merger.md", SECRET_DOC, collection_id)
    await _upload(client, admin, "handbook.md", SHARED_DOC, None)
    return admin, member, outsider, collection_id, secret_id


async def test_member_can_query_collection_content(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    _, member, _, _, _ = await _setup(client, make_user, auth_headers)
    answer = await client.post(
        "/api/v1/query", headers=member, json={"query": "Who does Project Neptune acquire?"}
    )
    body = answer.json()
    assert body["answered"] is True
    assert "contoso" in body["answer"].lower()


async def test_outsider_cannot_reach_collection_content(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    _, _, outsider, _, secret_id = await _setup(client, make_user, auth_headers)

    # Query: the secret document must not inform the answer.
    answer = await client.post(
        "/api/v1/query", headers=outsider, json={"query": "Who does Project Neptune acquire?"}
    )
    body = answer.json()
    assert body["answered"] is False
    assert all("merger.md" != c["filename"] for c in body["citations"])

    # Explicitly targeting the document must not bypass access control.
    targeted = await client.post(
        "/api/v1/query",
        headers=outsider,
        json={"query": "Who does Project Neptune acquire?", "document_ids": [secret_id]},
    )
    assert targeted.json()["answered"] is False

    # Search channel is filtered too.
    search = await client.post(
        "/api/v1/search", headers=outsider, json={"query": "Project Neptune Contoso"}
    )
    assert all(r["filename"] != "merger.md" for r in search.json()["results"])

    # Direct reads 404; the shared corpus still works.
    assert (await client.get(f"/api/v1/documents/{secret_id}", headers=outsider)).status_code == 404
    assert (
        await client.get(f"/api/v1/documents/{secret_id}/chunks", headers=outsider)
    ).status_code == 404
    listed = (await client.get("/api/v1/documents", headers=outsider)).json()
    assert [d["filename"] for d in listed] == ["handbook.md"]
    shared = await client.post(
        "/api/v1/query", headers=outsider, json={"query": "When does the office close?"}
    )
    assert shared.json()["answered"] is True


async def test_membership_revocation_takes_effect(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    admin, member, _, collection_id, _ = await _setup(client, make_user, auth_headers)
    members = (await client.get(f"{COLLECTIONS}/{collection_id}/members", headers=admin)).json()
    user_id = members[0]["user_id"]

    removed = await client.delete(f"{COLLECTIONS}/{collection_id}/members/{user_id}", headers=admin)
    assert removed.status_code == 204

    answer = await client.post(
        "/api/v1/query", headers=member, json={"query": "Who does Project Neptune acquire?"}
    )
    assert answer.json()["answered"] is False


async def test_collection_admin_rules(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    admin, member, _, collection_id, _ = await _setup(client, make_user, auth_headers)

    # Duplicate name conflicts; non-admin cannot create.
    assert (
        await client.post(COLLECTIONS, headers=admin, json={"name": "legal"})
    ).status_code == 409
    assert (
        await client.post(COLLECTIONS, headers=member, json={"name": "mine"})
    ).status_code == 403

    # Members see their collections; counts are real.
    mine = (await client.get(COLLECTIONS, headers=member)).json()
    assert [c["name"] for c in mine] == ["legal"]
    assert mine[0]["document_count"] == 1 and mine[0]["member_count"] == 1

    # Deleting the collection makes its documents shared again.
    assert (await client.delete(f"{COLLECTIONS}/{collection_id}", headers=admin)).status_code == 204
    answer = await client.post(
        "/api/v1/query", headers=member, json={"query": "Who does Project Neptune acquire?"}
    )
    assert answer.json()["answered"] is True
