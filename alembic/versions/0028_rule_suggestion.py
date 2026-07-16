"""Rule Auto-Suggestion — ``operation.added_manually`` + ``suggested_action`` (M3.10).

Spec ``#ai-rule-suggest`` (AI Feature 2). Build-notes:
* "Add ``added_manually BOOL`` to ``OperationInstance`` — set when an operation
  is added directly by the estimator, cleared if resolved by a rule." Our
  operation-instance table is ``operation``. The column defaults ``true``: it is
  the common case, and pre-M3.10 rows recorded no provenance, so existing
  rule-added (M3.8 ADD_OPERATION) and library-imported rows are *conservatively*
  backfilled to ``true`` — the worst case is a self-healing false-positive
  suggestion that ages out of the 90-day window. Going forward the two auto-add
  paths write ``false`` explicitly, so the detector only learns from real manual
  adds.
* "Nightly Celery job scans for patterns per org and surfaces suggestions via
  the existing ``SuggestedAction`` mechanism." That mechanism did not exist, so
  this migration introduces the ``suggested_action`` table (org-scoped, RLS,
  one open row per pattern via ``UNIQUE (org_id, dedup_key)``).

Both changes are additive and reversible; the column has a server default so the
backfill is free, and the table is regenerable (the scan re-derives it), so
there is nothing to backfill for it.

Revision ID: 0028_rule_suggestion
Revises: 0027_triage_ai_settings
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028_rule_suggestion"
down_revision: str | None = "0027_triage_ai_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    # Provenance flag on the operation instance (spec build-note).
    op.execute("ALTER TABLE operation ADD COLUMN added_manually boolean NOT NULL DEFAULT true")

    # The suggested-actions mechanism (net-new; spec build-note references it as
    # "existing"). Org-scoped + RLS, mirroring org_ai_settings (migration 0027).
    op.execute(
        """
        CREATE TABLE suggested_action (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            kind text NOT NULL,
            status text NOT NULL DEFAULT 'open',
            dedup_key text NOT NULL,
            operation_def_id uuid,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            dismissed_at timestamptz,
            CONSTRAINT uq_suggested_action_dedup UNIQUE (org_id, dedup_key)
        )
        """
    )
    # Dashboard strip reads open rows per org, newest first.
    op.execute("CREATE INDEX ix_suggested_action_org_status ON suggested_action (org_id, status)")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON suggested_action TO {APP_ROLE}")
    op.execute("ALTER TABLE suggested_action ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE suggested_action FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON suggested_action
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # The nightly rule-suggestion scan fans out one task per org, but runs
    # before any org GUC is set — RLS (correctly) hides every organization row.
    # Narrow SECURITY DEFINER enumeration (the ``list_email_sync_targets``
    # precedent, 0024): ids only, no org data; the per-org task then re-checks
    # the AI gate and does every read/write in an org-scoped session.
    op.execute(
        """
        CREATE FUNCTION list_scan_org_ids()
            RETURNS TABLE (org_id uuid)
            LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = public
            AS 'SELECT id FROM organization'
        """
    )
    op.execute("REVOKE ALL ON FUNCTION list_scan_org_ids() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION list_scan_org_ids() TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS list_scan_org_ids()")
    op.execute("DROP POLICY IF EXISTS org_isolation ON suggested_action")
    op.execute(f"REVOKE ALL ON suggested_action FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS suggested_action")
    op.execute("ALTER TABLE operation DROP COLUMN IF EXISTS added_manually")
