"""Materials catalog + processes + operation library + per-qty cost cells (M1.7).

Spec ``#partview`` (Materials · Operations), ``#costing``, ``#oplibrary``; grill
decisions in DECISIONS.md 2026-07-07 ("M1.7 material catalog content", "Operation
model shape", "Calculated source", "Change Process semantics") and the resolved
2026-06-27 money decision — **cost columns are ``numeric(14,4)``** (4-dp unit-level
intermediates; integer-minor-unit rounding happens only at the quote-total boundary).

New tables (all org-scoped, RLS ``org_isolation`` per the 0010 pattern):

* ``material_class`` / ``material_family`` / ``material`` — the 3-level DACH
  hierarchy (Werkstoffnummer + EN name + AISI alias) behind the nested picker.
* ``process`` — minimal entity (Change Process targets); templates/routers M1.12/M4.
* ``operation_def`` — the org operation library, spec ``#oplibrary`` DACH shape:
  ``calculation_mode``, €/hr rates, flat-vs-time setup, ``surcharge_pct``,
  **times in minutes**. The Kalk ``cost_formula`` column lands at M1.9.
* ``operation`` — instances on a component (router rows + material lines) with
  config copied from the def at attach (config-freeze) and per-row calc/manual
  time pairs.
* ``quote_cell`` — per-(operation x quantity) cost cell with the
  calc/override pair; composite-FK'd onto ``component_quantity`` so cells always
  belong to a real break and cascade when breaks are removed.

``component`` gains ``material_id`` / ``process_id`` (forward ALTER per the
stub-then-extend precedent).

Revision ID: 0011_materials_operations
Revises: 0010_component_quantity
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_materials_operations"
down_revision: str | None = "0010_component_quantity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

# Every M1.7 table gets the same org-isolation policy (0010 pattern).
_RLS_TABLES = (
    "material_class",
    "material_family",
    "material",
    "process",
    "operation_def",
    "operation",
    "quote_cell",
)


def upgrade() -> None:
    # --- enums -----------------------------------------------------------------
    op.execute("CREATE TYPE op_category AS ENUM ('operation', 'material')")
    op.execute(
        "CREATE TYPE calculation_mode AS ENUM "
        "('machine_plus_operator', 'labour_only', 'outside_process')"
    )
    op.execute("CREATE TYPE setup_basis AS ENUM ('flat', 'time')")

    # --- materials: 3-level hierarchy (Class → Family → Material) ---------------
    op.execute(
        """
        CREATE TABLE material_class (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            position integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_material_class_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_material_class_org_name UNIQUE (org_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE material_family (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            class_id uuid NOT NULL,
            name text NOT NULL,                   -- German-first display name
            alias text,                           -- English/hubs name (type-ahead)
            position integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_material_family_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_material_family_org_class_name UNIQUE (org_id, class_id, name),
            CONSTRAINT fk_material_family_class_org
                FOREIGN KEY (org_id, class_id)
                REFERENCES material_class(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_material_family_org_class ON material_family (org_id, class_id)")
    op.execute(
        """
        CREATE TABLE material (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            family_id uuid NOT NULL,
            display_name text NOT NULL,
            werkstoffnummer text,                 -- DIN EN 10027, e.g. '1.4301'
            en_name text,                         -- 'X5CrNi18-10'
            aisi_alias text,                      -- '304' (reference)
            density numeric(10,4),                -- g/cm3
            cost_per_volume numeric(14,6),        -- shop rate; NULL until configured
            cost_per_area numeric(14,6),
            added_lead_time_days integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_material_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_material_org_family_name UNIQUE (org_id, family_id, display_name),
            CONSTRAINT fk_material_family_org
                FOREIGN KEY (org_id, family_id)
                REFERENCES material_family(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_material_org_family ON material (org_id, family_id)")

    # --- process: minimal entity (templates/routers arrive M1.12/M4) ------------
    op.execute(
        """
        CREATE TABLE process (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            external_name text,
            default_lead_time_days integer NOT NULL DEFAULT 0,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_process_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_process_org_name UNIQUE (org_id, name)
        )
        """
    )

    # --- operation_def: the org library (#oplibrary DACH shape, minutes) --------
    op.execute(
        """
        CREATE TABLE operation_def (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            category op_category NOT NULL DEFAULT 'operation',
            calculation_mode calculation_mode NOT NULL DEFAULT 'machine_plus_operator',
            run_rate numeric(14,4),               -- EUR/hr (MSS or labour rate by mode)
            labour_rate numeric(14,4),            -- EUR/hr operator rate (Nebenzeit)
            setup_basis setup_basis NOT NULL DEFAULT 'flat',
            setup_cost numeric(14,4),             -- flat EUR per lot (basis = flat)
            setup_time_mins numeric(10,2),        -- Advanced toggle (basis = time)
            surcharge_pct numeric(6,3) NOT NULL DEFAULT 0,
            is_outside_service boolean NOT NULL DEFAULT false,
            is_finish boolean NOT NULL DEFAULT false,
            is_pre_installed boolean NOT NULL DEFAULT false,
            sort_order integer NOT NULL DEFAULT 0,
            deleted_at timestamptz,               -- hidden (pre-installed) / deleted (custom)
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_operation_def_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_operation_def_surcharge_range
                CHECK (surcharge_pct >= 0 AND surcharge_pct <= 100)
        )
        """
    )
    # Live library names are unique per org — the auto-save dedup key. Partial so a
    # hidden/deleted def frees its name.
    op.execute(
        "CREATE UNIQUE INDEX uq_operation_def_org_name_live "
        "ON operation_def (org_id, name) WHERE deleted_at IS NULL"
    )
    op.execute("CREATE INDEX ix_operation_def_org_sort ON operation_def (org_id, sort_order)")

    # --- operation: instances on a component (router rows + material lines) -----
    op.execute(
        """
        CREATE TABLE operation (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            component_id uuid NOT NULL,
            operation_def_id uuid,                -- NULL = ad-hoc (def deleted later)
            name text NOT NULL,
            category op_category NOT NULL DEFAULT 'operation',
            position integer NOT NULL DEFAULT 0,
            calculation_mode calculation_mode NOT NULL DEFAULT 'machine_plus_operator',
            run_rate numeric(14,4),
            labour_rate numeric(14,4),
            setup_basis setup_basis NOT NULL DEFAULT 'flat',
            setup_cost numeric(14,4),
            calc_setup_mins numeric(10,2),        -- Calculated setup time (minutes)
            manual_setup_mins numeric(10,2),      -- Override setup time
            calc_runtime_mins numeric(12,4),      -- Hauptzeit / Arbeitszeit per unit
            manual_runtime_mins numeric(12,4),
            calc_attend_mins numeric(12,4),       -- Nebenzeit per unit (machine mode)
            manual_attend_mins numeric(12,4),
            surcharge_pct numeric(6,3) NOT NULL DEFAULT 0,
            yield_factor numeric(6,4) NOT NULL DEFAULT 1.0,
            is_outside_service boolean NOT NULL DEFAULT false,
            is_finish boolean NOT NULL DEFAULT false,
            is_from_factory boolean NOT NULL DEFAULT false,
            notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_operation_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_operation_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_operation_def_org
                FOREIGN KEY (org_id, operation_def_id)
                REFERENCES operation_def(org_id, id),
            CONSTRAINT ck_operation_surcharge_range
                CHECK (surcharge_pct >= 0 AND surcharge_pct <= 100),
            CONSTRAINT ck_operation_yield_factor_range
                CHECK (yield_factor > 0 AND yield_factor <= 1)
        )
        """
    )
    op.execute("CREATE INDEX ix_operation_org_component ON operation (org_id, component_id)")

    # --- quote_cell: per-(operation x quantity) cost cell -----------------------
    op.execute(
        """
        CREATE TABLE quote_cell (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            operation_id uuid NOT NULL,
            component_id uuid NOT NULL,
            quantity integer NOT NULL,
            calc_cost numeric(14,4),              -- mode arithmetic (M1.7) / Kalk (M1.9)
            manual_cost numeric(14,4),            -- estimator override; never recalculated
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_quote_cell_operation_qty UNIQUE (operation_id, quantity),
            CONSTRAINT fk_quote_cell_operation_org
                FOREIGN KEY (org_id, operation_id)
                REFERENCES operation(org_id, id) ON DELETE CASCADE,
            -- A cell exists only for a real quantity break; break removal cascades.
            CONSTRAINT fk_quote_cell_component_quantity
                FOREIGN KEY (component_id, quantity)
                REFERENCES component_quantity(component_id, quantity) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_quote_cell_org_component ON quote_cell (org_id, component_id)")

    # --- component: material/process assignment (forward ALTER) -----------------
    op.execute("ALTER TABLE component ADD COLUMN material_id uuid")
    op.execute("ALTER TABLE component ADD COLUMN process_id uuid")
    op.execute(
        """
        ALTER TABLE component
            ADD CONSTRAINT fk_component_material_org
            FOREIGN KEY (org_id, material_id) REFERENCES material(org_id, id)
        """
    )
    op.execute(
        """
        ALTER TABLE component
            ADD CONSTRAINT fk_component_process_org
            FOREIGN KEY (org_id, process_id) REFERENCES process(org_id, id)
        """
    )

    # --- grants + RLS (0010 pattern). DELETE where rows are removed by the app:
    # operation (remove-from-part), quote_cell (recalc prunes), operation_def is
    # soft-deleted only, catalog/process rows are never deleted in M1.7. ---------
    for table in ("material_class", "material_family", "material", "process", "operation_def"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    for table in ("operation", "quote_cell"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")

    for table in _RLS_TABLES:
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
    op.execute("ALTER TABLE component DROP CONSTRAINT IF EXISTS fk_component_material_org")
    op.execute("ALTER TABLE component DROP CONSTRAINT IF EXISTS fk_component_process_org")
    op.execute("ALTER TABLE component DROP COLUMN IF EXISTS material_id")
    op.execute("ALTER TABLE component DROP COLUMN IF EXISTS process_id")
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS quote_cell")
    op.execute("DROP TABLE IF EXISTS operation")
    op.execute("DROP TABLE IF EXISTS operation_def")
    op.execute("DROP TABLE IF EXISTS process")
    op.execute("DROP TABLE IF EXISTS material")
    op.execute("DROP TABLE IF EXISTS material_family")
    op.execute("DROP TABLE IF EXISTS material_class")
    op.execute("DROP TYPE IF EXISTS setup_basis")
    op.execute("DROP TYPE IF EXISTS calculation_mode")
    op.execute("DROP TYPE IF EXISTS op_category")
