"""Multi-component sheet nesting — ``nest`` (M4.3).

The canonical DDL (DB-SCHEMA.sql ``nest``) verbatim — org-scoped + RLS,
``config``/``result`` JSONB — plus ``created_at`` for the per-quote "Nest #N"
ordering (the lean-extend precedent) and a ``kind`` CHECK pinning the DDL's
``sheet|linear`` comment. Reversible.

Revision ID: 0030_nest
Revises: 0029_interrogation_run
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030_nest"
down_revision: str | None = "0029_interrogation_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE nest (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_id uuid,
            label text,
            kind text,
            config jsonb,
            result jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_nest_kind CHECK (kind IN ('sheet', 'linear')),
            -- same-org pin (the quote_item precedent): a nest can never
            -- reference another org's quote, defense-in-depth beside RLS
            CONSTRAINT fk_nest_quote_org
                FOREIGN KEY (org_id, quote_id)
                REFERENCES quote (org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_nest_org_quote ON nest (org_id, quote_id)")
    # membership/locking checks probe config @> {"component_ids": [...]} on
    # every quantity change / material-op delete — give the containment a GIN
    op.execute("CREATE INDEX ix_nest_config_gin ON nest USING gin (config jsonb_path_ops)")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON nest TO {APP_ROLE}")
    op.execute("ALTER TABLE nest ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE nest FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON nest
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON nest")
    op.execute(f"REVOKE ALL ON nest FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS nest")
