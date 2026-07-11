"""Add-Ons / Lead Times / Expedite (M1.11).

Spec ``#addons`` (per-line add-ons with Required toggle + AddOnType dropdown;
per-qty lead times; quote-level expedite tiers), folded DDL ``add_on`` /
``add_on_cell`` / ``expedite_option``; grill decisions in the M1.11 PR:

* ``add_on_def`` — the admin-configurable AddOnType list (spec dropdown), the
  M1.10 def/snapshot pattern (E4-d); ``add_on`` rows snapshot name/formula/
  flat price/required-default on attach.
* ``add_on.calc_is_required``/``manual_is_required`` — the CLAUDE.md §5
  calc-vs-override pair over the folded DDL's single ``is_required`` (the
  calc side is Kalk ``set_is_required``; the toggle is manual).
* ``add_on_cell`` gains ``org_id`` + composite FKs over the folded DDL —
  the tier-1 "every domain table org-scoped (RLS)" invariant governs.
* ``component_quantity.lead_time_days`` (folded DDL) lands as the
  calc/manual/resolved triple, the same split M1.10 used for unit_price.
* ``quote_cell.days`` — the deferred column from the M1.7 decision ("``days``
  arrives with M1.11"): the operation's Kalk DAYS output, calc-only.
* ``quote.expedite_tiers`` JSONB — the top-of-quote editor staging that
  APPLY-TO-ALL pushes into per-component ``expedite_option`` rows.
* Tax (MwSt/USt) stays **out of the schema**: computed at the quote-total
  boundary by the Tax service, never stored on cells (DB-SCHEMA note §554,
  PRICING-ENGINE-SPEC §1, DACH-DELTA §3).

Revision ID: 0014_addons_leadtimes
Revises: 0013_pricing_discounts
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_addons_leadtimes"
down_revision: str | None = "0013_pricing_discounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_RLS_TABLES = (
    "add_on_def",
    "add_on",
    "add_on_cell",
    "expedite_option",
)

_CQ_LEAD_COLUMNS = ("calc_lead_time_days", "manual_lead_time_days", "lead_time_days")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE add_on_def (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            formula text,                       -- Kalk (add_on context) → PRICE
            default_price numeric(14,4),        -- flat price when no formula
            default_is_required boolean NOT NULL DEFAULT false,
            position integer NOT NULL DEFAULT 0,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_add_on_def_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_add_on_def_price_positive
                CHECK (default_price IS NULL OR default_price >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_add_on_def_org_name_live
            ON add_on_def (org_id, name) WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE add_on (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            component_id uuid NOT NULL,         -- always a root component
            source_def_id uuid,
            name text NOT NULL,
            formula text,
            default_price numeric(14,4),
            default_is_required boolean NOT NULL DEFAULT false,
            calc_is_required boolean,           -- Kalk set_is_required() output
            calc_name text,                     -- Kalk set_add_on_name() output
            manual_is_required boolean,         -- the UI Required toggle
            position integer NOT NULL DEFAULT 0,
            is_from_factory boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_add_on_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_add_on_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_add_on_source_def_org
                FOREIGN KEY (org_id, source_def_id)
                REFERENCES add_on_def(org_id, id),
            CONSTRAINT ck_add_on_price_positive
                CHECK (default_price IS NULL OR default_price >= 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_add_on_org_component ON add_on (org_id, component_id)")

    op.execute(
        """
        CREATE TABLE add_on_cell (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            add_on_id uuid NOT NULL,
            component_id uuid NOT NULL,
            quantity integer NOT NULL,
            calc_price numeric(14,4),           -- Kalk PRICE or the flat default
            manual_price numeric(14,4),         -- estimator override
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_add_on_cell_add_on_qty UNIQUE (add_on_id, quantity),
            CONSTRAINT fk_add_on_cell_add_on_org
                FOREIGN KEY (org_id, add_on_id)
                REFERENCES add_on(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_add_on_cell_component_quantity
                FOREIGN KEY (component_id, quantity)
                REFERENCES component_quantity(component_id, quantity) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_add_on_cell_org_component ON add_on_cell (org_id, component_id)")

    op.execute(
        """
        CREATE TABLE expedite_option (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            component_id uuid NOT NULL,
            days_faster integer NOT NULL,
            markup_pct numeric(7,3) NOT NULL,
            position integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_expedite_option_comp_days UNIQUE (component_id, days_faster),
            CONSTRAINT fk_expedite_option_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE CASCADE,
            CONSTRAINT ck_expedite_option_days_positive CHECK (days_faster > 0),
            CONSTRAINT ck_expedite_option_markup_positive CHECK (markup_pct >= 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_expedite_option_org_component ON expedite_option (org_id, component_id)"
    )

    # per-break lead time: calc/manual/resolved triple (folded DDL's single
    # lead_time_days split per CLAUDE.md §5 — the M1.10 unit_price precedent)
    for column in _CQ_LEAD_COLUMNS:
        op.execute(f"ALTER TABLE component_quantity ADD COLUMN {column} integer")

    # the operation's Kalk DAYS output (M1.7 decision: "days arrives with M1.11")
    op.execute("ALTER TABLE quote_cell ADD COLUMN days integer")

    # top-of-quote expedite editor staging (APPLY TO ALL writes expedite_option rows)
    op.execute("ALTER TABLE quote ADD COLUMN expedite_tiers jsonb")

    # grants + RLS (0010-0013 pattern)
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
    op.execute("ALTER TABLE quote DROP COLUMN IF EXISTS expedite_tiers")
    op.execute("ALTER TABLE quote_cell DROP COLUMN IF EXISTS days")
    for column in reversed(_CQ_LEAD_COLUMNS):
        op.execute(f"ALTER TABLE component_quantity DROP COLUMN IF EXISTS {column}")
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS expedite_option")
    op.execute("DROP TABLE IF EXISTS add_on_cell")
    op.execute("DROP TABLE IF EXISTS add_on")
    op.execute("DROP TABLE IF EXISTS add_on_def")
