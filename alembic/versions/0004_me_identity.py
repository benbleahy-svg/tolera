"""me-identity — a scoped SECURITY DEFINER read for ``GET /api/me`` (M0.4).

The app shell's session bootstrap must surface the caller's own identity
(``app_user`` — which the restricted ``tolera_app`` role has *no* grant on) and
their memberships *across all orgs* (``user_org_membership``/``organization`` —
under FORCE row-level security keyed to the single active org). Neither is
reachable through the normal request path, by M0.2's deliberate design (see the
0002 grant comment: *"a later block that must surface users will mediate via …
a scoped view"*). This is that block.

Mechanism (DECISIONS.md 2026-06-24 "/api/me cross-org identity read"): one
``SECURITY DEFINER`` function, ``app_current_identity()``, owned by a dedicated
``BYPASSRLS`` role ``tolera_identity`` — a plain table-owner would *still* be
subject to FORCE RLS, so the definer must hold ``BYPASSRLS``. The function takes
**no argument**: it reads the caller from the transaction-local
``app.current_user_id`` GUC (stamped by ``app.deps.get_session`` from the verified
principal) and returns only that user's rows. Binding to the GUC rather than a
parameter means the *database* enforces "a caller can only ever read their own
identity" — there is no argument to aim at another user. ``tolera_app`` is granted
nothing but ``EXECUTE`` (revoked from ``PUBLIC``). Every table's RLS is left
exactly as M0.2 set it — the only privileged path is this one audited function.

Role provisioning is infra (per the 0002 ``tolera_app`` precedent): the migration
*ensures the role exists* and self-provisions its attributes where it has the
privilege (dev/test owner is superuser); in prod the ``tolera_identity`` role —
and the migration role's membership in it (needed for ``ALTER FUNCTION … OWNER``)
— are provisioned by the runbook. The role is cluster infra: not dropped on
downgrade.

Reversible (CLAUDE.md §5): ``downgrade`` drops the function and revokes the
identity role's grants; the role itself is left in place.

Revision ID: 0004_me_identity
Revises: 0003_authz_roles
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_me_identity"
down_revision: str | None = "0003_authz_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
IDENTITY_ROLE = "tolera_identity"

# The scoped identity read. Takes NO argument: it reads the caller from the
# transaction-local ``app.current_user_id`` GUC (set by app.deps.get_session from
# the verified principal). Binding to the GUC rather than a function argument means
# the database — not application discipline — guarantees a caller can only ever read
# their own identity: there is no parameter to aim at another user. An unset GUC
# yields NULL → zero rows → a null ``user`` (the API maps that to 401). STABLE,
# read-only.
_FUNCTION_BODY = """
CREATE OR REPLACE FUNCTION app_current_identity()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
  WITH caller AS (
    SELECT current_setting('app.current_user_id', true)::uuid AS user_id
  )
  SELECT jsonb_build_object(
    'user', (
      SELECT jsonb_build_object(
        'id', u.id,
        'email', u.email,
        'first_name', u.first_name,
        'last_name', u.last_name
      )
      FROM app_user u
      WHERE u.id = (SELECT user_id FROM caller)
    ),
    'memberships', COALESCE((
      SELECT jsonb_agg(
        jsonb_build_object(
          'org_id', o.id,
          'org_name', o.name,
          'org_slug', o.slug,
          'country', o.country::text,
          'currency', o.currency,
          'locale', o.locale,
          'roles', to_jsonb(m.roles),
          'status', m.status::text
        )
        ORDER BY o.name
      )
      FROM user_org_membership m
      JOIN organization o ON o.id = m.org_id
      WHERE m.user_id = (SELECT user_id FROM caller)
    ), '[]'::jsonb)
  );
$fn$
"""


def upgrade() -> None:
    # --- dedicated BYPASSRLS definer role (ensure-exists; attributes self-set
    #     where privileged, else provisioned by infra — per 0002's tolera_app) ---
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{IDENTITY_ROLE}') THEN
                CREATE ROLE {IDENTITY_ROLE} NOLOGIN NOSUPERUSER BYPASSRLS;
            END IF;
        END
        $$
        """
    )
    # Harden unconditionally: a pre-provisioned role must be NOLOGIN (cannot be
    # connected to) + NOSUPERUSER + BYPASSRLS (so the definer escapes FORCE RLS).
    op.execute(f"ALTER ROLE {IDENTITY_ROLE} NOLOGIN NOSUPERUSER BYPASSRLS")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {IDENTITY_ROLE}")
    # The definer needs column access; BYPASSRLS handles row visibility.
    op.execute(f"GRANT SELECT ON app_user, organization, user_org_membership TO {IDENTITY_ROLE}")

    # --- the scoped function ---
    op.execute(_FUNCTION_BODY)
    # New functions grant EXECUTE to PUBLIC by default — revoke, then grant only
    # to the request-serving role (a SECURITY DEFINER fn must not be world-callable).
    op.execute("REVOKE ALL ON FUNCTION app_current_identity() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_current_identity() TO {APP_ROLE}")
    # Run the body with the definer's (BYPASSRLS) privileges.
    op.execute(f"ALTER FUNCTION app_current_identity() OWNER TO {IDENTITY_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_current_identity()")
    op.execute(f"REVOKE SELECT ON app_user, organization, user_org_membership FROM {IDENTITY_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {IDENTITY_ROLE}")
    # tolera_identity is cluster infra (like tolera_app) — intentionally not dropped.
