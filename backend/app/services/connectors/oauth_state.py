"""Signed state tokens for connector OAuth flows.

The state parameter is a short-lived JWT naming the connector being wired up;
the provider callback is unauthenticated, so the state IS the auth. Each
provider uses its own `kind` so a Google state cannot complete a Notion flow.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError

_STATE_TTL_SECONDS = 600


def make_state(kind: str, connector_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "type": kind,
            "connector_id": str(connector_id),
            "iat": now,
            "exp": now + timedelta(seconds=_STATE_TTL_SECONDS),
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def read_state(kind: str, state: str) -> uuid.UUID:
    try:
        claims = jwt.decode(
            state, settings.secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired connect state.") from exc
    if claims.get("type") != kind:
        raise AuthenticationError("Invalid connect state.")
    return uuid.UUID(str(claims["connector_id"]))
