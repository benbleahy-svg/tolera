"""Vendor RFQ batch-send (M6.4) — batch lifecycle, the vendor link, Buy mode and the
calc-vs-override outside-service cost pair.

M6.2 built the RFQ *substrate* (batch → line → recipient → response) with fixtures as
its only writer and M6.3 added the ``Vendor`` directory. This migration adds what the
compose modal actually needs to create batches for real (spec ``#vendor-rfq`` →
"Batch send modal" + "Build implications"):

* ``vendor_rfq.status`` ``ENUM(open|closed|cancelled)`` — the spec's batch lifecycle.
  Only ``open`` batches feed the "Awaiting N vendor response(s)" chip, the
  workflow-advance soft warning and the directory's Active-RFQ count.
* ``vendor_rfq.created_by`` — the composing estimator, pinned to a membership of this
  org by a composite FK (the ``quote.estimator_id`` precedent, M1.4).
* ``vendor_rfq_counter`` — the per-org atomic ``number`` allocator M6.2 explicitly left
  to "the block that creates batches for real" (mirrors ``quote_counter``, 0008).
* ``vendor_rfq_recipient.vendor_id`` / ``vendor_contact_id`` / ``sent_at`` — the link
  to the M6.3 directory that the M6.3 merge note assigned to this block. Nullable by
  design: ``vendor_name``/``contact_email`` stay the send-time *snapshot* so renaming or
  archiving a vendor never rewrites RFQ history.
* ``vendor_rfq_response.applied_at`` — written by **M6.6**'s Apply, *read* here as the
  top two vendor-ranking signals ("most recent accepted response", then "historical
  acceptance rate"). Uniformly NULL until then; ranking degrades to capability match.
* ``quote_item.costing_mode`` ``ENUM(make|buy)`` — part-level Buy mode. ``buy`` disables
  internal costing for the line; the vendor's price becomes its cost.
* ``component_quantity.calc_outside_cost`` + ``manual_outside_cost`` — the
  calc-vs-override pair behind the existing ``outside_cost``, which becomes the
  *resolved* ``COALESCE(manual, calc)`` value every downstream reader already uses
  (CLAUDE.md §5: persist both; a reprice never destroys human input). ``manual_`` is
  where M6.6's Apply writes the accepted vendor price, and the only cost source a
  Buy-mode line has. Existing rows are backfilled ``calc_ := outside_cost`` so the
  invariant holds from the first migration onward without a reprice.

Money stays ``numeric(14,4)`` at the same scale as the sibling cost cells (DECISIONS.md
2026-06-27 / M1.7). Reversible: ``downgrade`` drops every added column, the counter
table and both enum types.

Revision ID: 0052_vendor_rfq_batch_send
Revises: 0051_vendor_library
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0052_vendor_rfq_batch_send"
down_revision: str | None = "0051_vendor_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    # --- batch lifecycle + author ------------------------------------------
    op.execute("CREATE TYPE vendor_rfq_status AS ENUM ('open', 'closed', 'cancelled')")
    op.execute(
        "ALTER TABLE vendor_rfq "
        "ADD COLUMN status vendor_rfq_status NOT NULL DEFAULT 'open', "
        "ADD COLUMN created_by uuid, "
        "ADD CONSTRAINT fk_vendor_rfq_created_by_membership FOREIGN KEY (created_by, org_id) "
        "REFERENCES user_org_membership (user_id, org_id)"
    )
    op.execute("CREATE INDEX ix_vendor_rfq_org_status ON vendor_rfq (org_id, status)")

    # --- per-org RFQ number allocator (mirrors quote_counter, 0008) ---------
    # ``last_number`` = last assigned number (0 ⇒ the first batch gets 1). Not
    # org-scoped by RLS: it is a bare counter with no tenant data, keyed by org_id
    # like ``quote_counter``, and the upsert row-locks so concurrent sends serialise.
    op.execute(
        """
        CREATE TABLE vendor_rfq_counter (
            org_id uuid PRIMARY KEY REFERENCES organization(id),
            last_number bigint NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON vendor_rfq_counter TO {APP_ROLE}")

    # --- recipient → directory link ----------------------------------------
    # ``vendor_contact`` has no composite-FK target yet (M6.3 needed none); add the
    # house-pattern ``(org_id, id)`` unique so the recipient FK can pin same-org.
    op.execute(
        "ALTER TABLE vendor_contact ADD CONSTRAINT uq_vendor_contact_org_id_id UNIQUE (org_id, id)"
    )
    op.execute(
        "ALTER TABLE vendor_rfq_recipient "
        "ADD COLUMN vendor_id uuid, "
        "ADD COLUMN vendor_contact_id uuid, "
        "ADD COLUMN sent_at timestamptz, "
        "ADD CONSTRAINT fk_vendor_rfq_recipient_vendor_org FOREIGN KEY (org_id, vendor_id) "
        "REFERENCES vendor (org_id, id), "
        "ADD CONSTRAINT fk_vendor_rfq_recipient_contact_org "
        "FOREIGN KEY (org_id, vendor_contact_id) REFERENCES vendor_contact (org_id, id)"
    )
    op.execute(
        "CREATE INDEX ix_vendor_rfq_recipient_org_vendor "
        "ON vendor_rfq_recipient (org_id, vendor_id)"
    )

    # --- acceptance signal the ranking reads (M6.6 writes it) ---------------
    op.execute("ALTER TABLE vendor_rfq_response ADD COLUMN applied_at timestamptz")

    # --- Buy mode -----------------------------------------------------------
    op.execute("CREATE TYPE costing_mode AS ENUM ('make', 'buy')")
    op.execute(
        "ALTER TABLE quote_item ADD COLUMN costing_mode costing_mode NOT NULL DEFAULT 'make'"
    )

    # --- outside-service calc-vs-override pair ------------------------------
    op.execute(
        "ALTER TABLE component_quantity "
        "ADD COLUMN calc_outside_cost numeric(14,4), "
        "ADD COLUMN manual_outside_cost numeric(14,4)"
    )
    # Existing rows: today's ``outside_cost`` is purely computed, so it *is* the calc
    # side. Backfill it so ``outside_cost = COALESCE(manual, calc)`` holds immediately
    # rather than only after the next reprice.
    op.execute("UPDATE component_quantity SET calc_outside_cost = outside_cost")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE component_quantity "
        "DROP COLUMN IF EXISTS manual_outside_cost, "
        "DROP COLUMN IF EXISTS calc_outside_cost"
    )
    op.execute("ALTER TABLE quote_item DROP COLUMN IF EXISTS costing_mode")
    op.execute("DROP TYPE IF EXISTS costing_mode")
    op.execute("ALTER TABLE vendor_rfq_response DROP COLUMN IF EXISTS applied_at")
    op.execute("DROP INDEX IF EXISTS ix_vendor_rfq_recipient_org_vendor")
    op.execute(
        "ALTER TABLE vendor_rfq_recipient "
        "DROP CONSTRAINT IF EXISTS fk_vendor_rfq_recipient_contact_org, "
        "DROP CONSTRAINT IF EXISTS fk_vendor_rfq_recipient_vendor_org, "
        "DROP COLUMN IF EXISTS sent_at, "
        "DROP COLUMN IF EXISTS vendor_contact_id, "
        "DROP COLUMN IF EXISTS vendor_id"
    )
    op.execute("ALTER TABLE vendor_contact DROP CONSTRAINT IF EXISTS uq_vendor_contact_org_id_id")
    op.execute("DROP TABLE IF EXISTS vendor_rfq_counter")
    op.execute("DROP INDEX IF EXISTS ix_vendor_rfq_org_status")
    op.execute(
        "ALTER TABLE vendor_rfq "
        "DROP CONSTRAINT IF EXISTS fk_vendor_rfq_created_by_membership, "
        "DROP COLUMN IF EXISTS created_by, "
        "DROP COLUMN IF EXISTS status"
    )
    op.execute("DROP TYPE IF EXISTS vendor_rfq_status")
