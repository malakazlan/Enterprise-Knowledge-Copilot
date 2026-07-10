"""Tests for admin-only user management and RBAC enforcement."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.models.user import User, UserRole

USERS = "/api/v1/users"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]


async def test_admin_can_list_users(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    await make_user("member@example.com", role=UserRole.USER)
    headers = await auth_headers("admin@example.com")

    resp = await client.get(USERS, headers=headers)
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert {"admin@example.com", "member@example.com"} <= emails


async def test_non_admin_is_forbidden(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    headers = await auth_headers("member@example.com")

    resp = await client.get(USERS, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "permission_denied"


async def test_reviewer_is_forbidden_from_admin_route(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("rev@example.com", role=UserRole.REVIEWER)
    headers = await auth_headers("rev@example.com")

    resp = await client.get(USERS, headers=headers)
    assert resp.status_code == 403


async def test_unauthenticated_is_rejected(client: AsyncClient) -> None:
    assert (await client.get(USERS)).status_code == 401
