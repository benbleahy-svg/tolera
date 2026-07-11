"""Seed-catalog config schema (M1.12).

Spec ``#oplibrary`` + ``#zuschlagskalkulation``; SEED-AND-FIXTURES Part 1
§2-§7; folded DDL ``process_operation`` / ``workflow_step_def``. Grill
decisions in the M1.12 PR:

* ``process_family`` enum + the deferred M1.7 process columns (family,
  ``is_default_purchased_component_process``, ``available_in_smart_rfq``,
  ``deleted_at``) land by forward ALTER (the stub-then-extend precedent).
* ``process_operation`` — router membership (which op defs a process
  generates, ordered, with per_setup / is_assembly / root_component_only
  flags). Stored as data; auto-routing application is M4's.
* ``workflow_step_def`` — the org's custom quote-item workflow steps
  (§7); the per-item ``quote_item_workflow_step`` waits for its consumer.
* ``email_template`` — minimal (key, locale, subject, body); German
  templates seeded, consumed by the M5 send flow.
* ``organization.dach_costing_mode`` (spec #dach-costing: default OFF,
  DACH orgs provisioned ON) + ``organization.default_expedite_tiers``
  (§6 expedite default set; prefills the M1.11 top-of-quote editor).
* All new tables org-scoped with RLS (tier-1 invariant) — the folded DDL's
  ``process_operation`` lacks ``org_id``; the invariant governs.

Revision ID: 0015_seed_catalog_config
Revises: 0014_addons_leadtimes
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_seed_catalog_config"
down_revision: str | None = "0014_addons_leadtimes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_RLS_TABLES = ("process_operation", "workflow_step_def", "email_template")

_PROCESS_COLUMNS = (
    "family",
    "is_default_purchased_component_process",
    "available_in_smart_rfq",
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE process_family AS ENUM ('SHEET_METAL','MILLING','LATHE','TUBE_LASER',"
        "'WIRE_EDM','CAST_URETHANE','ADDITIVE','ASSEMBLY','GENERIC')"
    )
    op.execute("ALTER TABLE process ADD COLUMN family process_family NOT NULL DEFAULT 'GENERIC'")
    op.execute(
        "ALTER TABLE process ADD COLUMN is_default_purchased_component_process boolean "
        "NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE process ADD COLUMN available_in_smart_rfq boolean NOT NULL DEFAULT false"
    )

    op.execute(
        """
        CREATE TABLE process_operation (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            process_id uuid NOT NULL,
            operation_def_id uuid NOT NULL,
            position integer NOT NULL,
            per_setup boolean NOT NULL DEFAULT false,
            is_assembly boolean NOT NULL DEFAULT false,
            root_component_only boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_process_operation_process_position
                UNIQUE (process_id, position),
            CONSTRAINT fk_process_operation_process_org
                FOREIGN KEY (org_id, process_id)
                REFERENCES process(org_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_process_operation_def_org
                FOREIGN KEY (org_id, operation_def_id)
                REFERENCES operation_def(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_process_operation_org_process ON process_operation (org_id, process_id)"
    )

    op.execute(
        """
        CREATE TABLE workflow_step_def (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            name text NOT NULL,
            position integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_workflow_step_def_org_name UNIQUE (org_id, name),
            CONSTRAINT uq_workflow_step_def_org_id_id UNIQUE (org_id, id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE email_template (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            key text NOT NULL,
            locale text NOT NULL DEFAULT 'de-DE',
            subject text NOT NULL,
            body text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_email_template_org_key_locale UNIQUE (org_id, key, locale)
        )
        """
    )

    # DACH Costing Mode (spec #dach-costing: config switch, default off; DACH
    # orgs provisioned on) + the §6 expedite default set
    op.execute(
        "ALTER TABLE organization ADD COLUMN dach_costing_mode boolean NOT NULL DEFAULT false"
    )
    op.execute("ALTER TABLE organization ADD COLUMN default_expedite_tiers jsonb")

    for table in _RLS_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
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
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS default_expedite_tiers")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS dach_costing_mode")
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS email_template")
    op.execute("DROP TABLE IF EXISTS workflow_step_def")
    op.execute("DROP TABLE IF EXISTS process_operation")
    for column in reversed(_PROCESS_COLUMNS):
        op.execute(f"ALTER TABLE process DROP COLUMN IF EXISTS {column}")
    op.execute("DROP TYPE IF EXISTS process_family")
