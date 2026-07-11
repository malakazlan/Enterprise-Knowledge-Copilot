"""API key management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: UserRole = UserRole.USER
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyCreated(BaseModel):
    """Returned once at creation — the only time the full key is visible."""

    id: uuid.UUID
    name: str
    role: UserRole
    key: str
    key_prefix: str
    expires_at: datetime | None
    created_at: datetime


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: UserRole
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
