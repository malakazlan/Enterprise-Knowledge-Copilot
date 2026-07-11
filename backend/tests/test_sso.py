"""Tests for OIDC SSO — a fake identity provider with real RSA signatures."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import AsyncIterator

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient

from app.core.config import settings
from app.services import sso

ISSUER = "https://idp.example"
CLIENT_ID = "ekc-client"
LOGIN = "/api/v1/auth/oidc/login"
CALLBACK = "/api/v1/auth/oidc/callback"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks() -> dict[str, object]:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def _id_token(nonce: str, email: str = "sso.user@example.com", **extra: object) -> str:
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "idp-subject-1",
        "email": email,
        "email_verified": True,
        "name": "Sso User",
        "nonce": nonce,
        "exp": 4102444800,  # far future
        "iat": 1,
        **extra,
    }
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "test-key"})


@pytest.fixture
async def fake_idp() -> AsyncIterator[dict[str, str]]:
    """Configure OIDC and route provider traffic to an in-test IdP."""
    issued: dict[str, str] = {}  # nonce -> configured per test via login redirect

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                },
            )
        if path.endswith("/jwks"):
            return httpx.Response(200, json=_jwks())
        if path.endswith("/token"):
            return httpx.Response(
                200,
                json={"access_token": "at", "id_token": issued["id_token"]},
            )
        return httpx.Response(404)

    sso.reset_caches()
    sso._transport = httpx.MockTransport(handler)
    settings.oidc_issuer = ISSUER
    settings.oidc_client_id = CLIENT_ID
    from pydantic import SecretStr

    settings.oidc_client_secret = SecretStr("client-secret")
    settings.oidc_redirect_url = "http://testserver/api/v1/auth/oidc/callback"
    yield issued
    settings.oidc_issuer = None
    settings.oidc_client_id = None
    settings.oidc_client_secret = None
    settings.oidc_redirect_url = None
    sso._transport = None
    sso.reset_caches()


def _nonce_from_redirect(location: str) -> tuple[str, str]:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    return query["nonce"][0], query["state"][0]


async def test_status_reflects_configuration(client: AsyncClient, fake_idp: dict[str, str]) -> None:
    body = (await client.get("/api/v1/auth/oidc/status")).json()
    assert body["enabled"] is True


async def test_full_login_flow_provisions_user(
    client: AsyncClient, fake_idp: dict[str, str]
) -> None:
    redirect = await client.get(LOGIN)
    assert redirect.status_code == 307
    location = redirect.headers["location"]
    assert location.startswith(f"{ISSUER}/authorize?")
    nonce, state = _nonce_from_redirect(location)

    fake_idp["id_token"] = _id_token(nonce)
    done = await client.get(CALLBACK, params={"code": "abc", "state": state})
    assert done.status_code == 307
    fragment = urllib.parse.urlparse(done.headers["location"]).fragment
    tokens = urllib.parse.parse_qs(fragment)
    access = tokens["sso_access"][0]

    # The issued token is a working session; first SSO user is the admin.
    who = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert who.status_code == 200
    body = who.json()
    assert body["email"] == "sso.user@example.com"
    assert body["role"] == "admin"

    # Second login: same account, no duplicate.
    redirect = await client.get(LOGIN)
    nonce, state = _nonce_from_redirect(redirect.headers["location"])
    fake_idp["id_token"] = _id_token(nonce)
    again = await client.get(CALLBACK, params={"code": "abc", "state": state})
    assert again.status_code == 307


async def test_wrong_nonce_and_bad_state_rejected(
    client: AsyncClient, fake_idp: dict[str, str]
) -> None:
    redirect = await client.get(LOGIN)
    _nonce, state = _nonce_from_redirect(redirect.headers["location"])

    fake_idp["id_token"] = _id_token("a-different-nonce")
    replayed = await client.get(CALLBACK, params={"code": "abc", "state": state})
    assert replayed.status_code == 401

    forged = await client.get(CALLBACK, params={"code": "abc", "state": "not-a-state"})
    assert forged.status_code == 401


async def test_unverified_email_rejected(client: AsyncClient, fake_idp: dict[str, str]) -> None:
    redirect = await client.get(LOGIN)
    nonce, state = _nonce_from_redirect(redirect.headers["location"])
    fake_idp["id_token"] = _id_token(nonce, email_verified=False)
    rejected = await client.get(CALLBACK, params={"code": "abc", "state": state})
    assert rejected.status_code == 401


async def test_login_when_unconfigured_is_503(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/oidc/status")).json()["enabled"] is False
    assert (await client.get(LOGIN)).status_code == 503
