"""Outbound webhooks — push trust events into enterprise workflows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Events a webhook can subscribe to.
WEBHOOK_EVENTS = (
    "query.refused",
    "query.needs_review",
    "review.resolved",
    "document.ingested",
    "document.failed",
)


class Webhook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhooks"

    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Optional HMAC-SHA256 signing secret; deliveries are signed when set.
    secret: Mapped[str | None] = mapped_column(String(200), nullable=True)
    events: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
