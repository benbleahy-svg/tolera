"""org privacy-policy (Datenschutzerklärung) URL (M6.9).

DACH-DELTA-LAYER §5 requires "Impressum + Datenschutzerklärung on all
customer-facing surfaces". M5.9 built the Impressum out of fields the org already
had (``commercial_register`` / ``ust_id_nr`` / address). The Datenschutzerklärung
has no such source: it is a **document the shop publishes**, and its URL is not
derivable from anything in the schema.

Inventing a URL is exactly what CLAUDE.md §6.4 forbids, so this adds the one
nullable column that lets a shop supply it. Null renders no link — the same
"render only what's present, never invent" contract ``app/impressum.py`` already
follows for a missing commercial register.

Reversible: one nullable column, no data migration.

Revision ID: 0057_org_privacy_policy_url
Revises: 0056_export_control_audit
Create Date: 2026-07-19

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0057_org_privacy_policy_url"
down_revision: str | None = "0056_export_control_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE organization ADD COLUMN privacy_policy_url text")


def downgrade() -> None:
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS privacy_policy_url")
