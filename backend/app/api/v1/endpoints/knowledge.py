"""Knowledge write-back — agents deposit what they learn.

An entry is a small, attributed piece of knowledge ("customer X prefers
net-60 terms") that flows through the SAME pipeline as documents: chunked,
embedded, access-controlled by collection, retrievable with citations within
seconds. Requires an admin or reviewer principal — give writer agents a
reviewer-role API key.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import DbSession, Principal, Storage, require_principal_roles
from app.core.exceptions import ValidationAppError
from app.models.collection import Collection
from app.models.user import UserRole
from app.schemas.document import DocumentRead
from app.services.documents import DocumentService
from app.services.ingestion.pipeline import IngestionError, IngestionPipeline

router = APIRouter(tags=["knowledge"])

Writer = Annotated[Principal, Depends(require_principal_roles(UserRole.ADMIN, UserRole.REVIEWER))]


class KnowledgeEntry(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=10, max_length=50_000)
    # Who/what learned this (agent name, workflow id); recorded in metadata.
    source: str | None = Field(default=None, max_length=200)
    collection_id: uuid.UUID | None = None


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:80] or "entry"


@router.post(
    "",
    response_model=DocumentRead,
    status_code=201,
    summary="Write a knowledge entry (agents deposit what they learn)",
)
async def create_entry(
    payload: KnowledgeEntry,
    db: DbSession,
    storage: Storage,
    writer: Writer,
) -> DocumentRead:
    if (
        payload.collection_id is not None
        and await db.get(Collection, payload.collection_id) is None
    ):
        raise ValidationAppError("Collection not found.")

    body = f"# {payload.title}\n\n{payload.content}\n"
    service = DocumentService(db, storage)
    document, job = await service.create_from_upload(
        filename=f"{_slug(payload.title)}.md",
        content_type="text/markdown",
        data=body.encode("utf-8"),
        uploaded_by=writer.user_id,
        collection_id=payload.collection_id,
    )
    document.doc_metadata = {
        **document.doc_metadata,
        "knowledge_entry": True,
        "source": payload.source
        or (writer.api_key.name if writer.api_key else None)
        or (writer.user.email if writer.user else "unknown"),
    }
    await db.commit()

    try:
        await IngestionPipeline(db, storage).run(job.id)
    except IngestionError:
        pass  # recorded on the document; surfaced in the response status
    await db.refresh(document)
    return DocumentRead.model_validate(document)
