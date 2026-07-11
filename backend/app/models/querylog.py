"""Query audit log — every question, answer, and trust decision is recorded."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import portable_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ReviewStatus(str, enum.Enum):
    """Human-review lifecycle of a flagged answer."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class QueryLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "query_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Set when the query came from a service API key instead of a human session.
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="SET NULL"), index=True, nullable=True
    )
    profile: Mapped[str] = mapped_column(String(64), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    refusal_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    grounded_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    # Flagged for the human review queue (confidence in the review band).
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    # Review lifecycle; null for answers that never needed review.
    review_status: Mapped[ReviewStatus | None] = mapped_column(
        portable_enum(ReviewStatus, "review_status"), nullable=True, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    # [{marker, chunk_id, document_id, filename, page_number}, ...]
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    took_ms: Mapped[float] = mapped_column(Float, nullable=False)
