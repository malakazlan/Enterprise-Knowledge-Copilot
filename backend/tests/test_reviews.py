"""Tests for the review queue and admin stats."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.querylog import QueryLog, ReviewStatus
from app.models.user import User, UserRole
from app.services.generation.llm_generator import LLMCitationGenerator
from app.services.generation.ports import CompletionRequest, CompletionResult
from app.services.generation.service import GenerationService
from app.services.profiles.loader import get_profile
from app.services.profiles.schema import RagProfile

REVIEWS = "/api/v1/reviews"
STATS = "/api/v1/admin/stats"
DOCUMENTS = "/api/v1/documents"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

SAFETY_DOC = b"# Safety\n\nAll workers must wear a helmet on the construction site."


def _paranoid_profile() -> RagProfile:
    """A profile whose review band catches every answer."""
    base = get_profile("general")
    return base.model_copy(
        update={
            "generation": base.generation.model_copy(
                update={
                    "confidence_threshold_review": 1.0,
                    "confidence_threshold_refuse": 0.0,
                }
            )
        }
    )


class _PartiallyGroundedLLM:
    """One grounded sentence, one unverifiable claim -> mid-band confidence."""

    name = "fake"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(
            text=(
                "All workers must wear a helmet on the construction site [1]. "
                "The fine for violations is exactly five hundred dollars [9]."
            )
        )


async def _flag_one_answer(
    client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
) -> QueryLog:
    upload = await client.post(
        DOCUMENTS, headers=headers, files={"file": ("safety.md", SAFETY_DOC, "text/markdown")}
    )
    assert upload.status_code == 201
    service = GenerationService(db_session, generator=LLMCitationGenerator(_PartiallyGroundedLLM()))
    outcome = await service.answer("Who must wear a helmet?", _paranoid_profile())
    assert outcome.answered and outcome.needs_review, (
        outcome.confidence,
        outcome.refusal_reason,
    )
    log = await db_session.get(QueryLog, outcome.query_id)
    assert log is not None and log.review_status is ReviewStatus.PENDING
    return log


async def test_flagged_answer_lands_in_queue_and_can_be_approved(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    reviewer = await make_user("rev@example.com", role=UserRole.REVIEWER)
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")
    rev = await auth_headers("rev@example.com")

    log = await _flag_one_answer(client, admin, db_session)

    queue = await client.get(REVIEWS, headers=rev)
    assert queue.status_code == 200
    items = queue.json()
    assert len(items) == 1
    assert items[0]["id"] == str(log.id)
    assert items[0]["review_status"] == "pending"

    resolved = await client.post(
        f"{REVIEWS}/{log.id}/resolve", headers=rev, json={"action": "approve"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["review_status"] == "approved"

    await db_session.refresh(log)
    assert log.review_status is ReviewStatus.APPROVED
    assert log.reviewed_by == reviewer.id
    assert log.reviewed_at is not None

    # Queue is empty; re-resolving conflicts.
    assert (await client.get(REVIEWS, headers=rev)).json() == []
    again = await client.post(f"{REVIEWS}/{log.id}/resolve", headers=rev, json={"action": "reject"})
    assert again.status_code == 409


async def test_reject_records_note(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")
    log = await _flag_one_answer(client, admin, db_session)

    resolved = await client.post(
        f"{REVIEWS}/{log.id}/resolve",
        headers=admin,
        json={"action": "reject", "note": "citation points at the wrong clause"},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["review_status"] == "rejected"
    assert body["review_note"] == "citation points at the wrong clause"

    rejected = await client.get(f"{REVIEWS}?status=rejected", headers=admin)
    assert len(rejected.json()) == 1


async def test_review_rbac(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("member@example.com", role=UserRole.USER)
    member = await auth_headers("member@example.com")
    assert (await client.get(REVIEWS, headers=member)).status_code == 403
    assert (await client.get(REVIEWS)).status_code == 401
    assert (await client.get(STATS, headers=member)).status_code == 403


async def test_admin_stats(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    admin = await auth_headers("admin@example.com")
    await _flag_one_answer(client, admin, db_session)

    # One refused query for the breakdown.
    refused = await client.post(
        "/api/v1/query", headers=admin, json={"query": "quantum banana smoothie recipe"}
    )
    assert refused.json()["answered"] is False

    stats = (await client.get(STATS, headers=admin)).json()
    assert stats["documents_total"] == 1
    assert stats["chunks_total"] >= 1
    assert stats["queries_total"] == 2
    assert stats["queries_answered"] == 1
    assert stats["queries_refused"] == 1
    assert stats["refusal_breakdown"] == {"insufficient_evidence": 1}
    assert stats["reviews_pending"] == 1
    assert stats["users_total"] == 1
    assert 0 < stats["avg_confidence_answered"] <= 1
