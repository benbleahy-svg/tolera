"""Finalized Quote Settings — per-org ``org_quote_settings`` + ``local_pickup``
shipping option (M5.8).

Spec ``#digital-quote-settings`` (the Finalized Quote Settings group) +
``#company-settings-detail``. One row per org (``org_id`` PRIMARY KEY), mirroring
``org_ai_settings`` (migration 0027): every existing org is backfilled with the
all-default row, and the accessor treats an absent row as all-defaults too, so
this is safe for orgs created before the insert.

The row backs two pre-existing read seams (``load_display_settings`` /
``load_quote_content``) that M5.1/M5.4 left returning hardcoded defaults, plus
the M5.8 toggles (Requotes, Checkout Settings, Lead-Time preference, the
Email-Notification recipient matrix, an informational default tax rate).

Also appends ``local_pickup`` to the ``order_shipping_method`` enum — the
fulfilment option the "Allow Local Pickup" checkout setting gates. ``ADD VALUE``
runs in-txn on PG12+ (mirrors migration 0008); ``downgrade`` rebuilds the enum
without the value (mirrors migration 0003) — safe because the value is brand new
(no order can reference it on a same-release downgrade).

Revision ID: 0047_org_quote_settings
Revises: 0046_facilitate_order
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0047_org_quote_settings"
down_revision: str | None = "0046_facilitate_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

#: Display-Settings ``show_*`` toggles → DEFAULT (mirror app.buyer_portal.DisplaySettings).
_SHOW_FLAGS: dict[str, bool] = {
    "show_part_number": True,
    "show_revision": True,
    "show_description": True,
    "show_process": True,
    "show_material": True,
    "show_dimensions": False,
    "show_dfm": False,
    "show_3d": True,
    "show_part_file_name": False,
    "show_thumbnail": False,
    "show_quote_number": True,
    "show_rfq_number": True,
    "show_facility_phone": True,
    "show_facility_website": True,
    "show_digital_quote_link": True,
}

#: Shipping-method values still offered after the enum extension (for downgrade).
_SHIPPING_VALUES_PRE = (
    "bill_at_shipment",
    "use_my_shipping_account",
    "no_shipping_fees",
)


def upgrade() -> None:
    show_cols = "\n            ".join(
        f"{name} boolean NOT NULL DEFAULT {str(default).lower()},"
        for name, default in _SHOW_FLAGS.items()
    )
    op.execute(
        f"""
        CREATE TABLE org_quote_settings (
            org_id uuid PRIMARY KEY REFERENCES organization(id) ON DELETE CASCADE,
            {show_cols}
            total_display text NOT NULL DEFAULT 'price_range',
            preparer text NOT NULL DEFAULT 'salesperson',
            notes_placement text NOT NULL DEFAULT 'above',
            terms text,
            manufacturers_notes text,
            quote_notes text,
            require_terms_acceptance boolean NOT NULL DEFAULT false,
            requotes_enabled boolean NOT NULL DEFAULT true,
            allow_local_pickup boolean NOT NULL DEFAULT true,
            send_order_confirmation_emails boolean NOT NULL DEFAULT true,
            disabled_shipping_methods jsonb NOT NULL DEFAULT '[]'::jsonb,
            lead_time_business_days boolean NOT NULL DEFAULT true,
            notification_recipients jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            default_tax_rate_pct numeric(5, 2),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Spec (mirrors org_ai_settings): a default row per org — backfill existing.
    op.execute(
        "INSERT INTO org_quote_settings (org_id) SELECT id FROM organization "
        "ON CONFLICT (org_id) DO NOTHING"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON org_quote_settings TO {APP_ROLE}")
    op.execute("ALTER TABLE org_quote_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_quote_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON org_quote_settings
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # The "Allow Local Pickup" fulfilment option (spec Checkout Settings). ADD
    # VALUE is not used inside this txn afterwards, so PG12+ accepts it in-txn.
    op.execute("ALTER TYPE order_shipping_method ADD VALUE IF NOT EXISTS 'local_pickup'")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON org_quote_settings")
    op.execute(f"REVOKE ALL ON org_quote_settings FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS org_quote_settings")

    # Preflight: an order placed with local_pickup cannot be cast into the
    # reduced enum. Rather than let the cast fail cryptically mid-DDL — or
    # silently rewrite a real order's shipping method — refuse the downgrade with
    # a clear, actionable error. On a same-release rollback (no such orders yet)
    # this is a no-op and the rebuild proceeds.
    in_use = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM order_ WHERE shipping_method = 'local_pickup'"))
        .scalar()
        or 0
    )
    if in_use:
        raise RuntimeError(
            f"Cannot downgrade 0047: {in_use} order(s) use shipping_method "
            "'local_pickup'. Reassign or archive them before removing the enum value."
        )

    # Rebuild order_shipping_method without local_pickup (mirrors migration 0003).
    members = ", ".join(f"'{v}'" for v in _SHIPPING_VALUES_PRE)
    op.execute("ALTER TYPE order_shipping_method RENAME TO order_shipping_method_old")
    op.execute(f"CREATE TYPE order_shipping_method AS ENUM ({members})")
    op.execute(
        "ALTER TABLE order_ ALTER COLUMN shipping_method TYPE order_shipping_method "
        "USING shipping_method::text::order_shipping_method"
    )
    op.execute("DROP TYPE order_shipping_method_old")
