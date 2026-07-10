"""Document persistence: upload intake, listing, and deletion."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from pathlib import Path

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, IngestionJob, JobStatus
from app.services.storage import ObjectStorage

logger = structlog.get_logger("app.documents")


class DocumentService:
    def __init__(self, db: AsyncSession, storage: ObjectStorage) -> None:
        self.db = db
        self.storage = storage

    async def create_from_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
        uploaded_by: uuid.UUID | None = None,
    ) -> tuple[Document, IngestionJob]:
        document_id = uuid.uuid4()
        safe_name = Path(filename).name or "upload"
        storage_key = f"{document_id}/{safe_name}"
        await self.storage.save(storage_key, data)

        document = Document(
            id=document_id,
            filename=safe_name,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(data),
            checksum=hashlib.sha256(data).hexdigest(),
            storage_uri=storage_key,
            uploaded_by=uploaded_by,
        )
        job = IngestionJob(document_id=document_id, status=JobStatus.QUEUED)
        self.db.add(document)
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(document)
        await self.db.refresh(job)
        return document, job

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self.db.get(Document, document_id)

    async def list_documents(self, *, limit: int = 50, offset: int = 0) -> Sequence[Document]:
        result = await self.db.execute(
            select(Document).order_by(desc(Document.created_at)).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def list_jobs(self, document_id: uuid.UUID) -> Sequence[IngestionJob]:
        result = await self.db.execute(
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(desc(IngestionJob.created_at))
        )
        return result.scalars().all()

    async def delete(self, document: Document) -> None:
        try:
            await self.storage.delete(document.storage_uri)
        except Exception as exc:  # storage cleanup is best-effort
            logger.warning("storage_delete_failed", uri=document.storage_uri, error=str(exc))
        await self.db.delete(document)
        await self.db.commit()
