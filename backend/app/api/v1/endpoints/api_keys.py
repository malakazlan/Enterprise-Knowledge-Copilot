"""API key management — human administrators only.

Keys authenticate the data-plane endpoints via the ``X-API-Key`` header; key
management itself deliberately requires a human admin session (keys cannot
mint or revoke keys).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.exceptions import NotFoundError
from app.models.user import UserRole
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.services.api_keys import ApiKeyService

router = APIRouter(
    tags=["api-keys"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a service API key (secret shown once)",
)
async def create_api_key(
    payload: ApiKeyCreate, db: DbSession, current_user: CurrentUser
) -> ApiKeyCreated:
    api_key, raw_key = await ApiKeyService(db).create(
        name=payload.name,
        role=payload.role,
        expires_in_days=payload.expires_in_days,
        created_by=current_user.id,
    )
    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        role=api_key.role,
        key=raw_key,
        key_prefix=api_key.key_prefix,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get("", response_model=list[ApiKeyRead], summary="List API keys (metadata only)")
async def list_api_keys(db: DbSession) -> list[ApiKeyRead]:
    keys = await ApiKeyService(db).list_keys()
    return [ApiKeyRead.model_validate(key) for key in keys]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key (idempotent)",
)
async def revoke_api_key(key_id: uuid.UUID, db: DbSession) -> None:
    if await ApiKeyService(db).revoke(key_id) is None:
        raise NotFoundError("API key not found.")
