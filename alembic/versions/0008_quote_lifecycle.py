"""quote lifecycle — state machine, quote_item, component stub, audit + counter (M1.4).

Extends the M1.3 ``quote`` stub into the real quoting core, all by **forward ALTER**
(never reshaping what M1.3 laid down — DECISIONS.md 2026-06-26):

  * ``quote_status`` gains ``cancelled``, ``no_quote``, ``on_hold`` (append-only ADD
    VALUE; PG16 permits this inside a transaction as the values aren't used here).
    Trash is soft-delete (``quote.deleted_at``), not a status; ``superseded`` + the
    revision flow are M5.
  * ``quote`` is **hardened**: the stub's plain global FKs (account/salesperson/
    estimator) are dropped and re-added as **composite same-org FKs** (the M1.1
    rationale — RLS scopes the row, not the FK target's org), plus a new ``contact_id``
    composite FK (``contact`` first gains ``UNIQUE (org_id, id)``). The canonical
    columns M1.4 needs are added (workflow-tracker timestamps, ``status_before_hold``,
    ``config_frozen_at`` column-only per E4-d, ``deleted_at``). Send/digital-quote
    columns + the revision flow are deferred to M5.
  * ``component`` — a **minimal stub** (Part-with-pricing) anchoring a quote item's
    root component to a Part; M1.5 extends it (process/material/BOM).
  * ``quote_item`` — the root component tied to a quote at a position, with its own
    ``qi_workflow_status``.
  * ``quote_status_event`` — append-only transition audit (SELECT/INSERT only).
  * ``quote_counter`` — per-org atomic sequential quote-number allocator.

The app role gains INSERT/UPDATE on ``quote`` (it was SELECT-only in M1.3) and the
appropriate grants on the new tables. Every new table inherits the M0.2 RLS pattern.

Revision ID: 0008_quote_lifecycle
Revises: 0007_quotes_saved_views
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_quote_lifecycle"
down_revision: str | None = "0007_quotes_saved_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
# New org-scoped tables that get the standard ENABLE/FORCE RLS + org_isolation policy.
_NEW_ORG_SCOPED_TABLES = ("component", "quote_item", "quote_status_event", "quote_counter")
# Stub FKs the M1.3 quote table created inline (auto-named) — dropped + hardened here.
_STUB_QUOTE_FKS = (
    "quote_account_id_fkey",
    "quote_salesperson_id_fkey",
    "quote_estimator_id_fkey",
)


def upgrade() -> None:
    # --- enums ---------------------------------------------------------------
    # Append the three M1.4 statuses (ADD VALUE is not used in this txn, so PG16 is
    # happy to run it transactionally). IF NOT EXISTS keeps re-runs idempotent.
    for value in ("cancelled", "no_quote", "on_hold"):
        op.execute(f"ALTER TYPE quote_status ADD VALUE IF NOT EXISTS '{value}'")
    op.execute(
        "CREATE TYPE qi_workflow_status AS ENUM "
        "('not_started', 'in_progress', 'on_hold', 'completed', 'no_quote')"
    )

    # --- contact: composite-FK target so quote.contact_id can pin same-org -----
    op.execute("ALTER TABLE contact ADD CONSTRAINT uq_contact_org_id_id UNIQUE (org_id, id)")

    # --- quote: drop stub FKs, add canonical columns, add composite same-org FKs --
    for fk in _STUB_QUOTE_FKS:
        op.execute(f"ALTER TABLE quote DROP CONSTRAINT IF EXISTS {fk}")
    op.execute(
        """
        ALTER TABLE quote
            ADD COLUMN revision bigint NOT NULL DEFAULT 0,
            ADD COLUMN status_before_hold quote_status,
            ADD COLUMN currency varchar(3) NOT NULL DEFAULT 'EUR',
            ADD COLUMN contact_id uuid,
            ADD COLUMN private_notes text,
            ADD COLUMN config_frozen_at timestamptz,
            ADD COLUMN rfq_received_date timestamptz,
            ADD COLUMN started_at timestamptz,
            ADD COLUMN sent_at timestamptz,
            ADD COLUMN expiration_date timestamptz,
            ADD COLUMN expired_at timestamptz,
            ADD COLUMN estimator_assigned_at timestamptz,
            ADD COLUMN salesperson_assigned_at timestamptz,
            ADD COLUMN deleted_at timestamptz
        """
    )
    op.execute(
        """
        ALTER TABLE quote
            ADD CONSTRAINT fk_quote_account_org
                FOREIGN KEY (org_id, account_id) REFERENCES account(org_id, id),
            ADD CONSTRAINT fk_quote_contact_org
                FOREIGN KEY (org_id, contact_id) REFERENCES contact(org_id, id),
            ADD CONSTRAINT fk_quote_salesperson_membership
                FOREIGN KEY (salesperson_id, org_id)
                REFERENCES user_org_membership(user_id, org_id),
            ADD CONSTRAINT fk_quote_estimator_membership
                FOREIGN KEY (estimator_id, org_id)
                REFERENCES user_org_membership(user_id, org_id)
        """
    )
    # Quotes can no longer be deleted by app role? No — Trash is UPDATE (deleted_at).
    op.execute(f"GRANT INSERT, UPDATE ON quote TO {APP_ROLE}")

    # --- component (minimal stub — M1.5 extends) -----------------------------
    op.execute(
        """
        CREATE TABLE component (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid NOT NULL,
            is_root_component boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_component_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_component_part_org
                FOREIGN KEY (org_id, part_id) REFERENCES part(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_component_org_part ON component (org_id, part_id)")

    # --- quote_item (root component tied to a quote at a position) ------------
    op.execute(
        """
        CREATE TABLE quote_item (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_id uuid NOT NULL,
            root_component_id uuid NOT NULL,
            position bigint NOT NULL,
            workflow_status qi_workflow_status NOT NULL DEFAULT 'not_started',
            was_won boolean NOT NULL DEFAULT false,
            export_controlled boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_quote_item_quote_org
                FOREIGN KEY (org_id, quote_id) REFERENCES quote(org_id, id),
            CONSTRAINT fk_quote_item_component_org
                FOREIGN KEY (org_id, root_component_id) REFERENCES component(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_quote_item_quote_position ON quote_item (quote_id, position)")

    # --- quote_status_event (append-only audit) ------------------------------
    op.execute(
        """
        CREATE TABLE quote_status_event (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_id uuid NOT NULL,
            from_status quote_status,
            to_status quote_status NOT NULL,
            actor_id uuid,
            note text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_qse_quote_org
                FOREIGN KEY (org_id, quote_id) REFERENCES quote(org_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_qse_org_quote_created ON quote_status_event (org_id, quote_id, created_at)"
    )

    # --- quote_counter (per-org atomic sequential number allocator) ----------
    # ``last_number`` = last assigned number (0 ⇒ first quote gets 1). A configurable
    # starting number is achieved by seeding this row with ``last_number = start - 1``.
    op.execute(
        """
        CREATE TABLE quote_counter (
            org_id uuid PRIMARY KEY REFERENCES organization(id),
            last_number bigint NOT NULL DEFAULT 0
        )
        """
    )

    # --- grants (restricted app role) ----------------------------------------
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON component TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON quote_item TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON quote_status_event TO {APP_ROLE}")  # append-only
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON quote_counter TO {APP_ROLE}")

    # --- row-level security (identical pattern to quote/account/part, M0.2) ---
    for table in _NEW_ORG_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table}
                USING (org_id = current_setting('app.current_org_id', true)::uuid)
                WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in _NEW_ORG_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS quote_counter")
    op.execute("DROP TABLE IF EXISTS quote_status_event")
    op.execute("DROP TABLE IF EXISTS quote_item")
    op.execute("DROP TABLE IF EXISTS component")
    op.execute("DROP TYPE IF EXISTS qi_workflow_status")

    # Revert the quote hardening: drop composite FKs + added columns, restore the
    # stub's plain FKs. NOTE: the three quote_status enum VALUES added above are
    # *not* removed — PostgreSQL cannot drop enum values; they are harmless if unused.
    op.execute("REVOKE INSERT, UPDATE ON quote FROM " + APP_ROLE)
    for fk in (
        "fk_quote_account_org",
        "fk_quote_contact_org",
        "fk_quote_salesperson_membership",
        "fk_quote_estimator_membership",
    ):
        op.execute(f"ALTER TABLE quote DROP CONSTRAINT IF EXISTS {fk}")
    op.execute(
        """
        ALTER TABLE quote
            DROP COLUMN IF EXISTS revision,
            DROP COLUMN IF EXISTS status_before_hold,
            DROP COLUMN IF EXISTS currency,
            DROP COLUMN IF EXISTS contact_id,
            DROP COLUMN IF EXISTS private_notes,
            DROP COLUMN IF EXISTS config_frozen_at,
            DROP COLUMN IF EXISTS rfq_received_date,
            DROP COLUMN IF EXISTS started_at,
            DROP COLUMN IF EXISTS sent_at,
            DROP COLUMN IF EXISTS expiration_date,
            DROP COLUMN IF EXISTS expired_at,
            DROP COLUMN IF EXISTS estimator_assigned_at,
            DROP COLUMN IF EXISTS salesperson_assigned_at,
            DROP COLUMN IF EXISTS deleted_at
        """
    )
    op.execute("ALTER TABLE contact DROP CONSTRAINT IF EXISTS uq_contact_org_id_id")
    op.execute(
        "ALTER TABLE quote ADD CONSTRAINT quote_account_id_fkey "
        "FOREIGN KEY (account_id) REFERENCES account(id)"
    )
    op.execute(
        "ALTER TABLE quote ADD CONSTRAINT quote_salesperson_id_fkey "
        "FOREIGN KEY (salesperson_id) REFERENCES app_user(id)"
    )
    op.execute(
        "ALTER TABLE quote ADD CONSTRAINT quote_estimator_id_fkey "
        "FOREIGN KEY (estimator_id) REFERENCES app_user(id)"
    )
