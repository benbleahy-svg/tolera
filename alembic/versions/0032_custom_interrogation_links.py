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
name" rule per org (pre-existing duplicates deterministically renamed).
Reversible: the downgrade rebuilds the 0031 partial index and ABORTS with an
actionable error if non-default unlinked rows exist (unrepresentable under
0031) — it never silently deletes customer-authored profiles.

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
    # 0031 allowed duplicates, so deterministically rename any first (oldest
    # keeps the plain name) — the index must never block a deploy on data
    # that was legal when written.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, name,
                   row_number() OVER (
                       PARTITION BY org_id, name ORDER BY created_at, id
                   ) AS rn
            FROM custom_interrogation
        )
        UPDATE custom_interrogation c
        SET name = ranked.name || ' (' || ranked.rn || ')'
        FROM ranked
        WHERE c.id = ranked.id AND ranked.rn > 1
        """
    )
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
    # The 0031 partial index (one all-NULL row per org+family = the default)
    # cannot represent non-default unlinked profiles. Never silently delete
    # customer-authored rows on the way down — abort with an actionable
    # message instead; the operator deletes or links them, then retries.
    op.execute(
        """
        DO $$
        DECLARE incompatible bigint;
        BEGIN
            SELECT count(*) INTO incompatible
            FROM custom_interrogation
            WHERE NOT is_default
              AND material_class_id IS NULL
              AND material_family_id IS NULL
              AND material_id IS NULL;
            IF incompatible > 0 THEN
                RAISE EXCEPTION
                    'cannot downgrade 0032: % non-default custom interrogation(s)'
                    ' without material links exist (unrepresentable under 0031);'
                    ' delete them or link them to a material first',
                    incompatible;
            END IF;
        END $$
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
