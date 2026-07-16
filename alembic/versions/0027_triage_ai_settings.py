"""RFQ Triage Brief cache + per-org AI settings (M3.9).

Spec ``#ai-triage`` (Build notes: "Add ``triage_brief JSONB`` to ``Quote``")
and ``#ai-settings`` (Build notes: the ``org_ai_settings`` table — ``org_id`` +
``master_enabled`` + one BOOL per AI feature, "Default row is inserted on org
creation with the above defaults", "Seed the fixture orgs with AI fully
enabled").

M3.9 is the first AI feature to need the gate, so it introduces the whole
table per the canonical spec build-note (all thirteen flags, cheap-to-add
booleans, avoids a second migration when M3.10/M5/M6 land). M3.9 itself only
reads ``master_enabled`` (checked first) then ``triage_brief_enabled``.

``org_ai_settings.org_id`` is the PRIMARY KEY — exactly one row per org — so
get-or-create is a single upsert. All flags default ``true`` (spec: fixture
orgs AI-fully-enabled); the accessor treats an absent row as all-enabled too,
so this backfills existing orgs but a missing row is never a silent disable.

``quote.triage_brief`` is an additive, nullable JSONB cache (mirrors the
``suggested_line_items`` lean-extend precedent, migration 0022) — regenerable,
so no data to backfill.

Revision ID: 0027_triage_ai_settings
Revises: 0026_review_item
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027_triage_ai_settings"
down_revision: str | None = "0026_review_item"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

#: The thirteen per-feature flags (spec ``#ai-settings`` build-note), all
#: default TRUE. ``master_enabled`` gates every feature and is checked first.
_FLAGS = (
    "master_enabled",
    "wingman_enabled",
    "triage_brief_enabled",
    "quote_assembly_enabled",
    "estimation_coaching_enabled",
    "presend_review_enabled",
    "assistant_enabled",
    "mcp_enabled",
    "customer_brief_enabled",
    "requote_diff_enabled",
    "rule_suggest_enabled",
    "margin_coach_enabled",
    "benchmarking_opt_out",
)


def upgrade() -> None:
    flag_cols = ",\n            ".join(f"{name} boolean NOT NULL DEFAULT true" for name in _FLAGS)
    op.execute(
        f"""
        CREATE TABLE org_ai_settings (
            org_id uuid PRIMARY KEY REFERENCES organization(id) ON DELETE CASCADE,
            {flag_cols},
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Spec: "Default row is inserted on org creation" — backfill every existing
    # org with the all-enabled defaults (idempotent).
    op.execute(
        "INSERT INTO org_ai_settings (org_id) SELECT id FROM organization "
        "ON CONFLICT (org_id) DO NOTHING"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON org_ai_settings TO {APP_ROLE}")
    op.execute("ALTER TABLE org_ai_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_ai_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON org_ai_settings
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # The regenerable triage-brief cache (spec ``#ai-triage`` build-note).
    op.execute("ALTER TABLE quote ADD COLUMN triage_brief jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE quote DROP COLUMN IF EXISTS triage_brief")
    op.execute("DROP POLICY IF EXISTS org_isolation ON org_ai_settings")
    op.execute(f"REVOKE ALL ON org_ai_settings FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS org_ai_settings")
