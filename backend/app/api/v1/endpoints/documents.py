"""Document upload, listing, retrieval, job status, and deletion."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status

from app.api.deps import (
    CurrentPrincipal,
    DbSession,
    Principal,
    Storage,
    require_principal_roles,
)
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.collection import Collection
from app.models.document import IngestionStatus
from app.models.user import UserRole
from app.schemas.document import ChunkRead, DocumentRead, DocumentWithJob, IngestionJobRead
from app.services.access import allowed_document_ids
from app.services.documents import DocumentService
from app.services.ingestion.factory import get_parser, get_vector_store
from app.services.ingestion.pipeline import IngestionError, IngestionPipeline
from app.services.webhooks import deliver, subscribed

router = APIRouter(tags=["documents"])

Uploader = Annotated[Principal, Depends(require_principal_roles(UserRole.ADMIN, UserRole.REVIEWER))]
Admin = Annotated[Principal, Depends(require_principal_roles(UserRole.ADMIN))]


@router.post(
    "",
    response_model=DocumentWithJob,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document (admin/reviewer)",
)
async def upload_document(
    db: DbSession,
    storage: Storage,
    uploader: Uploader,
    file: Annotated[UploadFile, File(...)],
    background: BackgroundTasks,
    collection_id: Annotated[uuid.UUID | None, Query()] = None,
) -> DocumentWithJob:
    if collection_id is not None and await db.get(Collection, collection_id) is None:
        raise ValidationAppError("Collection not found.")
    data = await file.read()
    if not data:
        raise ValidationAppError("Uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ValidationAppError(
            f"File exceeds the maximum size of {settings.max_upload_bytes} bytes."
        )

    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    if not get_parser().supports(content_type, filename):
        raise ValidationAppError(f"Unsupported file type: {filename} ({content_type}).")

    service = DocumentService(db, storage)
    document, job = await service.create_from_upload(
        filename=filename,
        content_type=content_type,
        data=data,
        uploaded_by=uploader.user_id,
        collection_id=collection_id,
    )

    if settings.ingestion_eager:
        try:
            await IngestionPipeline(db, storage).run(job.id)
        except IngestionError:
            # Failure is recorded on the job/document and surfaced in the response.
            pass
        await db.refresh(document)
        await db.refresh(job)
    else:
        from app.workers.tasks import run_ingestion

        run_ingestion.delay(str(job.id))

    event = "document.failed" if document.status == IngestionStatus.FAILED else "document.ingested"
    targets = await subscribed(db, event)
    if targets:
        background.add_task(
            deliver,
            event,
            targets,
            {
                "document_id": str(document.id),
                "filename": document.filename,
                "status": document.status.value,
                "error": document.error,
            },
        )

    return DocumentWithJob(
        document=DocumentRead.model_validate(document),
        job=IngestionJobRead.model_validate(job),
    )


@router.get("", response_model=list[DocumentRead], summary="List documents")
async def list_documents(
    db: DbSession,
    storage: Storage,
    principal: CurrentPrincipal,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentRead]:
    documents = await DocumentService(db, storage).list_documents(limit=limit, offset=offset)
    allowed = await allowed_document_ids(db, principal)
    if allowed is not None:
        permitted = set(allowed)
        documents = [document for document in documents if document.id in permitted]
    return [DocumentRead.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentRead, summary="Get a document")
async def get_document(
    db: DbSession, storage: Storage, principal: CurrentPrincipal, document_id: uuid.UUID
) -> DocumentRead:
    document = await DocumentService(db, storage).get(document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    allowed = await allowed_document_ids(db, principal)
    if allowed is not None and document.id not in set(allowed):
        raise NotFoundError("Document not found.")
    return DocumentRead.model_validate(document)


@router.get(
    "/{document_id}/jobs",
    response_model=list[IngestionJobRead],
    summary="List a document's ingestion jobs",
)
async def list_document_jobs(
    db: DbSession, storage: Storage, _principal: CurrentPrincipal, document_id: uuid.UUID
) -> list[IngestionJobRead]:
    service = DocumentService(db, storage)
    if await service.get(document_id) is None:
        raise NotFoundError("Document not found.")
    jobs = await service.list_jobs(document_id)
    return [IngestionJobRead.model_validate(job) for job in jobs]


@router.get(
    "/{document_id}/chunks",
    response_model=list[ChunkRead],
    summary="List a document's chunks in reading order",
)
async def list_document_chunks(
    db: DbSession, storage: Storage, principal: CurrentPrincipal, document_id: uuid.UUID
) -> list[ChunkRead]:
    service = DocumentService(db, storage)
    if await service.get(document_id) is None:
        raise NotFoundError("Document not found.")
    allowed = await allowed_document_ids(db, principal)
    if allowed is not None and document_id not in set(allowed):
        raise NotFoundError("Document not found.")
    chunks = await service.list_chunks(document_id)
    return [ChunkRead.model_validate(chunk) for chunk in chunks]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its chunks/vectors (admin)",
)
async def delete_document(
    db: DbSession, storage: Storage, _admin: Admin, document_id: uuid.UUID
) -> None:
    service = DocumentService(db, storage)
    document = await service.get(document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    await get_vector_store().delete_by_document(str(document.id))
    await service.delete(document)
