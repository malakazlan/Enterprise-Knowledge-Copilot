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
from app.core.crypto import encrypt_secret
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.collection import Collection
from app.models.connector import CONNECTOR_TYPES, Connector
from app.models.document import Document, IngestionStatus
from app.models.user import UserRole
from app.services.connectors import confluence, gdrive, notion
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


class NotionConfig(BaseModel):
    collection_id: uuid.UUID | None = None
    max_pages: int = Field(default=100, ge=1, le=500)


class ConfluenceConfig(BaseModel):
    # Site URL like https://yourorg.atlassian.net/wiki; token from
    # id.atlassian.com → Security → API tokens. Arrives plain once at create,
    # stored encrypted, masked from every read.
    base_url: str = Field(min_length=8, max_length=500, pattern=r"^https?://")
    email: str = Field(min_length=3, max_length=320)
    api_token: str | None = Field(default=None, min_length=1, max_length=500)
    space_keys: list[str] = Field(default_factory=list, max_length=20)
    collection_id: uuid.UUID | None = None
    max_pages: int = Field(default=200, ge=1, le=500)


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


async def _existing_checksums(db: DbSession) -> set[str]:
    return {checksum for (checksum,) in (await db.execute(select(Document.checksum))).all()}


async def _require_collection(db: DbSession, collection_id: uuid.UUID | None) -> None:
    if collection_id is not None and await db.get(Collection, collection_id) is None:
        raise ValidationAppError("Collection not found.")


