"""append-only GDPR data-subject request log (M6.9, ship-review finding).

The erasure endpoint destroys direct identifiers across six tables and, as first
written, left no record that it had run. The tombstone values were the only trace
and they name no actor — so "who erased whom, and when" was unanswerable
immediately after the most destructive action the product offers.

That is the same audit obligation ``export_control_access`` exists to satisfy, but
it is **not the same log**: that one is the export-control ("CUI Audit") trail the
spec surfaces as its own CSV, and folding an unrelated action into it would make
both harder to read and the export-control CSV wrong. Hence a small sibling table
with the same guarantees.

Append-only at the database (``tolera_app`` gets SELECT + INSERT only) and
RLS-scoped, exactly like ``export_control_access`` (0056) and
``quote_status_event`` (0008). ``actor_user_id`` carries no FK so the entry
outlives the user it names.

**The subject address is stored.** That is itself personal data, and keeping it is
deliberate: an erasure log that cannot say *whose* data was erased cannot evidence
compliance with the request it records. Art. 17(3)(b)/(e) covers retention needed
to establish that an obligation was met. It is the only personal datum here.

Revision ID: 0058_gdpr_request_log
Revises: 0057_org_privacy_policy_url
Create Date: 2026-07-19

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0058_gdpr_request_log"
down_revision: str | None = "0057_org_privacy_policy_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
_TABLE = "gdpr_request_log"


def upgrade() -> None:
    op.execute("CREATE TYPE gdpr_request_kind AS ENUM ('export', 'erasure')")
    op.execute(
        f"""
        CREATE TABLE {_TABLE} (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            -- No FK: the entry must outlive the admin who ran it.
            actor_user_id uuid,
            kind gdpr_request_kind NOT NULL,
            subject_email text NOT NULL,
            -- Per-table row counts, e.g. {{"contact": 1, "account": 1}}.
            affected jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            affected_row_count integer NOT NULL DEFAULT 0,
            occurred_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(f"CREATE INDEX ix_gdpr_request_log_org_occurred ON {_TABLE} (org_id, occurred_at)")
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY org_isolation ON {_TABLE}
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS org_isolation ON {_TABLE}")
    op.execute(f"REVOKE ALL ON {_TABLE} FROM {APP_ROLE}")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
    op.execute("DROP TYPE IF EXISTS gdpr_request_kind")
