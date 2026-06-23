"""Application settings (pydantic-settings).

Per the M0.0 runbook, configuration is loaded from the environment (and a local,
gitignored ``.env`` for dev) — *not* Infisical (see DECISIONS.md, 2026-06-23).
Real environment variables take precedence over ``.env`` so Docker Compose / CI
can override without editing files.

M0.1 only needs ``database_url`` + ``redis_url``; auth/LLM/mail settings land in
later blocks, so every non-infra field has a safe default and the app boots
without them.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # --- Infra (M0.1) ---
    database_url: str = "postgresql+asyncpg://tolera:tolera@localhost:5432/tolera"
    redis_url: str = "redis://localhost:6379/0"

    # --- Branding (parameterised from day one — DECISIONS: Product name and domain) ---
    brand: str = "tolera"
    default_locale: str = "de-DE"
    app_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
