"""End-to-end tests for the hybrid /search endpoint."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient, Response

from app.models.user import User, UserRole

SEARCH = "/api/v1/search"
DOCUMENTS = "/api/v1/documents"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

SAFETY_DOC = (
    b"# Site Safety Manual\n\n"
    b"All workers must wear a helmet at all times on the construction site. "
    b"Helmets are inspected monthly by the safety officer.\n\n"
    b"Fire extinguishers are located at every exit."
)
FINANCE_DOC = (
    b"# Expense Policy\n\n"
    b"Invoices must be submitted before the 5th of each month. "
    b"Reimbursements are processed by the finance department within 10 days."
)


async def _upload(client: AsyncClient, headers: dict[str, str], name: str, data: bytes) -> Response:
    resp = await client.post(
        DOCUMENTS, headers=headers, files={"file": (name, data, "text/markdown")}
    )
    assert resp.status_code == 201, resp.text
    return resp


async def _search(
    client: AsyncClient, headers: dict[str, str], query: str, **kwargs: object
) -> Response:
    return await client.post(SEARCH, headers=headers, json={"query": query, **kwargs})


async def test_search_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(SEARCH, json={"query": "helmet"})
    assert resp.status_code == 401


async def test_hybrid_search_finds_the_right_document(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    await make_user("reader@example.com", role=UserRole.USER)
    admin = await auth_headers("admin@example.com")
    reader = await auth_headers("reader@example.com")

    await _upload(client, admin, "safety.md", SAFETY_DOC)
    await _upload(client, admin, "expenses.md", FINANCE_DOC)

    resp = await _search(client, reader, "who must wear a helmet?")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["profile"] == "general"
    assert body["reranked"] is True
    assert body["dense_candidates"] > 0
    assert body["sparse_candidates"] > 0
    assert body["results"], "expected at least one result"

    top = body["results"][0]
    assert top["filename"] == "safety.md"
    assert "helmet" in top["content"].lower()
    assert top["page_number"] == 1
    assert top["score"] > 0
    assert "sparse" in top["channels"] or "dense" in top["channels"]


async def test_search_respects_document_filter(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")

    await _upload(client, admin, "safety.md", SAFETY_DOC)
    finance_id = (await _upload(client, admin, "expenses.md", FINANCE_DOC)).json()["document"]["id"]

    resp = await _search(client, admin, "helmet safety", document_ids=[finance_id])
    assert resp.status_code == 200
    for item in resp.json()["results"]:
        assert item["document_id"] == finance_id


async def test_search_top_k_override(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")
    await _upload(client, admin, "safety.md", SAFETY_DOC)
    await _upload(client, admin, "expenses.md", FINANCE_DOC)

    resp = await _search(client, admin, "policy department safety", top_k=1)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) <= 1


async def test_search_with_named_profile(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")
    await _upload(client, admin, "safety.md", SAFETY_DOC)

    resp = await _search(client, admin, "helmet", profile="legal")
    assert resp.status_code == 200
    assert resp.json()["profile"] == "legal"

    missing = await _search(client, admin, "helmet", profile="does-not-exist")
    assert missing.status_code == 404


async def test_new_uploads_are_searchable_immediately(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")

    await _upload(client, admin, "safety.md", SAFETY_DOC)
    first = await _search(client, admin, "zephyrite")
    # The term does not exist yet: nothing from the sparse channel, and no
    # result can come from the not-yet-uploaded document.
    assert all(item["filename"] != "minerals.md" for item in first.json()["results"])

    await _upload(client, admin, "minerals.md", b"Zephyrite is a rare mineral used in coatings.")
    second = await _search(client, admin, "zephyrite")
    results = second.json()["results"]
    assert results, "expected the fresh document to be retrievable"
    assert results[0]["filename"] == "minerals.md"
    assert "sparse" in results[0]["channels"], "BM25 index should have refreshed"


async def test_deleted_documents_disappear_from_search(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")

    doc_id = (await _upload(client, admin, "safety.md", SAFETY_DOC)).json()["document"]["id"]
    before = await _search(client, admin, "helmet")
    assert before.json()["results"]

    deleted = await client.delete(f"{DOCUMENTS}/{doc_id}", headers=admin)
    assert deleted.status_code == 204

    after = await _search(client, admin, "helmet")
    assert all(item["document_id"] != doc_id for item in after.json()["results"])


async def test_empty_query_rejected(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")
    resp = await _search(client, admin, "")
    assert resp.status_code == 422
