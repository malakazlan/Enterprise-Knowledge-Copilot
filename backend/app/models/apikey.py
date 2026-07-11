"""Service API keys for machine-to-machine access.

Only a SHA-256 hash of the key is stored — the full secret is shown once at
creation and is unrecoverable afterwards. The indexed prefix identifies keys
in logs and lookups without exposing the secret.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import portable_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.user import UserRole


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # The key acts with this role through the same RBAC as human users.
    role: Mapped[UserRole] = mapped_column(
        portable_enum(UserRole, "user_role"), default=UserRole.USER, nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is None:
            return True
        expires = self.expires_at
        if expires.tzinfo is None:  # SQLite returns naive datetimes; stored as UTC
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)
