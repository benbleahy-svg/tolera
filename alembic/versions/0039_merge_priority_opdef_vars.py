"""Merge the two 0038 heads — M5.0 ``line_item_priority`` and M4.14
``opdef_variable_visibility`` both branched off ``0037_value_source`` on parallel
build blocks. No schema change; this only reconciles the alembic tree to a single
head (the standard remedy logged in DECISIONS 2026-07-18).

Revision ID: 0039_merge_priority_opdef_vars
Revises: 0038_line_item_priority, 0038_opdef_variable_visibility
Create Date: 2026-07-18
"""

from __future__ import annotations

revision: str = "0039_merge_priority_opdef_vars"
down_revision: tuple[str, str] | None = (
    "0038_line_item_priority",
    "0038_opdef_variable_visibility",
)
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
