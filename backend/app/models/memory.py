"""Agent memory — fast, scoped, semantic recall; not documents.

Each memory belongs to a scope (one agent / API key / user). Scopes are
private: an agent can only recall its own memories. Memories can expire
(TTL), and recall is dense-vector semantic search inside the scope.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

MEMORY_KINDS = ("fact", "episode", "preference")


class AgentMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_memories"

    scope: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="fact")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Who/what recorded it (workflow id, run id, ...).
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
