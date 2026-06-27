"""component_quantity — quantity breaks + per-break cells (M1.6).

The per-break grid every downstream cost/price renders into (DOMAIN-MODEL "the richest
entity"; spec ``#partview`` Pricing & Quantities). M1.6 lands the table with **only the
quantity triple** — ``quantity`` (customer-requested), ``make_quantity`` (``part.qty``),
``deliver_quantity`` (``part.bom_qty``). The cost/price/discount/profit/lead-time columns
in ``DB-SCHEMA.sql`` arrive with their owning milestones (M1.7 op-cost cells, M1.10
pricing, M1.11 lead times) by **forward ALTER** — the same minimal-stub pattern M1.4/M1.5
used (no column lands before the feature that fills it). The money representation those
columns will use is the open question in DECISIONS.md 2026-06-27, so **no money column
lands here**.

Scope/invariants (M1.6 grill, 2026-06-27): in M1.6 we only **create** breaks on root
components — but ``component_quantity`` is intentionally per-component (DOMAIN-MODEL:
``COMPONENT ||--o{ COMPONENT_QUANTITY``), so **child components get their own cells at M4**;
this is deliberately *not* constrained to roots at the DB (that would block M4). Enforced
invariants: duplicate break values forbidden (``UNIQUE (component_id, quantity)`` — a
deliberate divergence from PP's KB, which allows them; the schema is the higher tier);
``quantity > 0``. The table is org-scoped with a composite same-org FK + RLS, like
``node`` (M1.5). The
app role gets DELETE here (unlike M1.5's tables) because "Change quantities" **removes**
breaks. Existing root components (the M1.4 golden-thread quote) are backfilled a single
``quantity = 1`` break so every line item has the >=1 break the grid requires.

Revision ID: 0010_component_quantity
Revises: 0009_part_node_geometry
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_component_quantity"
down_revision: str | None = "0009_part_node_geometry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    # --- component_quantity: per-break cells (M1.6 = quantity triple only) ----
    op.execute(
        """
        CREATE TABLE component_quantity (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            component_id uuid NOT NULL,
            quantity integer NOT NULL,            -- customer-requested break value
            make_quantity integer,                -- part.qty  (= quantity for the root in M1.6)
            deliver_quantity integer,             -- part.bom_qty (= quantity for the root in M1.6)
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            -- No duplicate break values for one component (the index-aligned lists key on
            -- the quantity); the M1.7+ cost-cell tables FK onto (component, quantity).
            CONSTRAINT uq_component_quantity_comp_qty UNIQUE (component_id, quantity),
            CONSTRAINT ck_component_quantity_positive CHECK (quantity > 0),
            -- A cell's component must be in the SAME org (composite FK); CASCADE so a
            -- (future) hard component delete takes its cells with it.
            CONSTRAINT fk_component_quantity_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_component_quantity_org_component "
        "ON component_quantity (org_id, component_id)"
    )

    # --- grants (restricted app role) — incl. DELETE for break removal -------
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON component_quantity TO {APP_ROLE}")

    # --- row-level security (identical pattern to node/part_geometry, M1.5) ---
    op.execute("ALTER TABLE component_quantity ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE component_quantity FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON component_quantity
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # --- backfill: every existing root component gets a single qty=1 break ----
    # Runs as the migration owner (bypasses RLS), so org_id comes from the component
    # row. M1.6 breaks live on the root component only; in practice every component to
    # date is a root component (M1.5 only creates roots).
    op.execute(
        """
        INSERT INTO component_quantity
            (org_id, component_id, quantity, make_quantity, deliver_quantity)
        SELECT org_id, id, 1, 1, 1 FROM component WHERE is_root_component = true
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON component_quantity")
    op.execute(f"REVOKE ALL ON component_quantity FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS component_quantity")
