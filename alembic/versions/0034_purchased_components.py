"""Purchased-component library + Smart Match memory + auto-routing columns (M4.10).

Spec ``#assembly`` (Convert to Purchased Component / persistent geometry
memory) + DOMAIN-MODEL §5 ``PurchasedComponent``:

- ``purchased_component`` — the org PC library (KB ``purchased-components``):
  OEM part number + piece price required, flexible ``custom_fields`` JSONB in
  place of PP's editable custom columns (column-def editor deferred).
- ``oem_product`` — the mock OEM catalog Smart Match searches beside the org's
  previously-used entries (the Würth/real adapter arrives in M6 and feeds the
  same table). "Unlinked OEM Products" = rows no library entry references.
- ``pc_geometry_memory`` — the org-level geometry→purchased-component map
  behind "auto-tag the same geometry as purchased in all future quotes";
  ``match_count`` is the Historical Geometric Match "(N)" counter.

Forward ALTERs (stub-then-extend precedent):

- ``component.purchased_component_id`` — the link a Convert creates (the
  M1.5/M1.10 comments' long-promised M4 column); ``piece_price`` stays the
  frozen-at-convert cost input per E4-d.
- ``operation.origin`` + ``operation.operation_properties`` — provenance for
  auto-routing-generated rows ("imported values carry their source") and the
  ``generate_operation(..., operation_properties=)`` payload read back by
  ``get_operation_property`` (KB ``custom-operation-generation``).
- ``process.generation_formula`` — process-level Kalk for custom processes;
  NULL = generic template instantiation from ``process_operation`` rows.

Revision ID: 0034_purchased_components
Revises: 0033_bom_draft
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0034_purchased_components"
down_revision: str | None = "0033_bom_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_NEW_TABLES = ("purchased_component", "oem_product", "pc_geometry_memory")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE purchased_component (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            oem_part_number text NOT NULL,
            internal_part_number text,
            piece_price numeric(14, 4),
            currency varchar(3) NOT NULL DEFAULT 'EUR',
            description text,
            brand text,
            custom_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
            oem_product_id uuid,
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_purchased_component_org_id_id UNIQUE (org_id, id),
            CONSTRAINT ck_purchased_component_currency CHECK (currency IN ('EUR', 'CHF')),
            CONSTRAINT ck_purchased_component_piece_price
                CHECK (piece_price IS NULL OR piece_price >= 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_purchased_component_org_oem"
        " ON purchased_component (org_id, oem_part_number)"
    )

    op.execute(
        """
        CREATE TABLE oem_product (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            brand text NOT NULL,
            oem_part_number text NOT NULL,
            geom_hash text,
            specs jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_oem_product_org_id_id UNIQUE (org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_oem_product_org_geom ON oem_product (org_id, geom_hash)")
    op.execute("CREATE INDEX ix_oem_product_org_oem ON oem_product (org_id, oem_part_number)")

    # The PC-library row a catalog product was imported into (Smart Match's
    # "Unlinked OEM Products" = catalog rows nothing references).
    op.execute(
        """
        ALTER TABLE purchased_component
            ADD CONSTRAINT fk_purchased_component_oem_product_org
            FOREIGN KEY (org_id, oem_product_id)
            REFERENCES oem_product (org_id, id)
            ON DELETE SET NULL (oem_product_id)
        """
    )

    op.execute(
        """
        CREATE TABLE pc_geometry_memory (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            geom_hash text NOT NULL,
            purchased_component_id uuid NOT NULL,
            match_count integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_pc_geometry_memory_org_hash UNIQUE (org_id, geom_hash),
            CONSTRAINT fk_pc_geometry_memory_pc_org
                FOREIGN KEY (org_id, purchased_component_id)
                REFERENCES purchased_component (org_id, id) ON DELETE CASCADE
        )
        """
    )

    for table in _NEW_TABLES:
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

    op.execute("ALTER TABLE component ADD COLUMN purchased_component_id uuid")
    op.execute(
        """
        ALTER TABLE component
            ADD CONSTRAINT fk_component_purchased_component_org
            FOREIGN KEY (org_id, purchased_component_id)
            REFERENCES purchased_component (org_id, id)
            ON DELETE SET NULL (purchased_component_id)
        """
    )

    op.execute("ALTER TABLE operation ADD COLUMN origin text NOT NULL DEFAULT 'manual'")
    op.execute(
        """
        ALTER TABLE operation
            ADD CONSTRAINT ck_operation_origin
            CHECK (origin IN ('manual', 'auto_routing'))
        """
    )
    op.execute("ALTER TABLE operation ADD COLUMN operation_properties jsonb")

    op.execute("ALTER TABLE process ADD COLUMN generation_formula text")


def downgrade() -> None:
    op.execute("ALTER TABLE process DROP COLUMN IF EXISTS generation_formula")
    op.execute("ALTER TABLE operation DROP COLUMN IF EXISTS operation_properties")
    op.execute("ALTER TABLE operation DROP CONSTRAINT IF EXISTS ck_operation_origin")
    op.execute("ALTER TABLE operation DROP COLUMN IF EXISTS origin")
    op.execute(
        "ALTER TABLE component DROP CONSTRAINT IF EXISTS fk_component_purchased_component_org"
    )
    op.execute("ALTER TABLE component DROP COLUMN IF EXISTS purchased_component_id")
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS pc_geometry_memory")
    op.execute(
        "ALTER TABLE purchased_component"
        " DROP CONSTRAINT IF EXISTS fk_purchased_component_oem_product_org"
    )
    op.execute("DROP TABLE IF EXISTS oem_product")
    op.execute("DROP TABLE IF EXISTS purchased_component")
