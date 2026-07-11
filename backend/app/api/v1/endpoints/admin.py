"""Deployment statistics for the admin dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select

from app.api.deps import DbSession, require_principal_roles
from app.models.apikey import ApiKey
from app.models.document import Document, DocumentChunk, IngestionStatus
from app.models.querylog import QueryLog, ReviewStatus
from app.models.user import User, UserRole
from app.schemas.review import AdminStats

router = APIRouter(tags=["admin"], dependencies=[Depends(require_principal_roles(UserRole.ADMIN))])


@router.get("/stats", response_model=AdminStats, summary="Deployment statistics")
async def stats(db: DbSession) -> AdminStats:
    async def count(query: Select[Any]) -> int:
        return int((await db.execute(query)).scalar_one() or 0)

    refusals = await db.execute(
        select(QueryLog.refusal_reason, func.count(QueryLog.id))
        .where(QueryLog.refusal_reason.is_not(None))
        .group_by(QueryLog.refusal_reason)
    )
    avg_confidence = (
        await db.execute(select(func.avg(QueryLog.confidence)).where(QueryLog.answered.is_(True)))
    ).scalar_one()

    return AdminStats(
        documents_total=await count(select(func.count(Document.id))),
        documents_failed=await count(
            select(func.count(Document.id)).where(Document.status == IngestionStatus.FAILED)
        ),
        chunks_total=await count(select(func.count(DocumentChunk.id))),
        queries_total=await count(select(func.count(QueryLog.id))),
        queries_answered=await count(
            select(func.count(QueryLog.id)).where(QueryLog.answered.is_(True))
        ),
        queries_refused=await count(
            select(func.count(QueryLog.id)).where(QueryLog.answered.is_(False))
        ),
        refusal_breakdown={reason: int(n) for reason, n in refusals.all()},
        avg_confidence_answered=round(float(avg_confidence), 4) if avg_confidence else None,
        reviews_pending=await count(
            select(func.count(QueryLog.id)).where(QueryLog.review_status == ReviewStatus.PENDING)
        ),
        api_keys_active=await count(
            select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_(None))
        ),
        users_total=await count(select(func.count(User.id))),
    )
