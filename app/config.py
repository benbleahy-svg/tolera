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
        """Parsed ``azp`` allow-list. Required outside dev/test (fails closed): an
        empty list there would skip ``azp`` validation and accept same-issuer
        tokens minted for a different frontend under the same Clerk tenant."""
        parties = frozenset(
            p.strip() for p in self.clerk_authorized_parties.split(",") if p.strip()
        )
        if not parties and self.environment.lower() not in {"development", "test"}:
            raise ValueError("CLERK_AUTHORIZED_PARTIES must be set outside development/test.")
        return parties

    # --- Object storage (M1.2 — DECISIONS.md 2026-06-25) ---
    # ``memory`` is the default so the app boots and round-trips a file with no
    # external dependency (used by tests + a bare local run). docker-compose sets
    # ``s3`` against MinIO; production sets ``s3`` against an EU-resident bucket
    # (provider still OPEN — EU data residency).
    storage_backend: str = "memory"  # "memory" | "s3"
    s3_endpoint: str = ""  # e.g. http://minio:9000 (blank = AWS default endpoint)
    # No default bucket — an S3 deploy that forgets S3_BUCKET must fail closed
    # (validate_storage), not silently write customer files to a fallback bucket.
    s3_bucket: str = ""
    s3_region: str = "eu-central-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    # Max upload size — spec ``#viewer3d-limits`` reconciles PP's 150/250 MB
    # conflict to 200 (DECISIONS.md 2026-06-25).
    max_upload_mb: int = 200

    @property
    def max_upload_bytes(self) -> int:
        """The upload size cap in bytes."""
        return self.max_upload_mb * 1024 * 1024

    def validate_storage(self) -> None:
        """Fail closed: the S3 backend must be configured outside dev/test, so a
        misconfigured prod deploy can't silently fall back / lose customer files."""
        if self.storage_backend not in {"memory", "s3"}:
            raise ValueError(
                f"STORAGE_BACKEND must be 'memory' or 's3', got {self.storage_backend!r}"
            )
        if self.max_upload_mb <= 0:
            raise ValueError(f"MAX_UPLOAD_MB must be positive, got {self.max_upload_mb}.")
        is_dev = self.environment.lower() in {"development", "test"}
        if self.storage_backend == "memory" and not is_dev:
            raise ValueError("STORAGE_BACKEND=memory is not allowed outside development/test.")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET must be set when STORAGE_BACKEND=s3.")

    # --- Lens / AI (M3.1 — spec #lens-models, #ai-settings) ---
    # Provider is configurable, never hard-coded (build-plan M3.1 Decisions).
    # v1 = "anthropic": the Claude API under a zero-data-retention agreement
    # (spec #ai-settings). The model is PINNED (M3 test plan: pinned model +
    # versioned prompts); claude-opus-4-8 — Fable-tier is excluded because it
    # is unavailable under zero data retention. Key is empty by default: the
    # gating tests mock the provider, live extraction requires it in .env.
    lens_provider: str = "anthropic"
    lens_model: str = "claude-opus-4-8"
    anthropic_api_key: str = ""
    # Inference-region routing for the DPA default path (DACH delta). Passed
    # through as the API's `inference_geo`; empty = provider default. The API
    # accepts only "us" | "global" today (no EU geo yet — verified 2026-07-15;
    # DECISIONS.md), so the GDPR basis is the zero-data-retention DPA (spec
    # #ai-settings) and this stays the seam to flip when an EU geo ships.
    lens_inference_geo: str = ""

    # --- Email ingest / Mailgun EU (M3.3 — spec #email-connectivity; M0.0 §5) ---
    # Only the inbound-webhook signing key is needed here: Mailgun is retained
    # for inbound RFQ forwarding only ({org-slug}@rfq.tolera.eu → webhook →
    # auto-quote); outbound goes through the user's own mailbox (M3.5). Empty
    # default so the app boots without it — the webhook itself FAILS CLOSED
    # (503) when the key is unset, in every environment: an unauthenticated
    # ingest endpoint must never accept unsigned posts (the validate_storage /
    # clerk_authorized_party_set fail-closed precedent).
    mailgun_webhook_signing_key: str = ""

    # --- Email connectivity / two-way threading (M3.5 — spec #email-connectivity) ---
    # AES-256-GCM key for credentials at rest: 64 hex chars (32 bytes).
    # Delivered as env (Infisical in prod — spec build notes); empty default =
    # the connections API FAILS CLOSED (503), never plaintext storage.
    email_credentials_key: str = ""
    # OAuth app registrations (spec build notes: registered on day one; Gmail
    # ships behind Google's pending-verification warning — DECISIONS.md
    # 2026-06-14). Empty = that provider's connect button reports
    # "not configured"; SMTP/IMAP and CI mocks work without them.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    ms_oauth_client_id: str = ""
    ms_oauth_client_secret: str = ""
    ms_oauth_tenant: str = "common"
    # Inbound sync cadence (spec: "Celery task every 5 min").
    email_sync_interval_seconds: int = 300

    # --- Branding (parameterised from day one — DECISIONS: Product name and domain) ---
    brand: str = "tolera"
    default_locale: str = "de-DE"
    app_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
