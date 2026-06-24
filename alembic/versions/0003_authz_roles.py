"""authz role set — extend ``membership_role`` to the spec personas.

M0.2 shipped a four-value starter enum (``admin``/``estimator``/``salesperson``/
``viewer``). M0.3 reconciles it to the authoritative spec ``#authz``/``#personas``
matrix by **adding** the four missing personas — ``manager`` (Exec/Mgr),
``engineer``, ``material_purchasing``, ``outside_service``. The existing four
spellings are kept verbatim (a rename would break the M0.2 tenancy test and is
painful in Postgres); ``viewer`` is retained as an explicit non-spec read-only
role. See DECISIONS.md 2026-06-24 ("Authorization role set — adopt the 7 spec
personas + retain ``viewer``").

The permission *matrix* that maps these roles to capabilities lives in
``app/authz.py`` (code, not schema) — this migration only widens the type.

Irreversible by design: ``ALTER TYPE … ADD VALUE`` cannot be reversed (Postgres
has no ``DROP VALUE``), so ``downgrade()`` is a deliberate no-op — the added
values are harmless when unused, and removing them would require rebuilding the
type and rewriting every dependent column. Each ADD is ``IF NOT EXISTS`` so the
migration is idempotent. On Postgres 12+ these run inside the migration's
transaction because the new values are not *used* within it.

Revision ID: 0003_authz_roles
Revises: 0002_tenancy_auth
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_authz_roles"
down_revision: str | None = "0002_tenancy_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The personas added in M0.3 (the M0.2 four already exist on the type).
_NEW_ROLES = ("manager", "engineer", "material_purchasing", "outside_service")


def upgrade() -> None:
    for role in _NEW_ROLES:
        op.execute(f"ALTER TYPE membership_role ADD VALUE IF NOT EXISTS '{role}'")


def downgrade() -> None:
    # Intentional no-op: Postgres enum values cannot be dropped without rebuilding
    # the type and every column that uses it. The added values are inert if unused.
    # See this revision's docstring + DECISIONS.md 2026-06-24 (role set).
    pass
