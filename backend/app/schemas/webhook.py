"""Webhook management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.webhook import WEBHOOK_EVENTS


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(min_length=1, max_length=10)
    # Optional HMAC-SHA256 signing secret (recommended).
    secret: str | None = Field(default=None, min_length=16, max_length=200)

    @field_validator("events")
    @classmethod
    def known_events(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - set(WEBHOOK_EVENTS))
        if unknown:
            raise ValueError(f"Unknown events: {unknown}. Valid: {sorted(WEBHOOK_EVENTS)}")
        return sorted(set(v))


class WebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    has_secret: bool = False
    created_at: datetime
