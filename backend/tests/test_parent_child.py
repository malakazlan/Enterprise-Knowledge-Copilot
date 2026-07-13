"""Tests for parent-child retrieval (neighbour expansion)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.services.generation.service import GenerationService
from app.services.profiles.loader import get_profile
from app.services.retrieval.service import RetrievalService

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

# Three paragraphs padded past chunk_size (1200 chars) so each becomes its
# own chunk instead of packing together.
_PAD = "Additional unrelated filler text keeps this paragraph long enough. " * 16
DOC = (
    "Section one covers general site conduct and daily briefings. " + _PAD + "\n\n"
    "The gamma clearance badge unlocks the server room. " + _PAD + "\n\n"
    "Badge holders must renew certification every ninety days. " + _PAD
).encode()


async def _setup(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> dict[str, str]:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    upload = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("badges.txt", DOC, "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    chunks = (
        await client.get(
            f"/api/v1/documents/{upload.json()['document']['id']}/chunks", headers=headers
        )
    ).json()
    assert len(chunks) >= 3, f"expected the paragraphs to chunk apart, got {len(chunks)}"
    return headers


async def test_generation_sees_neighbor_context(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    await _setup(client, make_user, auth_headers)

    profile = get_profile("general")
    search = await RetrievalService(db_session).search("gamma clearance badge", profile, top_k=1)
    (hit,) = search.results
    assert "gamma clearance" in hit.content

    from app.services.retrieval.expand import expand_neighbors

    await expand_neighbors(db_session, search.results)
    assert hit.expanded_content is not None
    # The window includes both neighbours; the precise match is unchanged.
    assert "ninety days" in hit.expanded_content
    assert "site conduct" in hit.expanded_content
    assert "ninety days" not in hit.content


async def test_neighbor_context_changes_answers(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    db_session: AsyncSession,
) -> None:
    """The renewal detail lives ONLY in the neighbour of the matching chunk."""
    await _setup(client, make_user, auth_headers)
    base = get_profile("general")

    # This query matches ONLY the gamma-badge chunk (top_k=1); the renewal
    # rule lives in its neighbour, so only expansion can surface it.
    question = "What does the gamma clearance badge unlock?"
    service = GenerationService(db_session)
    expanded = await service.answer(question, base, top_k=1)
    assert expanded.answered, expanded.refusal_reason
    assert "server room" in (expanded.answer or "")
    assert "ninety days" in (expanded.answer or "")

    disabled = base.model_copy(
        update={"generation": base.generation.model_copy(update={"neighbor_context": False})}
    )
    narrow = await service.answer(question, disabled, top_k=1)
    assert "server room" in (narrow.answer or "")
    assert "ninety days" not in (narrow.answer or "")
