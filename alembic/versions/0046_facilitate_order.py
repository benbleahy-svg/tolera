"""Facilitate Order drawer — per-line adjustments + order history (M5.7).

Adds the two entities the internal Build-Order flow needs on top of the M5.2
``order_``/``order_line`` spine:

* ``order_line_adjustment`` — the Build-Order drawer's per-line **Discounts**
  (Percent) and **Additional Charges** (Price). Exactly one shape per row
  (``kind`` check); ``effect_minor`` persists the resolved money effect
  (negative for a discount, positive for a charge) so the order total is a pure
  read, never a recompute (the money invariant, CLAUDE.md §5).
* ``order_history_event`` — the pre-shipment **order-history trail** (spec
  ``#order``; KB ``post-order-changes-and-limitations``). Append-only; a
  facilitated build writes ``created`` and each edit writes ``edited`` with a
  ``changes`` diff + ``buyer_notified`` flag.

Both are org-scoped + RLS like every tenant table. Fully reversible.

Revision ID: 0046_facilitate_order
Revises: 0045_email_composer
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0046_facilitate_order"
down_revision: str | None = "0045_email_composer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_ORG_SCOPED_TABLES = ("order_line_adjustment", "order_history_event")


def upgrade() -> None:
    # --- enums ----------------------------------------------------------------
    op.execute("CREATE TYPE order_line_adjustment_kind AS ENUM ('discount', 'additional_charge')")
    op.execute("CREATE TYPE order_history_event_kind AS ENUM ('created', 'edited')")

    # --- order_line_adjustment ------------------------------------------------
    op.execute(
        """
        CREATE TABLE order_line_adjustment (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            order_line_id uuid NOT NULL,
            kind order_line_adjustment_kind NOT NULL,
            label text NOT NULL,
            percent numeric(9,4),
            amount_minor bigint,
            effect_minor bigint NOT NULL,
            position integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_order_line_adjustment_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_order_line_adjustment_kind_shape CHECK (
                (kind = 'discount' AND percent IS NOT NULL AND amount_minor IS NULL)
                OR (kind = 'additional_charge' AND amount_minor IS NOT NULL AND percent IS NULL)
            ),
            CONSTRAINT ck_order_line_adjustment_percent_range CHECK (
                percent IS NULL OR (percent >= 0 AND percent <= 100)
            ),
            CONSTRAINT fk_order_line_adjustment_line_org
                FOREIGN KEY (org_id, order_line_id)
                REFERENCES order_line(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_order_line_adjustment_org_line "
        "ON order_line_adjustment (org_id, order_line_id)"
    )

    # --- order_history_event --------------------------------------------------
    op.execute(
        """
        CREATE TABLE order_history_event (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            order_id uuid NOT NULL,
            kind order_history_event_kind NOT NULL,
            actor_user_id uuid,
            changes jsonb NOT NULL DEFAULT '{}'::jsonb,
            buyer_notified boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_order_history_event_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_order_history_event_order_org
                FOREIGN KEY (org_id, order_id)
                REFERENCES order_(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_order_history_event_org_order "
        "ON order_history_event (org_id, order_id, created_at)"
    )

    # --- grants + RLS (identical pattern to order_/order_line) -----------------
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON order_line_adjustment TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON order_history_event TO {APP_ROLE}")
    for table in _ORG_SCOPED_TABLES:
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
    for table in _ORG_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS order_history_event")
    op.execute("DROP TABLE IF EXISTS order_line_adjustment")
    op.execute("DROP TYPE IF EXISTS order_history_event_kind")
    op.execute("DROP TYPE IF EXISTS order_line_adjustment_kind")
