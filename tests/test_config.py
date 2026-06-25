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


# --- storage config (M1.2) ---
def test_validate_storage_memory_ok_in_test() -> None:
    Settings(environment="test", storage_backend="memory").validate_storage()  # no raise


def test_validate_storage_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        Settings(environment="test", storage_backend="disk").validate_storage()


def test_validate_storage_rejects_non_positive_upload_cap() -> None:
    for bad in (0, -1):
        with pytest.raises(ValueError, match="MAX_UPLOAD_MB"):
            Settings(environment="test", max_upload_mb=bad).validate_storage()


def test_validate_storage_s3_requires_bucket() -> None:
    # No default bucket → an S3 deploy without S3_BUCKET fails closed.
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings(environment="production", storage_backend="s3", s3_bucket="").validate_storage()
    # With a bucket it passes.
    Settings(environment="production", storage_backend="s3", s3_bucket="b").validate_storage()


def test_validate_storage_memory_forbidden_in_production() -> None:
    with pytest.raises(ValueError, match="memory"):
        Settings(environment="production", storage_backend="memory").validate_storage()
