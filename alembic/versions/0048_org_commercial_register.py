"""Org commercial-register field for the Impressum footer (M5.9).

Customer-facing quote/order PDFs and quote emails must carry a legal Impressum:
the shop's legal name, address, commercial-register entry (Handelsregister — DE
HRB / AT Firmenbuch / CH HR) and USt-IdNr (``DACH-DELTA §Email/§37``; §5 TMG /
§14 UStG). USt-IdNr already exists on ``organization``; this adds the free-text
commercial register.

Free text (not structured court + number) so a single column stays DACH-generic.
Display-only — it never enters ``resolve_order_tax``/Kalk. Nullable → every
existing org is safe and a bare org renders no Impressum block. Reversible.

Revision ID: 0048_org_commercial_register
Revises: 0047_org_quote_settings
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0048_org_commercial_register"
down_revision: str | None = "0047_org_quote_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE organization ADD COLUMN commercial_register varchar")


def downgrade() -> None:
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS commercial_register")
