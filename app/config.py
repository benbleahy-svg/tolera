"""Application settings (pydantic-settings).

Per the M0.0 runbook, configuration is loaded from the environment (and a local,
gitignored ``.env`` for dev) — *not* Infisical (see DECISIONS.md, 2026-06-23).
Real environment variables take precedence over ``.env`` so Docker Compose / CI
can override without editing files.

M0.1 only needs ``database_url`` + ``redis_url``; auth/LLM/mail settings land in
later blocks, so every non-infra field has a safe default and the app boots
without them.

M0.2 adds the tenancy spine: ``app_database_url`` (the restricted, ``NOBYPASSRLS``
role the app serves requests as — distinct from the owner role that runs
migrations; see DECISIONS.md 2026-06-24 "RLS enforcement mechanism + DB role
split") and the Clerk session-auth settings (DECISIONS.md "Login type / auth
flow"; "Org identity model — Clerk native Organizations").
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
    # ``database_url`` connects as the OWNER role (runs migrations / DDL).
    database_url: str = "postgresql+asyncpg://tolera:tolera@localhost:5432/tolera"
    redis_url: str = "redis://localhost:6379/0"

    # --- Tenancy (M0.2) ---
    # The app serves requests as a restricted, NOBYPASSRLS role so Postgres RLS
    # is actually enforced (the owner/superuser would bypass it). Falls back to
    # ``database_url`` only when unset — set it in every real deployment.
    app_database_url: str | None = None

    # --- Auth / Clerk (M0.2) ---
    # Session JWTs are RS256, verified against Clerk's JWKS. Empty by default so
    # the app still boots locally / in tests (where ``get_principal`` is
    # dependency-overridden and never calls Clerk).
    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_jwt_issuer: str = ""
    clerk_jwks_url: str = ""
    # Optional comma-separated list of accepted `azp` (authorized-party) values.
    # Clerk session tokens are audience-less; when set, the token's `azp` must
    # match one of these (defence against tokens minted for another app).
    clerk_authorized_parties: str = ""

    @property
    def effective_app_database_url(self) -> str:
        """The DSN the request-serving engine connects with (restricted role).

        Fails closed: outside dev/test the restricted ``app_database_url`` MUST be
        set, so a misconfiguration can't silently fall back to the owner DSN and
        bypass RLS (which would expose every org's data).
        """
        if self.app_database_url:
            return self.app_database_url
        if self.environment.lower() in {"development", "test"}:
            return self.database_url
        raise ValueError(
            "APP_DATABASE_URL must be set outside development/test — the app must "
            "connect as the restricted, RLS-bound role, never the owner."
        )

    @property
    def clerk_authorized_party_set(self) -> frozenset[str]:
        """Parsed, non-empty ``azp`` allow-list (empty → no azp check)."""
        return frozenset(p.strip() for p in self.clerk_authorized_parties.split(",") if p.strip())

    # --- Branding (parameterised from day one — DECISIONS: Product name and domain) ---
    brand: str = "tolera"
    default_locale: str = "de-DE"
    app_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
