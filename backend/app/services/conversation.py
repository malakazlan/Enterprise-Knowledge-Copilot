"""Follow-up condensation — make thread questions standalone before retrieval.

"What about visitors?" retrieves nothing on its own; the words that matter
live in the previous exchange. When a thread has history, the follow-up is
rewritten into a self-contained query: by the configured LLM when one is
available, otherwise by a conservative heuristic (prepend the previous
question's words). The user's ORIGINAL words are what gets audited — the
rewrite only steers retrieval and generation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.querylog import QueryLog
from app.services.generation.ports import CompletionRequest, LLMProvider

logger = get_logger("app.conversation")

_HISTORY_TURNS = 3
_FOLLOWUP_MAX_WORDS = 6
_REWRITE_MAX_TOKENS = 120

_REWRITE_SYSTEM = (
    "You rewrite a follow-up question into ONE self-contained search query, "
    "using the conversation for missing referents. Reply with the rewritten "
    "query only — no quotes, no explanation. If the question is already "
    "self-contained, return it unchanged."
)


async def recent_exchanges(
    db: AsyncSession, thread_id: uuid.UUID, limit: int = _HISTORY_TURNS
) -> list[QueryLog]:
    """Latest exchanges in the thread, oldest first."""
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.thread_id == thread_id)
        .order_by(desc(QueryLog.created_at))
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


def _heuristic(history: list[QueryLog], query: str) -> str:
    """Offline fallback: short follow-ups borrow the previous question's words."""
    if len(query.split()) > _FOLLOWUP_MAX_WORDS:
        return query
    previous = history[-1].query
    return f"{previous} {query}"


async def condense_query(
    db: AsyncSession, thread_id: uuid.UUID, query: str, llm: LLMProvider | None
) -> str:
    """A standalone version of `query`, given the thread so far."""
    history = await recent_exchanges(db, thread_id)
    if not history:
        return query

    if llm is None:
        return _heuristic(history, query)

    lines: list[str] = []
    for log in history:
        lines.append(f"User: {log.query}")
        if log.answer:
            lines.append(f"Assistant: {log.answer}")
    prompt = "\n".join(lines) + f"\n\nFollow-up question: {query}"

    try:
        result = await llm.complete(
            CompletionRequest(
                system=_REWRITE_SYSTEM, user=prompt, temperature=0.0, max_tokens=_REWRITE_MAX_TOKENS
            )
        )
        rewritten = (result.text or "").strip().strip('"')
    except Exception as exc:  # provider errors must never break the question
        logger.warning("condense_failed", error=str(exc))
        return _heuristic(history, query)

    if not rewritten or len(rewritten) > 2000:
        return _heuristic(history, query)
    logger.info("query_condensed", original=query, rewritten=rewritten)
    return rewritten
