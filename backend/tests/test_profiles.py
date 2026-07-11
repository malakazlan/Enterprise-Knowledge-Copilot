"""Tests for profile schema validation, pack loading, and the profiles API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.exceptions import NotFoundError
from app.models.user import User
from app.services.profiles.loader import DEFAULT_PROFILE, get_profile, load_profiles
from app.services.profiles.schema import ChunkingConfig, GenerationConfig, RagProfile

PROFILES = "/api/v1/profiles"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

EXPECTED_PACKS = {
    "general",
    "legal",
    "finance",
    "healthcare",
    "government",
    "manufacturing",
    "insurance",
}


# --- schema validation ---


def test_chunk_overlap_must_be_below_size() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(chunk_size=200, chunk_overlap=200)


def test_refuse_threshold_cannot_exceed_review_threshold() -> None:
    with pytest.raises(ValidationError):
        GenerationConfig(confidence_threshold_review=0.3, confidence_threshold_refuse=0.6)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RagProfile.model_validate(
            {"name": "x", "display_name": "X", "description": "d", "unknown_knob": 1}
        )


# --- pack loading ---


def test_all_packs_load_and_validate() -> None:
    profiles = load_profiles()
    assert EXPECTED_PACKS <= set(profiles)
    assert DEFAULT_PROFILE in profiles


def test_pack_invariants_hold() -> None:
    for profile in load_profiles().values():
        gen = profile.generation
        assert gen.confidence_threshold_refuse <= gen.confidence_threshold_review
        assert profile.chunking.chunk_overlap < profile.chunking.chunk_size
        assert gen.citations_required, "every shipped pack must require citations"


def test_get_unknown_profile_raises() -> None:
    with pytest.raises(NotFoundError):
        get_profile("does-not-exist")


def test_government_pack_defaults_to_local_providers() -> None:
    profile = get_profile("government")
    assert profile.providers.parser == "local"
    assert profile.providers.llm == "local"


# --- API ---


async def test_profiles_require_auth(client: AsyncClient) -> None:
    assert (await client.get(PROFILES)).status_code == 401


async def test_list_profiles_endpoint(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("reader@example.com")
    headers = await auth_headers("reader@example.com")
    resp = await client.get(PROFILES, headers=headers)
    assert resp.status_code == 200
    names = {profile["name"] for profile in resp.json()}
    assert EXPECTED_PACKS <= names


async def test_get_profile_endpoint(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("reader@example.com")
    headers = await auth_headers("reader@example.com")
    resp = await client.get(f"{PROFILES}/legal", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["generation"]["temperature"] == 0.0
    assert body["generation"]["citations_required"] is True

    missing = await client.get(f"{PROFILES}/nope", headers=headers)
    assert missing.status_code == 404
