"""Review items — matched rules become assignable, resolvable work (M3.8).

Spec ``#rules`` / ``#rules-lifecycle`` / ``#rules-resolutions``;
RULES-ENGINE-SPEC §3 (resolutions) + §6 (lifecycle & collaboration). Canonical
DDL ``DB-SCHEMA.sql`` ``review_item`` is a five-column sketch (``status``,
``detail``, the three FKs); the lifecycle it must carry — assign → collaborate
→ resolve → audit — needs more. Deviations from the frozen DDL, resolved up
the ladder (CLAUDE.md §2: the sub-spec wins for its own internals):

* ``component_id`` added, and it is the **subject** of a review item. The DDL
  addresses only ``quote_item_id``, but §1 is explicit — "when a rule's signals
  match a **component**, a review item is created" — and the evaluator's whole
  input is one component's analyzed data. A line item aggregates its
  components' items (spec: quote-level SET ALL across "every part with the
  flag"), so the component is the finer, correct grain.
* ``quote_id``/``quote_item_id`` NOT NULL (the DDL leaves both nullable). A
  review item exists to be resolved *against a line item* — NO_QUOTE sets its
  status, ASSIGN_ESTIMATOR routes it — so an item with no line item could not
  be resolved. Every app-created ``component`` is a root component with exactly
  one ``quote_item`` (``quotes.py`` / ``bulk_create.py``); when M4's BOM
  builder adds child components they resolve to their root's line item, which
  is the line item those effects must mutate anyway. So this stays satisfiable.
* ``assignee_id`` / ``resolved_at`` / ``resolved_by`` / ``resolution_type`` /
  ``resolution_label`` added — §6's lifecycle and audit trail ("resolutions,
  assignee, thread, and timestamps are retained"). ``resolution_type`` mirrors
  the §3 catalogue; ``resolution_label`` carries RESOLVE's ``custom_label``
  ("Outsource", "Contacted customer").
* ``status`` gains a CHECK (``open``/``resolved``) — the DDL's bare ``text
  DEFAULT 'open'`` names no domain. Two states only: §6's lifecycle is
  trigger → assign → collaborate → resolve, and "assigned" is
  ``assignee_id IS NOT NULL``, not a status.
* ``UNIQUE (org_id, component_id, rule_id)`` — the spec's evaluation contract
  is "on any extraction/geometry change, evaluate all org rules against the
  part → **create/update** ReviewItems". Re-evaluation after every Lens run
  must converge, not accumulate duplicates, so one item per (component, rule)
  is the identity that makes generation idempotent.
* ``assignee_id``/``resolved_by`` reference the global ``app_user`` (no org
  column to compose with); active-membership is enforced in the service layer,
  the ``collab.py`` precedent.
* ``uq_quote_item_org_id_id`` / ``uq_rule_org_id_id`` added to the parent
  tables — the same-org composite-FK convention (§5 tenancy) needs an
  ``(org_id, id)`` unique to point at, and neither table had one.

Revision ID: 0026_review_item
Revises: 0025_rules
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_review_item"
down_revision: str | None = "0025_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

#: The §3 resolution catalogue — kept in sync with
#: ``app.rules_schema.Resolution.type``.
RESOLUTION_TYPES = "'NO_QUOTE', 'RESOLVE', 'ADD_OPERATION', 'SET_PROCESS', 'ASSIGN_ESTIMATOR'"


def upgrade() -> None:
    # Composite-FK targets the convention requires (neither parent had one).
    op.execute("ALTER TABLE quote_item ADD CONSTRAINT uq_quote_item_org_id_id UNIQUE (org_id, id)")
    op.execute("ALTER TABLE rule ADD CONSTRAINT uq_rule_org_id_id UNIQUE (org_id, id)")

    op.execute(
        f"""
        CREATE TABLE review_item (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_id uuid NOT NULL,
            quote_item_id uuid NOT NULL,
            component_id uuid NOT NULL,
            rule_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'open',
            assignee_id uuid REFERENCES app_user(id),
            resolution_type text,
            resolution_label text,
            resolved_at timestamptz,
            resolved_by uuid REFERENCES app_user(id),
            detail jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_review_item_org_id_id UNIQUE (org_id, id),
            CONSTRAINT uq_review_item_component_rule
                UNIQUE (org_id, component_id, rule_id),
            CONSTRAINT fk_review_item_quote_org
                FOREIGN KEY (org_id, quote_id)
                REFERENCES quote(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_review_item_quote_item_org
                FOREIGN KEY (org_id, quote_item_id)
                REFERENCES quote_item(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_review_item_component_org
                FOREIGN KEY (org_id, component_id)
                REFERENCES component(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_review_item_rule_org
                FOREIGN KEY (org_id, rule_id)
                REFERENCES rule(org_id, id) ON DELETE CASCADE,
            CONSTRAINT ck_review_item_status
                CHECK (status IN ('open', 'resolved')),
            CONSTRAINT ck_review_item_resolution_type
                CHECK (resolution_type IS NULL OR resolution_type IN ({RESOLUTION_TYPES})),
            CONSTRAINT ck_review_item_resolved_is_complete
                CHECK (
                    (status = 'open'
                        AND resolution_type IS NULL
                        AND resolved_at IS NULL
                        AND resolved_by IS NULL)
                    OR
                    (status = 'resolved'
                        AND resolution_type IS NOT NULL
                        AND resolved_at IS NOT NULL)
                )
        )
        """
    )
    # The burn-down list: the panel filters by quote + Unresolved (§6.1), and
    # the unresolved count drives "Outstanding Work / Incomplete Quote Items".
    op.execute(
        "CREATE INDEX ix_review_item_org_quote_status ON review_item (org_id, quote_id, status)"
    )
    # Generation upserts per component; the line-item panel reads per component.
    op.execute("CREATE INDEX ix_review_item_org_component ON review_item (org_id, component_id)")
    # §6.4: "up to 5 past parts the rule flagged + the decision taken there" —
    # a per-rule lookup of recent resolved items, newest first.
    op.execute(
        """
        CREATE INDEX ix_review_item_org_rule_resolved
            ON review_item (org_id, rule_id, resolved_at DESC)
            WHERE status = 'resolved'
        """
    )
    op.execute("CREATE INDEX ix_review_item_org_assignee ON review_item (org_id, assignee_id)")

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON review_item TO {APP_ROLE}")
    op.execute("ALTER TABLE review_item ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review_item FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON review_item
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON review_item")
    op.execute(f"REVOKE ALL ON review_item FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS review_item")
    op.execute("ALTER TABLE rule DROP CONSTRAINT IF EXISTS uq_rule_org_id_id")
    op.execute("ALTER TABLE quote_item DROP CONSTRAINT IF EXISTS uq_quote_item_org_id_id")
