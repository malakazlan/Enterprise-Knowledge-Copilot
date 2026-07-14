"""Tests for the Confluence connector — a fake Atlassian, real crypto."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.services.connectors import confluence
from app.services.connectors.confluence import storage_to_markdown

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

CONNECTORS = "/api/v1/connectors"

_PAGES = {
    "results": [
        {
            "id": "101",
            "title": "Incident response",
            "space": {"key": "ENG"},
            "body": {
                "storage": {
                    "value": (
                        "<h1>Severity levels</h1>"
                        "<p>A SEV-1 incident requires paging the on-call engineer "
                        "within five minutes.</p>"
                        "<ul><li>SEV-1: total outage</li><li>SEV-2: degraded</li></ul>"
                    )
                }
            },
        },
        {
            "id": "102",
            "title": "Empty stub",
            "space": {"key": "ENG"},
            "body": {"storage": {"value": "<p>   </p>"}},
        },
    ]
}


@pytest.fixture
async def fake_confluence() -> AsyncIterator[dict[str, int]]:
    calls = {"list": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rest/api/content"):
            calls["list"] += 1
            expected = base64.b64encode(b"ops@example.com:atl-token-7").decode()
            assert request.headers["Authorization"] == f"Basic {expected}"
            assert request.url.params["spaceKey"] == "ENG"
            return httpx.Response(200, json=_PAGES)
        return httpx.Response(404)

    confluence._transport = httpx.MockTransport(handler)
    yield calls
    confluence._transport = None


async def _admin(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> dict[str, str]:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    return await auth_headers("admin@example.com")


def test_storage_to_markdown_structure() -> None:
    text = storage_to_markdown(
        "<h2>Rules</h2><p>Be kind.</p><ul><li>One</li><li>Two</li></ul><script>alert(1)</script>"
    )
    assert "## Rules" in text
    assert "- One" in text and "- Two" in text
    assert "alert" not in text


async def test_create_encrypts_token_and_sync_ingests(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    fake_confluence: dict[str, int],
) -> None:
    admin = await _admin(client, make_user, auth_headers)

    created = await client.post(
        CONNECTORS,
        headers=admin,
        json={
            "name": "eng-wiki",
            "type": "confluence",
            "config": {
                "base_url": "https://acme.atlassian.net/wiki",
                "email": "ops@example.com",
                "api_token": "atl-token-7",
                "space_keys": ["ENG"],
            },
        },
    )
    assert created.status_code == 201, created.text
    connector = created.json()
    # Ready immediately; the plaintext token never comes back in any form.
    assert connector["config"]["connected"] is True
    assert "api_token" not in connector["config"]
    assert "api_token_enc" not in connector["config"]

    report = (await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)).json()
    assert report["ingested"] == ["ENG - Incident response.md"]
    assert report["skipped_unsupported"] == 1  # the whitespace-only stub

    answer = await client.post(
        "/api/v1/query",
        headers=admin,
        json={"query": "How fast must the on-call engineer be paged for a SEV-1?"},
    )
    assert answer.json()["answered"] is True
    assert "five minutes" in answer.json()["answer"].lower()

    # Re-sync: idempotent.
    again = (await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)).json()
    assert again["ingested"] == [] and again["skipped_existing"] == 1


async def test_create_without_token_is_rejected(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    admin = await _admin(client, make_user, auth_headers)
    missing = await client.post(
        CONNECTORS,
        headers=admin,
        json={
            "name": "eng-wiki",
            "type": "confluence",
            "config": {"base_url": "https://acme.atlassian.net/wiki", "email": "a@b.co"},
        },
    )
    assert missing.status_code == 422
    assert "api_token" in missing.text
