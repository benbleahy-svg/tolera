"""Two-way email threading (M3.5).

Spec ``#email-connectivity`` ("Data model (M0 — required from day one)"):

* ``user_email_connection`` — a user's connected mailbox (Gmail / Outlook /
  generic SMTP+IMAP) an org's quotes are sent from. Credentials (OAuth refresh
  token or SMTP password bundle) are AES-256-GCM ciphertext (``bytea``) —
  encrypted by the app, never logged. Per (org, user): a user in two orgs
  connects per org (CLAUDE.md §5 tenancy). "Can have multiple, one marked
  primary" → partial unique index. ``gmail_history_id`` / ``outlook_delta_link``
  are the incremental sync cursors; ``last_synced_at`` is the status-page
  timestamp.
* ``quote_email_thread`` — ONE row per quote that has been sent by email:
  ``sent_message_id`` = RFC 2822 Message-ID of the *first* outbound message,
  ``provider_thread_id`` = Gmail threadId / Outlook conversationId. Replies
  match on these (or on ``quote.email_thread_id`` from M3.3 ingest).
* ``email_message`` — every message in a quote thread, both directions.
  ``rfc_message_id`` carries the partial unique index that makes the 5-minute
  sync idempotent (a re-poll can never duplicate a reply). Attachments are
  saved to Object Storage and linked here as JSONB metadata.

RLS + grants follow the 0022 pattern. No DELETE grant on the thread/message
tables — the communications timeline is an audit trail; connections may be
deleted (disconnect).

Revision ID: 0024_email_threading
Revises: 0023_rfq_suggested_line_items
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024_email_threading"
down_revision: str | None = "0023_rfq_suggested_line_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "tolera_app"


def upgrade() -> None:
    op.execute("CREATE TYPE email_connection_type AS ENUM ('gmail', 'outlook', 'smtp_imap')")
    op.execute("CREATE TYPE email_direction AS ENUM ('outbound', 'inbound')")

    op.execute(
        """
        CREATE TABLE user_email_connection (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            user_id uuid NOT NULL REFERENCES app_user(id),
            connection_type email_connection_type NOT NULL,
            from_address citext NOT NULL,
            from_name text,
            encrypted_credentials bytea NOT NULL,
            is_primary boolean NOT NULL DEFAULT false,
            gmail_history_id text,
            outlook_delta_link text,
            last_synced_at timestamptz,
            last_sync_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_email_connection_org_id_id UNIQUE (org_id, id)
        )
        """
    )
    # "One marked primary" per user (spec #email-connectivity data model).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_email_connection_primary
            ON user_email_connection (org_id, user_id)
            WHERE is_primary
        """
    )
    op.execute(
        "CREATE INDEX ix_email_connection_org_user ON user_email_connection (org_id, user_id)"
    )

    op.execute(
        """
        CREATE TABLE quote_email_thread (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            quote_id uuid NOT NULL,
            sent_message_id text NOT NULL,
            provider_thread_id text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_quote_email_thread_org_id_id UNIQUE (org_id, id),
            CONSTRAINT fk_quote_email_thread_quote_org
                FOREIGN KEY (org_id, quote_id) REFERENCES quote (org_id, id),
            CONSTRAINT uq_quote_email_thread_quote UNIQUE (org_id, quote_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_quote_email_thread_sent_message_id
            ON quote_email_thread (org_id, sent_message_id)
        """
    )

    op.execute(
        """
        CREATE TABLE email_message (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organization(id),
            thread_id uuid NOT NULL,
            connection_id uuid,
            direction email_direction NOT NULL,
            rfc_message_id text,
            in_reply_to text,
            from_address citext NOT NULL,
            to_addresses jsonb NOT NULL DEFAULT '[]'::jsonb,
            subject text,
            body_text text,
            body_html text,
            attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
            sent_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_email_message_thread_org
                FOREIGN KEY (org_id, thread_id) REFERENCES quote_email_thread (org_id, id),
            CONSTRAINT fk_email_message_connection_org
                FOREIGN KEY (org_id, connection_id)
                REFERENCES user_email_connection (org_id, id)
                ON DELETE SET NULL (connection_id)
        )
        """
    )
    # Sync idempotency: one stored copy per Message-Id per org — a re-polled
    # UNSEEN message or a redelivered sync task can never duplicate a reply.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_email_message_org_message_id
            ON email_message (org_id, rfc_message_id)
            WHERE rfc_message_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX ix_email_message_org_thread ON email_message (org_id, thread_id, created_at)"
    )

    for table in ("user_email_connection", "quote_email_thread", "email_message"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table}
                USING (org_id = current_setting('app.current_org_id', true)::uuid)
                WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
            """
        )
    # Connections are disconnectable; threads/messages are an audit trail.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON user_email_connection TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON quote_email_thread TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON email_message TO {APP_ROLE}")

    # The 5-minute beat task fans out one sync task per connection, but it runs
    # before any org GUC is set — RLS (correctly) hides every connection row.
    # Narrow SECURITY DEFINER enumeration (the resolve_org_id_by_slug precedent,
    # 0022): ids only, no addresses, no credentials; every actual read/write
    # then happens in an org-scoped session.
    op.execute(
        """
        CREATE FUNCTION list_email_sync_targets()
            RETURNS TABLE (org_id uuid, connection_id uuid)
            LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = public
            AS 'SELECT org_id, id FROM user_email_connection'
        """
    )
    op.execute("REVOKE ALL ON FUNCTION list_email_sync_targets() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION list_email_sync_targets() TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS list_email_sync_targets()")
    for table in ("email_message", "quote_email_thread", "user_email_connection"):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP TYPE email_direction")
    op.execute("DROP TYPE email_connection_type")
