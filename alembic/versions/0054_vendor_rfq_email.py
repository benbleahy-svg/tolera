"""Vendor RFQ outbound email + email-reply ingest (M6.5).

M6.4 composes a batch and mints the per-vendor portal token but explicitly does not
mail it ("M6.5 owns the transport"). This migration adds the columns that transport
and its return leg need (spec ``#vendor-rfq`` → "Outbound RFQ email" +
"Email-channel ingest (Lens)"):

* ``vendor_rfq_recipient.sent_message_id`` — the RFC 2822 ``Message-ID`` we minted for
  this vendor's copy. Kept so a reply can be threaded (``In-Reply-To``/``References``)
  on the follow-up M6.6 sends; it is deliberately **not** the matching key — the spec
  matches a reply by RFQ reference number, never by sender or thread, because vendors
  reply from shared inboxes.
* ``vendor_rfq_response.ai_extracted`` / ``verified`` — the spec's own build-implication
  fields (``VendorQuoteResponse(… ai_extracted BOOL, verified BOOL, applied BOOL)``;
  ``applied`` is the existing ``applied_at``). A Lens-extracted email reply is born
  ``ai_extracted = true, verified = false`` and renders as "AI extracted — verify";
  **M6.6's estimator confirmation is what flips ``verified``**, and only a verified
  response may be applied to costing. This is the suggestion-only invariant
  (CLAUDE.md §5) expressed in the schema rather than in a code path.
  Existing rows are portal submissions a human typed, so they backfill ``verified =
  true`` / ``ai_extracted = false`` — the defaults for the portal channel going forward.
* ``vendor_rfq_response.email_message_id`` + a partial unique index — webhook
  idempotency. Mailgun retries on any non-2xx, so a redelivered reply must be a no-op
  rather than a second response; this mirrors ``uq_rfq_org_message_id`` (0031).
* ``vendor_rfq_response.email_body_text`` — the reply's plain-text body, kept as the
  corpus the never-hallucinate guard checks extracted prices against, so a re-run of
  the extraction does not need the raw MIME back.

Renumbered to 0054 on top of M3.13's ``0053_part_file_scan_status``, which landed on
``develop`` while this block was building (the same single-head resolution M6.3 made
against M6.2). The two are complementary: that one adds the AV scan state this block's
vendor forward gate reads, this one the email columns.

Reversible: ``downgrade`` drops every added column and the index. No enum is touched —
the outbound RFQ email is *system-generated* per the spec, so it needs no
``email_template_type`` value (a PG enum value cannot be dropped, which would have
broken the reversible-migration invariant).

Revision ID: 0054_vendor_rfq_email
Revises: 0053_part_file_scan_status
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0054_vendor_rfq_email"
down_revision: str | None = "0053_part_file_scan_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- outbound: the message-id of this vendor's copy ----------------------
    op.execute("ALTER TABLE vendor_rfq_recipient ADD COLUMN sent_message_id text")

    # --- inbound: the AI-extracted / verify pair + idempotency ---------------
    op.execute(
        "ALTER TABLE vendor_rfq_response "
        "ADD COLUMN ai_extracted boolean NOT NULL DEFAULT false, "
        "ADD COLUMN verified boolean NOT NULL DEFAULT false, "
        "ADD COLUMN email_message_id text, "
        "ADD COLUMN email_body_text text"
    )
    # Every response that exists today came through the portal — a human typed it, so
    # there is nothing to verify. Stamp them so "verified" means the same thing for
    # both channels from the first migration onward.
    op.execute("UPDATE vendor_rfq_response SET verified = true WHERE source = 'portal'")

    # Idempotency key for the inbound webhook. Partial: portal responses have no
    # message id and must not collide with each other on NULL.
    op.execute(
        "CREATE UNIQUE INDEX uq_vendor_rfq_response_org_message_id "
        "ON vendor_rfq_response (org_id, email_message_id) "
        "WHERE email_message_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_vendor_rfq_response_org_message_id")
    op.execute(
        "ALTER TABLE vendor_rfq_response "
        "DROP COLUMN IF EXISTS email_body_text, "
        "DROP COLUMN IF EXISTS email_message_id, "
        "DROP COLUMN IF EXISTS verified, "
        "DROP COLUMN IF EXISTS ai_extracted"
    )
    op.execute("ALTER TABLE vendor_rfq_recipient DROP COLUMN IF EXISTS sent_message_id")
