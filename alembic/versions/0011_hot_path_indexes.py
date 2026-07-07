"""Hot-path indexes for the quotes list + account filters (codebase review, 2026-07-07).

Every ``/api/quotes/search`` starts with ``deleted_at IS NULL`` — ``account``/
``contact``/``part`` carry an ``(org_id, deleted_at)`` index for exactly that
predicate, but ``quote`` (whose list is the hottest in the product) was missed
when 0008 added soft-delete. Likewise the filter grammar allow-lists
``account_id``/``salesperson_id``/``estimator_id`` and ``/api/accounts`` filters
by ``salesperson_id``, none of which had a supporting index — each filtered
search was a per-org seq scan, and membership/account row changes scanned the
referencing tables for FK enforcement.

Revision ID: 0011_hot_path_indexes
Revises: 0010_component_quantity
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_hot_path_indexes"
down_revision: str | None = "0010_component_quantity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index name, table, columns) — org_id leads: RLS scopes every query by org.
_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_quote_org_deleted_at", "quote", "org_id, deleted_at"),
    ("ix_quote_org_account", "quote", "org_id, account_id"),
    ("ix_quote_org_salesperson", "quote", "org_id, salesperson_id"),
    ("ix_quote_org_estimator", "quote", "org_id, estimator_id"),
    ("ix_account_org_salesperson", "account", "org_id, salesperson_id"),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.execute(f"CREATE INDEX {name} ON {table} ({columns})")


def downgrade() -> None:
    for name, _table, _columns in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
