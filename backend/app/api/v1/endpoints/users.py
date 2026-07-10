"""Admin-only user management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_roles
from app.models.user import UserRole
from app.schemas.user import UserRead
from app.services.users import UserService

router = APIRouter(
    tags=["users"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


@router.get("", response_model=list[UserRead], summary="List users (admin only)")
async def list_users(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[UserRead]:
    users = await UserService(db).list_users(limit=limit, offset=offset)
    return [UserRead.model_validate(user) for user in users]
