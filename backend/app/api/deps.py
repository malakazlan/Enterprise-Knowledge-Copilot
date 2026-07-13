"""Shared FastAPI dependencies: DB session, identity resolution, RBAC guards.

Two identity layers:

- :data:`CurrentUser` — a human session (JWT bearer). Used for account and
  management endpoints (auth, user admin, API-key admin).
- :data:`CurrentPrincipal` — a human **or** a service API key (``X-API-Key``
  header), unified behind :class:`Principal`. Used by the data-plane endpoints
  (documents, search, query, profiles) so agencies can integrate
  machine-to-machine with the same RBAC rules.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.apikey import ApiKey
from app.models.user import User, UserRole
from app.services.api_keys import ApiKeyService
from app.services.ingestion.factory import get_storage as _resolve_storage
from app.services.storage import ObjectStorage
from app.services.users import UserService

_bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")
_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, description="Service API key")

DbSession = Annotated[AsyncSession, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]
ApiKeyValue = Annotated[str | None, Depends(_api_key_scheme)]


def get_storage() -> ObjectStorage:
    return _resolve_storage()


Storage = Annotated[ObjectStorage, Depends(get_storage)]


async def _resolve_user(db: AsyncSession, credentials: HTTPAuthorizationCredentials) -> User:
    payload = decode_token(credentials.credentials, expected_type="access")
    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("Malformed token subject.") from exc

    user = await UserService(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive.")
    return user


async def get_current_user(db: DbSession, credentials: BearerCredentials) -> User:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    return await _resolve_user(db, credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Human-session RBAC guard (management endpoints)."""

    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError()
        return user

    return _guard


@dataclass(slots=True)
class Principal:
    """The authenticated caller: a human user or a service API key."""

    role: UserRole
    user: User | None = None
    api_key: ApiKey | None = None

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user is not None else None

    @property
    def api_key_id(self) -> uuid.UUID | None:
        return self.api_key.id if self.api_key is not None else None


async def get_current_principal(
    db: DbSession, credentials: BearerCredentials, api_key_value: ApiKeyValue
) -> Principal:
    if api_key_value:
        api_key = await ApiKeyService(db).authenticate(api_key_value)
        if api_key is None:
            raise AuthenticationError("Invalid, revoked, or expired API key.")
        return Principal(role=api_key.role, api_key=api_key)

    if credentials is None:
        raise AuthenticationError(
            "Missing credentials: provide a bearer token or an X-API-Key header."
        )
    user = await _resolve_user(db, credentials)
    return Principal(role=user.role, user=user)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_principal_roles(*roles: UserRole) -> Callable[[Principal], Awaitable[Principal]]:
    """RBAC guard for data-plane endpoints (users and API keys alike)."""

    async def _guard(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise PermissionDeniedError()
        return principal

    return _guard


async def limit_query_rate(request: Request, principal: CurrentPrincipal) -> None:
    """Per-principal rate limit for query/search endpoints."""
    from app.core.ratelimit import check_query_rate, query_rate_key

    if not settings.rate_limit_enabled:
        return
    await check_query_rate(query_rate_key(request, principal))
