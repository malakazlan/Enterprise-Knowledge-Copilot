"""Tests for agent memory: scoped writes, semantic recall, TTL, isolation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import AgentMemory
from app.models.user import User, UserRole

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

MEMORY = "/api/v1/memory"


async def _user(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders, email: str
) -> dict[str, str]:
    await make_user(email, role=UserRole.USER)
    return await auth_headers(email)


async def test_remember_recall_roundtrip(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _user(client, make_user, auth_headers, "agent-a@example.com")

    for content in (
        "Acme Corp prefers invoices in euros with net-60 terms.",
        "The staging deploy window is Tuesday mornings.",
    ):
        created = await client.post(MEMORY, headers=headers, json={"content": content})
        assert created.status_code == 201, created.text
        assert created.json()["scope"] == "user:agent-a@example.com"

    matches = (
        await client.post(
            f"{MEMORY}/recall", headers=headers, json={"query": "Acme invoice currency terms"}
        )
    ).json()
    assert matches, "expected at least one recalled memory"
    assert "net-60" in matches[0]["content"]
    assert matches[0]["score"] > 0

    listed = (await client.get(MEMORY, headers=headers)).json()
    assert len(listed) == 2


async def test_scopes_are_private(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    agent_a = await _user(client, make_user, auth_headers, "agent-a@example.com")
    agent_b = await _user(client, make_user, auth_headers, "agent-b@example.com")

    await client.post(
        MEMORY, headers=agent_a, json={"content": "Secret plan Zebra launches in March."}
    )

    # B cannot see or recall A's memory.
    assert (await client.get(MEMORY, headers=agent_b)).json() == []
    recalled = (
        await client.post(f"{MEMORY}/recall", headers=agent_b, json={"query": "plan Zebra launch"})
    ).json()
    assert recalled == []

    # Non-admins cannot address someone else's scope.
    denied = await client.post(
        MEMORY,
        headers=agent_b,
        json={"content": "spoofed", "scope": "user:agent-a@example.com"},
    )
    assert denied.status_code == 403


async def test_expired_memories_do_not_recall(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    headers = await _user(client, make_user, auth_headers, "agent-a@example.com")
    created = (
        await client.post(
            MEMORY,
            headers=headers,
            json={"content": "The promo code SPRING24 is active.", "ttl_days": 30},
        )
    ).json()
    assert created["expires_at"] is not None

    # Time passes: force it expired.
    import uuid as _uuid

    await db_session.execute(
        update(AgentMemory)
        .where(AgentMemory.id == _uuid.UUID(created["id"]))
        .values(expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    )
    await db_session.commit()

    assert (await client.get(MEMORY, headers=headers)).json() == []
    recalled = (
        await client.post(f"{MEMORY}/recall", headers=headers, json={"query": "promo code"})
    ).json()
    assert recalled == []


async def test_forget_removes_memory(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    headers = await _user(client, make_user, auth_headers, "agent-a@example.com")
    created = (
        await client.post(MEMORY, headers=headers, json={"content": "Temporary note to forget."})
    ).json()

    assert (await client.delete(f"{MEMORY}/{created['id']}", headers=headers)).status_code == 204
    assert (await client.get(MEMORY, headers=headers)).json() == []
    # Forgetting someone else's (or twice) is a 404.
    assert (await client.delete(f"{MEMORY}/{created['id']}", headers=headers)).status_code == 404
