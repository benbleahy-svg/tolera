"""Application settings."""

from __future__ import annotations

from app.config import Settings, get_settings


def test_explicit_values_override_environment() -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@h/db", brand="acme")
    assert settings.database_url.endswith("/db")
    assert settings.brand == "acme"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
