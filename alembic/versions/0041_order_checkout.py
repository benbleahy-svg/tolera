"""Orders + checkout (M5.2) & DACH tax profile (M5.3).

Adds the quote spine's terminal entity — ``order_`` (``order`` is reserved) +
``order_line`` — created by buyer-portal PO checkout (M5.2) or facilitation
(M5.7), plus ``order_counter`` (per-org sequential number, mirrors
``quote_counter``). Money is integer minor units + explicit currency (the total
boundary); the §14-UStG tax breakdown is persisted from ``app.vat_service``.

Extends ``organization`` with the M5.3 tax profile: ``ust_id_nr`` (the shop's
own VAT-ID, carried onto §13b reverse-charge invoices) and
``is_kleinunternehmer`` (§19 — suppresses VAT lines).

All three new tables are org-scoped + RLS like every tenant table. No order
status lifecycle in v1 (ERP-owned) — only a nullable ``shipped_at``.

Revision ID: 0041_order_checkout
Revises: 0040_quote_token
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041_order_checkout"
down_revision: str | None = "0040_quote_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_ORG_SCOPED_TABLES = ("order_counter", "order_", "order_line")


def upgrade() -> None:
    # --- M5.3 org tax profile -------------------------------------------------
    op.execute("ALTER TABLE organization ADD COLUMN ust_id_nr text")
    op.execute(
        "ALTER TABLE organization ADD COLUMN is_kleinunternehmer boolean NOT NULL DEFAULT false"
    )

    # --- enums ----------------------------------------------------------------
    op.execute("CREATE TYPE order_source AS ENUM ('buyer_portal', 'facilitated')")
    op.execute(
        "CREATE TYPE order_shipping_method AS ENUM "
        "('bill_at_shipment', 'use_my_shipping_account', 'no_shipping_fees')"
    )

    # --- order_counter (per-org atomic sequential number allocator) -----------
    op.execute(
        """
        CREATE TABLE order_counter (
            org_id uuid PRIMARY KEY REFERENCES organization(id),
            last_number bigint NOT NULL DEFAULT 0
        )
        """
    )

    # --- order_ (reserved word → trailing underscore) -------------------------
    op.execute(
        """
        CREATE TABLE order_ (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            number text NOT NULL,
            source order_source NOT NULL,
            quote_id uuid NOT NULL,
            account_id uuid,
            contact_id uuid,
            po_number text,
            company_name text,
            billing_address text,
            notes text,
            shipping_method order_shipping_method,
            currency varchar(3) NOT NULL,
            net_minor bigint NOT NULL,
            vat_minor bigint NOT NULL,
            gross_minor bigint NOT NULL,
            vat_rate_pct numeric(7,4) NOT NULL,
            vat_label text,
            reverse_charge boolean NOT NULL DEFAULT false,
            kleinunternehmer boolean NOT NULL DEFAULT false,
            tax_note text,
            supplier_ust_id_nr text,
            buyer_ust_id_nr text,
            tax_rate_lines jsonb,
            vies_valid boolean,
            vies_checked_at timestamptz,
            shipped_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_order_currency_dach CHECK (currency IN ('EUR', 'CHF')),
            CONSTRAINT uq_order_org_number UNIQUE (org_id, number),
            CONSTRAINT uq_order_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_order_quote_org
                FOREIGN KEY (org_id, quote_id) REFERENCES quote(org_id, id),
            CONSTRAINT fk_order_account_org
                FOREIGN KEY (org_id, account_id) REFERENCES account(org_id, id),
            CONSTRAINT fk_order_contact_org
                FOREIGN KEY (org_id, contact_id) REFERENCES contact(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_order_org_created ON order_ (org_id, created_at)")

    # --- order_line -----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE order_line (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            order_id uuid NOT NULL,
            quote_item_id uuid NOT NULL,
            component_id uuid NOT NULL,
            quantity integer NOT NULL,
            unit_price_minor bigint NOT NULL,
            total_price_minor bigint NOT NULL,
            expedite_option_id uuid,
            expedites_fee_minor bigint NOT NULL DEFAULT 0,
            shipping_price_minor bigint,
            lead_time_days integer,
            ships_on date,
            add_ons jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_order_line_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_order_line_order_org
                FOREIGN KEY (org_id, order_id)
                REFERENCES order_(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_order_line_quote_item_org
                FOREIGN KEY (org_id, quote_item_id)
                REFERENCES quote_item(org_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_order_line_org_order ON order_line (org_id, order_id)")

    # --- grants + RLS (identical pattern to quote/quote_token) ----------------
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON order_counter TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON order_ TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON order_line TO {APP_ROLE}")
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
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS order_line")
    op.execute("DROP TABLE IF EXISTS order_")
    op.execute("DROP TABLE IF EXISTS order_counter")
    op.execute("DROP TYPE IF EXISTS order_shipping_method")
    op.execute("DROP TYPE IF EXISTS order_source")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS is_kleinunternehmer")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS ust_id_nr")
