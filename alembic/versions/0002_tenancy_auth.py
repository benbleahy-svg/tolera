"""tenancy + auth spine — identity tables, the restricted app role, and RLS.

Creates the M0.2 core (``organization`` / ``app_user`` / ``user_org_membership``
with a multi-role array, plus the throwaway ``note`` entity), grants the
restricted ``tolera_app`` role, and declares the row-level-security policies that
make org isolation a *database* guarantee. See DECISIONS.md 2026-06-24
("RLS enforcement mechanism + DB role split", "Membership role cardinality").

Role provisioning is infra (docker initdb / test fixture / prod runbook set the
LOGIN password); this migration only *ensures the role exists* so its GRANTs are
self-contained, and never embeds a password. The role is intentionally NOT
dropped on downgrade (roles are cluster-scoped infra, not schema).

Revision ID: 0002_tenancy_auth
Revises: 0001_baseline
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_tenancy_auth"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

# Org-scoped tables get ENABLE + FORCE RLS and an org_id-keyed policy. The policy
# reads the transaction-local GUC set by app.db.org_scoped_session; an unset GUC
# (missing_ok => true) yields NULL, so every row fails the predicate → zero rows.
_ORG_SCOPED_TABLES = ("user_org_membership", "note")


def upgrade() -> None:
    # --- extensions ---
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # --- enums ---
    op.execute("CREATE TYPE org_country AS ENUM ('DE', 'AT', 'CH')")
    op.execute(
        "CREATE TYPE membership_role AS ENUM ('admin', 'estimator', 'salesperson', 'viewer')"
    )
    op.execute("CREATE TYPE membership_status AS ENUM ('active', 'pending', 'disabled')")

    # --- tables ---
    op.execute(
        """
        CREATE TABLE organization (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            slug text NOT NULL UNIQUE,
            country org_country NOT NULL DEFAULT 'DE',
            currency char(3) NOT NULL DEFAULT 'EUR',
            locale text NOT NULL DEFAULT 'de-DE',
            clerk_org_id text UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_organization_currency CHECK (currency IN ('EUR', 'CHF'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE app_user (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email citext NOT NULL UNIQUE,
            first_name text,
            last_name text,
            clerk_user_id text UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE user_org_membership (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES app_user(id),
            org_id uuid NOT NULL REFERENCES organization(id),
            roles membership_role[] NOT NULL,
            status membership_status NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_membership_user_org UNIQUE (user_id, org_id),
            CONSTRAINT ck_membership_roles_nonempty CHECK (cardinality(roles) > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE note (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            body text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    # --- restricted app role (ensure-exists only; password set by infra) ---
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    # Harden unconditionally: a pre-provisioned role (initdb / runbook) must also
    # be NOSUPERUSER + NOBYPASSRLS, or it would silently bypass the RLS policies
    # below. (APP_ROLE is a constant, not user input — no injection surface.)
    op.execute(f"ALTER ROLE {APP_ROLE} NOSUPERUSER NOBYPASSRLS")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    # NB: app_user is deliberately excluded — it is global identity (email,
    # clerk_user_id) with no org_id and thus no org RLS, so granting the app role
    # DML on it would expose every user's PII across orgs. M0.2 needs no app-role
    # access to it (auth reads the JWT claims, not the table); a later block that
    # must surface users will mediate via user_org_membership joins / a scoped view.
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON "
        f"organization, user_org_membership, note TO {APP_ROLE}"
    )
    # Readiness probe (served as the app role) reports the applied revision.
    op.execute(f"GRANT SELECT ON alembic_version TO {APP_ROLE}")

    # --- row-level security ---
    # ``organization`` is keyed on its own id (an org sees only itself).
    op.execute("ALTER TABLE organization ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_self_isolation ON organization
            USING (id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (id = current_setting('app.current_org_id', true)::uuid)
        """
    )
    # ``user_org_membership`` and ``note`` are keyed on org_id.
    for table in _ORG_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table}
                USING (org_id = current_setting('app.current_org_id', true)::uuid)
                WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in _ORG_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
    op.execute("DROP POLICY IF EXISTS org_self_isolation ON organization")

    op.execute(f"REVOKE ALL ON organization, user_org_membership, note FROM {APP_ROLE}")
    op.execute(f"REVOKE SELECT ON alembic_version FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")

    op.execute("DROP TABLE IF EXISTS note")
    op.execute("DROP TABLE IF EXISTS user_org_membership")
    op.execute("DROP TABLE IF EXISTS app_user")
    op.execute("DROP TABLE IF EXISTS organization")

    op.execute("DROP TYPE IF EXISTS membership_status")
    op.execute("DROP TYPE IF EXISTS membership_role")
    op.execute("DROP TYPE IF EXISTS org_country")

    # pgcrypto + citext are database-wide infra (like the tolera_app role): other
    # objects may depend on them, so they are intentionally left in place.
