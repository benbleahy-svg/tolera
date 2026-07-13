"""part_file.source_file_id — provenance for derived files (M2.5).

Split-PDF page files (and later redacted copies, M2.4, and Part-Library
merges, M2.12) are *derived* from another file of the same part. The
nullable self-referencing FK records that lineage (DECISIONS.md 2026-07-13).
The composite (org_id, id) reference keeps the link same-org at the DB level
(the UNIQUE target exists since 0016); deleting the original clears only
``source_file_id`` (PG15+ column-list SET NULL), never the derived file.

Revision ID: 0017_part_file_source
Revises: 0016_file_annotation_layer
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017_part_file_source"
down_revision: str | None = "0016_file_annotation_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE part_file ADD COLUMN source_file_id uuid")
    op.execute(
        """
        ALTER TABLE part_file ADD CONSTRAINT fk_part_file_source_same_org
            FOREIGN KEY (org_id, source_file_id)
            REFERENCES part_file(org_id, id)
            ON DELETE SET NULL (source_file_id)
        """
    )
    # Derived files are looked up by their source (e.g. "pages split from X").
    op.execute("CREATE INDEX ix_part_file_source_file_id ON part_file(source_file_id)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_part_file_source_file_id")
    op.execute("ALTER TABLE part_file DROP CONSTRAINT fk_part_file_source_same_org")
    op.execute("ALTER TABLE part_file DROP COLUMN source_file_id")
