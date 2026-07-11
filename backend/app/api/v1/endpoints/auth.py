"""Authentication endpoints: register, login, token refresh, and profile."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import AuthenticationError
from app.core.ratelimit import limit_auth
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.schemas.auth import LoginRequest, TokenPair, TokenRefreshRequest
from app.schemas.user import UserCreate, UserRead
from app.services.users import UserService

router = APIRouter(tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_auth)],
    summary="Register a new user",
)
async def register(payload: UserCreate, db: DbSession) -> UserRead:
    user = await UserService(db).create(payload)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    dependencies=[Depends(limit_auth)],
    summary="Exchange credentials for tokens",
)
async def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    user = await UserService(db).authenticate(payload.email, payload.password)
    if user is None:
        raise AuthenticationError("Incorrect email or password.")
    subject = str(user.id)
    return TokenPair(
        access_token=create_access_token(subject),
        refresh_token=create_refresh_token(subject),
    )


@router.post("/refresh", response_model=TokenPair, summary="Rotate tokens using a refresh token")
async def refresh(payload: TokenRefreshRequest, db: DbSession) -> TokenPair:
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    subject = str(claims.get("sub"))

    # Ensure the subject still resolves to an active user before re-issuing.
    try:
        user = await UserService(db).get_by_id(uuid.UUID(subject))
    except ValueError as exc:
        raise AuthenticationError("Malformed token subject.") from exc
    if user is None or not user.is_active:
        raise AuthenticationError("User no longer active.")

    return TokenPair(
        access_token=create_access_token(subject),
        refresh_token=create_refresh_token(subject),
    )


@router.get("/me", response_model=UserRead, summary="Current authenticated user")
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
