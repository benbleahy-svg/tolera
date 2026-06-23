"""baseline — establishes the migration chain; no domain tables yet.

Tenancy tables (Org / User / UserOrgMembership + RLS) arrive in M0.2. Running
this migration creates Alembic's own ``alembic_version`` table, which the
readiness probe reads back.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
