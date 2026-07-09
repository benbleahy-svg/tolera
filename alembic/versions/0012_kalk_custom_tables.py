"""Custom tables + Kalk cost formulas + variable overrides (M1.9).

Spec ``#kalk-tables`` (custom tables), ``#kalk-vars`` (overridable variables),
``#kalk-contexts``; grill decisions in DECISIONS.md 2026-07-08:

* ``custom_table`` / ``custom_table_row`` — org-scoped Custom Tables backing
  ``table_var`` / ``table_lookup``. Column types are **boolean | numeric |
  string** stored as ``columns jsonb`` ``[{name, type}]``; row values live in
  ``data jsonb`` keyed by column name. ``custom_table_row`` carries its own
  ``org_id`` (tier-1: every table org-scoped, RLS) plus a composite FK so a
  row can never point at another org's table.
* ``operation_def.cost_formula`` — the library-level Kalk operation-cost
  formula (deferred from M1.7 by decision "Operation model shape").
* ``operation.cost_formula`` — the **snapshot-on-attach** copy (E4-d
  config-freeze: editing the def never reprices an existing draft).
* ``operation.variable_overrides jsonb`` — UI overrides of Kalk-declared
  variables: ``{name: value}``, ``{name: {"<qty>": value}}`` for
  quantity-specific ones. ``runtime``/``setup_time`` keep flowing through the
  existing ``manual_*_mins`` columns, not this jsonb.

Revision ID: 0012_kalk_custom_tables
Revises: 0011_materials_operations
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_kalk_custom_tables"
down_revision: str | None = "0011_materials_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_RLS_TABLES = ("custom_table", "custom_table_row")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custom_table (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            columns jsonb NOT NULL,               -- [{name, type}] (boolean|numeric|string)
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_custom_table_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_custom_table_org_name UNIQUE (org_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE custom_table_row (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            table_id uuid NOT NULL,
            row_number integer NOT NULL,
            data jsonb NOT NULL,                  -- {column: value}, null = empty cell
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_custom_table_row_table_number UNIQUE (table_id, row_number),
            CONSTRAINT fk_custom_table_row_table_org
                FOREIGN KEY (org_id, table_id)
                REFERENCES custom_table(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_custom_table_row_org_table ON custom_table_row (org_id, table_id)")

    # Kalk formula columns (snapshot-on-attach; DECISIONS.md 2026-07-08)
    op.execute("ALTER TABLE operation_def ADD COLUMN cost_formula text")
    op.execute("ALTER TABLE operation ADD COLUMN cost_formula text")
    op.execute(
        "ALTER TABLE operation ADD COLUMN variable_overrides jsonb NOT NULL DEFAULT '{}'::jsonb"
    )

    # grants + RLS (0010/0011 pattern); rows and whole tables are app-deletable
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
    op.execute("ALTER TABLE operation DROP COLUMN IF EXISTS variable_overrides")
    op.execute("ALTER TABLE operation DROP COLUMN IF EXISTS cost_formula")
    op.execute("ALTER TABLE operation_def DROP COLUMN IF EXISTS cost_formula")
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS custom_table_row")
    op.execute("DROP TABLE IF EXISTS custom_table")
