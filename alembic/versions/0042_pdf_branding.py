"""Quote/Order PDF branding + artifact keys (M5.4).

The white-label quote/order PDF (WeasyPrint) needs the shop's **Facility
Information** to render (spec ``#company-settings-detail`` "logo on PDFs") — none
of it lives on ``organization`` yet (kept lean, DECISIONS.md 2026-06-24), so M5.4
(the consuming block) adds it via this reversible migration:

* ``logo_object_key`` — object-storage key of the org logo, embedded as an inline
  data-URI on the PDF (no external asset; CSP-clean, spec :603).
* ``brand_accent_color`` — hex accent (e.g. ``#1a3c5e``) for the PDF header rule.
* ``facility_phone`` / ``facility_website`` — the Facility-Phone / Facility-Website
  Display-Settings toggles read from here.
* ``facility_address`` — supplier address for the §14-UStG invoice block.

And the artifact location for the rendered PDF (spec :603 "URL on the Quote
model"; the send-time snapshot is written by M5.5): ``pdf_object_key`` on both
``quote`` and ``order_``.

The settings **UI** to edit these fields is M5.8; M5.4 only renders them. All
columns are nullable — a brand-new org renders a plain white-label document.

Revision ID: 0042_pdf_branding
Revises: 0041_order_checkout
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0042_pdf_branding"
down_revision: str | None = "0041_order_checkout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Facility Information for the white-label PDF (spec #company-settings) --
    op.execute("ALTER TABLE organization ADD COLUMN logo_object_key text")
    op.execute("ALTER TABLE organization ADD COLUMN brand_accent_color text")
    op.execute("ALTER TABLE organization ADD COLUMN facility_phone text")
    op.execute("ALTER TABLE organization ADD COLUMN facility_website text")
    op.execute("ALTER TABLE organization ADD COLUMN facility_address text")

    # --- Rendered-PDF artifact location (snapshot written at send, M5.5) -------
    op.execute("ALTER TABLE quote ADD COLUMN pdf_object_key text")
    op.execute("ALTER TABLE order_ ADD COLUMN pdf_object_key text")


def downgrade() -> None:
    op.execute("ALTER TABLE order_ DROP COLUMN IF EXISTS pdf_object_key")
    op.execute("ALTER TABLE quote DROP COLUMN IF EXISTS pdf_object_key")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS facility_address")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS facility_website")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS facility_phone")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS brand_accent_color")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS logo_object_key")
