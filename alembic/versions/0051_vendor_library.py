"""vendor library — the Supplier Directory's entities (M6.3).

Adds ``vendor`` (an outside-process supplier) and ``vendor_contact`` (a quoting
contact at one), the data model behind the spec's Supplier Directory
(``#vendor-rfq`` → "Supplier Directory (nav: Suppliers)") and the counterparties
the M6.4 batch-send modal will address.

**Why not ``account.type = 'vendor'``**: the spec is explicit that "vendors are
separate entities from Accounts (customers) — distinct data model, separate auth
scope". Vendors carry capabilities, portal credentials and response history that
have no meaning on a customer, and the (M6.2) vendor portal authenticates against
a token scope that must never be able to reach customer rows.

Both tables inherit the M0.2 tenancy pattern verbatim — ENABLE + FORCE row-level
security with the ``org_isolation`` policy keyed on the transaction-local
``app.current_org_id`` GUC — plus the restricted ``tolera_app`` GRANTs (no DELETE:
archive is a soft-delete UPDATE, per the M1.1 convention). Cross-org references
are impossible at the DB, not merely RLS-scoped: ``vendor_contact`` FKs the
composite ``vendor(org_id, id)``, exactly as ``contact`` does to ``account``.

DACH: ``vendor.vat_id`` is the EU vendor **USt-IdNr** required by
DACH-DELTA-LAYER §5 ("Vendor RFQ / Collaboration: German vendor portal; EU vendor
VAT-ID; GDPR data-handling for external parties"). No VIES validation hangs off it
here — that is the customer-side (Account) path.

``capabilities`` is JSONB (``{"processes": [...], "materials": [...]}``) rather
than two join tables: the tags are free-text chips typed by estimators and read
back whole for the directory filter and (M6.4) the vendor ranking; a GIN index
keeps the containment filter indexed.

``downgrade`` drops both policies + grants, then the tables (child first) and the
``vendor_status`` enum — fully reversible, no data migration to unwind.

Revision ID: 0051_vendor_library
Revises: 0050_vendor_rfq
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0051_vendor_library"
down_revision: str | None = "0050_vendor_rfq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

# Both new tables are org_id-keyed and isolated exactly like ``account`` (M1.1):
# the policy reads the GUC set by app.db.org_scoped_session; an unset GUC yields
# NULL, so every row fails the predicate → zero rows for an unpinned connection.
_ORG_SCOPED_TABLES = ("vendor", "vendor_contact")


def upgrade() -> None:
    # --- enum ---
    # Active/Inactive is the spec's detail-view toggle — a *live* row excluded from
    # sourcing. It is orthogonal to deleted_at (archived = out of the directory).
    op.execute("CREATE TYPE vendor_status AS ENUM ('active', 'inactive')")

    # --- tables ---
    op.execute(
        """
        CREATE TABLE vendor (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            address text,
            -- EU vendor USt-IdNr (DACH-DELTA-LAYER §5).
            vat_id text,
            phone text,
            website text,
            -- Non-NULL ⇒ identity owned by the connected ERP (one-way ERP → BF);
            -- app.vendors rejects writes to the identity fields of such a row.
            erp_vendor_id text,
            status vendor_status NOT NULL DEFAULT 'active',
            -- {"processes": [...], "materials": [...]}, tags normalized lowercase.
            capabilities jsonb NOT NULL
                DEFAULT '{"processes": [], "materials": []}'::jsonb,
            -- INTERNAL ONLY — never serialized into a vendor-facing payload.
            notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            -- Composite-FK target so vendor_contact.vendor_id is same-org pinned.
            CONSTRAINT uq_vendor_org_id_id UNIQUE (org_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE vendor_contact (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            vendor_id uuid NOT NULL,
            name text,
            email citext NOT NULL,
            phone text,
            -- The addressee of the outbound RFQ email (M6.5); cc rides along.
            is_primary boolean NOT NULL DEFAULT false,
            cc boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            -- A contact's vendor must be in the SAME org — a DB invariant, not
            -- merely an RLS scope (mirrors fk_contact_account_same_org, M1.1).
            CONSTRAINT fk_vendor_contact_vendor_same_org
                FOREIGN KEY (org_id, vendor_id)
                REFERENCES vendor(org_id, id)
        )
        """
    )

    # --- indexes ---
    # The directory list always filters org_id (RLS) + deleted_at; lead with org_id
    # so it doesn't seq-scan other tenants' rows as the table grows.
    op.execute("CREATE INDEX ix_vendor_org_deleted_at ON vendor (org_id, deleted_at)")
    # Re-importing the same ERP record must UPDATE, never duplicate. Live rows only,
    # so an archived vendor frees its ERP id again. Vendor *name* is intentionally
    # NOT unique (multiple sites/legal entities may share one).
    op.execute(
        "CREATE UNIQUE INDEX uq_vendor_org_erp_id_live ON vendor (org_id, erp_vendor_id) "
        "WHERE deleted_at IS NULL AND erp_vendor_id IS NOT NULL"
    )
    # The capabilities filter is a JSONB containment probe — GIN keeps it indexed.
    op.execute("CREATE INDEX ix_vendor_capabilities ON vendor USING gin (capabilities)")
    # Contacts are always listed by their parent vendor.
    op.execute("CREATE INDEX ix_vendor_contact_vendor_id ON vendor_contact (vendor_id)")
    # One address per vendor among live rows; an archived contact frees it for reuse
    # (the live-only partial-unique convention from contact, M1.1).
    op.execute(
        "CREATE UNIQUE INDEX uq_vendor_contact_vendor_email_live "
        "ON vendor_contact (vendor_id, email) WHERE deleted_at IS NULL"
    )

    # --- restricted app-role grants (role itself provisioned in 0002 / infra) ---
    # No DELETE: archive/restore are UPDATEs and there is no hard-delete route
    # (M1.1 convention) — withholding DELETE keeps the blast radius minimal.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON vendor, vendor_contact TO {APP_ROLE}")

    # --- row-level security (identical pattern to account/contact, M1.1) ---
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
    op.execute(f"REVOKE ALL ON vendor, vendor_contact FROM {APP_ROLE}")
    # vendor_contact references vendor, so drop it first.
    op.execute("DROP TABLE IF EXISTS vendor_contact")
    op.execute("DROP TABLE IF EXISTS vendor")
    op.execute("DROP TYPE IF EXISTS vendor_status")
