"""Tests for registration, login, token refresh, and the /me endpoint."""

from __future__ import annotations

from httpx import AsyncClient

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"


async def test_register_login_me_flow(client: AsyncClient) -> None:
    reg = await client.post(
        REGISTER,
        json={"email": "ann@example.com", "password": "supersecret", "full_name": "Ann"},
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body["email"] == "ann@example.com"
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert "hashed_password" not in body

    login = await client.post(LOGIN, json={"email": "ann@example.com", "password": "supersecret"})
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"

    me = await client.get(ME, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ann@example.com"


async def test_email_is_normalized_to_lowercase(client: AsyncClient) -> None:
    reg = await client.post(
        REGISTER, json={"email": "MixedCase@Example.com", "password": "supersecret"}
    )
    assert reg.status_code == 201
    assert reg.json()["email"] == "mixedcase@example.com"


async def test_login_with_wrong_password_is_rejected(client: AsyncClient) -> None:
    await client.post(REGISTER, json={"email": "bob@example.com", "password": "supersecret"})
    resp = await client.post(LOGIN, json={"email": "bob@example.com", "password": "wrongpass"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_failed"


async def test_duplicate_registration_conflicts(client: AsyncClient) -> None:
    payload = {"email": "carol@example.com", "password": "supersecret"}
    assert (await client.post(REGISTER, json=payload)).status_code == 201
    dup = await client.post(REGISTER, json=payload)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"


async def test_short_password_is_rejected(client: AsyncClient) -> None:
    resp = await client.post(REGISTER, json={"email": "dan@example.com", "password": "short"})
    assert resp.status_code == 422


async def test_me_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(ME)).status_code == 401


async def test_me_rejects_malformed_token(client: AsyncClient) -> None:
    resp = await client.get(ME, headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_refresh_rotates_tokens(client: AsyncClient) -> None:
    await client.post(REGISTER, json={"email": "erin@example.com", "password": "supersecret"})
    login = await client.post(LOGIN, json={"email": "erin@example.com", "password": "supersecret"})
    refresh_token = login.json()["refresh_token"]

    resp = await client.post(REFRESH, json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_access_token_cannot_be_used_as_refresh(client: AsyncClient) -> None:
    await client.post(REGISTER, json={"email": "fay@example.com", "password": "supersecret"})
    login = await client.post(LOGIN, json={"email": "fay@example.com", "password": "supersecret"})
    access_token = login.json()["access_token"]

    resp = await client.post(REFRESH, json={"refresh_token": access_token})
    assert resp.status_code == 401
