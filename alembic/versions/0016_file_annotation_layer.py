"""PDF annotation layer (M2.2).

Spec ``#pdf-capabilities`` / VIEWER-AND-FILE-TYPES §4 Annotate/Shapes: the
markup layer persists **per file** — one JSONB document of page-anchored
annotation objects (pdf-unit coordinates), written by the viewer, drawn into
a copy on download-with-annotations. Org-scoped with RLS (tier-1); the
composite same-org FK pins the layer to its file. One row per file
(UNIQUE part_file_id) — history/threading arrives with the M2.11
collaboration block.

Revision ID: 0016_file_annotation_layer
Revises: 0015_seed_catalog_config
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_file_annotation_layer"
down_revision: str | None = "0015_seed_catalog_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    # composite-FK target (part_file only had UNIQUE (id, part_id) so far)
    op.execute("ALTER TABLE part_file ADD CONSTRAINT uq_part_file_org_id_id UNIQUE (org_id, id)")
    op.execute(
        """
        CREATE TABLE file_annotation_layer (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_file_id uuid NOT NULL,
            data jsonb NOT NULL DEFAULT '{"objects": []}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_file_annotation_layer_file UNIQUE (part_file_id),
            CONSTRAINT fk_file_annotation_layer_file_org
                FOREIGN KEY (org_id, part_file_id)
                REFERENCES part_file(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON file_annotation_layer TO {APP_ROLE}")
    op.execute("ALTER TABLE file_annotation_layer ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE file_annotation_layer FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON file_annotation_layer
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON file_annotation_layer")
    op.execute(f"REVOKE ALL ON file_annotation_layer FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS file_annotation_layer")
    op.execute("ALTER TABLE part_file DROP CONSTRAINT IF EXISTS uq_part_file_org_id_id")
