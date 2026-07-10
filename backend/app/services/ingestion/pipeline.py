"""Ingestion pipeline: parse -> chunk -> embed -> index.

Drives one :class:`IngestionJob` to completion, updating the job and its
document as it advances through each stage. On failure both are marked failed
with the error recorded; a re-run clears prior chunks/vectors first, so the
pipeline is safe to retry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import (
    Document,
    DocumentChunk,
    IngestionJob,
    IngestionStatus,
    JobStage,
    JobStatus,
)
from app.services.ingestion.chunking import Chunker
from app.services.ingestion.factory import (
    get_chunker,
    get_embedder,
    get_parser,
    get_vector_store,
)
from app.services.ingestion.ports import DocumentParser, Embedder
from app.services.storage import ObjectStorage
from app.services.vectorstore import VectorRecord, VectorStore

logger = structlog.get_logger("app.ingestion")


class IngestionError(Exception):
    """Raised when a document cannot be ingested."""


class IngestionPipeline:
    def __init__(
        self,
        db: AsyncSession,
        storage: ObjectStorage,
        *,
        parser: DocumentParser | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        chunker: Chunker | None = None,
    ) -> None:
        self.db = db
        self.storage = storage
        self.parser = parser or get_parser()
        self.embedder = embedder or get_embedder()
        self.vector_store = vector_store or get_vector_store()
        self.chunker = chunker or get_chunker()

    async def run(self, job_id: uuid.UUID) -> IngestionJob:
        job = await self.db.get(IngestionJob, job_id)
        if job is None:
            raise IngestionError(f"Ingestion job {job_id} not found.")
        document = await self.db.get(Document, job.document_id)
        if document is None:
            raise IngestionError(f"Document {job.document_id} not found.")

        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        document.status = IngestionStatus.PROCESSING
        await self.db.commit()

        try:
            await self._execute(job, document)
        except Exception as exc:
            await self.db.rollback()
            await self._mark_failed(job.id, document.id, exc)
            raise
        return job

    async def _execute(self, job: IngestionJob, document: Document) -> None:
        job.stage = JobStage.PARSE
        await self.db.commit()
        file_path = await self.storage.materialize(document.storage_uri)
        parsed = await self.parser.parse(
            file_path=file_path,
            content_type=document.content_type,
            filename=document.filename,
        )

        if parsed.title and not document.title:
            document.title = parsed.title
        document.page_count = parsed.page_count
        document.doc_metadata = {**document.doc_metadata, **parsed.metadata}

        job.stage = JobStage.CHUNK
        await self.db.commit()
        chunk_data = self.chunker.chunk_document(parsed)
        if not chunk_data:
            raise IngestionError("Document produced no text to index.")

        # Clear any prior artifacts so re-ingestion is idempotent.
        await self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        await self.vector_store.delete_by_document(str(document.id))

        job.stage = JobStage.EMBED
        await self.db.commit()
        embeddings = await self.embedder.embed([chunk.content for chunk in chunk_data])

        job.stage = JobStage.INDEX
        records: list[VectorRecord] = []
        for data, embedding in zip(chunk_data, embeddings, strict=True):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=data.index,
                content=data.content,
                page_number=data.page_number,
                token_count=data.token_count,
                chunk_metadata=data.metadata,
            )
            chunk.vector_id = str(chunk.id)
            self.db.add(chunk)
            records.append(
                VectorRecord(
                    id=str(chunk.id),
                    values=embedding,
                    metadata={
                        "document_id": str(document.id),
                        "chunk_id": str(chunk.id),
                        "chunk_index": data.index,
                        "page_number": data.page_number,
                        "filename": document.filename,
                        "title": document.title,
                        "text": data.content,
                    },
                )
            )

        # Persist chunks before touching the external vector store so a vector
        # failure leaves recoverable state (retry clears and rebuilds both).
        await self.db.commit()
        await self.vector_store.upsert(records)

        document.status = IngestionStatus.COMPLETED
        document.error = None
        job.status = JobStatus.SUCCEEDED
        job.stage = None
        job.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(
            "ingestion_completed",
            document_id=str(document.id),
            chunks=len(records),
            pages=parsed.page_count,
        )

    async def _mark_failed(self, job_id: uuid.UUID, document_id: uuid.UUID, exc: Exception) -> None:
        job = await self.db.get(IngestionJob, job_id)
        document = await self.db.get(Document, document_id)
        now = datetime.now(timezone.utc)
        if job is not None:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.finished_at = now
        if document is not None:
            document.status = IngestionStatus.FAILED
            document.error = str(exc)
        await self.db.commit()
        logger.error("ingestion_failed", document_id=str(document_id), error=str(exc))
