"""Async SQLAlchemy 2.0 engine + the org-scoped session that enforces RLS.

The request-serving engine connects as a restricted, ``NOBYPASSRLS`` role (see
``Settings.effective_app_database_url`` and DECISIONS.md 2026-06-24). Every unit
of work runs inside :func:`org_scoped_session`, which opens a transaction and
sets the transaction-local ``app.current_org_id`` GUC; the Postgres RLS policies
(authored in the migration) read that GUC, so a query can only ever see rows of
the active org. This is the tenancy pattern every later block inherits.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# The GUC the RLS policies key on. Must match the migration's policy definitions.
ORG_ID_GUC = "app.current_org_id"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(database_url: str) -> AsyncEngine:
    """Create the async engine. ``pool_pre_ping`` keeps connections healthy."""
    return create_async_engine(database_url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the (restricted) app engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def org_scoped_session(
    sessionmaker: async_sessionmaker[AsyncSession], org_id: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    """Yield a session pinned to ``org_id`` for the life of one transaction.

    ``set_config(..., is_local => true)`` scopes the GUC to this transaction, so
    it cannot leak across pooled connections. The transaction commits on clean
    exit and rolls back on error.
    """
    async with sessionmaker() as session, session.begin():
        await session.execute(
            text(f"SELECT set_config('{ORG_ID_GUC}', :oid, true)"),
            {"oid": str(org_id)},
        )
        yield session
