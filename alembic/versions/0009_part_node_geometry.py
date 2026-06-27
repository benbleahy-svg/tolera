"""part / node / geometry — the 4-layer model + manual geometry (M1.5).

Extends the M1.2 ``part`` stub and the M1.4 ``component`` stub into the full
4-layer Part→Node→Component→QuoteItem model, all by **forward ALTER** (no reshaping
of what M1.2/M1.4 laid down — DECISIONS.md 2026-06-26 "M1.5"):

  * ``obtain_method`` enum (``MANUFACTURED`` | ``PURCHASED``) — the make-vs-buy axis.
  * ``part`` gains identity (``name``/``part_number``/``revision``/``description`` —
    free-text, **not** unique; matching is M2), ``is_assembly``, ``obtain_method``,
    ``custom_attributes``, ``geom_hash`` (inert until M4 interrogation), and
    ``export_controlled`` (the EU dual-use flag — DACH delta; runtime enforcement → M6).
  * ``component`` gains ``obtain_method`` + ``is_assembly``. The ``process_id`` /
    ``material_id`` / ``purchased_component_id`` FKs are **deferred** (their tables
    arrive in M1.7/M4) — adding them now would FK to non-existent tables.
  * ``part_geometry`` — a 1:1 manual-dims cache (metric). ``raw`` stays NULL until M4
    interrogation; ``overrides`` records which dims a human set, so the calc-vs-override
    invariant (``COALESCE(override, raw)``) holds from day one (DECISIONS.md 2026-06-26).
  * ``node`` — an occurrence of a part in a BOM tree. M1.5 populates only the **root**
    node (``parent_node_id = NULL``, qty 1); child nodes / the BOM Builder are M4.

``part_geometry`` and ``node`` are org-scoped with composite same-org FKs + RLS. The
canonical ``DB-SCHEMA.sql`` omits ``org_id`` on ``part_geometry``, but CLAUDE.md §5
requires every domain table be org-scoped — the M1.2 ``part_file`` precedent governs
(the invariant wins over the raw DDL).

Revision ID: 0009_part_node_geometry
Revises: 0008_quote_lifecycle
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_part_node_geometry"
down_revision: str | None = "0008_quote_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
_NEW_ORG_SCOPED_TABLES = ("part_geometry", "node")


def upgrade() -> None:
    # --- enum: make-vs-buy (values UPPERCASE per DB-SCHEMA.sql) ---------------
    op.execute("CREATE TYPE obtain_method AS ENUM ('MANUFACTURED', 'PURCHASED')")

    # --- part: identity + flags + geometry/interrogation pointers ------------
    op.execute(
        """
        ALTER TABLE part
            ADD COLUMN name text,
            ADD COLUMN part_number text,
            ADD COLUMN revision text,
            ADD COLUMN description text,
            ADD COLUMN is_assembly boolean NOT NULL DEFAULT false,
            ADD COLUMN obtain_method obtain_method NOT NULL DEFAULT 'MANUFACTURED',
            ADD COLUMN custom_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN geom_hash text,
            ADD COLUMN export_controlled boolean NOT NULL DEFAULT false
        """
    )
    # Part-library historical match by geometry signature (populated at M4).
    op.execute("CREATE INDEX ix_part_org_geom_hash ON part (org_id, geom_hash)")

    # --- component: make-vs-buy + assembly flag (process/material → M1.7/M4) --
    op.execute(
        """
        ALTER TABLE component
            ADD COLUMN obtain_method obtain_method NOT NULL DEFAULT 'MANUFACTURED',
            ADD COLUMN is_assembly boolean NOT NULL DEFAULT false
        """
    )

    # --- part_geometry: 1:1 manual-dims cache (metric) -----------------------
    op.execute(
        """
        CREATE TABLE part_geometry (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid NOT NULL,
            -- effective metric dims (what Kalk reads): mm / mm² / mm³ / g
            size_x numeric, size_y numeric, size_z numeric,
            max_dim numeric, med_dim numeric, min_dim numeric,
            area numeric, volume numeric, weight numeric,
            raw jsonb,  -- AnalysisResult by family (NULL until M4 interrogation)
            overrides jsonb NOT NULL DEFAULT '{}'::jsonb,  -- manual override provenance
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            -- One geometry row per part (1:1).
            CONSTRAINT uq_part_geometry_part UNIQUE (part_id),
            -- A geometry row's part must be in the SAME org (composite FK); CASCADE so a
            -- (future, M4) hard part delete takes its geometry with it.
            CONSTRAINT fk_part_geometry_part_org
                FOREIGN KEY (org_id, part_id) REFERENCES part(org_id, id) ON DELETE CASCADE
        )
        """
    )

    # --- node: occurrence of a part in a BOM tree (M1.5 = root node only) -----
    op.execute(
        """
        CREATE TABLE node (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid NOT NULL,
            parent_node_id uuid,                         -- NULL = root node (qty 1)
            qty_relative_to_parent integer NOT NULL DEFAULT 1,
            root_part_id uuid NOT NULL,                  -- denormalized tree root for fast scoping
            created_at timestamptz NOT NULL DEFAULT now(),
            -- Composite-FK target so a child node's (org_id, parent_node_id) is same-org.
            CONSTRAINT uq_node_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_node_qty_positive CHECK (qty_relative_to_parent > 0),
            CONSTRAINT fk_node_part_org
                FOREIGN KEY (org_id, part_id) REFERENCES part(org_id, id),
            -- The denormalized tree root must be a same-org part (NOT NULL above).
            CONSTRAINT fk_node_root_part_org
                FOREIGN KEY (org_id, root_part_id) REFERENCES part(org_id, id),
            -- Self-referential same-org parent (MATCH SIMPLE skips the check when NULL).
            CONSTRAINT fk_node_parent_org
                FOREIGN KEY (org_id, parent_node_id) REFERENCES node(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_node_parent ON node (parent_node_id)")
    op.execute("CREATE INDEX ix_node_org_part ON node (org_id, part_id)")
    op.execute("CREATE INDEX ix_node_org_root_part ON node (org_id, root_part_id)")

    # --- grants (restricted app role) ----------------------------------------
    # No DELETE: parts/geometry/nodes are not hard-deleted in M1.5 (node removal via
    # tree edits is M4, which grants DELETE then). part_geometry rows are upserted.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON part_geometry TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON node TO {APP_ROLE}")

    # --- row-level security (identical pattern to part/component, M0.2) -------
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
    op.execute("DROP TABLE IF EXISTS node")
    op.execute("DROP TABLE IF EXISTS part_geometry")
    # Drop the enum-typed columns before the enum type itself.
    op.execute(
        "ALTER TABLE component "
        "DROP COLUMN IF EXISTS obtain_method, DROP COLUMN IF EXISTS is_assembly"
    )
    op.execute("DROP INDEX IF EXISTS ix_part_org_geom_hash")
    op.execute(
        """
        ALTER TABLE part
            DROP COLUMN IF EXISTS name,
            DROP COLUMN IF EXISTS part_number,
            DROP COLUMN IF EXISTS revision,
            DROP COLUMN IF EXISTS description,
            DROP COLUMN IF EXISTS is_assembly,
            DROP COLUMN IF EXISTS obtain_method,
            DROP COLUMN IF EXISTS custom_attributes,
            DROP COLUMN IF EXISTS geom_hash,
            DROP COLUMN IF EXISTS export_controlled
        """
    )
    op.execute("DROP TYPE IF EXISTS obtain_method")
