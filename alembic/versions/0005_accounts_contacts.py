"""accounts & contacts — the first real org-scoped domain tables (M1.1).

Adds the CRM core: ``account`` (customer/vendor company) and ``contact`` (a person
at an account, the human a quote is emailed to). Both are org-scoped and inherit
the M0.2 tenancy pattern verbatim — ENABLE + FORCE row-level security with the
``org_isolation`` policy keyed on the transaction-local ``app.current_org_id``
GUC — plus the restricted ``tolera_app`` GRANTs. Both are archived by soft-delete
(``deleted_at``); see DECISIONS.md 2026-06-25 for the four resolved M1.1 decisions
this encodes (nullable ``contact.account_id``, the live-only partial unique email
index, archive=soft-delete, and the salesperson-membership guard).

Cross-org references are made impossible at the DB, not merely RLS-scoped: the
``salesperson_id`` columns FK to ``user_org_membership(user_id, org_id)`` and
``contact.account_id`` FKs to ``account(org_id, id)`` — composite keys that pin
each reference to the row's own org. The app-layer check in ``app.accounts`` still
runs (it additionally requires *active* membership and returns a clean 422); these
FKs are the belt to its braces.

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
            salesperson_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            -- Composite-FK target so contact.account_id can be scoped same-org.
            CONSTRAINT uq_account_org_id_id UNIQUE (org_id, id),
            -- Defense-in-depth for the salesperson tenancy guard (DECISIONS.md
            -- 2026-06-25): a non-null salesperson must be a MEMBER of THIS org.
            -- The app-layer check (app.accounts) additionally requires *active*
            -- status and yields a clean 422; this FK makes same-org a DB invariant.
            CONSTRAINT fk_account_salesperson_membership
                FOREIGN KEY (salesperson_id, org_id)
                REFERENCES user_org_membership(user_id, org_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE contact (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            account_id uuid,
            email citext NOT NULL,
            first_name text,
            last_name text,
            role text,
            phone text,
            phone_ext text,
            notes text,
            salesperson_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            -- A contact's account must be in the SAME org. account_id stays
            -- nullable (RFQ-origin contacts, DECISIONS.md 2026-06-25); a NULL skips
            -- this composite FK (MATCH SIMPLE), so account-less contacts are allowed.
            CONSTRAINT fk_contact_account_same_org
                FOREIGN KEY (org_id, account_id)
                REFERENCES account(org_id, id),
            -- Same-org salesperson membership guard (see account).
            CONSTRAINT fk_contact_salesperson_membership
                FOREIGN KEY (salesperson_id, org_id)
                REFERENCES user_org_membership(user_id, org_id)
        )
        """
    )

    # --- indexes ---
    # The account list/archive paths always filter org_id (RLS) + deleted_at; lead
    # with org_id so they don't seq-scan other tenants' rows as the table grows.
    op.execute("CREATE INDEX ix_account_org_deleted_at ON account (org_id, deleted_at)")
    # Email is unique per org among LIVE rows only — an archived contact's email
    # frees up for reuse (DECISIONS.md 2026-06-25). Account name is intentionally
    # NOT unique (multiple sites/legal entities may share a name).
    op.execute(
        "CREATE UNIQUE INDEX uq_contact_org_email_live "
        "ON contact (org_id, email) WHERE deleted_at IS NULL"
    )
    # Contacts are listed by their parent account; index the FK we filter on.
    op.execute("CREATE INDEX ix_contact_account_id ON contact (account_id)")
    # The cross-account contact list filters org_id (RLS) + deleted_at, like account.
    op.execute("CREATE INDEX ix_contact_org_deleted_at ON contact (org_id, deleted_at)")

    # --- restricted app-role grants (role itself provisioned in 0002 / infra) ---
    # No DELETE: archive/restore are UPDATEs and v1 has no hard-delete route
    # (DECISIONS.md 2026-06-25) — withholding DELETE keeps the blast radius minimal.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON account, contact TO {APP_ROLE}")

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
