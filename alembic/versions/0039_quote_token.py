"""Quote tokens — the Digital Quote buyer portal's unauthenticated access (M5.1).

Spec ``#digitalquote`` ("QuoteToken entity (unified — covers all external
access)"). The buyer opens ``/q/:token`` with no login; the token is a signed
JWT (``exp`` deliberately omitted — expiry is a soft app-layer property) whose
row is the authority for revocation and access logging.

M5.1 mints/accepts only the ``buyer_portal`` scope; ``vendor_share`` /
``vendor_rfq`` are reserved values for M6 (no target tables yet, so the spec's
``external_share_id`` / ``vendor_rfq_recipient_id`` columns are deferred with
them — the M1.4 precedent: no speculative column without a FK target).

Two tables:

* ``quote_token`` — the credential. ``quote_id`` is nullable at the DB (the
  unified entity also serves the file-only vendor scopes later) but the service
  enforces NOT NULL for ``buyer_portal``. Composite same-org FK to ``quote``
  (§5 tenancy) with ON DELETE CASCADE — a token is worthless without its quote.
* ``quote_token_access`` — append-only load log ("Access is logged (feeds the
  CUI audit log)"). CASCADE with the token.

Both are org-scoped + RLS like every tenant table.

Revision ID: 0039_quote_token
Revises: 0038_opdef_variable_visibility
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0039_quote_token"
down_revision: str | None = "0038_opdef_variable_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute(
        "CREATE TYPE quote_token_scope AS ENUM ('buyer_portal', 'vendor_share', 'vendor_rfq')"
    )

    op.execute(
        """
        CREATE TABLE quote_token (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            scope quote_token_scope NOT NULL,
            quote_id uuid,
            recipient_email text,
            token text NOT NULL,
            revoked_at timestamptz,
            file_permissions jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_quote_token_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_quote_token_quote_org
                FOREIGN KEY (org_id, quote_id)
                REFERENCES quote(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_quote_token_org_quote ON quote_token (org_id, quote_id)")

    op.execute(
        """
        CREATE TABLE quote_token_access (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_token_id uuid NOT NULL,
            ip_address text,
            user_agent text,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_quote_token_access_token_org
                FOREIGN KEY (org_id, quote_token_id)
                REFERENCES quote_token(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_quote_token_access_org_token "
        "ON quote_token_access (org_id, quote_token_id, occurred_at)"
    )

    for table in ("quote_token", "quote_token_access"):
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
    for table in ("quote_token_access", "quote_token"):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP TYPE IF EXISTS quote_token_scope")
