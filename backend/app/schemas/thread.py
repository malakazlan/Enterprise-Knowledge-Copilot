"""Chat thread schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ThreadMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    answer: str | None
    answered: bool
    refusal_reason: str | None
    confidence: float
    needs_review: bool
    citations: list[dict[str, Any]]
    created_at: datetime


class ThreadDetail(ThreadRead):
    messages: list[ThreadMessage]
