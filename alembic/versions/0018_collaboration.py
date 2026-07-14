"""Collaboration: channels · messages · annotations · tasks · notifications (M2.11).

Spec ``#collab`` / VIEWER-AND-FILE-TYPES §1/§4: the viewer (CAD + PDF) hosts
**TEAM** (internal) and **EXTERNAL** (per customer/vendor) channels. A message
can bind to a picked 3D face (M2.7 ``EntityRef``) or a PDF region (M2.2 layer)
via a collaboration ``annotation``; you can ``@mention`` a teammate and
**Assign Task** — the task surfaces on the Dashboard. Secure external *sharing*
(the recipient composer, per-file scope/expiry, ``external_share``) is **M6**;
this block lands the collaboration substrate only.

Five canonical tables (DB-SCHEMA "collaboration / sourcing" + "tasks /
notifications"): ``channel``, ``message``, ``annotation``, ``task``,
``notification``. The canonical DDL omits ``org_id`` on ``message`` (parent-
scoped); the tier-1 invariant (CLAUDE.md §5 "every table org-scoped, RLS")
wins — like ``quote_cell`` / ``component_quantity`` every table here carries its
own ``org_id`` + composite same-org FK + RLS. Assignee/author/mention reference
the org-less ``app_user`` per the canonical schema; the **active-membership**
tenancy guard is enforced at the app edge (the salesperson pattern,
DECISIONS.md 2026-06-25).

Revision ID: 0018_collaboration
Revises: 0017_part_file_source
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018_collaboration"
down_revision: str | None = "0017_part_file_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
IDENTITY_ROLE = "tolera_identity"

_TABLES = ("channel", "annotation", "message", "task", "notification")

# Scoped teammate directory for the @mention / Assign-Task pickers. Like
# ``app_current_identity()`` (0004): the restricted role has NO grant on
# ``app_user`` (M0.2 by design), so surfacing teammates goes through a
# ``SECURITY DEFINER`` function owned by the BYPASSRLS ``tolera_identity`` role.
# It takes NO argument — it reads the caller's active org from the
# ``app.current_org_id`` GUC (stamped by ``get_session``) and returns only that
# org's **active** members, so the database (not app discipline) guarantees the
# caller can never list another org's users. STABLE, read-only.
_MEMBERS_FUNCTION = """
CREATE OR REPLACE FUNCTION app_org_members()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
  SELECT COALESCE((
    SELECT jsonb_agg(
      jsonb_build_object(
        'id', u.id,
        'email', u.email,
        'first_name', u.first_name,
        'last_name', u.last_name
      )
      ORDER BY u.email
    )
    FROM user_org_membership m
    JOIN app_user u ON u.id = m.user_id
    WHERE m.org_id = current_setting('app.current_org_id', true)::uuid
      AND m.status = 'active'
  ), '[]'::jsonb);
$fn$
"""


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY org_isolation ON {table}
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def upgrade() -> None:
    op.execute("CREATE TYPE task_status AS ENUM ('open', 'overdue', 'resolved')")

    # --- channel: TEAM (one per part) + EXTERNAL (per vendor/customer) --------
    op.execute(
        """
        CREATE TABLE channel (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid NOT NULL,
            quote_id uuid,
            scope text NOT NULL DEFAULT 'team',      -- 'team' | 'external'
            label text,                              -- EXTERNAL channel name (e.g. 'Plating RFQ')
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_channel_scope CHECK (scope IN ('team', 'external')),
            -- composite-FK target so message/task pin to a channel in the same org
            CONSTRAINT uq_channel_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_channel_part_org
                FOREIGN KEY (org_id, part_id) REFERENCES part(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_channel_quote_org
                FOREIGN KEY (org_id, quote_id) REFERENCES quote(org_id, id) ON DELETE SET NULL
        )
        """
    )
    # Exactly one TEAM channel per part; EXTERNAL channels are unconstrained (many).
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_one_team_per_part ON channel (part_id) WHERE scope = 'team'"
    )
    op.execute("CREATE INDEX ix_channel_org_part ON channel (org_id, part_id)")

    # --- annotation: a feature/region locator a message can bind to -----------
    op.execute(
        """
        CREATE TABLE annotation (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid NOT NULL,
            kind text NOT NULL,                      -- 'face' (3D) | 'region' (PDF)
            geometry_ref jsonb NOT NULL,             -- {file_id,entity} (3D) | {file_id,page,rect}
            note text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_annotation_kind CHECK (kind IN ('face', 'region')),
            CONSTRAINT uq_annotation_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_annotation_part_org
                FOREIGN KEY (org_id, part_id) REFERENCES part(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_annotation_org_part ON annotation (org_id, part_id)")

    # --- message: belongs to a channel; may bind an annotation + @mentions ----
    op.execute(
        """
        CREATE TABLE message (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            channel_id uuid NOT NULL,
            author_id uuid REFERENCES app_user(id),
            annotation_id uuid,
            parent_id uuid,                          -- reply target (same channel)
            body text NOT NULL,
            mentions jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [app_user id, ...]
            edited_at timestamptz,
            deleted_at timestamptz,                  -- tombstone (Delete keeps the row/replies)
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_message_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_message_channel_org
                FOREIGN KEY (org_id, channel_id) REFERENCES channel(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_message_annotation_org
                FOREIGN KEY (org_id, annotation_id)
                REFERENCES annotation(org_id, id) ON DELETE SET NULL,
            CONSTRAINT fk_message_parent_org
                FOREIGN KEY (org_id, parent_id) REFERENCES message(org_id, id) ON DELETE SET NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_message_org_channel ON message (org_id, channel_id, created_at)")

    # --- task: Assign Task → surfaces on the Dashboard ------------------------
    op.execute(
        """
        CREATE TABLE task (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid,
            quote_id uuid,
            annotation_id uuid,
            assignee_id uuid REFERENCES app_user(id),
            created_by uuid REFERENCES app_user(id),
            message text,
            due_date date,
            status task_status NOT NULL DEFAULT 'open',
            resolved_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_task_part_org
                FOREIGN KEY (org_id, part_id) REFERENCES part(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_task_quote_org
                FOREIGN KEY (org_id, quote_id) REFERENCES quote(org_id, id) ON DELETE SET NULL,
            CONSTRAINT fk_task_annotation_org
                FOREIGN KEY (org_id, annotation_id)
                REFERENCES annotation(org_id, id) ON DELETE SET NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_task_org_assignee ON task (org_id, assignee_id, status)")

    # --- notification: @mention + task-assignment fan-out (per recipient) -----
    op.execute(
        """
        CREATE TABLE notification (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            user_id uuid NOT NULL REFERENCES app_user(id),
            kind text NOT NULL,                      -- 'mention' | 'task_assigned'
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            read_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_notification_org_user ON notification (org_id, user_id, read_at)")

    for table in _TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        _enable_rls(table)

    # --- scoped teammate directory (SECURITY DEFINER, owned by tolera_identity) --
    op.execute(_MEMBERS_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION app_org_members() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_org_members() TO {APP_ROLE}")
    op.execute(f"ALTER FUNCTION app_org_members() OWNER TO {IDENTITY_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_org_members()")
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP TYPE IF EXISTS task_status")
