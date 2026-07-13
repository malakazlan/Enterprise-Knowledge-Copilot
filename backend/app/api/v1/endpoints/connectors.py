"""Connectors: bulk ingestion sources, configured once and synced on demand.

The folder connector points at a directory on the server (a mounted SMB/NFS
share, an rclone-synced bucket, a drop folder) and ingests everything new.
Files are deduplicated by content checksum, so re-syncing is idempotent.
Saved connectors keep their configuration and last sync report in the
database — click "Sync now" in the UI or schedule the endpoint with cron.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession, Principal, Storage, require_principal_roles
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.collection import Collection
from app.models.connector import CONNECTOR_TYPES, Connector
from app.models.document import Document, IngestionStatus
from app.models.user import UserRole
from app.services.documents import DocumentService
from app.services.ingestion.factory import get_parser
from app.services.ingestion.pipeline import IngestionError, IngestionPipeline

router = APIRouter(
    tags=["connectors"], dependencies=[Depends(require_principal_roles(UserRole.ADMIN))]
)

Admin = Annotated[Principal, Depends(require_principal_roles(UserRole.ADMIN))]

_MAX_FILES_PER_SYNC = 500


class FolderSyncRequest(BaseModel):
    # Server-side directory (mounted share / drop folder), not a client path.
    path: str = Field(min_length=1, max_length=1000)
    recursive: bool = True
    collection_id: uuid.UUID | None = None


class FolderSyncFailure(BaseModel):
    filename: str
    error: str


class FolderSyncReport(BaseModel):
    path: str
    scanned: int
    ingested: list[str]
    skipped_existing: int
    skipped_unsupported: int
    failed: list[FolderSyncFailure]


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str
    config: FolderSyncRequest


class ConnectorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    config: dict[str, Any]
    is_active: bool
    last_sync_at: datetime | None
    last_sync_report: dict[str, Any] | None
    created_at: datetime


async def _run_folder_sync(
    db: DbSession, storage: Storage, request: FolderSyncRequest, uploaded_by: uuid.UUID | None
) -> FolderSyncReport:
    root = Path(request.path)

    def _scan() -> list[Path] | None:
        if not root.is_dir():
            return None
        pattern = "**/*" if request.recursive else "*"
        return sorted(p for p in root.glob(pattern) if p.is_file())[:_MAX_FILES_PER_SYNC]

    files = await asyncio.to_thread(_scan)
    if files is None:
        raise ValidationAppError(f"Not a directory on the server: {request.path}")
    if (
        request.collection_id is not None
        and await db.get(Collection, request.collection_id) is None
    ):
        raise ValidationAppError("Collection not found.")

    existing = {checksum for (checksum,) in (await db.execute(select(Document.checksum))).all()}

    parser = get_parser()
    service = DocumentService(db, storage)
    report = FolderSyncReport(
        path=str(root),
        scanned=len(files),
        ingested=[],
        skipped_existing=0,
        skipped_unsupported=0,
        failed=[],
    )

    for file in files:
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if not parser.supports(content_type, file.name):
            report.skipped_unsupported += 1
            continue
        try:
            data = await asyncio.to_thread(file.read_bytes)
        except OSError as exc:
            report.failed.append(FolderSyncFailure(filename=file.name, error=str(exc)))
            continue
        if not data or len(data) > settings.max_upload_bytes:
            report.failed.append(
                FolderSyncFailure(filename=file.name, error="empty or exceeds size limit")
            )
            continue

        checksum = hashlib.sha256(data).hexdigest()
        if checksum in existing:
            report.skipped_existing += 1
            continue
        existing.add(checksum)

        document, job = await service.create_from_upload(
            filename=file.name,
            content_type=content_type,
            data=data,
            uploaded_by=uploaded_by,
            collection_id=request.collection_id,
        )
        try:
            await IngestionPipeline(db, storage).run(job.id)
        except IngestionError:
            pass  # recorded on the document; reported below
        await db.refresh(document)
        if document.status == IngestionStatus.FAILED:
            report.failed.append(
                FolderSyncFailure(filename=file.name, error=document.error or "ingestion failed")
            )
        else:
            report.ingested.append(file.name)

    return report


@router.post(
    "/folder/sync",
    response_model=FolderSyncReport,
    summary="One-off sync of a server-side folder (idempotent)",
)
async def folder_sync(
    payload: FolderSyncRequest, db: DbSession, storage: Storage, admin: Admin
) -> FolderSyncReport:
    return await _run_folder_sync(db, storage, payload, admin.user_id)


@router.post(
    "",
    response_model=ConnectorRead,
    status_code=201,
    summary="Save a connector configuration",
)
async def create_connector(payload: ConnectorCreate, db: DbSession, admin: Admin) -> ConnectorRead:
    if payload.type not in CONNECTOR_TYPES:
        raise ValidationAppError(
            f"Unknown connector type {payload.type!r}. Available: {', '.join(CONNECTOR_TYPES)}."
        )
    connector = Connector(
        id=uuid.uuid4(),
        name=payload.name,
        type=payload.type,
        config=payload.config.model_dump(mode="json"),
        created_by=admin.user_id,
    )
    db.add(connector)
    await db.commit()
    await db.refresh(connector)
    return ConnectorRead.model_validate(connector)


@router.get("", response_model=list[ConnectorRead], summary="List saved connectors")
async def list_connectors(db: DbSession) -> list[ConnectorRead]:
    result = await db.execute(select(Connector).order_by(Connector.created_at))
    return [ConnectorRead.model_validate(connector) for connector in result.scalars().all()]


@router.post(
    "/{connector_id}/sync",
    response_model=FolderSyncReport,
    summary="Run a saved connector now",
)
async def sync_connector(
    db: DbSession, storage: Storage, admin: Admin, connector_id: uuid.UUID
) -> FolderSyncReport:
    connector = await db.get(Connector, connector_id)
    if connector is None:
        raise NotFoundError("Connector not found.")
    request = FolderSyncRequest.model_validate(connector.config)
    report = await _run_folder_sync(db, storage, request, admin.user_id)
    connector.last_sync_at = datetime.now(timezone.utc)
    connector.last_sync_report = report.model_dump(mode="json")
    await db.commit()
    return report


@router.delete("/{connector_id}", status_code=204, summary="Delete a saved connector")
async def delete_connector(db: DbSession, connector_id: uuid.UUID) -> None:
    connector = await db.get(Connector, connector_id)
    if connector is None:
        raise NotFoundError("Connector not found.")
    await db.delete(connector)
    await db.commit()
