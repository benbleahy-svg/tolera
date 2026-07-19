"""ClamAV upload scanning + quarantine (M3.13) — the malware verdict on ``part_file``.

Customers upload arbitrary files that staff download and forward to vendors, and since
M3.3 (Mailgun ingest, PR #40) anyone who knows an org's ingest address can put bytes in
that path. ``DECISIONS.md`` 2026-06-25 (RESOLVED 2026-07-17) settles it: **async ClamAV
in our own infrastructure** — a Celery task scans each stored file, this column carries
the verdict, and download/forward are blocked until it reads ``clean``. (A cloud
scanning API was rejected: shipping a customer's print to a third-party scanner adds a
GDPR subprocessor.)

* ``scan_status`` ``ENUM(pending|clean|infected|error)`` — the charter's four states.
  ``clean``/``infected`` are terminal verdicts; ``error`` means the scan could not be
  completed (clamd outage) and is retryable. **Existing rows are backfilled
  ``pending``, not ``clean``**: they predate scanning, so their verdict is genuinely
  unknown, and an unknown verdict must never masquerade as clean. In a deployment with
  ``AV_SCANNER=none`` the gate ignores ``pending`` (nothing would ever move it), so this
  backfill blocks nothing today; where scanning is on, those files re-scan on demand.
* ``scan_signature`` — clamd's malware name (e.g. ``Eicar-Test-Signature``) so a
  quarantine is explainable to staff. Never file contents.
* ``scanned_at`` — when the verdict was recorded.

A partial index on the un-verdicted rows keeps the "what still needs scanning" sweep
cheap without paying for an index over every file.

No new table, so no new RLS policy: the columns inherit ``part_file``'s existing
``org_isolation`` policy and grants (0006). Reversible: ``downgrade`` drops the three
columns, the index and the enum type.

Revision ID: 0053_part_file_scan_status
Revises: 0052_vendor_rfq_batch_send
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0053_part_file_scan_status"
down_revision: str | None = "0052_vendor_rfq_batch_send"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE part_file_scan_status AS ENUM ('pending', 'clean', 'infected', 'error')"
    )
    op.execute(
        "ALTER TABLE part_file "
        "ADD COLUMN scan_status part_file_scan_status NOT NULL DEFAULT 'pending', "
        "ADD COLUMN scan_signature text, "
        "ADD COLUMN scanned_at timestamptz"
    )
    # Only infected files carry a signature — a verdict-free row must not claim one.
    op.execute(
        "ALTER TABLE part_file ADD CONSTRAINT ck_part_file_scan_signature "
        "CHECK (scan_signature IS NULL OR scan_status = 'infected')"
    )
    # The re-scan/backlog sweep looks only at rows without a terminal verdict.
    op.execute(
        "CREATE INDEX ix_part_file_scan_pending ON part_file (org_id, id) "
        "WHERE scan_status IN ('pending', 'error')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_part_file_scan_pending")
    op.execute("ALTER TABLE part_file DROP CONSTRAINT IF EXISTS ck_part_file_scan_signature")
    op.execute(
        "ALTER TABLE part_file "
        "DROP COLUMN IF EXISTS scan_status, "
        "DROP COLUMN IF EXISTS scan_signature, "
        "DROP COLUMN IF EXISTS scanned_at"
    )
    op.execute("DROP TYPE IF EXISTS part_file_scan_status")
