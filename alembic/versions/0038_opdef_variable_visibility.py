"""M4.14 — op-def Variables-table eye toggles.

``variable_visibility jsonb {var_name: bool}`` on ``operation_def`` (the
Configure-side eyes) and on ``operation`` (the attach-time snapshot, E4-d
freeze — same posture as the ``cost_formula`` copy, DECISIONS.md 2026-07-08).
Overlaid on the formula-declared ``default_visible`` at report time; existing
rows backfill to the empty map (formula rules until an eye is touched).

Revision ID: 0038_opdef_variable_visibility
Revises: 0037_value_source
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0038_opdef_variable_visibility"
down_revision: str | None = "0037_value_source"
branch_labels: str | None = None
depends_on: str | None = None

_TABLES = ("operation_def", "operation")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "variable_visibility",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "variable_visibility")
