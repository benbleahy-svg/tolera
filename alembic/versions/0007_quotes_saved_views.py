"""quotes (stub) & saved views — saved-view engine + quotes list (M1.3).

Adds two org-scoped tables behind the quotes list:

  * ``quote`` — a **minimal stub** carrying only the columns the list needs to
    *render and filter* (number, status, account/salesperson/estimator, rfq_number,
    due_date). This mirrors how M1.2 created a minimal ``part`` that "M1.5 extends …
    does not reshape": **M1.4 owns** quote creation, the lifecycle state machine
    (enforced transitions), ``quote_item``, the Trash/soft-delete + ``cancelled``
    rulings, and same-org composite-FK hardening — all added by forward ALTER, not by
    reshaping this table (DECISIONS.md 2026-06-25 "M1.3 build path"). The app role is
    granted **SELECT only** here: M1.3 has no quote-create endpoint (quotes are planted
    by the seeder/owner for the list test); M1.4's migration grants INSERT/UPDATE.

  * ``saved_view`` — a user-owned filter/sort preset. ``filters``/``sort`` are JSONB
    whose shape is **identical** to the ``POST /api/quotes/search`` request body, so
    applying a view = replaying its stored clauses (one grammar, no translation). The
    owner is pinned to an active org membership by a composite FK ((owner_id, org_id)
    → user_org_membership) — a member of *this* org, a tenancy invariant RLS alone
    can't give for the org-less ``app_user`` (the salesperson-FK pattern, M1.1).
    ``visibility`` (``private`` | ``org``) is **reserved**: only ``private`` is honored
    in v1; org-sharing is deferred (DECISIONS.md 2026-06-25 "SavedView sharing").
    System/derived views (All Quotes, My Quotes, Drafts, Outstanding, Overdue) are
    computed in code — never stored — so this table holds only user-created views.

Both tables inherit the M0.2 tenancy pattern verbatim (ENABLE + FORCE RLS with the
``org_isolation`` policy keyed on the ``app.current_org_id`` GUC).

``quote_status`` is the canonical 5-value enum (``draft, sent, won, lost, expired``),
NOT the 7 UI "folders": Drafts→draft, Outstanding→sent, Accepted→won, Expired→expired,
Lost→lost; Cancelled/Trash are M1.4 lifecycle decisions (DECISIONS.md 2026-06-25).

Revision ID: 0007_quotes_saved_views
Revises: 0006_parts_files
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_quotes_saved_views"
down_revision: str | None = "0006_parts_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
_ORG_SCOPED_TABLES = ("quote", "saved_view")


def upgrade() -> None:
    # --- enums ---
    # Canonical 5-value status (DB-SCHEMA.sql). M1.4 may extend (e.g. 'cancelled').
    op.execute("CREATE TYPE quote_status AS ENUM ('draft', 'sent', 'won', 'lost', 'expired')")
    op.execute("CREATE TYPE saved_view_scope AS ENUM ('quotes', 'line_items')")
    op.execute("CREATE TYPE saved_view_visibility AS ENUM ('private', 'org')")

    # --- quote (minimal stub — M1.4 extends, does not reshape) ---
    op.execute(
        """
        CREATE TABLE quote (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            number text NOT NULL,
            status quote_status NOT NULL DEFAULT 'draft',
            -- The grid's Account/Salesperson columns + the account/owner filters.
            -- Plain FKs here (as in the canonical DDL); M1.4 hardens these to the
            -- same-org composite-FK rigor when it builds the real relationships.
            account_id uuid REFERENCES account(id),
            salesperson_id uuid REFERENCES app_user(id),
            estimator_id uuid REFERENCES app_user(id),
            rfq_number text,
            due_date timestamptz,          -- powers the computed "Overdue" system view
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            -- Quote numbers are unique within an org (auto-incremented by M1.4).
            CONSTRAINT uq_quote_org_number UNIQUE (org_id, number),
            -- Composite-FK target so M1.4's quote_item.(org_id, quote_id) can be
            -- pinned same-org without reshaping this table (mirrors part/part_file).
            CONSTRAINT uq_quote_org_id_id UNIQUE (org_id, id)
        )
        """
    )

    # --- saved_view (user-owned filter/sort presets) ---
    op.execute(
        """
        CREATE TABLE saved_view (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            owner_id uuid NOT NULL,
            view_scope saved_view_scope NOT NULL,
            name text NOT NULL,
            filters jsonb NOT NULL DEFAULT '[]'::jsonb,
            sort jsonb NOT NULL DEFAULT '[]'::jsonb,
            visibility saved_view_visibility NOT NULL DEFAULT 'private',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            -- The owner must be a member of THIS org (tenancy invariant; the
            -- salesperson-membership FK pattern from M1.1, but required not nullable).
            CONSTRAINT fk_saved_view_owner_membership
                FOREIGN KEY (owner_id, org_id)
                REFERENCES user_org_membership(user_id, org_id),
            -- A user can't keep two views of the same scope under one name.
            CONSTRAINT uq_saved_view_owner_scope_name
                UNIQUE (org_id, owner_id, view_scope, name)
        )
        """
    )

    # --- indexes ---
    # Quotes list: filter by status, default-sort + paginate by created_at; both
    # lead with org_id (RLS scopes on it).
    op.execute("CREATE INDEX ix_quote_org_status ON quote (org_id, status)")
    op.execute("CREATE INDEX ix_quote_org_created_at ON quote (org_id, created_at)")
    # Saved-view list query is (org_id, owner_id, view_scope).
    op.execute(
        "CREATE INDEX ix_saved_view_org_owner_scope ON saved_view (org_id, owner_id, view_scope)"
    )

    # --- restricted app-role grants ---
    # quote: SELECT only — M1.3 reads quotes; M1.4's migration grants INSERT/UPDATE
    # when it adds quote creation. saved_view: full CRUD (presets hard-delete).
    op.execute(f"GRANT SELECT ON quote TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON saved_view TO {APP_ROLE}")

    # --- row-level security (identical pattern to note/account/part, M0.2) ---
    for table in _ORG_SCOPED_TABLES:
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
    for table in _ORG_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
    op.execute(f"REVOKE ALL ON saved_view FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON quote FROM {APP_ROLE}")
    op.execute("DROP TABLE IF EXISTS saved_view")
    op.execute("DROP TABLE IF EXISTS quote")
    op.execute("DROP TYPE IF EXISTS saved_view_visibility")
    op.execute("DROP TYPE IF EXISTS saved_view_scope")
    op.execute("DROP TYPE IF EXISTS quote_status")
