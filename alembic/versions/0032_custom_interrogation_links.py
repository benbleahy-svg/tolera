"""Custom-interrogation links (M4.8) — op-def junction, is_default, names.

INTERROGATION-ENGINE-SPEC §4 / KB ``custom-interrogations``: a
``CustomInterrogation`` binds to material class/family/material (columns
shipped in 0031) **and/or operation defs** — the op-def side is a junction
(``custom_interrogation_operation_def``) because a profile links to zero or
more ops. Default-ness becomes an explicit ``is_default`` flag: 0031 keyed
the org default as "all material links NULL", but M4.8 must allow further
no-material-link profiles (the KB Laser/Punch example, op-linked profiles),
which that partial index forbade. Also adds the ``(org_id, id)`` unique pin
0031 omitted (composite-FK target, the house pattern) and the KB "unique
name" rule per org. Reversible (downgrade restores the 0031 invariant by
deleting the non-default no-link rows M4.7 could not express).

Revision ID: 0032_custom_interrogation_links
Revises: 0031_custom_interrogation
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0032_custom_interrogation_links"
down_revision: str | None = "0031_custom_interrogation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE custom_interrogation
            ADD COLUMN is_default boolean NOT NULL DEFAULT false
        """
    )
    # Every 0031-era all-NULL row IS the org default (that was its key).
    op.execute(
        """
        UPDATE custom_interrogation SET is_default = true
        WHERE material_class_id IS NULL
          AND material_family_id IS NULL
          AND material_id IS NULL
        """
    )
    op.execute("DROP INDEX uq_custom_interrogation_org_family_default")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_custom_interrogation_org_family_default
            ON custom_interrogation (org_id, family)
            WHERE is_default
        """
    )
    op.execute(
        """
        ALTER TABLE custom_interrogation
            ADD CONSTRAINT uq_custom_interrogation_org_id_id UNIQUE (org_id, id)
        """
    )
    # KB custom-interrogations: "Each custom interrogation has a unique name".
    op.execute(
        """
        CREATE UNIQUE INDEX uq_custom_interrogation_org_name
            ON custom_interrogation (org_id, name)
        """
    )
    op.execute(
        """
        CREATE TABLE custom_interrogation_operation_def (
            custom_interrogation_id uuid NOT NULL,
            operation_def_id uuid NOT NULL,
            org_id uuid NOT NULL REFERENCES organization(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (custom_interrogation_id, operation_def_id),
            -- same-org pins (the 0031 precedent): a profile can never link
            -- another org's op defs, defense-in-depth beside RLS
            CONSTRAINT fk_ci_operation_def_interrogation
                FOREIGN KEY (org_id, custom_interrogation_id)
                REFERENCES custom_interrogation (org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_ci_operation_def_operation_def
                FOREIGN KEY (org_id, operation_def_id)
                REFERENCES operation_def (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ci_operation_def_org_interrogation
            ON custom_interrogation_operation_def (org_id, custom_interrogation_id)
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON custom_interrogation_operation_def TO {APP_ROLE}"
    )
    op.execute("ALTER TABLE custom_interrogation_operation_def ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE custom_interrogation_operation_def FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON custom_interrogation_operation_def
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON custom_interrogation_operation_def")
    op.execute("DROP TABLE custom_interrogation_operation_def")
    op.execute("DROP INDEX uq_custom_interrogation_org_name")
    op.execute("ALTER TABLE custom_interrogation DROP CONSTRAINT uq_custom_interrogation_org_id_id")
    # Restore the 0031 invariant (one all-NULL row per org+family = the
    # default): rows M4.7 could not express — no material links, not the
    # default — must go, or the recreated partial index cannot build.
    op.execute(
        """
        DELETE FROM custom_interrogation
        WHERE NOT is_default
          AND material_class_id IS NULL
          AND material_family_id IS NULL
          AND material_id IS NULL
        """
    )
    op.execute("DROP INDEX uq_custom_interrogation_org_family_default")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_custom_interrogation_org_family_default
            ON custom_interrogation (org_id, family)
            WHERE material_class_id IS NULL
              AND material_family_id IS NULL
              AND material_id IS NULL
        """
    )
    op.execute("ALTER TABLE custom_interrogation DROP COLUMN is_default")
