"""Review rules — the portable query AST (M3.6).

Spec ``#rules-schema`` / RULES-ENGINE-SPEC §4, canonical DDL ``DB-SCHEMA.sql``
``rule``: one org-scoped row per rule, the AST stored verbatim in JSONB
(``signals``/``resolutions``). Deviations from the frozen DDL, resolved up the
ladder (CLAUDE.md §2):

* ``uuid`` column added — the *portable* identity from the import/export JSON
  string (spec: rule sets are portable/diffable). Unique per ``(org_id,
  uuid)`` so re-import upserts and the same pasted set imports into any org
  without colliding with the internal PK.
* ``description``/``logical_operator``/``default_assignee_id`` added — fields
  of the canonical rule schema ("build to this") the DDL sketch omitted.
* ``filters jsonb`` dropped — no counterpart in the canonical schema; the
  rules sub-spec wins for its own internals.
* ``default_assignee_id`` is un-FK'd on purpose: imported sets may name users
  absent from this org; M3.8 validates at assignment time.

Revision ID: 0025_rules
Revises: 0024_email_threading
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_rules"
down_revision: str | None = "0024_email_threading"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE rule (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            uuid uuid NOT NULL,
            name text NOT NULL,
            description text NOT NULL DEFAULT '',
            logical_operator text NOT NULL,
            signals jsonb NOT NULL,
            resolutions jsonb NOT NULL,
            default_assignee_id uuid,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_rule_org_uuid UNIQUE (org_id, uuid),
            CONSTRAINT ck_rule_logical_operator
                CHECK (logical_operator IN ('AND', 'OR'))
        )
        """
    )
    op.execute("CREATE INDEX ix_rule_org_active ON rule (org_id, is_active)")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON rule TO {APP_ROLE}")
    op.execute("ALTER TABLE rule ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rule FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON rule
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON rule")
    op.execute(f"REVOKE ALL ON rule FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS rule")
