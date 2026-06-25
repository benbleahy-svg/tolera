"""parts & part files — file upload & storage (M1.2).

Adds the ``part`` stub and ``part_file`` (the entity uploaded files attach to).
Files belong to a Part — never to a quote/line-item — and a Part can exist
independently (DECISIONS.md 2026-06-25). M1.2 creates only the columns
``part_file`` needs; M1.5 extends ``part`` (part_number, BOM/Node tree, …) via its
own reversible migration.

Both tables inherit the M0.2 tenancy pattern verbatim (ENABLE + FORCE RLS with the
``org_isolation`` policy on the ``app.current_org_id`` GUC). Cross-org references
are DB invariants, not merely RLS-scoped: ``part_file.(org_id, part_id)`` FKs to
``part(org_id, id)``, and ``part.primary_file_id`` FKs to ``part_file(id)`` (added
by ALTER after both tables exist, to break the circular dependency).

Two M1.2 rulings encoded here (DECISIONS.md 2026-06-25):
  * **One PRIMARY per part** — partial unique index ``uq_part_file_one_primary``;
    ``part.primary_file_id`` is the authority, ``part_file.role`` is kept in sync.
  * **Hard delete** of files — ``part_file`` has no ``deleted_at`` and the app role
    is granted DELETE (purging the blob is GDPR erasure); ``part`` keeps soft-delete
    (``deleted_at``) and is granted no DELETE.

Revision ID: 0006_parts_files
Revises: 0005_accounts_contacts
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_parts_files"
down_revision: str | None = "0005_accounts_contacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"
_ORG_SCOPED_TABLES = ("part", "part_file")


def upgrade() -> None:
    # --- part (stub) ---
    op.execute(
        """
        CREATE TABLE part (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            -- authoritative pointer to the PRIMARY file; FK to part_file added below
            -- (ON DELETE SET NULL: deleting the last/primary file clears the pointer).
            primary_file_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            -- Composite-FK target so part_file.(org_id, part_id) is pinned same-org.
            CONSTRAINT uq_part_org_id_id UNIQUE (org_id, id)
        )
        """
    )

    # --- part_file ---
    op.execute(
        """
        CREATE TABLE part_file (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            part_id uuid NOT NULL,
            storage_key text NOT NULL,
            filename text NOT NULL,
            file_type text NOT NULL,          -- FileCategory: brep_cad|mesh|vector_2d|...
            content_type text,                -- MIME, for download headers
            size_bytes bigint NOT NULL,
            role text NOT NULL DEFAULT 'supporting',
            is_redacted boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            -- A file's part must be in the SAME org (composite FK). CASCADE so a
            -- (future, M1.5) hard part delete takes its files with it.
            CONSTRAINT fk_part_file_part_same_org
                FOREIGN KEY (org_id, part_id) REFERENCES part(org_id, id)
                ON DELETE CASCADE,
            CONSTRAINT ck_part_file_role CHECK (role IN ('primary', 'supporting')),
            -- File size is a byte count — never negative (integrity at the boundary).
            CONSTRAINT ck_part_file_size_nonneg CHECK (size_bytes >= 0),
            -- Composite-FK target so part.primary_file_id can be pinned to a file
            -- OF THIS PART (id is already unique as PK; this lets (id, part_id) be
            -- referenced).
            CONSTRAINT uq_part_file_id_part UNIQUE (id, part_id)
        )
        """
    )

    # Close the circular reference and make "the PRIMARY file belongs to THIS part"
    # a DB invariant, not just an app check: part.(primary_file_id, id) references
    # part_file.(id, part_id), so a part can only point at one of its OWN files.
    # Column-specific SET NULL (Postgres 15+) nulls ONLY primary_file_id when the
    # referenced file is deleted — part.id (a NOT NULL PK) is left untouched.
    op.execute(
        """
        ALTER TABLE part ADD CONSTRAINT fk_part_primary_file_same_part
            FOREIGN KEY (primary_file_id, id) REFERENCES part_file(id, part_id)
            ON DELETE SET NULL (primary_file_id)
        """
    )

    # --- indexes ---
    op.execute("CREATE INDEX ix_part_org_deleted_at ON part (org_id, deleted_at)")
    # At most one PRIMARY per part (DECISIONS.md 2026-06-25).
    op.execute(
        "CREATE UNIQUE INDEX uq_part_file_one_primary ON part_file (part_id) WHERE role = 'primary'"
    )
    op.execute("CREATE INDEX ix_part_file_part_id ON part_file (part_id)")

    # --- restricted app-role grants ---
    # part: no DELETE (soft-delete only). part_file: DELETE granted — file removal is
    # a hard delete that purges the blob (GDPR erasure, DECISIONS.md 2026-06-25).
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON part TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON part_file TO {APP_ROLE}")

    # --- row-level security (identical pattern to note/account, M0.2) ---
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
    op.execute(f"REVOKE ALL ON part_file FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON part FROM {APP_ROLE}")
    # Break the circular FK before dropping the tables it ties together.
    op.execute("ALTER TABLE part DROP CONSTRAINT IF EXISTS fk_part_primary_file_same_part")
    op.execute("DROP TABLE IF EXISTS part_file")
    op.execute("DROP TABLE IF EXISTS part")
