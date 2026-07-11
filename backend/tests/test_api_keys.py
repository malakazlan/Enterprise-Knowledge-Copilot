"""Tests for API key management and machine-to-machine authentication."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.apikey import ApiKey
from app.models.querylog import QueryLog
from app.models.user import User, UserRole

KEYS = "/api/v1/api-keys"
QUERY = "/api/v1/query"
SEARCH = "/api/v1/search"
DOCUMENTS = "/api/v1/documents"
PROFILES = "/api/v1/profiles"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]


async def _admin_headers(make_user: MakeUser, auth_headers: AuthHeaders) -> dict[str, str]:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    return await auth_headers("admin@example.com")


async def _create_key(
    client: AsyncClient, headers: dict[str, str], **payload: object
) -> dict[str, object]:
    resp = await client.post(KEYS, headers=headers, json={"name": "bot", **payload})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_returns_secret_once_and_lists_metadata_only(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _admin_headers(make_user, auth_headers)
    created = await _create_key(client, headers, name="intranet-bot")

    key = str(created["key"])
    assert key.startswith("ekc_")
    assert created["key_prefix"] == key[:12]
    assert created["role"] == "user"

    listing = await client.get(KEYS, headers=headers)
    assert listing.status_code == 200
    entries = listing.json()
    assert len(entries) == 1
    assert entries[0]["key_prefix"] == key[:12]
    assert entries[0]["is_active"] is True
    assert "key" not in entries[0], "the full secret must never be listed"
    assert "key_hash" not in entries[0]


async def test_key_management_is_admin_only(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    member = await auth_headers("member@example.com")
    assert (await client.post(KEYS, headers=member, json={"name": "x"})).status_code == 403
    assert (await client.get(KEYS, headers=member)).status_code == 403
    assert (await client.get(KEYS)).status_code == 401


async def test_api_key_works_on_data_plane(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    admin = await _admin_headers(make_user, auth_headers)
    upload = await client.post(
        DOCUMENTS,
        headers=admin,
        files={"file": ("safety.md", b"All workers must wear a helmet on site.", "text/markdown")},
    )
    assert upload.status_code == 201

    key = str((await _create_key(client, admin))["key"])
    key_headers = {"X-API-Key": key}

    assert (await client.get(PROFILES, headers=key_headers)).status_code == 200
    assert (
        await client.post(SEARCH, headers=key_headers, json={"query": "helmet"})
    ).status_code == 200

    answer = await client.post(QUERY, headers=key_headers, json={"query": "Who wears a helmet?"})
    assert answer.status_code == 200
    assert answer.json()["answered"] is True

    # The audit log attributes the query to the key, not a user.
    log = (
        (await db_session.execute(select(QueryLog).order_by(QueryLog.created_at.desc())))
        .scalars()
        .first()
    )
    assert log is not None
    assert log.api_key_id is not None
    assert log.user_id is None


async def test_key_role_is_enforced(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    admin = await _admin_headers(make_user, auth_headers)
    user_key = str((await _create_key(client, admin, role="user"))["key"])
    reviewer_key = str((await _create_key(client, admin, role="reviewer"))["key"])

    files = {"file": ("doc.md", b"some content here", "text/markdown")}
    denied = await client.post(DOCUMENTS, headers={"X-API-Key": user_key}, files=files)
    assert denied.status_code == 403

    allowed = await client.post(DOCUMENTS, headers={"X-API-Key": reviewer_key}, files=files)
    assert allowed.status_code == 201


async def test_revoked_key_is_rejected(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    admin = await _admin_headers(make_user, auth_headers)
    created = await _create_key(client, admin)
    key_headers = {"X-API-Key": str(created["key"])}
    assert (await client.get(PROFILES, headers=key_headers)).status_code == 200

    revoke = await client.delete(f"{KEYS}/{created['id']}", headers=admin)
    assert revoke.status_code == 204
    # Idempotent; unknown ids are 404.
    assert (await client.delete(f"{KEYS}/{created['id']}", headers=admin)).status_code == 204
    assert (await client.delete(f"{KEYS}/{uuid.uuid4()}", headers=admin)).status_code == 404

    assert (await client.get(PROFILES, headers=key_headers)).status_code == 401


async def test_expired_key_is_rejected(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    admin = await _admin_headers(make_user, auth_headers)
    created = await _create_key(client, admin, expires_in_days=30)

    api_key = await db_session.get(ApiKey, uuid.UUID(str(created["id"])))
    assert api_key is not None
    api_key.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    resp = await client.get(PROFILES, headers={"X-API-Key": str(created["key"])})
    assert resp.status_code == 401


async def test_garbage_keys_are_rejected(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await _admin_headers(make_user, auth_headers)
    for bad in ("ekc_totally-not-a-real-key-000000", "sk_wrong_scheme", "x"):
        resp = await client.get(PROFILES, headers={"X-API-Key": bad})
        assert resp.status_code == 401, bad
