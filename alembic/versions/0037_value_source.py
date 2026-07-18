"""Row provenance for the M4.13 import paths — ``value_source`` enum +
``source``/``source_quote_id`` on router and pricing rows.

Spec ``#ai-quote-assembly`` build note: "Add source ENUM(manual | imported |
ai_drafted) and source_quote_id to OperationInstance and pricing variable
overrides." Existing rows are all estimator-made → backfilled ``manual`` via
the server default. ``source_quote_id`` is a plain FK to ``quote`` with
ON DELETE SET NULL (the tag is provenance, never a hard dependency).

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
            sa.Column(
                "source_quote_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("quote.id", ondelete="SET NULL", name=f"fk_{table}_source_quote"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "source_quote_id")
        op.drop_column(table, "source")
    op.execute("DROP TYPE value_source")