async def _ingest_file(
    db: DbSession,
    storage: Storage,
    report: FolderSyncReport,
    existing: set[str],
    filename: str,
    content_type: str,
    data: bytes,
    uploaded_by: uuid.UUID | None,
    collection_id: uuid.UUID | None,
) -> None:
    """Shared tail of every connector sync: dedupe, ingest, record the outcome."""
    if not get_parser().supports(content_type, filename):
        report.skipped_unsupported += 1
        return
    if not data or len(data) > settings.max_upload_bytes:
        report.failed.append(
            FolderSyncFailure(filename=filename, error="empty or exceeds size limit")
        )
        return
    checksum = hashlib.sha256(data).hexdigest()
    if checksum in existing:
        report.skipped_existing += 1
        return
    existing.add(checksum)

    document, job = await DocumentService(db, storage).create_from_upload(
        filename=filename,
        content_type=content_type,
        data=data,
        uploaded_by=uploaded_by,
        collection_id=collection_id,
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
    await _require_collection(db, request.collection_id)

    existing = await _existing_checksums(db)
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
        try:
            data = await asyncio.to_thread(file.read_bytes)
        except OSError as exc:
            report.failed.append(FolderSyncFailure(filename=file.name, error=str(exc)))
            continue
        await _ingest_file(
            db,
            storage,
            report,
            existing,
            file.name,
            content_type,
            data,
            uploaded_by,
            request.collection_id,
        )

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
    elif payload.type == "gdrive":
        config = GdriveConfig.model_validate(payload.config).model_dump(mode="json")
        config["connected"] = False
    elif payload.type == "notion":
        config = NotionConfig.model_validate(payload.config).model_dump(mode="json")
        config["connected"] = False
    else:  # confluence — token arrives plain exactly once, stored encrypted
        parsed = ConfluenceConfig.model_validate(payload.config)
        if not parsed.api_token:
            raise ValidationAppError("Confluence needs an api_token (id.atlassian.com).")
        config = parsed.model_dump(mode="json", exclude={"api_token"})
        config["api_token_enc"] = encrypt_secret(parsed.api_token)
        config["connected"] = True
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
    elif connector.type == "notion":
        report = await _run_notion_sync(db, storage, connector, admin.user_id)
    elif connector.type == "confluence":
        report = await _run_confluence_sync(db, storage, connector, admin.user_id)
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


def _plain_config(connector: Connector) -> dict[str, Any]:
    return {
        k: v for k, v in connector.config.items() if not k.endswith("_enc") and k != "connected"
    }


async def _run_gdrive_sync(
    db: DbSession, storage: Storage, connector: Connector, uploaded_by: uuid.UUID | None
) -> FolderSyncReport:
    refresh = connector.config.get("refresh_token_enc")
    if not refresh:
        raise ValidationAppError("Google Drive is not connected yet — click Connect first.")
    config = GdriveConfig.model_validate(_plain_config(connector))
    await _require_collection(db, config.collection_id)

    files = await gdrive.list_files(refresh, config.folder_id, config.max_files)
    existing = await _existing_checksums(db)
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
        await _ingest_file(
            db,
            storage,
            report,
            existing,
            filename,
            content_type,
            data,
            uploaded_by,
            config.collection_id,
        )

    return report


async def _run_notion_sync(
    db: DbSession, storage: Storage, connector: Connector, uploaded_by: uuid.UUID | None
) -> FolderSyncReport:
    token = connector.config.get("access_token_enc")
    if not token:
        raise ValidationAppError("Notion is not connected yet — click Connect first.")
    config = NotionConfig.model_validate(_plain_config(connector))
    await _require_collection(db, config.collection_id)

    pages = await notion.list_pages(token, config.max_pages)
    existing = await _existing_checksums(db)
    report = FolderSyncReport(
        path="notion:workspace",
        scanned=len(pages),
        ingested=[],
        skipped_existing=0,
        skipped_unsupported=0,
        failed=[],
    )

    for page in pages:
        exported = await notion.export_page(token, page)
        if exported is None:
            report.skipped_unsupported += 1
            continue
        filename, content_type, data = exported
        await _ingest_file(
            db,
            storage,
            report,
            existing,
            filename,
            content_type,
            data,
            uploaded_by,
            config.collection_id,
        )

    return report


async def _run_confluence_sync(
    db: DbSession, storage: Storage, connector: Connector, uploaded_by: uuid.UUID | None
) -> FolderSyncReport:
    token = connector.config.get("api_token_enc")
    if not token:
        raise ValidationAppError("Confluence connector has no API token — recreate it.")
    config = ConfluenceConfig.model_validate(_plain_config(connector))
    await _require_collection(db, config.collection_id)

    pages = await confluence.list_pages(
        config.base_url, config.email, token, config.space_keys, config.max_pages
    )
    existing = await _existing_checksums(db)
    report = FolderSyncReport(
        path=f"confluence:{','.join(config.space_keys) or 'all'}",
        scanned=len(pages),
        ingested=[],
        skipped_existing=0,
        skipped_unsupported=0,
        failed=[],
    )

    for page in pages:
        exported = confluence.export_page(page)
        if exported is None:
            report.skipped_unsupported += 1
            continue
        filename, content_type, data = exported
        await _ingest_file(
            db,
            storage,
            report,
            existing,
            filename,
            content_type,
            data,
            uploaded_by,
            config.collection_id,
        )

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
    if connector.type == "gdrive":
        return {"authorize_url": gdrive.authorization_url(connector.id)}
    if connector.type == "notion":
        return {"authorize_url": notion.authorization_url(connector.id)}
    raise ValidationAppError("Only OAuth connectors (gdrive, notion) use the consent flow.")


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


@public_router.get("/notion/callback", summary="Notion consent redirect target")
async def notion_callback(
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error or not code or not state:
        raise ValidationAppError(f"Notion connect failed: {error or 'missing code/state'}.")
    connector_id = notion.read_state(state)
    connector = await db.get(Connector, connector_id)
    if connector is None or connector.type != "notion":
        raise NotFoundError("Connector not found.")
    encrypted = await notion.exchange_code(code)
    connector.config = {**connector.config, "access_token_enc": encrypted, "connected": True}
    await db.commit()
    return RedirectResponse("/integrations/", status_code=307)
