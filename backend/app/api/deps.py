"""Shared FastAPI dependencies: DB session, current user, and RBAC guards."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.users import UserService

_bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[AsyncSession, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


async def get_current_user(db: DbSession, credentials: BearerCredentials) -> User:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")

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


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Dependency factory enforcing that the caller holds one of ``roles``."""

    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError()
        return user

    return _guard
