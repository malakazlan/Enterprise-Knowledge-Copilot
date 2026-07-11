"""Loads and validates profile packs from the ``packs/`` directory.

Packs are validated eagerly and cached process-wide. A malformed pack raises at
first access with the offending file named — configuration errors must surface
loudly, never silently at query time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.core.exceptions import NotFoundError
from app.services.profiles.schema import RagProfile

_PACKS_DIR = Path(__file__).parent / "packs"
DEFAULT_PROFILE = "general"


class ProfilePackError(Exception):
    """Raised when a profile pack on disk is invalid."""


@lru_cache
def load_profiles() -> dict[str, RagProfile]:
    """Load every ``*.yaml`` pack, keyed by profile name."""
    profiles: dict[str, RagProfile] = {}
    for path in sorted(_PACKS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            profile = RagProfile.model_validate(data)
        except (yaml.YAMLError, ValidationError) as exc:
            raise ProfilePackError(f"Invalid profile pack '{path.name}': {exc}") from exc
        if profile.name != path.stem:
            raise ProfilePackError(
                f"Profile pack '{path.name}' declares name '{profile.name}'; "
                "the name must match the filename."
            )
        profiles[profile.name] = profile

    if DEFAULT_PROFILE not in profiles:
        raise ProfilePackError(f"The default profile pack '{DEFAULT_PROFILE}' is missing.")
    return profiles


def list_profiles() -> list[RagProfile]:
    return list(load_profiles().values())


def get_profile(name: str) -> RagProfile:
    profile = load_profiles().get(name)
    if profile is None:
        raise NotFoundError(f"Profile '{name}' does not exist.")
    return profile
