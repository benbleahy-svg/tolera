"""Pricing layer — pricing items, discounts, roll-up columns (M1.10).

Spec ``#costing`` (five categories + custom categories + additive pricing
items), ``#kalk-rollup`` (roll-up math), ``#newscope`` §1 (target-margin);
grill decisions in DECISIONS.md 2026-07-09:

* ``calc_type`` enum gains ``target_margin`` over the folded DDL (the v1
  differentiator: back-solve the markup amount so profit/total hits a target).
* **No CostCategory table** — a custom category lives on its pricing item
  (``is_custom + custom_category_name + color + formula``); its per-break cost
  (the ``set_custom_cost()`` output) persists as
  ``pricing_item_cell.calc_custom_cost`` (the colored Costing row).
* ``pricing_item_def`` / ``discount_def`` — the org library behind Configure →
  Pricing/Discounts; quote items get **snapshot-on-attach** copies (E4-d
  freeze; the 2026-07-08 M1.9 precedent). ``is_pre_installed``-style soft
  delete via ``deleted_at`` + live-name partial unique (operation_def pattern).
* ``component.piece_price`` / ``component.manual_override_cost`` — per-unit
  cost sources for the Purchased-Components / Component-Overrides buckets
  until M4's ``purchased_component`` entity lands.
* ``component_quantity`` gains the per-break roll-up/price columns from the
  folded DDL (minus ``lead_time_days`` → M1.11). numeric(14,4) money per the
  2026-06-27 decision; pcts numeric(7,4).

Revision ID: 0013_pricing_discounts
Revises: 0012_kalk_custom_tables
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_pricing_discounts"
down_revision: str | None = "0012_kalk_custom_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_RLS_TABLES = (
    "pricing_item_def",
    "discount_def",
    "pricing_item",
    "pricing_item_cell",
    "discount",
    "discount_cell",
)

_CQ_MONEY_COLUMNS = (
    "material_cost",
    "inside_cost",
    "outside_cost",
    "purchased_component_cost",
    "child_override_cost",
    "unit_cost",
    "calc_unit_price",
    "manual_unit_price",
    "unit_price",
    "total_price",
    "total_discount",
    "total_profit",
)

_CQ_PCT_COLUMNS = ("total_discount_pct", "profit_margin_pct")


def upgrade() -> None:
    op.execute("CREATE TYPE calc_type AS ENUM ('markup', 'margin', 'target_margin')")
    op.execute(
        "CREATE TYPE cost_category AS ENUM "
        "('general', 'material', 'inside', 'outside', 'purchased_component')"
    )

    op.execute(
        """
        CREATE TABLE pricing_item_def (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            calc_type calc_type NOT NULL DEFAULT 'markup',
            category cost_category NOT NULL DEFAULT 'general',
            is_custom boolean NOT NULL DEFAULT false,
            custom_category_name text,
            color text,
            formula text,                       -- Kalk (pricing-item context)
            default_pct numeric(9,4),           -- fixed % when no formula
            position integer NOT NULL DEFAULT 0,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_pricing_item_def_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_pricing_item_def_custom_named
                CHECK (NOT is_custom OR custom_category_name IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pricing_item_def_org_name_live
            ON pricing_item_def (org_id, name) WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE discount_def (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            formula text,                       -- Kalk (discount context)
            default_pct numeric(9,4),
            position integer NOT NULL DEFAULT 0,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_discount_def_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_discount_def_pct_positive
                CHECK (default_pct IS NULL OR default_pct >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_discount_def_org_name_live
            ON discount_def (org_id, name) WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE pricing_item (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            component_id uuid NOT NULL,         -- always a root component
            source_def_id uuid,
            name text NOT NULL,
            calc_type calc_type NOT NULL DEFAULT 'markup',
            category cost_category NOT NULL DEFAULT 'general',
            is_custom boolean NOT NULL DEFAULT false,
            custom_category_name text,
            color text,
            formula text,
            default_pct numeric(9,4),           -- fixed % when no formula
            position integer NOT NULL DEFAULT 0,
            is_from_factory boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_pricing_item_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_pricing_item_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_pricing_item_source_def_org
                FOREIGN KEY (org_id, source_def_id)
                REFERENCES pricing_item_def(org_id, id),
            CONSTRAINT ck_pricing_item_custom_named
                CHECK (NOT is_custom OR custom_category_name IS NOT NULL)
        )
        """
    )
    op.execute("CREATE INDEX ix_pricing_item_org_component ON pricing_item (org_id, component_id)")

    op.execute(
        """
        CREATE TABLE pricing_item_cell (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            pricing_item_id uuid NOT NULL,
            component_id uuid NOT NULL,
            quantity integer NOT NULL,
            calc_pct numeric(9,4),
            manual_pct numeric(9,4),
            calc_profit numeric(14,4),          -- the item's computed $ contribution
            manual_profit numeric(14,4),        -- estimator override of the $ amount
            calc_custom_cost numeric(14,4),     -- set_custom_cost() output (custom rows)
            unreachable boolean NOT NULL DEFAULT false,  -- target-margin back-solve < 0
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_pricing_item_cell_item_qty UNIQUE (pricing_item_id, quantity),
            CONSTRAINT fk_pricing_item_cell_item_org
                FOREIGN KEY (org_id, pricing_item_id)
                REFERENCES pricing_item(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_pricing_item_cell_component_quantity
                FOREIGN KEY (component_id, quantity)
                REFERENCES component_quantity(component_id, quantity) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_pricing_item_cell_org_component "
        "ON pricing_item_cell (org_id, component_id)"
    )

    op.execute(
        """
        CREATE TABLE discount (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            component_id uuid NOT NULL,
            source_def_id uuid,
            name text NOT NULL,
            formula text,
            default_pct numeric(9,4),
            position integer NOT NULL DEFAULT 0,
            is_from_factory boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_discount_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_discount_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_discount_source_def_org
                FOREIGN KEY (org_id, source_def_id)
                REFERENCES discount_def(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_discount_org_component ON discount (org_id, component_id)")

    op.execute(
        """
        CREATE TABLE discount_cell (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            discount_id uuid NOT NULL,
            component_id uuid NOT NULL,
            quantity integer NOT NULL,
            calc_pct numeric(9,4),
            manual_pct numeric(9,4),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_discount_cell_discount_qty UNIQUE (discount_id, quantity),
            CONSTRAINT fk_discount_cell_discount_org
                FOREIGN KEY (org_id, discount_id)
                REFERENCES discount(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_discount_cell_component_quantity
                FOREIGN KEY (component_id, quantity)
                REFERENCES component_quantity(component_id, quantity) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_discount_cell_org_component ON discount_cell (org_id, component_id)"
    )

    # Purchased-Components / Component-Overrides cost sources until M4
    op.execute("ALTER TABLE component ADD COLUMN piece_price numeric(14,4)")
    op.execute("ALTER TABLE component ADD COLUMN manual_override_cost numeric(14,4)")

    # per-break roll-up + price columns (folded DDL minus lead_time_days → M1.11)
    for column in _CQ_MONEY_COLUMNS:
        op.execute(f"ALTER TABLE component_quantity ADD COLUMN {column} numeric(14,4)")
    for column in _CQ_PCT_COLUMNS:
        op.execute(f"ALTER TABLE component_quantity ADD COLUMN {column} numeric(7,4)")

    # grants + RLS (0010/0011/0012 pattern)
    for table in _RLS_TABLES:
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


def downgrade() -> None:
    for column in reversed(_CQ_PCT_COLUMNS):
        op.execute(f"ALTER TABLE component_quantity DROP COLUMN IF EXISTS {column}")
    for column in reversed(_CQ_MONEY_COLUMNS):
        op.execute(f"ALTER TABLE component_quantity DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE component DROP COLUMN IF EXISTS manual_override_cost")
    op.execute("ALTER TABLE component DROP COLUMN IF EXISTS piece_price")
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS discount_cell")
    op.execute("DROP TABLE IF EXISTS discount")
    op.execute("DROP TABLE IF EXISTS pricing_item_cell")
    op.execute("DROP TABLE IF EXISTS pricing_item")
    op.execute("DROP TABLE IF EXISTS discount_def")
    op.execute("DROP TABLE IF EXISTS pricing_item_def")
    op.execute("DROP TYPE IF EXISTS cost_category")
    op.execute("DROP TYPE IF EXISTS calc_type")
