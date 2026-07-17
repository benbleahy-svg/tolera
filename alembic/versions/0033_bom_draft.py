"""BOM Builder staging (M4.9) — bom_draft table + node ordering.

Spec ``#bombuilder``: the BOM Builder is a *staging area* — every edit
autosaves a draft, and nothing touches the line item until CHECK AND PUBLISH
(KB ``The-BOM-Builder`` §BOM drafts). The draft is one org-scoped row per
quote item holding the whole editable tree as JSONB; publish commits it as
``part``/``node``/``component`` rows and deletes the draft.

One additive extension to a shipped table (the stub-then-extend precedent):
``node.position`` — sibling order within a published tree, so the decimal-dot
Item No. numbering (DemoD/09) survives a round-trip through publish. The
``bom_draft`` composite FK targets ``uq_quote_item_org_id_id`` (added in 0026)
so a draft is pinned to a quote item of its own org at the DB level.

Revision ID: 0033_bom_draft
Revises: 0032_custom_interrogation_links
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0033_bom_draft"
down_revision: str | None = "0032_custom_interrogation_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    # Sibling order for published BOM trees (client derives Item No. from it).
    op.execute("ALTER TABLE node ADD COLUMN position integer NOT NULL DEFAULT 0")

    # Publish rebuilds child nodes and drops vanished child components — the
    # first flows that DELETE either table (0008/0009 granted only S/I/U; RLS
    # still scopes every row to the caller's org).
    op.execute(f"GRANT DELETE ON node TO {APP_ROLE}")
    op.execute(f"GRANT DELETE ON component TO {APP_ROLE}")

    # One draft per line item; CASCADE — a deleted line item takes its staging
    # state with it (a draft is worthless without the quote item it stages).
    op.execute(
        """
        CREATE TABLE bom_draft (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_item_id uuid NOT NULL,
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_bom_draft_quote_item UNIQUE (org_id, quote_item_id),
            CONSTRAINT fk_bom_draft_quote_item_org
                FOREIGN KEY (org_id, quote_item_id)
                REFERENCES quote_item (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON bom_draft TO {APP_ROLE}")
    op.execute("ALTER TABLE bom_draft ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE bom_draft FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON bom_draft
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON bom_draft")
    op.execute(f"REVOKE ALL ON bom_draft FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS bom_draft")
    op.execute(f"REVOKE DELETE ON node FROM {APP_ROLE}")
    op.execute(f"REVOKE DELETE ON component FROM {APP_ROLE}")
    op.execute("ALTER TABLE node DROP COLUMN IF EXISTS position")
