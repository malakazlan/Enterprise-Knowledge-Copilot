"""Unit tests for follow-up condensation."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.querylog import QueryLog
from app.models.thread import ChatThread
from app.models.user import User, UserRole
from app.services.conversation import condense_query
from app.services.generation.ports import CompletionRequest, CompletionResult


class _RewriteLLM:
    name = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        return CompletionResult(text=self.reply)


class _BrokenLLM:
    name = "broken"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise RuntimeError("provider down")


async def _thread_with_history(db_session: AsyncSession) -> uuid.UUID:
    user = User(
        id=uuid.uuid4(),
        email="c@example.com",
        hashed_password="x",
        full_name="C",
        role=UserRole.USER,
    )
    thread = ChatThread(id=uuid.uuid4(), title="t", created_by=user.id)
    log = QueryLog(
        id=uuid.uuid4(),
        thread_id=thread.id,
        profile="general",
        query="Who must wear a helmet on site?",
        answer="All workers must wear a helmet.",
        answered=True,
        confidence=0.9,
        grounded_ratio=1.0,
        needs_review=False,
        model="fake",
        citations=[],
        took_ms=1.0,
    )
    db_session.add_all([user, thread, log])
    await db_session.commit()
    return thread.id


async def test_no_history_returns_query_unchanged(db_session: AsyncSession) -> None:
    thread_id = uuid.uuid4()  # no logs attached
    assert await condense_query(db_session, thread_id, "hello there", None) == "hello there"


async def test_heuristic_borrows_previous_question(db_session: AsyncSession) -> None:
    thread_id = await _thread_with_history(db_session)
    condensed = await condense_query(db_session, thread_id, "what about visitors?", None)
    assert condensed == "Who must wear a helmet on site? what about visitors?"
    # Long, self-contained questions pass through untouched.
    long_q = "What does the manual say about high-visibility vests in vehicle zones?"
    assert await condense_query(db_session, thread_id, long_q, None) == long_q


async def test_llm_rewrite_used_and_conversation_included(db_session: AsyncSession) -> None:
    thread_id = await _thread_with_history(db_session)
    llm = _RewriteLLM("Do visitors need to wear helmets on site?")
    condensed = await condense_query(db_session, thread_id, "what about visitors?", llm)
    assert condensed == "Do visitors need to wear helmets on site?"
    prompt = llm.requests[0].user
    assert "Who must wear a helmet on site?" in prompt
    assert "what about visitors?" in prompt


async def test_llm_failure_falls_back_to_heuristic(db_session: AsyncSession) -> None:
    thread_id = await _thread_with_history(db_session)
    condensed = await condense_query(db_session, thread_id, "and visitors?", _BrokenLLM())
    assert condensed == "Who must wear a helmet on site? and visitors?"
