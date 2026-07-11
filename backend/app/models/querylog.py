"""Query audit log — every question, answer, and trust decision is recorded."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class QueryLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "query_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
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
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    # [{marker, chunk_id, document_id, filename, page_number}, ...]
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    took_ms: Mapped[float] = mapped_column(Float, nullable=False)
