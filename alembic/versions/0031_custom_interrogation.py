"""Interrogation profiles — ``custom_interrogation`` (M4.7).

The canonical DDL (DB-SCHEMA.sql ``custom_interrogation``) verbatim — the
named ``InterrogationInputs`` bundle (thresholds + ``should_detect_*``
toggles) linkable to material class/family/material — plus ``created_at``
(the lean-extend precedent) and a partial unique index keying the org
DEFAULT profile per family (all material links NULL): M4.7 seeds exactly one
default per Core-4 family; material-specific binding + most-specific
resolution arrive with M4.8. Reversible.

Revision ID: 0031_custom_interrogation
Revises: 0030_nest
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031_custom_interrogation"
down_revision: str | None = "0030_nest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custom_interrogation (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            family process_family NOT NULL,
            inputs jsonb NOT NULL,
            material_class_id uuid,
            material_family_id uuid,
            material_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            -- same-org pin (the nest/quote precedent): a profile can never
            -- bind another org's material tree, defense-in-depth beside RLS
            CONSTRAINT fk_custom_interrogation_material_class
                FOREIGN KEY (org_id, material_class_id)
                REFERENCES material_class (org_id, id),
            CONSTRAINT fk_custom_interrogation_material_family
                FOREIGN KEY (org_id, material_family_id)
                REFERENCES material_family (org_id, id),
            CONSTRAINT fk_custom_interrogation_material
                FOREIGN KEY (org_id, material_id)
                REFERENCES material (org_id, id)
        )
        """
    )
    # One org default (no material link) per family — the M4.7 seed target
    # and the fallback of M4.8's most-specific resolution.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_custom_interrogation_org_family_default
            ON custom_interrogation (org_id, family)
            WHERE material_class_id IS NULL
              AND material_family_id IS NULL
              AND material_id IS NULL
        """
    )
    op.execute(
        "CREATE INDEX ix_custom_interrogation_org_family ON custom_interrogation (org_id, family)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON custom_interrogation TO {APP_ROLE}")
    op.execute("ALTER TABLE custom_interrogation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE custom_interrogation FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON custom_interrogation
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON custom_interrogation")
    op.execute("DROP TABLE custom_interrogation")
