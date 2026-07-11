"""Chat threads: persistent conversations backed by the query audit log."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import delete, desc, select, update

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models.querylog import QueryLog
from app.models.thread import ChatThread
from app.schemas.thread import ThreadCreate, ThreadDetail, ThreadMessage, ThreadRead

router = APIRouter(tags=["threads"])

DEFAULT_TITLE = "New conversation"


async def get_owned_thread(db: DbSession, thread_id: uuid.UUID, user_id: uuid.UUID) -> ChatThread:
    thread = await db.get(ChatThread, thread_id)
    if thread is None or thread.created_by != user_id:
        raise NotFoundError("Thread not found.")
    return thread


@router.post("", response_model=ThreadRead, status_code=201, summary="Start a conversation")
async def create_thread(
    payload: ThreadCreate, db: DbSession, current_user: CurrentUser
) -> ThreadRead:
    thread = ChatThread(
        id=uuid.uuid4(),
        title=(payload.title or DEFAULT_TITLE).strip() or DEFAULT_TITLE,
        created_by=current_user.id,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return ThreadRead.model_validate(thread)


@router.get("", response_model=list[ThreadRead], summary="List my conversations")
async def list_threads(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ThreadRead]:
    result = await db.execute(
        select(ChatThread)
        .where(ChatThread.created_by == current_user.id)
        .order_by(desc(ChatThread.updated_at))
        .limit(limit)
    )
    return [ThreadRead.model_validate(t) for t in result.scalars().all()]


@router.get("/{thread_id}", response_model=ThreadDetail, summary="A conversation with messages")
async def get_thread(
    db: DbSession, current_user: CurrentUser, thread_id: uuid.UUID
) -> ThreadDetail:
    thread = await get_owned_thread(db, thread_id, current_user.id)
    result = await db.execute(
        select(QueryLog).where(QueryLog.thread_id == thread.id).order_by(QueryLog.created_at)
    )
    messages = [ThreadMessage.model_validate(log) for log in result.scalars().all()]
    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=messages,
    )


@router.delete("/{thread_id}", status_code=204, summary="Delete a conversation")
async def delete_thread(db: DbSession, current_user: CurrentUser, thread_id: uuid.UUID) -> None:
    thread = await get_owned_thread(db, thread_id, current_user.id)
    # Audit rows outlive the thread (thread_id becomes NULL via FK), by design.
    await db.execute(update(QueryLog).where(QueryLog.thread_id == thread.id).values(thread_id=None))
    await db.execute(delete(ChatThread).where(ChatThread.id == thread.id))
    await db.commit()
