"""Dashboard work-queue (M6.1) — org urgency weights, recently-opened tracking,
the account VIP flag, and the cross-org mention read.

Spec ``#newscope`` §2 ("Dashboard — first-principles redesign"): the landing page
becomes one merged, prioritised work queue whose ordering is an **explainable,
org-configurable** urgency score, plus a *Recently opened* strip. Four schema
pieces are needed and none exists yet:

* ``org_dashboard_settings`` — one row per org (``org_id`` PRIMARY KEY), holding
  the four urgency weights and the vendor-RFQ source flag. Mirrors
  ``org_quote_settings`` (0047) / ``org_ai_settings`` (0027) exactly: existing
  orgs are backfilled with the all-default row, and the accessor treats an absent
  row as all-defaults too, so an org created later behaves identically. Weights
  are ``numeric(6,4)`` — the score is Decimal end-to-end (``app.urgency``), never
  float, so the ordering is byte-identical on every machine.
* ``recent_view`` — the *Recently opened* strip's substrate (last 8 quotes/parts
  per user). One row per (org, user, entity), upserted on open; ``opened_at``
  carries the recency. Org-scoped + RLS like every tenant table.
* ``account.is_vip`` — the VIP half of the score's ``flags(expedite/VIP/export)``
  term, which the spec names but the model never had. Additive with a ``false``
  default, so no existing row changes meaning.
* ``app_user_mentions()`` — the queue's **@mentions** source. Mentions are the
  one *cross-org* row type (DECISIONS 2026-06-19 "Multi-organization users
  (E4-a)": cross-org notifications are labelled + switch-on-select), and a
  request's session is pinned to the active org by RLS, so the read cannot go
  through the ordinary path. It reuses the audited ``app_current_identity()``
  pattern (0004): a ``SECURITY DEFINER`` function owned by the ``BYPASSRLS``
  ``tolera_identity`` role, taking **no argument** and binding to the
  ``app.current_user_id`` GUC — so the database, not application discipline,
  guarantees a caller can only ever read their own mentions. It is further
  restricted to ``kind = 'mention'`` and to orgs where the caller holds an
  *active* membership, so a stale notification from an org the user has left
  cannot surface.

Reversible (CLAUDE.md §5): ``downgrade`` drops the function, both tables and the
column; ``tolera_identity`` is cluster infra and is left in place (0004's
precedent).

Revision ID: 0049_dashboard_work_queue
Revises: 0048_org_commercial_register
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0049_dashboard_work_queue"
down_revision: str | None = "0048_org_commercial_register"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
IDENTITY_ROLE = "tolera_identity"

# The caller's unread @mentions across every org they are an *active* member of.
# No argument (see module docstring): the caller comes from the GUC, so there is
# nothing to aim at another user. STABLE, read-only.
_MENTIONS_FN = """
CREATE OR REPLACE FUNCTION app_user_mentions(max_rows integer DEFAULT 50)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
  SELECT COALESCE(jsonb_agg(row ORDER BY row->>'created_at' DESC), '[]'::jsonb)
  FROM (
    SELECT jsonb_build_object(
             'id', n.id,
             'org_id', o.id,
             'org_name', o.name,
             'org_slug', o.slug,
             'payload', n.payload,
             'created_at', n.created_at
           ) AS row
    FROM notification n
    JOIN organization o ON o.id = n.org_id
    JOIN user_org_membership m
      ON m.org_id = n.org_id
     AND m.user_id = n.user_id
     AND m.status = 'active'
    WHERE n.user_id = current_setting('app.current_user_id', true)::uuid
      AND n.kind = 'mention'
      AND n.read_at IS NULL
    ORDER BY n.created_at DESC
    LIMIT LEAST(GREATEST(max_rows, 0), 200)
  ) rows;
$fn$
"""


def upgrade() -> None:
    # --- VIP flag (urgency ``flags`` term) ---
    op.execute("ALTER TABLE account ADD COLUMN is_vip boolean NOT NULL DEFAULT false")

    # --- per-org urgency weights + queue-source flags ---
    op.execute(
        """
        CREATE TABLE org_dashboard_settings (
            org_id uuid PRIMARY KEY REFERENCES organization(id) ON DELETE CASCADE,
            weight_due numeric(6, 4) NOT NULL DEFAULT 0.4000
                CHECK (weight_due >= 0),
            weight_value numeric(6, 4) NOT NULL DEFAULT 0.2500
                CHECK (weight_value >= 0),
            weight_unresolved numeric(6, 4) NOT NULL DEFAULT 0.2500
                CHECK (weight_unresolved >= 0),
            weight_flags numeric(6, 4) NOT NULL DEFAULT 0.1000
                CHECK (weight_flags >= 0),
            vendor_rfq_queue_enabled boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "INSERT INTO org_dashboard_settings (org_id) SELECT id FROM organization "
        "ON CONFLICT (org_id) DO NOTHING"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON org_dashboard_settings TO {APP_ROLE}")
    op.execute("ALTER TABLE org_dashboard_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_dashboard_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON org_dashboard_settings
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # --- Recently opened (last N quotes/parts per user) ---
    # PK is (org, user, entity): re-opening the same quote updates ``opened_at``
    # in place rather than growing an unbounded access log — the strip only ever
    # shows the most recent 8, and no history is promised.
    op.execute(
        """
        CREATE TABLE recent_view (
            org_id uuid NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            entity_type text NOT NULL CHECK (entity_type IN ('quote', 'part')),
            entity_id uuid NOT NULL,
            opened_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, user_id, entity_type, entity_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_recent_view_org_user_opened "
        "ON recent_view (org_id, user_id, opened_at DESC)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON recent_view TO {APP_ROLE}")
    op.execute("ALTER TABLE recent_view ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recent_view FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON recent_view
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # --- cross-org @mentions (audited SECURITY DEFINER read, 0004's pattern) ---
    op.execute(f"GRANT SELECT ON notification TO {IDENTITY_ROLE}")
    op.execute(_MENTIONS_FN)
    # A SECURITY DEFINER function must never be world-callable.
    op.execute("REVOKE ALL ON FUNCTION app_user_mentions(integer) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_user_mentions(integer) TO {APP_ROLE}")
    op.execute(f"ALTER FUNCTION app_user_mentions(integer) OWNER TO {IDENTITY_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_user_mentions(integer)")
    op.execute(f"REVOKE SELECT ON notification FROM {IDENTITY_ROLE}")

    op.execute("DROP POLICY IF EXISTS org_isolation ON recent_view")
    op.execute(f"REVOKE ALL ON recent_view FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS recent_view")

    op.execute("DROP POLICY IF EXISTS org_isolation ON org_dashboard_settings")
    op.execute(f"REVOKE ALL ON org_dashboard_settings FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS org_dashboard_settings")

    op.execute("ALTER TABLE account DROP COLUMN IF EXISTS is_vip")
