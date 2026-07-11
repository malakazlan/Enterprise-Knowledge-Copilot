"""Document and ingestion-job response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.document import IngestionStatus, JobStage, JobStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    checksum: str
    status: IngestionStatus
    title: str | None
    page_count: int | None
    doc_metadata: dict[str, Any]
    error: str | None
    created_at: datetime
    updated_at: datetime


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    page_number: int | None
    token_count: int | None


class IngestionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: JobStatus
    stage: JobStage | None
    attempts: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class DocumentWithJob(BaseModel):
    document: DocumentRead
    job: IngestionJobRead
