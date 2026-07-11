"""Connectors: bulk ingestion from sources beyond one-file uploads.

v1 ships the folder connector: point it at a directory on the server (a
mounted SMB/NFS share, an rclone-synced S3 bucket, a drop folder) and it
ingests everything new. Files are deduplicated by content checksum, so
re-syncing the same folder is idempotent — only new or changed files ingest.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, Principal, Storage, require_principal_roles
from app.core.config import settings
from app.core.exceptions import ValidationAppError
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


@router.post(
    "/folder/sync",
    response_model=FolderSyncReport,
    summary="Ingest new/changed files from a server-side folder (idempotent)",
)
async def folder_sync(
    payload: FolderSyncRequest, db: DbSession, storage: Storage, admin: Admin
) -> FolderSyncReport:
    root = Path(payload.path)

    def _scan() -> list[Path] | None:
        if not root.is_dir():
            return None
        pattern = "**/*" if payload.recursive else "*"
        return sorted(p for p in root.glob(pattern) if p.is_file())[:_MAX_FILES_PER_SYNC]

    files = await asyncio.to_thread(_scan)
    if files is None:
        raise ValidationAppError(f"Not a directory on the server: {payload.path}")

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
            uploaded_by=admin.user_id,
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
