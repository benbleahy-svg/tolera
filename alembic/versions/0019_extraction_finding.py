"""Lens extraction findings (M3.1).

Spec ``#lens-finding`` / AI-LENS-ENGINE §8, canonical DDL ``DB-SCHEMA.sql``
§AI/Lens: one structured extraction per row — value + units + bbox + confidence
+ AI-Governor status. Org-scoped with RLS (tier-1). Deviations from the frozen
DDL, resolved up the ladder (CLAUDE.md §2):

* ``type`` + ``confidence`` are NOT NULL — required in the spec's
  ``ExtractionFinding`` output contract (the DDL left them lax).
* FKs are the composite same-org form this codebase uses everywhere
  (``fk_*_same_org`` precedent), and the file FK cascades: part files are
  HARD-deleted for GDPR erasure (M1.2) and findings carry print content, so
  they must not survive their source file.

``extraction_correction`` (training loop) lands with M3.2, which owns the
corrections UX.

Revision ID: 0019_extraction_finding
Revises: 0018_collaboration
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019_extraction_finding"
down_revision: str | None = "0018_collaboration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE finding_category AS ENUM
            ('quote_setup', 'requirements', 'features', 'dimensions', 'regions')
        """
    )
    op.execute(
        """
        CREATE TYPE finding_status AS ENUM
            ('suggested', 'accepted', 'rejected', 'edited')
        """
    )
    op.execute(
        """
        CREATE TABLE extraction_finding (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            component_id uuid,
            source_file_id uuid,
            page int,
            category finding_category NOT NULL,
            type text NOT NULL,
            raw_text text,
            value text,
            normalized_value text,
            units text,
            tolerance jsonb,
            role text,
            gdt jsonb,
            bbox jsonb,
            confidence numeric(5,4) NOT NULL,
            status finding_status NOT NULL DEFAULT 'suggested',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_extraction_finding_file_org
                FOREIGN KEY (org_id, source_file_id)
                REFERENCES part_file(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_extraction_finding_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE SET NULL (component_id),
            CONSTRAINT ck_extraction_finding_confidence
                CHECK (confidence >= 0 AND confidence <= 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_extraction_finding_org_file ON extraction_finding (org_id, source_file_id)"
    )
    op.execute(
        "CREATE INDEX ix_extraction_finding_org_component"
        " ON extraction_finding (org_id, component_id)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON extraction_finding TO {APP_ROLE}")
    op.execute("ALTER TABLE extraction_finding ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE extraction_finding FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON extraction_finding
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON extraction_finding")
    op.execute(f"REVOKE ALL ON extraction_finding FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS extraction_finding")
    op.execute("DROP TYPE IF EXISTS finding_status")
    op.execute("DROP TYPE IF EXISTS finding_category")
