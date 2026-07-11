"""Settings parsing regressions."""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_cors_origins_accepts_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: pydantic-settings JSON-decodes list fields from .env by
    # default, crashing on the documented comma-separated form.
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, http://b.example")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://a.example", "http://b.example"]


def test_cors_origins_accepts_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=None, cors_origins=["http://x.example"])
    assert settings.cors_origins == ["http://x.example"]
