"""Email ingest → auto-quote (M3.3).

Spec ``#wingman`` (pipeline 1 · RFQ email ingest) / ``#email-connectivity``;
canonical DDL ``DB-SCHEMA.sql`` §intake (RFQ). Four pieces:

* ``request_for_quote`` — the canonical intake entity, plus the additive
  ingest columns (``email_message_id`` idempotency key, ``subject``, the
  stored raw ``.eml`` = the quote's ORIGINAL RFQ). Org-scoped with RLS.
* ``quote.email_thread_id`` — canonical column (DB-SCHEMA.sql), owned by this
  block: the inbound Message-Id that M3.5 threads replies onto.
* ``part_file.rfq_id`` — intake provenance (which RFQ a file arrived with),
  composite same-org FK; SET NULL on RFQ delete so a file outlives its intake
  record (files are the part's, the RFQ is bookkeeping).
* ``resolve_org_id_by_slug`` — a narrow SECURITY DEFINER lookup. The webhook
  authenticates by Mailgun signature, not a Clerk session, so no org GUC is
  set yet — and ``organization``'s ``org_self_isolation`` policy (0002) makes
  a pre-GUC slug lookup impossible for the restricted role. The function
  exposes exactly one thing (slug → id); every subsequent read/write runs in
  an org-scoped session. ``search_path`` is pinned (definer-function hygiene).

Revision ID: 0022_rfq_ingest
Revises: 0021_extraction_correction
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022_rfq_ingest"
down_revision: str | None = "0021_extraction_correction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE request_for_quote (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            rfq_number text,
            business_name text,
            first_name text,
            last_name text,
            email citext,
            phone text,
            description text,
            referrer text,
            marketing_source text,
            requested_delivery_date date,
            export_controlled boolean NOT NULL DEFAULT false,
            email_message_id text,
            subject text,
            eml_storage_key text,
            eml_filename text,
            eml_size_bytes bigint,
            quote_id uuid,
            processed_on timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_rfq_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_rfq_eml_size_nonneg CHECK (eml_size_bytes IS NULL OR eml_size_bytes >= 0)
        )
        """
    )
    # Converted quote must live in the SAME org (MATCH SIMPLE skips NULLs).
    op.execute(
        """
        ALTER TABLE request_for_quote
            ADD CONSTRAINT fk_rfq_quote_org
            FOREIGN KEY (org_id, quote_id) REFERENCES quote (org_id, id)
        """
    )
    # Webhook idempotency: a Mailgun retry of the same Message-Id can never
    # mint a second RFQ/quote. Partial — Smart-RFQ-form rows have no email.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_rfq_org_message_id
            ON request_for_quote (org_id, email_message_id)
            WHERE email_message_id IS NOT NULL
        """
    )
    op.execute("CREATE INDEX ix_rfq_org_created_at ON request_for_quote (org_id, created_at)")

    # Canonical quote.email_thread_id (DB-SCHEMA.sql) — M3.3 owns the add.
    op.execute("ALTER TABLE quote ADD COLUMN email_thread_id text")

    # Intake provenance on part_file; files outlive the intake record.
    op.execute("ALTER TABLE part_file ADD COLUMN rfq_id uuid")
    op.execute(
        """
        ALTER TABLE part_file
            ADD CONSTRAINT fk_part_file_rfq_org
            FOREIGN KEY (org_id, rfq_id) REFERENCES request_for_quote (org_id, id)
            ON DELETE SET NULL (rfq_id)
        """
    )
    op.execute("CREATE INDEX ix_part_file_rfq_id ON part_file (rfq_id)")

    # RLS + grants (0002/0006 pattern). No DELETE: intake rows are audit trail.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON request_for_quote TO {APP_ROLE}")
    op.execute("ALTER TABLE request_for_quote ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE request_for_quote FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON request_for_quote
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # Slug → org id for the signature-authenticated webhook (docstring above).
    # STRICT: NULL slug returns NULL without running the body.
    #
    # Threat-model note (CodeRabbit flagged the APP_ROLE grant as cross-tenant):
    # this design's RLS keys on the app-set GUC `app.current_org_id` — any
    # session holding APP_ROLE can already SET it to any org, so RLS here
    # guards against *application bugs* (a forgotten scope), not against
    # arbitrary SQL under the app role. slug→id is therefore strictly less
    # capability than the role already has; a dedicated ingest role would add
    # a second DSN/engine without moving the actual trust boundary. The
    # function stays single-purpose, PUBLIC-revoked, and returns only the id.
    op.execute(
        """
        CREATE FUNCTION resolve_org_id_by_slug(p_slug text) RETURNS uuid
            LANGUAGE sql STABLE STRICT SECURITY DEFINER
            SET search_path = public
            AS 'SELECT id FROM organization WHERE slug = p_slug'
        """
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_org_id_by_slug(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION resolve_org_id_by_slug(text) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_org_id_by_slug(text)")
    op.execute("DROP INDEX IF EXISTS ix_part_file_rfq_id")
    op.execute("ALTER TABLE part_file DROP CONSTRAINT IF EXISTS fk_part_file_rfq_org")
    op.execute("ALTER TABLE part_file DROP COLUMN IF EXISTS rfq_id")
    op.execute("ALTER TABLE quote DROP COLUMN IF EXISTS email_thread_id")
    op.execute("DROP POLICY IF EXISTS org_isolation ON request_for_quote")
    op.execute(f"REVOKE ALL ON request_for_quote FROM {APP_ROLE}")
    op.execute("DROP TABLE request_for_quote")
