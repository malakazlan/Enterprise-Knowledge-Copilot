"""Document, chunk, and ingestion-job models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import portable_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IngestionStatus(str, enum.Enum):
    """Overall ingestion state of a document."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    """Lifecycle state of a single ingestion job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobStage(str, enum.Enum):
    """The pipeline stage a job is currently executing."""

    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # SHA-256 hex digest of the raw bytes, for dedupe/audit.
    checksum: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[IngestionStatus] = mapped_column(
        portable_enum(IngestionStatus, "ingestion_status"),
        default=IngestionStatus.PENDING,
        nullable=False,
    )
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Knowledge lifecycle: re-verify this document by this date; past-due
    # documents surface as "stale" in listings and admin stats.
    verify_by: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_doc_index"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Identifier of this chunk's vector in the external vector store.
    vector_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        portable_enum(JobStatus, "job_status"), default=JobStatus.QUEUED, nullable=False
    )
    stage: Mapped[JobStage | None] = mapped_column(
        portable_enum(JobStage, "job_stage"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
