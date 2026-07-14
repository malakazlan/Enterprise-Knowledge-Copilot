"""Tests for Notion click-to-connect — a fake Notion, real crypto."""

from __future__ import annotations

import urllib.parse
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.services.connectors import notion

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

CONNECTORS = "/api/v1/connectors"

_PAGE = {
    "object": "page",
    "id": "page-1",
    "properties": {
        "title": {"type": "title", "title": [{"plain_text": "Expense policy"}]},
    },
}
_PAGE_2 = {
    "object": "page",
    "id": "page-2",
    "properties": {
        "Name": {"type": "title", "title": [{"plain_text": "Team rituals"}]},
    },
}


@pytest.fixture
async def fake_notion(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, int]]:
    """Configure Notion settings and serve a two-page fake workspace."""
    from pydantic import SecretStr

    from app.core.config import settings

    calls = {"token": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/oauth/token":
            calls["token"] += 1
            assert request.headers["Authorization"].startswith("Basic ")
            return httpx.Response(
                200, json={"access_token": "notion-token-9", "workspace_name": "Acme"}
            )
        if path == "/v1/search":
            assert request.headers["Authorization"] == "Bearer notion-token-9"
            return httpx.Response(200, json={"results": [_PAGE, _PAGE_2], "has_more": False})
        if path == "/v1/blocks/page-1/children":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "type": "heading_1",
                            "heading_1": {"rich_text": [{"plain_text": "Meals"}]},
                        },
                        {
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {"plain_text": "Meal reimbursements are capped at 40 euros."}
                                ]
                            },
                        },
                        {"type": "divider", "divider": {}},
                    ],
                    "has_more": False,
                },
            )
        if path == "/v1/blocks/page-2/children":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": [{"plain_text": "Demo day happens every Friday."}]
                            },
                        },
                        {
                            "type": "to_do",
                            "to_do": {
                                "rich_text": [{"plain_text": "Update the roadmap"}],
                                "checked": True,
                            },
                        },
                    ],
                    "has_more": False,
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(settings, "notion_client_id", "ekc-notion-client")
    monkeypatch.setattr(settings, "notion_client_secret", SecretStr("notion-secret"))
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    notion._transport = httpx.MockTransport(handler)
    yield calls
    notion._transport = None


async def _admin(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> dict[str, str]:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    return await auth_headers("admin@example.com")


async def test_full_connect_and_sync_flow(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    fake_notion: dict[str, int],
) -> None:
    admin = await _admin(client, make_user, auth_headers)

    created = await client.post(
        CONNECTORS,
        headers=admin,
        json={"name": "acme-notion", "type": "notion", "config": {"max_pages": 50}},
    )
    assert created.status_code == 201, created.text
    connector = created.json()
    assert connector["config"]["connected"] is False

    # Syncing before connecting is a clear error.
    early = await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)
    assert early.status_code == 422

    # 1. Authorize: consent URL on Notion with signed state.
    auth = await client.get(f"{CONNECTORS}/{connector['id']}/authorize", headers=admin)
    assert auth.status_code == 200
    location = auth.json()["authorize_url"]
    assert location.startswith("https://api.notion.com/v1/oauth/authorize?")
    state = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["state"][0]

    # 2. Notion redirects back (unauthenticated browser request).
    done = await client.get(
        f"{CONNECTORS}/notion/callback", params={"code": "consent-code", "state": state}
    )
    assert done.status_code == 307
    assert done.headers["location"] == "/integrations/"

    # Token stored encrypted; never exposed through the API.
    listed = (await client.get(CONNECTORS, headers=admin)).json()
    assert listed[0]["config"]["connected"] is True
    assert "access_token_enc" not in listed[0]["config"]

    # 3. Sync: both pages land as Markdown documents.
    report = (await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)).json()
    assert sorted(report["ingested"]) == ["Expense policy.md", "Team rituals.md"]
    assert report["failed"] == []

    # Content is immediately answerable.
    answer = await client.post(
        "/api/v1/query",
        headers=admin,
        json={"query": "What is the cap on meal reimbursements?"},
    )
    assert answer.json()["answered"] is True
    assert "40" in answer.json()["answer"]

    # Re-sync: idempotent.
    again = (await client.post(f"{CONNECTORS}/{connector['id']}/sync", headers=admin)).json()
    assert again["ingested"] == [] and again["skipped_existing"] == 2


async def test_forged_state_rejected(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    fake_notion: dict[str, int],
) -> None:
    await _admin(client, make_user, auth_headers)
    forged = await client.get(
        f"{CONNECTORS}/notion/callback", params={"code": "x", "state": "not-a-state"}
    )
    assert forged.status_code == 401


async def test_gdrive_state_cannot_complete_notion_flow(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    fake_notion: dict[str, int],
) -> None:
    """A state minted for one provider must not finish another provider's flow."""
    import uuid

    from app.services.connectors import gdrive

    await _admin(client, make_user, auth_headers)
    crossed = await client.get(
        f"{CONNECTORS}/notion/callback",
        params={"code": "x", "state": gdrive.make_state(uuid.uuid4())},
    )
    assert crossed.status_code == 401
