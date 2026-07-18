"""Facilitate Order Updates opt-in flag (M5.6).

The Orders tab gates its **Edit order** row-action on the shop having opted into
the 2025 order-editing feature (spec ``#orderslist`` "Edit order … only if
Facilitate Order Updates is enabled + order has no shipments yet"). The setting
lives at the org level; the editing drawer itself is M5.7 and the settings **UI**
that flips this toggle is M5.8. M5.6 only needs the column to exist so the list
can compute the affordance (``facilitate_order_updates AND shipped_at IS NULL``).

Default **off** — order editing is opt-in (a facility must consciously enable
mutating a placed order). NOT NULL with a ``false`` server default, so every
existing org is safe. Reversible.

Revision ID: 0044_facilitate_order_updates
Revises: 0043_purchased_components
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0044_facilitate_order_updates"
down_revision: str | None = "0043_purchased_components"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organization "
        "ADD COLUMN facilitate_order_updates boolean NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS facilitate_order_updates")
