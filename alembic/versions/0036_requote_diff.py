"""Requote Diff cache (M4.12) — ``quote.requote_diff`` JSONB.

Spec ``#ai-requote-diff`` build-note: "Cache as requote_diff JSONB on the new
Quote." Nullable, regenerable (the ``generate_requote_diff`` task overwrites
it), so no backfill — the ``triage_brief`` (0027) precedent exactly.

Revision ID: 0036_requote_diff
Revises: 0035_geometry_vector
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0036_requote_diff"
down_revision: str | None = "0035_geometry_vector"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("quote", sa.Column("requote_diff", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("quote", "requote_diff")
