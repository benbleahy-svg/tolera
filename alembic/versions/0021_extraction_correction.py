"""Lens correction training labels (M3.2).

Spec ``#wingman`` §3 / AI-LENS-ENGINE §7: each ``mark_inaccurate`` / ``replace``
/ add-missing persists ``{finding, predicted, corrected, tenant, file_ref,
source_region}``. **Per-tenant storage** (DECISIONS.md 2026-07-15) — org-scoped
with RLS like every domain table (tier-1); the global/anonymised pool is a
later opt-in and has no schema here.

FK semantics mirror 0020's reasoning, inverted per column:

* ``source_file_id`` CASCADEs — corrections carry print content, and part-file
  deletion is GDPR erasure (M1.2), so labels die with the file.
* ``finding_id`` SET-NULLs (column-list form) — labels feed the M3.11 eval set
  and must outlive the suggestion row they judged; the ``predicted`` snapshot
  keeps the payload after the finding is gone.

Revision ID: 0021_extraction_correction
Revises: 0020_extraction_finding
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021_extraction_correction"
down_revision: str | None = "0020_extraction_finding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE correction_type AS ENUM
            ('mark_inaccurate', 'replace', 'add_missing')
        """
    )
    # The composite FK below needs the (org_id, id) pair unique on its target
    # (the 0008 contact precedent — extraction_finding shipped without it).
    op.execute(
        "ALTER TABLE extraction_finding"
        " ADD CONSTRAINT uq_extraction_finding_org_id_id UNIQUE (org_id, id)"
    )
    op.execute(
        """
        CREATE TABLE extraction_correction (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            finding_id uuid,
            source_file_id uuid,
            correction_type correction_type NOT NULL,
            predicted jsonb,
            corrected jsonb,
            page int,
            bbox jsonb,
            created_by uuid REFERENCES app_user(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_extraction_correction_file_org
                FOREIGN KEY (org_id, source_file_id)
                REFERENCES part_file(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_extraction_correction_finding_org
                FOREIGN KEY (org_id, finding_id)
                REFERENCES extraction_finding(org_id, id) ON DELETE SET NULL (finding_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_extraction_correction_org_file"
        " ON extraction_correction (org_id, source_file_id)"
    )
    # The SET NULL FK is checked on every finding delete (each Lens re-run
    # bulk-deletes suggested rows) — keep that referencing-row scan indexed.
    op.execute(
        "CREATE INDEX ix_extraction_correction_org_finding"
        " ON extraction_correction (org_id, finding_id)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON extraction_correction TO {APP_ROLE}")
    op.execute("ALTER TABLE extraction_correction ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE extraction_correction FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON extraction_correction
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON extraction_correction")
    op.execute(f"REVOKE ALL ON extraction_correction FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS extraction_correction")
    op.execute(
        "ALTER TABLE extraction_finding DROP CONSTRAINT IF EXISTS uq_extraction_finding_org_id_id"
    )
    op.execute("DROP TYPE IF EXISTS correction_type")
