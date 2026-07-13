"""Tests for Google Drive click-to-connect — a fake Google, real crypto."""

from __future__ import annotations

import io
import urllib.parse
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from httpx import AsyncClient

from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.user import User, UserRole
from app.services.connectors import gdrive

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

CONNECTORS = "/api/v1/connectors"


def _docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
async def fake_google(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, int]]:
    """Configure gdrive settings and serve a two-file fake Drive."""
    from pydantic import SecretStr

    from app.core.config import settings

    calls = {"token": 0}
    exported = _docx("The onboarding checklist requires a signed NDA before day one.")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            calls["token"] += 1
            body = urllib.parse.parse_qs(request.content.decode())
            if body["grant_type"][0] == "authorization_code":
                return httpx.Response(
                    200, json={"refresh_token": "google-refresh-123", "access_token": "at-1"}
                )
            assert body["refresh_token"][0] == "google-refresh-123"
            return httpx.Response(200, json={"access_token": "at-2"})
        if path.endswith("/files"):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "gdoc-1",
                            "name": "Onboarding checklist",
                            "mimeType": "application/vnd.google-apps.document",
                        },
                        {"id": "bin-1", "name": "notes.md", "mimeType": "text/markdown"},
                        {"id": "img-x", "name": "photo.heic", "mimeType": "image/heic"},
                    ]
                },
            )
        if path.endswith("/files/gdoc-1/export"):
            return httpx.Response(200, content=exported)
        if path.endswith("/files/bin-1"):
            return httpx.Response(200, content=b"# Notes\n\nBadges are collected at the gate.")
        if path.endswith("/files/img-x"):
            return httpx.Response(200, content=b"\x00heic")
        return httpx.Response(404)

    monkeypatch.setattr(settings, "gdrive_client_id", "ekc-drive-client")
    monkeypatch.setattr(settings, "gdrive_client_secret", SecretStr("drive-secret"))
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    gdrive._transport = httpx.MockTransport(handler)
    yield calls
    gdrive._transport = None


async def _admin(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> dict[str, str]:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    return await auth_headers("admin@example.com")


async def test_crypto_roundtrip() -> None:
    token = encrypt_secret("super-secret-refresh")
    assert token != "super-secret-refresh"
    assert decrypt_secret(token) == "super-secret-refresh"


async def test_full_connect_and_sync_flow(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    fake_google: dict[str, int],
) -> None:
    admin = await _admin(client, make_user, auth_headers)

    created = await client.post(
        CONNECTORS,
        headers=admin,
        json={"name": "company-drive", "type": "gdrive", "config": {}},
    )
    assert created.status_code == 201, created.text
    connector = created.json()
    assert connector["config"]["connected"] is False

    # Syncing before connecting is a clear error.
    early = await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)
    assert early.status_code == 422

    # 1. Authorize: redirect to Google's consent screen with signed state.
    auth = await client.get(f"{CONNECTORS}/{connector['id']}/authorize", headers=admin)
    assert auth.status_code == 307
    location = auth.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    state = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["state"][0]

    # 2. Google redirects back (unauthenticated browser request).
    done = await client.get(
        f"{CONNECTORS}/gdrive/callback", params={"code": "consent-code", "state": state}
    )
    assert done.status_code == 307
    assert done.headers["location"] == "/integrations/"

    # Token stored encrypted; never exposed through the API.
    listed = (await client.get(CONNECTORS, headers=admin)).json()
    assert listed[0]["config"]["connected"] is True
    assert "refresh_token_enc" not in listed[0]["config"]

    # 3. Sync: gdoc exported to docx, markdown ingested, heic skipped.
    report = (await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)).json()
    assert sorted(report["ingested"]) == ["Onboarding checklist.docx", "notes.md"]
    assert report["skipped_unsupported"] == 1
    assert report["failed"] == []

    # Content is immediately answerable.
    answer = await client.post(
        "/api/v1/query",
        headers=admin,
        json={"query": "What does the onboarding checklist require before day one?"},
    )
    assert answer.json()["answered"] is True
    assert "NDA" in answer.json()["answer"]

    # Re-sync: idempotent.
    again = (await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)).json()
    assert again["ingested"] == [] and again["skipped_existing"] == 2


async def test_forged_state_rejected(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    fake_google: dict[str, int],
) -> None:
    await _admin(client, make_user, auth_headers)
    forged = await client.get(
        f"{CONNECTORS}/gdrive/callback", params={"code": "x", "state": "not-a-state"}
    )
    assert forged.status_code == 401


async def test_authorize_requires_admin(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    fake_google: dict[str, int],
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    member = await auth_headers("member@example.com")
    denied = await client.get(
        f"{CONNECTORS}/00000000-0000-0000-0000-000000000000/authorize", headers=member
    )
    assert denied.status_code == 403
