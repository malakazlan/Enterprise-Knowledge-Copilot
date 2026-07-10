"""End-to-end tests for document upload, ingestion, listing, and deletion."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.models.user import User, UserRole

DOCUMENTS = "/api/v1/documents"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
) -> object:
    return await client.post(
        DOCUMENTS,
        headers=headers,
        files={"file": (filename, content, content_type)},
    )


async def test_upload_ingests_document_end_to_end(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")

    resp = await _upload(
        client, headers, "sop.md", b"# Safety\n\nAlways wear a helmet on site.", "text/markdown"
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document"]["status"] == "completed"
    assert body["document"]["filename"] == "sop.md"
    assert body["document"]["page_count"] == 1
    assert body["document"]["checksum"]
    assert body["job"]["status"] == "succeeded"
    assert body["job"]["stage"] is None


async def test_reviewer_can_upload(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("rev@example.com", role=UserRole.REVIEWER)
    headers = await auth_headers("rev@example.com")
    resp = await _upload(client, headers, "manual.txt", b"Operating manual content here.")
    assert resp.status_code == 201


async def test_regular_user_cannot_upload(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    headers = await auth_headers("member@example.com")
    resp = await _upload(client, headers, "a.txt", b"content")
    assert resp.status_code == 403


async def test_upload_requires_authentication(client: AsyncClient) -> None:
    resp = await _upload(client, {}, "a.txt", b"content")
    assert resp.status_code == 401


async def test_empty_upload_is_rejected(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    resp = await _upload(client, headers, "empty.txt", b"")
    assert resp.status_code == 422


async def test_list_and_get_document(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    await make_user("reader@example.com", role=UserRole.USER)
    admin_headers = await auth_headers("admin@example.com")
    reader_headers = await auth_headers("reader@example.com")

    upload = await _upload(client, admin_headers, "doc.txt", b"some searchable text here")
    document_id = upload.json()["document"]["id"]

    listing = await client.get(DOCUMENTS, headers=reader_headers)
    assert listing.status_code == 200
    assert any(item["id"] == document_id for item in listing.json())

    fetched = await client.get(f"{DOCUMENTS}/{document_id}", headers=reader_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == document_id


async def test_jobs_endpoint_reports_success(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    upload = await _upload(client, headers, "doc.txt", b"content for jobs endpoint")
    document_id = upload.json()["document"]["id"]

    jobs = await client.get(f"{DOCUMENTS}/{document_id}/jobs", headers=headers)
    assert jobs.status_code == 200
    payload = jobs.json()
    assert len(payload) == 1
    assert payload[0]["status"] == "succeeded"


async def test_delete_is_admin_only_and_removes_document(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    await make_user("rev@example.com", role=UserRole.REVIEWER)
    admin_headers = await auth_headers("admin@example.com")
    rev_headers = await auth_headers("rev@example.com")

    upload = await _upload(client, admin_headers, "doc.txt", b"delete me content")
    document_id = upload.json()["document"]["id"]

    forbidden = await client.delete(f"{DOCUMENTS}/{document_id}", headers=rev_headers)
    assert forbidden.status_code == 403

    deleted = await client.delete(f"{DOCUMENTS}/{document_id}", headers=admin_headers)
    assert deleted.status_code == 204

    gone = await client.get(f"{DOCUMENTS}/{document_id}", headers=admin_headers)
    assert gone.status_code == 404


async def test_get_unknown_document_returns_404(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    resp = await client.get(f"{DOCUMENTS}/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
