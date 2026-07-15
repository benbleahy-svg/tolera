"""Part-Library match indexes + archive state (M2.12 — spec `#partlib`).

``part_file`` gains the four deterministic match-index fields from the spec's
"How matching works" table: ``file_hash`` (SHA-256 of the raw bytes — Exact
File Match), ``filename_normalized`` (File Name Match / auto-bundling key,
backfilled in SQL — the expression must stay equivalent to
``app.part_index.normalize_filename``), ``part_number_extracted`` (STEP
PRODUCT id — Part Number Match), and ``pdf_text`` (full-text search index —
"hard requirement for Part Library repeat-part discovery"). ``file_hash`` /
``pdf_text`` stay NULL on pre-existing rows (they need the blob; new uploads
populate them — no production data predates this).

``part`` gains ``archived_at``: the spec lifecycle is THREE states (Active →
Archived → Deleted), so the M1.2 convention of ``deleted_at`` doubling as
"archived" splits — existing values move to ``archived_at`` and ``deleted_at``
now means the irreversible delete (files purged, costing preserved).

Geometry match columns (``geometry_signature``/``geometry_vector`` + pgvector)
are deliberately absent — they land with GeometryService (M4); ``part.geom_hash``
already reserves the signature seat.

Revision ID: 0019_part_library_index
Revises: 0018_collaboration
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019_part_library_index"
down_revision: str | None = "0018_collaboration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE part_file ADD COLUMN file_hash text")
    op.execute("ALTER TABLE part_file ADD COLUMN filename_normalized text")
    op.execute("ALTER TABLE part_file ADD COLUMN part_number_extracted text")
    op.execute("ALTER TABLE part_file ADD COLUMN pdf_text text")
    # Backfill the deterministic key that needs no blob access. Equivalent to
    # app.part_index.normalize_filename: strip last extension, lowercase,
    # collapse non-alphanumeric runs to '_', trim, empty → NULL.
    op.execute(
        r"""
        UPDATE part_file SET filename_normalized = NULLIF(
            trim(BOTH '_' FROM lower(
                regexp_replace(
                    CASE WHEN filename ~ '.\.[^.]*$'
                         THEN regexp_replace(filename, '\.[^.]*$', '')
                         ELSE filename END,
                    '[^a-zA-Z0-9]+', '_', 'g')
            )), '')
        """
    )
    # Match lookups are always org-scoped equality probes; lead with org_id.
    op.execute("CREATE INDEX ix_part_file_org_hash ON part_file(org_id, file_hash)")
    op.execute("CREATE INDEX ix_part_file_org_fname_norm ON part_file(org_id, filename_normalized)")
    op.execute(
        "CREATE INDEX ix_part_file_org_pn_extracted ON part_file(org_id, part_number_extracted)"
    )
    # Full-text over pdf_text: 'simple' config — German stemming must never
    # rewrite part numbers / Werkstoffnummern (the very strings searched for).
    op.execute(
        """
        CREATE INDEX ix_part_file_pdf_text_fts ON part_file
            USING gin(to_tsvector('simple', coalesce(pdf_text, '')))
        """
    )

    op.execute("ALTER TABLE part ADD COLUMN archived_at timestamptz")
    # The M1.2/M1.5 API treated deleted_at as "archived" (restorable, listed
    # under the Archived tab) — that meaning moves to archived_at wholesale.
    op.execute(
        "UPDATE part SET archived_at = deleted_at, deleted_at = NULL WHERE deleted_at IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_part_org_archived_at ON part(org_id, archived_at)")


def downgrade() -> None:
    # Fold archive state back into deleted_at (the pre-split convention). A part
    # both archived and deleted keeps its deleted_at (the stronger state).
    op.execute(
        "UPDATE part SET deleted_at = archived_at WHERE deleted_at IS NULL "
        "AND archived_at IS NOT NULL"
    )
    op.execute("DROP INDEX ix_part_org_archived_at")
    op.execute("ALTER TABLE part DROP COLUMN archived_at")

    op.execute("DROP INDEX ix_part_file_pdf_text_fts")
    op.execute("DROP INDEX ix_part_file_org_pn_extracted")
    op.execute("DROP INDEX ix_part_file_org_fname_norm")
    op.execute("DROP INDEX ix_part_file_org_hash")
    op.execute("ALTER TABLE part_file DROP COLUMN pdf_text")
    op.execute("ALTER TABLE part_file DROP COLUMN part_number_extracted")
    op.execute("ALTER TABLE part_file DROP COLUMN filename_normalized")
    op.execute("ALTER TABLE part_file DROP COLUMN file_hash")
