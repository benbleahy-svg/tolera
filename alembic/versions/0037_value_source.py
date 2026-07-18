"""Row provenance for the M4.13 import paths — ``value_source`` enum +
``source``/``source_quote_id`` on router and pricing rows.

Spec ``#ai-quote-assembly`` build note: "Add source ENUM(manual | imported |
ai_drafted) and source_quote_id to OperationInstance and pricing variable
overrides." Existing rows are all estimator-made → backfilled ``manual`` via
the server default. Provenance is org-scoped belt-and-braces (§5): a
composite ``(org_id, source_quote_id) → quote (org_id, id)`` FK makes a
cross-org tag unrepresentable even if RLS were bypassed. ``ON DELETE SET
NULL (source_quote_id)`` (PG15+ column list) clears only the tag — the tag
is provenance, never a hard dependency.

Revision ID: 0037_value_source
Revises: 0036_requote_diff
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0037_value_source"
down_revision: str | None = "0036_requote_diff"
branch_labels: str | None = None
depends_on: str | None = None

_TABLES = ("operation", "pricing_item", "discount", "add_on")


def upgrade() -> None:
    op.execute("CREATE TYPE value_source AS ENUM ('manual', 'imported', 'ai_drafted')")
    source_type = postgresql.ENUM(
        "manual", "imported", "ai_drafted", name="value_source", create_type=False
    )
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("source", source_type, nullable=False, server_default=sa.text("'manual'")),
        )
        op.add_column(
            table,
            sa.Column("source_quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_source_quote",
            table,
            "quote",
            ["org_id", "source_quote_id"],
            ["org_id", "id"],
            ondelete="SET NULL (source_quote_id)",
        )
        # Postgres does not auto-index FK columns; the ON DELETE SET NULL
        # fixup on quote deletion would otherwise seq-scan all four tables.
        # Partial: the overwhelming majority of rows are manual (NULL).
        op.create_index(
            f"ix_{table}_source_quote",
            table,
            ["source_quote_id"],
            postgresql_where=sa.text("source_quote_id IS NOT NULL"),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_source_quote")
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_source_quote")
        op.drop_column(table, "source_quote_id")
        op.drop_column(table, "source")
    op.execute("DROP TYPE value_source")
