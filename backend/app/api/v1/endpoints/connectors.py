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
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession, Principal, Storage, require_principal_roles
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.collection import Collection
from app.models.connector import CONNECTOR_TYPES, Connector
from app.models.document import Document, IngestionStatus
from app.models.user import UserRole
from app.services.connectors import gdrive
from app.services.documents import DocumentService
from app.services.ingestion.factory import get_parser
from app.services.ingestion.pipeline import IngestionError, IngestionPipeline

router = APIRouter(
    tags=["connectors"], dependencies=[Depends(require_principal_roles(UserRole.ADMIN))]
)

Admin = Annotated[Principal, Depends(require_principal_roles(UserRole.ADMIN))]

# Browser redirects from Google land here; the signed state IS the auth.
public_router = APIRouter(tags=["connectors"])

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


class GdriveConfig(BaseModel):
    # Restrict to one Drive folder (empty = everything the grant can read).
    folder_id: str | None = Field(default=None, max_length=200)
    collection_id: uuid.UUID | None = None
    max_files: int = Field(default=200, ge=1, le=500)


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str
    config: dict[str, Any] = Field(default_factory=dict)


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
    if payload.type == "folder":
        config = FolderSyncRequest.model_validate(payload.config).model_dump(mode="json")
    else:
        config = GdriveConfig.model_validate(payload.config).model_dump(mode="json")
        config["connected"] = False
    connector = Connector(
        id=uuid.uuid4(),
        name=payload.name,
        type=payload.type,
        config=config,
        created_by=admin.user_id,
    )
    db.add(connector)
    await db.commit()
    await db.refresh(connector)
    return _read(connector)


def _read(connector: Connector) -> ConnectorRead:
    read = ConnectorRead.model_validate(connector)
    read.config = {k: v for k, v in read.config.items() if not k.endswith("_enc")}
    return read


@router.get("", response_model=list[ConnectorRead], summary="List saved connectors")
async def list_connectors(db: DbSession) -> list[ConnectorRead]:
    result = await db.execute(select(Connector).order_by(Connector.created_at))
    return [_read(connector) for connector in result.scalars().all()]


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
    if connector.type == "folder":
        request = FolderSyncRequest.model_validate(connector.config)
        report = await _run_folder_sync(db, storage, request, admin.user_id)
    else:
        report = await _run_gdrive_sync(db, storage, connector, admin.user_id)
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


async def _run_gdrive_sync(
    db: DbSession, storage: Storage, connector: Connector, uploaded_by: uuid.UUID | None
) -> FolderSyncReport:
    refresh = connector.config.get("refresh_token_enc")
    if not refresh:
        raise ValidationAppError("Google Drive is not connected yet — click Connect first.")
    config = GdriveConfig.model_validate(
        {k: v for k, v in connector.config.items() if not k.endswith("_enc") and k != "connected"}
    )
    if config.collection_id is not None and await db.get(Collection, config.collection_id) is None:
        raise ValidationAppError("Collection not found.")

    files = await gdrive.list_files(refresh, config.folder_id, config.max_files)
    existing = {checksum for (checksum,) in (await db.execute(select(Document.checksum))).all()}
    parser = get_parser()
    service = DocumentService(db, storage)
    report = FolderSyncReport(
        path=f"gdrive:{config.folder_id or 'all'}",
        scanned=len(files),
        ingested=[],
        skipped_existing=0,
        skipped_unsupported=0,
        failed=[],
    )

    for meta in files:
        downloaded = await gdrive.download_file(refresh, meta)
        if downloaded is None:
            report.skipped_unsupported += 1
            continue
        filename, content_type, data = downloaded
        if not parser.supports(content_type, filename):
            report.skipped_unsupported += 1
            continue
        if not data or len(data) > settings.max_upload_bytes:
            report.failed.append(
                FolderSyncFailure(filename=filename, error="empty or exceeds size limit")
            )
            continue
        checksum = hashlib.sha256(data).hexdigest()
        if checksum in existing:
            report.skipped_existing += 1
            continue
        existing.add(checksum)

        document, job = await service.create_from_upload(
            filename=filename,
            content_type=content_type,
            data=data,
            uploaded_by=uploaded_by,
            collection_id=config.collection_id,
        )
        try:
            await IngestionPipeline(db, storage).run(job.id)
        except IngestionError:
            pass  # recorded on the document; reported below
        await db.refresh(document)
        if document.status == IngestionStatus.FAILED:
            report.failed.append(
                FolderSyncFailure(filename=filename, error=document.error or "ingestion failed")
            )
        else:
            report.ingested.append(filename)

    return report


@router.get(
    "/{connector_id}/authorize",
    summary="Provider consent URL for an OAuth connector",
)
async def authorize_connector(
    db: DbSession, admin: Admin, connector_id: uuid.UUID
) -> dict[str, str]:
    # Returned as JSON (not a redirect): browsers hide Location headers from
    # fetch() on manual redirects, so the SPA navigates itself.
    connector = await db.get(Connector, connector_id)
    if connector is None:
        raise NotFoundError("Connector not found.")
    if connector.type != "gdrive":
        raise ValidationAppError("Only Google Drive connectors use the consent flow.")
    return {"authorize_url": gdrive.authorization_url(connector.id)}


@public_router.get("/gdrive/callback", summary="Google consent redirect target")
async def gdrive_callback(
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error or not code or not state:
        raise ValidationAppError(f"Google Drive connect failed: {error or 'missing code/state'}.")
    connector_id = gdrive.read_state(state)
    connector = await db.get(Connector, connector_id)
    if connector is None or connector.type != "gdrive":
        raise NotFoundError("Connector not found.")
    encrypted = await gdrive.exchange_code(code)
    connector.config = {**connector.config, "refresh_token_enc": encrypted, "connected": True}
    await db.commit()
    return RedirectResponse("/integrations/", status_code=307)
