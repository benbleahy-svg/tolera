"""Email-template composer schema + domain-event outbox (M5.5).

Extends the M1.12 ``email_template`` into the spec's per-type Email Templates
(``#settings``, DemoH 08): a ``template_type`` family (quote_send / order_shipment
/ order_refund), a display ``name``, an ``is_default`` flag (at most one per type +
locale), and ``last_edited_by``. The legacy ``key`` becomes nullable provenance;
existing rows backfill to ``quote_send`` and the ``quote_sent``-keyed row per org
becomes that type's default.

Adds ``domain_event`` — the org-scoped outbox the send-quote composer writes
``quote.sent`` onto in the same transaction as the Sent transition (the durable
seam M3.5 deferred to M5). Webhook delivery off it is M6.

Revision ID: 0043_email_composer
Revises: 0042_pdf_branding
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0043_email_composer"
down_revision: str | None = "0042_pdf_branding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    # --- email_template: per-type + default + audit --------------------------
    op.execute(
        "CREATE TYPE email_template_type AS ENUM ('quote_send', 'order_shipment', 'order_refund')"
    )
    # Add with a server default (matches the model's ``server_default``) so existing
    # rows are non-null immediately and an insert omitting template_type still works;
    # the explicit backfill below stays for clarity, then the column is tightened.
    op.execute(
        "ALTER TABLE email_template "
        "ADD COLUMN template_type email_template_type NOT NULL DEFAULT 'quote_send'"
    )
    op.execute("ALTER TABLE email_template ADD COLUMN name text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE email_template ADD COLUMN is_default boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE email_template ADD COLUMN last_edited_by uuid")

    # Backfill: every M1.12 row is a quote-send template (the column's default
    # already set that); name from the legacy key; the canonical quote-send seed row
    # becomes its type's default.
    op.execute(
        "UPDATE email_template SET name = key WHERE (name = '' OR name IS NULL) AND key IS NOT NULL"
    )
    op.execute("UPDATE email_template SET is_default = true WHERE key = 'quote_sent'")

    # Relabel the M1.12 Jinja placeholder to the M5.5 %%…%% syntax the composer's
    # renderer understands — else a pre-existing default would send the literal
    # ``{{quote_number}}`` to the customer (the placeholder-leak the design forbids).
    op.execute(
        "UPDATE email_template SET "
        "subject = replace(subject, '{{quote_number}}', '%%QUOTE_NUMBER%%'), "
        "body = replace(body, '{{quote_number}}', '%%QUOTE_NUMBER%%')"
    )

    # key is now optional provenance (new templates are keyless).
    op.execute("ALTER TABLE email_template ALTER COLUMN key DROP NOT NULL")
    # Replace the old one-per-key uniqueness with one-DEFAULT-per-type.
    op.execute(
        "ALTER TABLE email_template DROP CONSTRAINT IF EXISTS uq_email_template_org_key_locale"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_email_template_default_per_type "
        "ON email_template (org_id, template_type, locale) WHERE is_default"
    )

    # --- domain_event outbox -------------------------------------------------
    op.execute(
        """
        CREATE TABLE domain_event (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            event_type text NOT NULL,
            payload jsonb NOT NULL,
            delivered_at timestamptz,
            occurred_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_domain_event_org_type ON domain_event (org_id, event_type, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_domain_event_undelivered ON domain_event (org_id, occurred_at) "
        "WHERE delivered_at IS NULL"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON domain_event TO {APP_ROLE}")
    op.execute("ALTER TABLE domain_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE domain_event FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON domain_event
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON domain_event")
    op.execute(f"REVOKE ALL ON domain_event FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS domain_event")

    # Reverse the %%…%% relabel so the prior app sees its Jinja placeholder again.
    op.execute(
        "UPDATE email_template SET "
        "subject = replace(subject, '%%QUOTE_NUMBER%%', '{{quote_number}}'), "
        "body = replace(body, '%%QUOTE_NUMBER%%', '{{quote_number}}')"
    )
    op.execute("DROP INDEX IF EXISTS uq_email_template_default_per_type")
    # Restore a non-null, *unique* key before re-imposing the old (org,key,locale)
    # unique — the feature allows many templates per type, so a bare
    # ``template_type`` key would collide; qualify keyless rows by id.
    op.execute(
        "UPDATE email_template SET key = template_type::text || ':' || id::text WHERE key IS NULL"
    )
    op.execute("ALTER TABLE email_template ALTER COLUMN key SET NOT NULL")
    op.execute(
        "ALTER TABLE email_template ADD CONSTRAINT uq_email_template_org_key_locale "
        "UNIQUE (org_id, key, locale)"
    )
    op.execute("ALTER TABLE email_template DROP COLUMN IF EXISTS last_edited_by")
    op.execute("ALTER TABLE email_template DROP COLUMN IF EXISTS is_default")
    op.execute("ALTER TABLE email_template DROP COLUMN IF EXISTS name")
    op.execute("ALTER TABLE email_template DROP COLUMN IF EXISTS template_type")
    op.execute("DROP TYPE IF EXISTS email_template_type")
