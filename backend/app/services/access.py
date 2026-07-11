"""Document access control.

One rule, applied at retrieval time everywhere: a principal may retrieve from
shared documents (no collection) plus documents in collections they belong to.
Admins — human or API key — are unrestricted. Non-admin API keys carry no user
identity, so they see shared documents only (default-deny).
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.models.collection import CollectionMember
from app.models.document import Document
from app.models.user import UserRole


async def allowed_document_ids(db: AsyncSession, principal: Principal) -> list[uuid.UUID] | None:
    """Document ids this principal may retrieve from; None means unrestricted."""
    if principal.role == UserRole.ADMIN:
        return None

    conditions = [Document.collection_id.is_(None)]
    if principal.user_id is not None:
        member_of = select(CollectionMember.collection_id).where(
            CollectionMember.user_id == principal.user_id
        )
        conditions.append(Document.collection_id.in_(member_of))

    result = await db.execute(select(Document.id).where(or_(*conditions)))
    return [row for (row,) in result.all()]


def restrict_requested_ids(
    allowed: list[uuid.UUID] | None, requested: list[uuid.UUID] | None
) -> list[uuid.UUID] | None:
    """Intersect an explicit document filter with the principal's access.

    Returns the effective filter; an empty list means "nothing retrievable"
    and must be honoured (it is NOT the same as None/unrestricted).
    """
    if allowed is None:
        return requested
    if requested is None:
        return allowed
    allowed_set = set(allowed)
    return [document_id for document_id in requested if document_id in allowed_set]
