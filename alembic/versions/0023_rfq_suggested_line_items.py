"""Bulk Create prefill — suggested parts list on the RFQ (M3.4).

Spec ``#wingman`` (pipeline 1: body parse → pre-fills Bulk Create Line Items);
AI-LENS §3. One additive JSONB column on ``request_for_quote`` (the M3.3
lean-extend precedent): the guarded suggestion snapshot the email-body parse
task persists (``{status, prompt_version, parsed_at, dropped, error_code,
items[]}`` — ``app.email_parts._payload``). NULL until the task has run;
suggestions only — line items are created solely by the explicit Accept.

RLS/grants are untouched: the table is already org-scoped (0022) and the app
role already holds INSERT/UPDATE on it.

Revision ID: 0023_rfq_suggested_line_items
Revises: 0022_rfq_ingest
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0023_rfq_suggested_line_items"
down_revision: str | None = "0022_rfq_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "request_for_quote",
        sa.Column("suggested_line_items", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("request_for_quote", "suggested_line_items")
