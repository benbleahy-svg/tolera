"""export-control audit + org export regime (M6.9 — pilot hardening).

Two changes, both required by the block's "export-control/CUI-equivalent audit"
scope:

1. ``organization.export_regime`` — the config the spec ``#dach-delta`` demands
   ("Export-control regime = **config, not hardcoded**") and that DECISIONS
   2026-06-26 ("Export-controlled flag home", M1.5) explicitly deferred to M6:
   *"The org-level ``export_regime`` enum (``none|eu_dual_use|itar``) is deferred
   to M6 (export-control connectors)."* Defaulted to ``eu_dual_use`` because
   ``organization.country`` is a hard DE/AT/CH enum and DACH-DELTA-LAYER §5 puts
   Reg (EU) 2021/821 + AWG/AWV in place of ITAR/CUI for exactly that region.

2. ``export_control_access`` — the append-only compliance log behind the spec's
   Settings → Company Settings → **"CUI Audit: download CSV"** entry, and the
   evidence for ``#authz``'s decided posture: *"Export-controlled (ITAR / CUI /
   EU dual-use): flag + audit, **no hard block** in v1 — any internal user may
   open flagged quotes/parts/files, but access is **logged**."*

   Generalises :class:`QuoteTokenAccess` (M5.1), whose docstring defers "full
   CUI/GDPR archival hardening" to this compliance pass. ``quote_token_access``
   is left untouched — it keeps logging *every* external portal load, which is a
   broader duty than the export-control flag.

**Append-only at the database.** ``tolera_app`` receives SELECT + INSERT only —
no UPDATE, no DELETE — following the ``quote_status_event`` precedent (M1.4,
migration 0008). A compliance log a compromised app role can rewrite is not a
compliance log. The org owner role retains full rights for the (human-gated)
GDPR-erasure path.

``actor_user_id`` carries **no FK** on purpose: the audit entry must outlive the
user row it names, exactly as ``order_history_event.actor_user_id`` does (0046).
Erasing a user must never silently blank the compliance trail.

RLS follows the M0.2 tenancy pattern verbatim (ENABLE + FORCE + ``org_isolation``
keyed on the ``app.current_org_id`` GUC).

``downgrade`` drops the policy + grants, the table, then the three enum types and
the organization column — fully reversible, no data migration to unwind.

Revision ID: 0056_export_control_audit
Revises: 0055_crm_integration
Create Date: 2026-07-19

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0056_export_control_audit"
down_revision: str | None = "0055_crm_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"

_TABLE = "export_control_access"


def upgrade() -> None:
    # --- 1. enum types ----------------------------------------------------
    op.execute("CREATE TYPE export_regime AS ENUM ('none', 'eu_dual_use', 'itar')")
    op.execute(
        "CREATE TYPE export_control_subject AS ENUM "
        "('part', 'part_file', 'quote', 'quote_item', 'request_for_quote', 'vendor_rfq')"
    )
    op.execute(
        "CREATE TYPE export_control_action AS ENUM "
        "('view', 'download', 'ai_skip', 'external_send', 'screening')"
    )

    # --- 2. org-level regime config --------------------------------------
    op.execute(
        "ALTER TABLE organization "
        "ADD COLUMN export_regime export_regime NOT NULL DEFAULT 'eu_dual_use'"
    )

    # --- 3. the append-only compliance log --------------------------------
    op.execute(
        f"""
        CREATE TABLE {_TABLE} (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            -- NULL = system/worker action or unauthenticated external actor.
            -- Deliberately not an FK: the entry outlives the user it names.
            actor_user_id uuid,
            subject_type export_control_subject NOT NULL,
            subject_id uuid NOT NULL,
            action export_control_action NOT NULL,
            -- Denormalised so the log stays truthful after a Settings change.
            regime export_regime NOT NULL DEFAULT 'none',
            detail jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            ip_address text,
            user_agent text,
            occurred_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # The CSV export reads a date-ordered window per org; the subject index
    # serves "show me everything that touched this part".
    op.execute(
        f"CREATE INDEX ix_export_control_access_org_occurred ON {_TABLE} (org_id, occurred_at)"
    )
    op.execute(
        f"CREATE INDEX ix_export_control_access_org_subject "
        f"ON {_TABLE} (org_id, subject_type, subject_id)"
    )

    # --- 4. append-only grants (quote_status_event precedent, 0008) -------
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO {APP_ROLE}")

    # --- 5. row-level security (M0.2 pattern) -----------------------------
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY org_isolation ON {_TABLE}
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS org_isolation ON {_TABLE}")
    op.execute(f"REVOKE ALL ON {_TABLE} FROM {APP_ROLE}")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
    op.execute("ALTER TABLE organization DROP COLUMN IF EXISTS export_regime")
    op.execute("DROP TYPE IF EXISTS export_control_action")
    op.execute("DROP TYPE IF EXISTS export_control_subject")
    op.execute("DROP TYPE IF EXISTS export_regime")
