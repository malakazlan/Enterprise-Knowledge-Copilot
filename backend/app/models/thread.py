"""Chat threads — persistent conversations whose messages are query logs."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ChatThread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_threads"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
