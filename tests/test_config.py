"""Application settings."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings


def test_explicit_values_override_environment() -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@h/db", brand="acme")
    assert settings.database_url.endswith("/db")
    assert settings.brand == "acme"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_effective_app_database_url_prefers_restricted_role() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://owner:x@h/db",
        app_database_url="postgresql+asyncpg://app:x@h/db",
    )
    assert settings.effective_app_database_url == "postgresql+asyncpg://app:x@h/db"


@pytest.mark.parametrize("environment", ["development", "test"])
def test_effective_app_database_url_falls_back_in_dev_and_test(environment: str) -> None:
    settings = Settings(environment=environment, database_url="postgresql+asyncpg://owner:x@h/db")
    assert settings.effective_app_database_url == "postgresql+asyncpg://owner:x@h/db"


def test_effective_app_database_url_fails_closed_in_production() -> None:
    prod = Settings(environment="production", database_url="postgresql+asyncpg://owner:x@h/db")
    with pytest.raises(ValueError, match="APP_DATABASE_URL"):
        _ = prod.effective_app_database_url
