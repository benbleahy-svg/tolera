"""Shared test helpers."""

from __future__ import annotations

from app.config import Settings

DEFAULT_TEST_DB = "postgresql+asyncpg://tolera:tolera@localhost:5432/tolera_test"


def build_settings(
    database_url: str = DEFAULT_TEST_DB,
    app_database_url: str | None = None,
) -> Settings:
    """Construct deterministic test settings (init kwargs override any ``.env``).

    ``app_database_url`` is the restricted-role DSN the request-serving engine
    uses; when omitted the app falls back to the (owner) ``database_url``.
    """
    return Settings(
        environment="test",
        database_url=database_url,
        app_database_url=app_database_url,
        redis_url="redis://localhost:6379/15",
        log_level="INFO",
    )
