"""Collections: access boundaries for documents (admin-managed)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, require_principal_roles
from app.core.exceptions import ConflictError, NotFoundError
from app.models.collection import Collection, CollectionMember
from app.models.document import Document
from app.models.user import User, UserRole

router = APIRouter(tags=["collections"])

admin_only = Depends(require_principal_roles(UserRole.ADMIN))


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    document_count: int = 0
    member_count: int = 0


class MemberAdd(BaseModel):
    email: str


class MemberRead(BaseModel):
    user_id: uuid.UUID
    email: str


async def _get_or_404(db: DbSession, collection_id: uuid.UUID) -> Collection:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection


async def _read(db: DbSession, collection: Collection) -> CollectionRead:
    documents = await db.execute(
        select(func.count(Document.id)).where(Document.collection_id == collection.id)
    )
    members = await db.execute(
        select(func.count(CollectionMember.id)).where(
            CollectionMember.collection_id == collection.id
        )
    )
    read = CollectionRead.model_validate(collection)
    read.document_count = int(documents.scalar_one())
    read.member_count = int(members.scalar_one())
    return read


@router.post(
    "",
    response_model=CollectionRead,
    status_code=201,
    dependencies=[admin_only],
    summary="Create a collection",
)
async def create_collection(payload: CollectionCreate, db: DbSession) -> CollectionRead:
    exists = await db.execute(select(Collection).where(Collection.name == payload.name))
    if exists.scalar_one_or_none() is not None:
        raise ConflictError(f"Collection '{payload.name}' already exists.")
    collection = Collection(id=uuid.uuid4(), name=payload.name, description=payload.description)
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return await _read(db, collection)


@router.get("", response_model=list[CollectionRead], summary="List collections I can see")
async def list_collections(db: DbSession, current_user: CurrentUser) -> list[CollectionRead]:
    query = select(Collection).order_by(Collection.name)
    if current_user.role != UserRole.ADMIN:
        member_of = select(CollectionMember.collection_id).where(
            CollectionMember.user_id == current_user.id
        )
        query = query.where(Collection.id.in_(member_of))
    result = await db.execute(query)
    return [await _read(db, collection) for collection in result.scalars().all()]


@router.delete(
    "/{collection_id}",
    status_code=204,
    dependencies=[admin_only],
    summary="Delete a collection (documents become shared)",
)
async def delete_collection(db: DbSession, collection_id: uuid.UUID) -> None:
    collection = await _get_or_404(db, collection_id)
    await db.delete(collection)
    await db.commit()


@router.get(
    "/{collection_id}/members",
    response_model=list[MemberRead],
    dependencies=[admin_only],
    summary="List collection members",
)
async def list_members(db: DbSession, collection_id: uuid.UUID) -> list[MemberRead]:
    await _get_or_404(db, collection_id)
    result = await db.execute(
        select(CollectionMember.user_id, User.email)
        .join(User, User.id == CollectionMember.user_id)
        .where(CollectionMember.collection_id == collection_id)
        .order_by(User.email)
    )
    return [MemberRead(user_id=user_id, email=email) for user_id, email in result.all()]


@router.post(
    "/{collection_id}/members",
    response_model=MemberRead,
    status_code=201,
    dependencies=[admin_only],
    summary="Grant a user access to a collection",
)
async def add_member(payload: MemberAdd, db: DbSession, collection_id: uuid.UUID) -> MemberRead:
    await _get_or_404(db, collection_id)
    user = (
        await db.execute(select(User).where(User.email == payload.email.lower().strip()))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"No user with email {payload.email!r}.")
    existing = await db.execute(
        select(CollectionMember).where(
            CollectionMember.collection_id == collection_id,
            CollectionMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Already a member.")
    db.add(CollectionMember(id=uuid.uuid4(), collection_id=collection_id, user_id=user.id))
    await db.commit()
    return MemberRead(user_id=user.id, email=user.email)


@router.delete(
    "/{collection_id}/members/{user_id}",
    status_code=204,
    dependencies=[admin_only],
    summary="Revoke a user's access to a collection",
)
async def remove_member(db: DbSession, collection_id: uuid.UUID, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(CollectionMember).where(
            CollectionMember.collection_id == collection_id,
            CollectionMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise NotFoundError("Membership not found.")
    await db.delete(member)
    await db.commit()
