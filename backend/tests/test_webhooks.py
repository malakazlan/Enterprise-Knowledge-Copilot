"""Tests for outbound webhooks: registration, signed delivery, events."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.services import webhooks as webhook_service

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

WEBHOOKS = "/api/v1/admin/webhooks"
SECRET = "shhh-super-secret-signing-key"


@pytest.fixture
async def captured() -> AsyncIterator[list[httpx.Request]]:
    """Capture webhook deliveries instead of hitting the network."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    webhook_service._transport = httpx.MockTransport(handler)
    yield requests
    webhook_service._transport = None


async def _admin(client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders) -> dict[str, str]:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    return await auth_headers("admin@example.com")


async def test_webhook_crud_and_validation(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    admin = await _admin(client, make_user, auth_headers)

    bad = await client.post(
        WEBHOOKS, headers=admin, json={"url": "https://x.example/hook", "events": ["nope"]}
    )
    assert bad.status_code == 422

    created = await client.post(
        WEBHOOKS,
        headers=admin,
        json={"url": "https://x.example/hook", "events": ["query.refused"], "secret": SECRET},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["has_secret"] is True and "secret" not in body

    listed = await client.get(WEBHOOKS, headers=admin)
    assert len(listed.json()) == 1

    deleted = await client.delete(f"{WEBHOOKS}/{body['id']}", headers=admin)
    assert deleted.status_code == 204
    assert (await client.get(WEBHOOKS, headers=admin)).json() == []


async def test_refusal_triggers_signed_delivery(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    captured: list[httpx.Request],
) -> None:
    admin = await _admin(client, make_user, auth_headers)
    await client.post(
        WEBHOOKS,
        headers=admin,
        json={
            "url": "https://workflow.example/ekc",
            "events": ["query.refused", "query.needs_review"],
            "secret": SECRET,
        },
    )

    # Empty corpus -> every query refuses -> webhook fires.
    resp = await client.post(
        "/api/v1/query", headers=admin, json={"query": "quantum banana smoothie recipe"}
    )
    assert resp.json()["answered"] is False

    assert len(captured) == 1
    delivery = captured[0]
    assert delivery.headers["X-EKC-Event"] == "query.refused"

    # Signature verifies against the raw body.
    expected = hmac.new(SECRET.encode(), delivery.content, hashlib.sha256).hexdigest()
    assert delivery.headers["X-EKC-Signature"] == f"sha256={expected}"

    payload = json.loads(delivery.content)
    assert payload["event"] == "query.refused"
    assert payload["data"]["query"] == "quantum banana smoothie recipe"
    assert payload["data"]["refusal_reason"]


async def test_unsubscribed_events_do_not_fire(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    captured: list[httpx.Request],
) -> None:
    admin = await _admin(client, make_user, auth_headers)
    await client.post(
        WEBHOOKS,
        headers=admin,
        json={"url": "https://x.example/hook", "events": ["review.resolved"]},
    )
    await client.post("/api/v1/query", headers=admin, json={"query": "anything at all"})
    assert captured == []


async def test_document_ingested_event(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    captured: list[httpx.Request],
) -> None:
    admin = await _admin(client, make_user, auth_headers)
    await client.post(
        WEBHOOKS,
        headers=admin,
        json={"url": "https://x.example/hook", "events": ["document.ingested"]},
    )
    upload = await client.post(
        "/api/v1/documents",
        headers=admin,
        files={"file": ("h.md", b"# Hi\n\nHello world.", "text/markdown")},
    )
    assert upload.status_code == 201
    assert len(captured) == 1
    data = json.loads(captured[0].content)["data"]
    assert data["filename"] == "h.md" and data["status"] == "completed"


async def test_webhooks_require_admin(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    member = await auth_headers("member@example.com")
    resp = await client.get(WEBHOOKS, headers=member)
    assert resp.status_code == 403
