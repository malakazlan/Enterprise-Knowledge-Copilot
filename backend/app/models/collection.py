"""Collections — access boundaries for documents.

A document in no collection is shared: every authenticated principal can
retrieve from it. A document in a collection is retrievable only by that
collection's members (and admins). Enforcement happens at retrieval time in
both search channels, not by post-filtering answers.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Collection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collections"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CollectionMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collection_members"
    __table_args__ = (
        UniqueConstraint("collection_id", "user_id", name="uq_collection_members_pair"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
