"""Review queue and admin statistics schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.querylog import ReviewStatus


class ReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    answer: str | None
    profile: str
    confidence: float
    grounded_ratio: float
    model: str
    citations: list[dict[str, Any]]
    review_status: ReviewStatus | None
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ReviewResolve(BaseModel):
    action: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)


class AdminStats(BaseModel):
    documents_total: int
    documents_failed: int
    chunks_total: int
    queries_total: int
    queries_answered: int
    queries_refused: int
    refusal_breakdown: dict[str, int]
    avg_confidence_answered: float | None
    reviews_pending: int
    api_keys_active: int
    users_total: int
