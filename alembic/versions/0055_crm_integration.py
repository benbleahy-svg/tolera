"""M6.8 — CRM sync fields + the Managed-Integrations v1 data model.

Two independent additions land together because the HubSpot adapter needs both:

**1. CRM sync columns on the records the adapter syncs.** Spec ``#crm`` "Build
implications (2)/(3)" names them verbatim: ``Account``/``Contact`` are full
native records (Tolera is system of record) that *also* carry
``external_crm_id`` + ``crm_source`` + ``last_synced_at``, and the Tolera quote
maps onto the CRM's opportunity object via a nullable ``crm_opportunity_id``.

``last_synced_at`` is not decoration — it IS the conflict rule. DECISIONS.md
2026-07-17 ("HubSpot CRM conflict") settles v1 as **Tolera-always-wins**, no
field-level merge. Implemented as: an inbound CRM change applies only while the
Tolera row is untouched since the last sync (``updated_at <= last_synced_at``);
once a human edits in Tolera, inbound writes to that record are refused and the
attempt is logged. Without a synced-at watermark there is no way to tell "Tolera
changed too" from "Tolera never changed", so the rule would be unimplementable.

**2. The Managed-Integrations framework tables** (INTEGRATION-API-CONTRACT §2).
Build-plan M6.8 puts the *UI* post-pilot but the **v1 data model** here, so the
export contract exists and the action log is real from day one:

``integration``
    one connected external system per org (HubSpot, the ERP push stub).
``integration_action_definition``
    a *capability* ("Export Quote"), not an attempt. ``direction`` drives the
    notification default: §6 says only **export** actions notify on failure by
    default — a DATEV/ERP export failing silently is the dangerous case, an
    import failure is not.
``integration_action``
    one attempt, the audit trail the user sees. Status carries all **six**
    states the sub-spec lists (§2), not the four the build-plan prose
    abbreviates to; the extra ``cancelled``/``timed_out`` are terminal states
    §6 explicitly notifies on, so omitting them would break that rule.

``downgrade`` unwinds exactly this: the three tables (child first), the two
enums, and the four added columns.

Revision ID: 0055_crm_integration
Revises: 0054_vendor_rfq_email
Create Date: 2026-07-19

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0055_crm_integration"
down_revision: str | None = "0054_vendor_rfq_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

# Isolated exactly like ``account`` (M1.1): the policy reads the GUC set by
# app.db.org_scoped_session; an unset GUC yields NULL, so every row fails the
# predicate → zero rows for an unpinned connection.
_ORG_SCOPED_TABLES = (
    "integration",
    "integration_action_definition",
    "integration_action",
)


def upgrade() -> None:
    # --- 1. CRM sync columns ---------------------------------------------
    # Nullable throughout: a record that has never been near a CRM carries NULL
    # in all three, which is also the "safe to accept inbound" state.
    for table in ("account", "contact"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN external_crm_id text,
                ADD COLUMN crm_source text,
                ADD COLUMN last_synced_at timestamptz
            """
        )
        # The inbound sync resolves a CRM record to a Tolera row by this pair.
        # Partial-unique on live rows only (mirrors uq_contact_org_email_live):
        # archiving a synced record frees its CRM id for a re-import.
        op.execute(
            f"""
            CREATE UNIQUE INDEX uq_{table}_org_crm_id_live
                ON {table} (org_id, crm_source, external_crm_id)
                WHERE deleted_at IS NULL AND external_crm_id IS NOT NULL
            """
        )

    # Spec #crm: "Expose a deal/opportunity ID field on Quote (nullable
    # crm_opportunity_id) and push quoted amount back to the deal on
    # quote-finalize." Text, not uuid — it holds the CRM's own id format.
    op.execute("ALTER TABLE quote ADD COLUMN crm_opportunity_id text")

    # --- 2. Managed-Integrations framework --------------------------------
    op.execute("CREATE TYPE integration_action_direction AS ENUM ('export', 'import')")
    op.execute(
        """
        CREATE TYPE integration_action_status AS ENUM (
            'queued', 'in_progress', 'completed', 'failed', 'cancelled', 'timed_out'
        )
        """
    )

    op.execute(
        """
        CREATE TABLE integration (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            -- Machine key ('hubspot', 'erp_push'); what code looks an org's
            -- integration up by. Stable; the display name may be renamed.
            key text NOT NULL,
            name text NOT NULL,
            author text,
            support_contact text,
            -- Pause/Play (§2). A disabled integration receives no dispatch;
            -- the transition itself is delivered as integration.turned_on/off.
            enabled boolean NOT NULL DEFAULT true,
            -- "last phoned home" (§2 heartbeat), so a user can trust the
            -- integration is live before requesting an action.
            last_heartbeat_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_integration_org_key UNIQUE (org_id, key),
            -- Composite-FK target so a definition is pinned to the SAME org.
            CONSTRAINT uq_integration_org_id_id UNIQUE (org_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE integration_action_definition (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            integration_id uuid NOT NULL,
            -- Machine key of the capability, e.g. 'export_quote'.
            type text NOT NULL,
            display_title text NOT NULL,
            display_description text,
            direction integration_action_direction NOT NULL,
            -- If true the action is about ONE Tolera entity: the user gets an
            -- entity picker, logs filter by it, and (post-pilot) it surfaces
            -- in-context on that entity's screen.
            has_tolera_entity boolean NOT NULL DEFAULT false,
            entity_type text,
            -- UI flag only: shows a manual "request" button (§2).
            can_be_requested boolean NOT NULL DEFAULT true,
            -- §6 default: exports notify on failure, imports do not.
            notify_on_failure boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_iad_org_integration_type UNIQUE (org_id, integration_id, type),
            CONSTRAINT uq_iad_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_iad_integration_same_org
                FOREIGN KEY (org_id, integration_id)
                REFERENCES integration (org_id, id),
            -- has_tolera_entity ⇒ the entity type must actually be named;
            -- and a scheduled/entity-less action must NOT carry a stray one.
            CONSTRAINT ck_iad_entity_type_present
                CHECK (has_tolera_entity = (entity_type IS NOT NULL))
        )
        """
    )

    op.execute(
        """
        CREATE TABLE integration_action (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            definition_id uuid NOT NULL,
            status integration_action_status NOT NULL DEFAULT 'queued',
            -- Human-readable; §2 notes the reference product surfaces it to the
            -- user only on completed/cancelled, so write it for those readers.
            status_message text,
            -- The quote/order/account this attempt is about (§2 related_object).
            related_object_type text,
            related_object_id uuid,
            -- NULL for an event-triggered attempt; set for a user-initiated
            -- Integration Action Request (§2).
            requested_by uuid REFERENCES app_user(id),
            -- The exact payload handed to the integration — the ERP-push export
            -- contract is asserted against this, and it is what a manual resend
            -- would replay. Never contains credentials.
            request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_ia_definition_same_org
                FOREIGN KEY (org_id, definition_id)
                REFERENCES integration_action_definition (org_id, id)
        )
        """
    )
    # The manager's main log view: newest attempts for one org, optionally
    # narrowed to one definition.
    op.execute(
        """
        CREATE INDEX ix_integration_action_org_created
            ON integration_action (org_id, definition_id, created_at DESC)
        """
    )
    # "Show me this quote's export attempts" (in-context, entity-filtered logs).
    op.execute(
        """
        CREATE INDEX ix_integration_action_related
            ON integration_action (org_id, related_object_type, related_object_id)
            WHERE related_object_id IS NOT NULL
        """
    )

    # --- 3. Tenancy -------------------------------------------------------
    for table in _ORG_SCOPED_TABLES:
        # No DELETE: an action log is an audit trail. Definitions/integrations
        # are configuration an admin may retire, but nothing in the app deletes
        # them today, so the grant stays minimal (add it with the block that
        # needs it).
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table}
                USING (org_id = current_setting('app.current_org_id', true)::uuid)
                WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in reversed(_ORG_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS integration_action")
    op.execute("DROP TABLE IF EXISTS integration_action_definition")
    op.execute("DROP TABLE IF EXISTS integration")
    op.execute("DROP TYPE IF EXISTS integration_action_status")
    op.execute("DROP TYPE IF EXISTS integration_action_direction")

    op.execute("ALTER TABLE quote DROP COLUMN IF EXISTS crm_opportunity_id")
    for table in ("account", "contact"):
        op.execute(f"DROP INDEX IF EXISTS uq_{table}_org_crm_id_live")
        op.execute(
            f"""
            ALTER TABLE {table}
                DROP COLUMN IF EXISTS external_crm_id,
                DROP COLUMN IF EXISTS crm_source,
                DROP COLUMN IF EXISTS last_synced_at
            """
        )
