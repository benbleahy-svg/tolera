"""GeometryService job state + result cache — ``interrogation_run`` (M4.1).

INTERROGATION-ENGINE-SPEC §5.4-6: interrogations run as jobs (surface an
``interrogating…`` state) and the AnalysisResult is persisted + cached keyed by
``(geom-hash, family, resolved-inputs)``. The canonical DDL keeps the dims
output on ``part_geometry.raw``; job state needs a home of its own — additive,
org-scoped + RLS (the lean-extend precedent), reversible.

``file_id`` rides the composite FK onto ``part_file (id, part_id)`` (its
``uq_part_file_id_part`` target), so a run is pinned to a file OF ITS PART and
disappears with the file (part files are hard-deleted). ON UPDATE CASCADE:
the M2.12 part-merge moves ``part_file.part_id`` onto the surviving part —
historical runs follow their file. Org isolation comes from the same-org part
FK + the RLS policy.

Revision ID: 0029_interrogation_run
Revises: 0028_rule_suggestion
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0029_interrogation_run"
down_revision: str | None = "0028_rule_suggestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE interrogation_run (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid NOT NULL,
            file_id uuid NOT NULL,
            family text,
            geom_hash text,
            inputs_hash text NOT NULL DEFAULT '',
            material_id uuid,
            status text NOT NULL DEFAULT 'queued',
            error_code text,
            error_detail text,
            result jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            finished_at timestamptz,
            CONSTRAINT ck_interrogation_run_status
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            CONSTRAINT fk_interrogation_run_part_org
                FOREIGN KEY (org_id, part_id)
                REFERENCES part (org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_interrogation_run_file_part
                FOREIGN KEY (file_id, part_id)
                REFERENCES part_file (id, part_id)
                ON DELETE CASCADE ON UPDATE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_interrogation_run_org_part_created
            ON interrogation_run (org_id, part_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_interrogation_run_cache
            ON interrogation_run (org_id, geom_hash, family, inputs_hash)
            WHERE status = 'succeeded'
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON interrogation_run TO {APP_ROLE}")
    op.execute("ALTER TABLE interrogation_run ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE interrogation_run FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON interrogation_run
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON interrogation_run")
    op.execute(f"REVOKE ALL ON interrogation_run FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS interrogation_run")
