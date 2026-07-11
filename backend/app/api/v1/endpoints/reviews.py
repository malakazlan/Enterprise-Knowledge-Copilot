"""Human review queue — answers flagged by the confidence policy.

Reviewers and admins work the queue; every resolution is recorded on the
audit row itself (who, when, verdict, note).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbSession, Principal, require_principal_roles
from app.core.exceptions import ConflictError, NotFoundError
from app.models.querylog import QueryLog, ReviewStatus
from app.models.user import UserRole
from app.schemas.review import ReviewItem, ReviewResolve

router = APIRouter(tags=["reviews"])

Reviewer = Annotated[Principal, Depends(require_principal_roles(UserRole.ADMIN, UserRole.REVIEWER))]


@router.get("", response_model=list[ReviewItem], summary="List review queue items")
async def list_reviews(
    db: DbSession,
    _reviewer: Reviewer,
    status_filter: ReviewStatus = Query(default=ReviewStatus.PENDING, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ReviewItem]:
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.review_status == status_filter)
        .order_by(QueryLog.created_at)
        .limit(limit)
    )
    return [ReviewItem.model_validate(row) for row in result.scalars().all()]


@router.post(
    "/{query_id}/resolve",
    response_model=ReviewItem,
    summary="Approve or reject a flagged answer",
)
async def resolve_review(
    payload: ReviewResolve, db: DbSession, reviewer: Reviewer, query_id: uuid.UUID
) -> ReviewItem:
    log = await db.get(QueryLog, query_id)
    if log is None or log.review_status is None:
        raise NotFoundError("Review item not found.")
    if log.review_status is not ReviewStatus.PENDING:
        raise ConflictError(f"Already resolved as {log.review_status.value}.")

    log.review_status = (
        ReviewStatus.APPROVED if payload.action == "approve" else ReviewStatus.REJECTED
    )
    log.reviewed_by = reviewer.user_id
    log.reviewed_at = datetime.now(timezone.utc)
    log.review_note = payload.note
    await db.commit()
    await db.refresh(log)
    return ReviewItem.model_validate(log)
