"""Vendor RFQ portal (M6.2) — the RFQ batch/recipient/response tables and the
``quote_token.vendor_rfq_recipient_id`` scoping column.

Spec ``#vendor-rfq``: an unauthenticated vendor opens ``/vendor-rfq/:token``, sees the
parts table for **exactly its RFQ batch**, fills the per-line response form and submits.
Six tables carry that, and none existed:

* ``vendor_rfq`` — the batch (quote + soft ``need_by_date`` + message + per-org
  ``number``). The batch, not the quote, is the unit of vendor scoping.
* ``vendor_rfq_line`` — the quote items in the batch, with the vendor-facing note.
* ``vendor_rfq_recipient`` — one row per vendor on the batch. Sends are blind (one
  token per recipient), so a vendor can never enumerate the others. No ``vendor_id``
  column: the ``Vendor`` table is M6.3's and the M1.4 precedent forbids a speculative
  column without a FK target — company/contact are denormalised until then.
* ``vendor_rfq_response`` (one per recipient, re-submit updates in place) +
  ``vendor_rfq_response_line`` (``cannot_quote`` = partial response) +
  ``vendor_rfq_response_price`` (per quantity break: ``numeric(14,4)`` unit price at the
  same scale as ``component_quantity``'s cost cells, where M6.6's Apply writes it, plus
  lead-time days). Currency lives on the response — a DACH vendor may quote EUR or CHF.

``quote_token.vendor_rfq_recipient_id`` is the column M5.1 deliberately deferred "to M6
with its target table"; that table now exists, so it lands here with a composite
same-org FK. The ``quote_token_scope`` enum already carries ``'vendor_rfq'`` (0040) —
no enum change is needed. ``quote_token.quote_id`` is already nullable, which is what a
recipient-scoped token needs.

**No hard expiry** is introduced: the M5.1 decision (JWT without ``exp``; the row's
``revoked_at`` is the authority) is what the spec's "portal never shows a hard closed
state / late submit allowed" requires, so it carries to the vendor scope unchanged.

Every table is org-scoped with the standard ``org_isolation`` RLS policy and the
``tolera_app`` grants. Reversible (CLAUDE.md §5): ``downgrade`` drops the column and all
six tables in FK order.

Revision ID: 0050_vendor_rfq
Revises: 0049_dashboard_work_queue
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0050_vendor_rfq"
down_revision: str | None = "0049_dashboard_work_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

#: Every vendor-RFQ table is a plain org-scoped tenant table — same grants + policy.
_TABLES = (
    "vendor_rfq",
    "vendor_rfq_line",
    "vendor_rfq_recipient",
    "vendor_rfq_response",
    "vendor_rfq_response_line",
    "vendor_rfq_response_price",
)


def _secure(table: str) -> None:
    """Grant the app role DML and force the org-isolation RLS policy on ``table``."""
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY org_isolation ON {table}
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def upgrade() -> None:
    # --- the batch ---
    op.execute(
        """
        CREATE TABLE vendor_rfq (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_id uuid NOT NULL,
            number text NOT NULL,
            need_by_date date,
            message text,
            sent_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_vendor_rfq_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_vendor_rfq_org_number UNIQUE (org_id, number),
            CONSTRAINT fk_vendor_rfq_quote_org FOREIGN KEY (org_id, quote_id)
                REFERENCES quote (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_vendor_rfq_org_quote ON vendor_rfq (org_id, quote_id)")
    _secure("vendor_rfq")

    # --- lines of the batch ---
    op.execute(
        """
        CREATE TABLE vendor_rfq_line (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            rfq_id uuid NOT NULL,
            quote_item_id uuid NOT NULL,
            position integer NOT NULL DEFAULT 0,
            estimator_notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_vendor_rfq_line_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_vendor_rfq_line_rfq_item UNIQUE (rfq_id, quote_item_id),
            CONSTRAINT fk_vendor_rfq_line_rfq_org FOREIGN KEY (org_id, rfq_id)
                REFERENCES vendor_rfq (org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_vendor_rfq_line_item_org FOREIGN KEY (org_id, quote_item_id)
                REFERENCES quote_item (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_vendor_rfq_line_org_rfq ON vendor_rfq_line (org_id, rfq_id)")
    _secure("vendor_rfq_line")

    # --- one vendor on the batch (the token's scope target) ---
    op.execute(
        """
        CREATE TABLE vendor_rfq_recipient (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            rfq_id uuid NOT NULL,
            vendor_name text NOT NULL,
            contact_email text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_vendor_rfq_recipient_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_vendor_rfq_recipient_rfq_org FOREIGN KEY (org_id, rfq_id)
                REFERENCES vendor_rfq (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_vendor_rfq_recipient_org_rfq ON vendor_rfq_recipient (org_id, rfq_id)"
    )
    _secure("vendor_rfq_recipient")

    # --- the submission (one per recipient; a re-submit updates it) ---
    op.execute(
        """
        CREATE TABLE vendor_rfq_response (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            recipient_id uuid NOT NULL,
            source text NOT NULL DEFAULT 'portal',
            currency char(3) NOT NULL DEFAULT 'EUR',
            valid_until date,
            notes text,
            attachment_object_key text,
            attachment_filename text,
            attachment_size_bytes bigint,
            attachment_content_type text,
            is_late boolean NOT NULL DEFAULT false,
            submitted_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_vendor_rfq_response_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_vendor_rfq_response_recipient UNIQUE (recipient_id),
            CONSTRAINT ck_vendor_rfq_response_attachment_size_nonneg
                CHECK (attachment_size_bytes IS NULL OR attachment_size_bytes >= 0),
            CONSTRAINT fk_vendor_rfq_response_recipient_org FOREIGN KEY (org_id, recipient_id)
                REFERENCES vendor_rfq_recipient (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_vendor_rfq_response_org_recipient "
        "ON vendor_rfq_response (org_id, recipient_id)"
    )
    _secure("vendor_rfq_response")

    # --- per-line answer (cannot_quote = partial response) ---
    op.execute(
        """
        CREATE TABLE vendor_rfq_response_line (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            response_id uuid NOT NULL,
            rfq_line_id uuid NOT NULL,
            cannot_quote boolean NOT NULL DEFAULT false,
            notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_vendor_rfq_response_line_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_vendor_rfq_response_line_response_line UNIQUE (response_id, rfq_line_id),
            CONSTRAINT fk_vendor_rfq_response_line_response_org FOREIGN KEY (org_id, response_id)
                REFERENCES vendor_rfq_response (org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_vendor_rfq_response_line_line_org FOREIGN KEY (org_id, rfq_line_id)
                REFERENCES vendor_rfq_line (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_vendor_rfq_response_line_org_response "
        "ON vendor_rfq_response_line (org_id, response_id)"
    )
    _secure("vendor_rfq_response_line")

    # --- per quantity break: unit price + lead time ---
    op.execute(
        """
        CREATE TABLE vendor_rfq_response_price (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            response_line_id uuid NOT NULL,
            quantity integer NOT NULL,
            unit_price numeric(14, 4),
            lead_time_days integer,
            CONSTRAINT uq_vendor_rfq_response_price_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_vendor_rfq_response_price_line_qty UNIQUE (response_line_id, quantity),
            CONSTRAINT ck_vendor_rfq_response_price_qty_positive CHECK (quantity > 0),
            CONSTRAINT ck_vendor_rfq_response_price_nonneg
                CHECK (unit_price IS NULL OR unit_price >= 0),
            CONSTRAINT ck_vendor_rfq_response_price_lead_nonneg
                CHECK (lead_time_days IS NULL OR lead_time_days >= 0),
            CONSTRAINT fk_vendor_rfq_response_price_line_org FOREIGN KEY (org_id, response_line_id)
                REFERENCES vendor_rfq_response_line (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_vendor_rfq_response_price_org_line "
        "ON vendor_rfq_response_price (org_id, response_line_id)"
    )
    _secure("vendor_rfq_response_price")

    # --- the deferred token column, now that its FK target exists ---
    op.execute("ALTER TABLE quote_token ADD COLUMN vendor_rfq_recipient_id uuid")
    op.execute(
        """
        ALTER TABLE quote_token
            ADD CONSTRAINT fk_quote_token_vendor_rfq_recipient_org
            FOREIGN KEY (org_id, vendor_rfq_recipient_id)
            REFERENCES vendor_rfq_recipient (org_id, id) ON DELETE CASCADE
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE quote_token DROP CONSTRAINT IF EXISTS fk_quote_token_vendor_rfq_recipient_org"
    )
    op.execute("ALTER TABLE quote_token DROP COLUMN IF EXISTS vendor_rfq_recipient_id")
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
