"""accounts & contacts — the first real org-scoped domain tables (M1.1).

Adds the CRM core: ``account`` (customer/vendor company) and ``contact`` (a person
at an account, the human a quote is emailed to). Both are org-scoped and inherit
the M0.2 tenancy pattern verbatim — ENABLE + FORCE row-level security with the
``org_isolation`` policy keyed on the transaction-local ``app.current_org_id``
GUC — plus the restricted ``tolera_app`` GRANTs. Both are archived by soft-delete
(``deleted_at``); see DECISIONS.md 2026-06-25 for the four resolved M1.1 decisions
this encodes (nullable ``contact.account_id``, the live-only partial unique email
index, archive=soft-delete, and the app-layer salesperson-membership guard — the
last is enforced in ``app.accounts``, not here, since RLS can't see ``app_user``).

The column set is deliberately **lean** (DECISIONS.md 2026-06-24 "M0.5 seed
scope"): the VAT/tax/ERP/billing-address fields the canonical ``account`` carries
in DB-SCHEMA.sql are deferred to their consuming blocks (M1.11/M5/M6), each added
by its own reversible migration.

Revision ID: 0005_accounts_contacts
Revises: 0004_me_identity
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_accounts_contacts"
down_revision: str | None = "0004_me_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

# Both new tables are org_id-keyed and isolated exactly like ``note`` (M0.2): the
# policy reads the GUC set by app.db.org_scoped_session; an unset GUC yields NULL,
# so every row fails the predicate → zero rows for an unpinned connection.
_ORG_SCOPED_TABLES = ("account", "contact")


def upgrade() -> None:
    # --- enum ---
    op.execute("CREATE TYPE account_type AS ENUM ('customer', 'vendor')")

    # --- tables ---
    op.execute(
        """
        CREATE TABLE account (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            type account_type NOT NULL DEFAULT 'customer',
            email citext,
            phone text,
            phone_ext text,
            website text,
            notes text,
            salesperson_id uuid REFERENCES app_user(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE contact (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            account_id uuid REFERENCES account(id),
            email citext NOT NULL,
            first_name text,
            last_name text,
            role text,
            phone text,
            phone_ext text,
            notes text,
            salesperson_id uuid REFERENCES app_user(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )

    # --- indexes ---
    # Email is unique per org among LIVE rows only — an archived contact's email
    # frees up for reuse (DECISIONS.md 2026-06-25). Account name is intentionally
    # NOT unique (multiple sites/legal entities may share a name).
    op.execute(
        "CREATE UNIQUE INDEX uq_contact_org_email_live "
        "ON contact (org_id, email) WHERE deleted_at IS NULL"
    )
    # Contacts are listed by their parent account; index the FK we filter on.
    op.execute("CREATE INDEX ix_contact_account_id ON contact (account_id)")

    # --- restricted app-role grants (role itself provisioned in 0002 / infra) ---
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON account, contact TO {APP_ROLE}")

    # --- row-level security (identical pattern to note, M0.2) ---
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
    op.execute(f"REVOKE ALL ON account, contact FROM {APP_ROLE}")
    # contact references account, so drop it first.
    op.execute("DROP TABLE IF EXISTS contact")
    op.execute("DROP TABLE IF EXISTS account")
    op.execute("DROP TYPE IF EXISTS account_type")
