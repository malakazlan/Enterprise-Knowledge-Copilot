"""User account model and role enumeration."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import portable_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    """Role-based access control tiers."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    USER = "user"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stored as a portable VARCHAR + CHECK constraint (not a native PG enum) so
    # migrations stay database-agnostic and adding roles needs no type surgery.
    role: Mapped[UserRole] = mapped_column(
        portable_enum(UserRole, "user_role"),
        default=UserRole.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id!s} email={self.email!r} role={self.role.value}>"
