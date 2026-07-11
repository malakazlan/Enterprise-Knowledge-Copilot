"""OIDC single sign-on (Authorization Code flow).

Works with any OpenID Connect provider — Microsoft Entra, Google Workspace,
Okta, Keycloak — configured by four settings: issuer, client id/secret, and
our redirect URL. No extra dependencies: discovery and token exchange use
httpx; ID-token signatures are verified against the provider's JWKS with
PyJWT + cryptography.

State is a short-lived signed JWT (carrying the nonce), so no server-side
session storage is needed. Users are provisioned on first login by verified
email; they get the standard first-user-is-admin bootstrap, USER otherwise.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import UserService

_STATE_TTL_SECONDS = 600
_DISCOVERY_TTL_SECONDS = 3600

# Test seam: routes provider calls (discovery, token, JWKS) into a mock.
_transport: httpx.AsyncBaseTransport | None = None

_discovery_cache: tuple[float, dict[str, Any]] | None = None


def oidc_enabled() -> bool:
    return bool(
        settings.oidc_issuer
        and settings.oidc_client_id
        and settings.oidc_client_secret
        and settings.oidc_redirect_url
    )


def _require_enabled() -> None:
    if not oidc_enabled():
        raise ServiceUnavailableError(
            "OIDC is not configured. Set OIDC_ISSUER, OIDC_CLIENT_ID, "
            "OIDC_CLIENT_SECRET and OIDC_REDIRECT_URL."
        )


async def _discovery() -> dict[str, Any]:
    global _discovery_cache
    now = time.monotonic()
    if _discovery_cache is not None and now - _discovery_cache[0] < _DISCOVERY_TTL_SECONDS:
        return _discovery_cache[1]
    issuer = str(settings.oidc_issuer).rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=15.0, transport=_transport) as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise ServiceUnavailableError(f"OIDC discovery failed ({response.status_code}).")
        document: dict[str, Any] = response.json()
    _discovery_cache = (now, document)
    return document


def reset_caches() -> None:
    """Test hook."""
    global _discovery_cache
    _discovery_cache = None


def _make_state(nonce: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": "oidc-state",
        "nonce": nonce,
        "iat": now,
        "exp": now + timedelta(seconds=_STATE_TTL_SECONDS),
    }
    return jwt.encode(
        payload, settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def _read_state(state: str) -> str:
    try:
        claims = jwt.decode(
            state,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired SSO state.") from exc
    if claims.get("type") != "oidc-state" or not claims.get("nonce"):
        raise AuthenticationError("Invalid SSO state.")
    return str(claims["nonce"])


async def build_authorization_url() -> str:
    """The provider URL to send the browser to."""
    _require_enabled()
    document = await _discovery()
    nonce = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_url,
        "scope": settings.oidc_scopes,
        "state": _make_state(nonce),
        "nonce": nonce,
    }
    return f"{document['authorization_endpoint']}?{urlencode(params)}"


async def _exchange_code(code: str, document: dict[str, Any]) -> dict[str, Any]:
    assert settings.oidc_client_secret is not None  # guarded by _require_enabled
    async with httpx.AsyncClient(timeout=20.0, transport=_transport) as client:
        response = await client.post(
            document["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_url,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret.get_secret_value(),
            },
        )
    if response.status_code != 200:
        raise AuthenticationError(f"OIDC code exchange failed ({response.status_code}).")
    body: dict[str, Any] = response.json()
    if "id_token" not in body:
        raise AuthenticationError("OIDC provider returned no id_token.")
    return body


async def _verify_id_token(id_token: str, nonce: str, document: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0, transport=_transport) as client:
        response = await client.get(document["jwks_uri"])
        if response.status_code != 200:
            raise ServiceUnavailableError("Could not fetch OIDC signing keys.")
        keys = response.json().get("keys", [])

    header = jwt.get_unverified_header(id_token)
    jwk = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    if jwk is None:
        raise AuthenticationError("OIDC signing key not found.")

    try:
        claims: dict[str, Any] = jwt.decode(
            id_token,
            key=jwt.PyJWK(jwk).key,
            algorithms=[header.get("alg", "RS256")],
            audience=settings.oidc_client_id,
            issuer=document["issuer"],
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"OIDC token validation failed: {exc}") from exc

    if claims.get("nonce") != nonce:
        raise AuthenticationError("OIDC nonce mismatch.")
    return claims


async def handle_callback(db: AsyncSession, code: str, state: str) -> User:
    """Complete the flow: validate everything, return the local user."""
    _require_enabled()
    nonce = _read_state(state)
    document = await _discovery()
    tokens = await _exchange_code(code, document)
    claims = await _verify_id_token(tokens["id_token"], nonce, document)

    email = (claims.get("email") or "").lower().strip()
    if not email:
        raise AuthenticationError("OIDC token carries no email claim.")
    if claims.get("email_verified") is False:
        raise AuthenticationError("OIDC email is not verified by the provider.")

    service = UserService(db)
    user = await service.get_by_email(email)
    if user is None:
        # SSO users authenticate at the provider; the local password is an
        # unguessable random value that is never used or shown.
        user = await service.create(
            UserCreate(
                email=email,
                password=secrets.token_urlsafe(32),
                full_name=str(claims.get("name") or claims.get("preferred_username") or email),
            )
        )
    if not user.is_active:
        raise AuthenticationError("Account is deactivated.")
    return user
