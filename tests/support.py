"""Shared test helpers."""

from __future__ import annotations

from app.config import Settings

DEFAULT_TEST_DB = "postgresql+asyncpg://tolera:tolera@localhost:5432/tolera_test"


def build_settings(database_url: str = DEFAULT_TEST_DB) -> Settings:
    """Construct deterministic test settings (init kwargs override any ``.env``)."""
    return Settings(
        environment="test",
        database_url=database_url,
        redis_url="redis://localhost:6379/15",
        log_level="INFO",
    )
