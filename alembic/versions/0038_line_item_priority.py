"""M5.0 — per-line-item ``priority`` on ``quote_item``.

Spec ``#partview`` routes the estimating screen per line item and makes priority
a line-item field ("numeric priorities seen (6, 7) and blank"). The quotes grid /
filter grammar / "Highest Priority" saved view derive **MAX(priority)** per quote —
one source of truth, no quote-level column (DECISIONS 2026-07-17 *Quote-level
priority home*). Nullable numeric; positive-or-NULL (higher = more urgent).

Revision ID: 0038_line_item_priority
Revises: 0037_value_source
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0038_line_item_priority"
down_revision: str | None = "0037_value_source"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("quote_item", sa.Column("priority", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_quote_item_priority_positive",
        "quote_item",
        "priority IS NULL OR priority >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_quote_item_priority_positive", "quote_item", type_="check")
    op.drop_column("quote_item", "priority")
