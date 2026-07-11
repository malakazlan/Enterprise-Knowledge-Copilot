"""Read-only access to the built-in domain profile packs."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal
from app.services.profiles.loader import get_profile, list_profiles
from app.services.profiles.schema import RagProfile

router = APIRouter(tags=["profiles"])


@router.get("", response_model=list[RagProfile], summary="List available domain profiles")
async def list_domain_profiles(_principal: CurrentPrincipal) -> list[RagProfile]:
    return list_profiles()


@router.get("/{name}", response_model=RagProfile, summary="Get one domain profile")
async def get_domain_profile(_principal: CurrentPrincipal, name: str) -> RagProfile:
    return get_profile(name)
