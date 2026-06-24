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

Reversible (CLAUDE.md §5 — reversible migrations only). Postgres has no
``DROP VALUE``, so the directions are asymmetric: ``upgrade`` adds values online
with ``ALTER TYPE … ADD VALUE`` (no table rewrite); ``downgrade`` rebuilds the
type with just the M0.2 values and re-casts the one dependent column
(``user_org_membership.roles``). The downgrade fails by design if any membership
still references an M0.3 role — you cannot roll back past data that depends on
the new values, which is the correct contract rather than silent data loss. On
Postgres 12+ ``ADD VALUE`` runs inside the migration transaction because the new
values are not *used* within it.

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
# The M0.2 starter set the downgrade rebuilds the type back to.
_M02_ROLES = ("admin", "estimator", "salesperson", "viewer")


def upgrade() -> None:
    for role in _NEW_ROLES:
        op.execute(f"ALTER TYPE membership_role ADD VALUE IF NOT EXISTS '{role}'")


def downgrade() -> None:
    # Rebuild the enum with only the M0.2 values and re-point the one column that
    # uses it. Casting through text[] converts the array element-wise; a row that
    # still holds an M0.3 role makes the cast raise (intended — block the rollback
    # rather than drop data). The CHECK on ``roles`` is type-agnostic and survives.
    members = ", ".join(f"'{r}'" for r in _M02_ROLES)
    op.execute("ALTER TYPE membership_role RENAME TO membership_role_old")
    op.execute(f"CREATE TYPE membership_role AS ENUM ({members})")
    op.execute(
        "ALTER TABLE user_org_membership "
        "ALTER COLUMN roles TYPE membership_role[] "
        "USING roles::text[]::membership_role[]"
    )
    op.execute("DROP TYPE membership_role_old")
