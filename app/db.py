"""Async SQLAlchemy 2.0 engine.

M0.1 defines no domain tables (those arrive with tenancy in M0.2). This module
only stands up the async engine the readiness probe round-trips through.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models (org-scoped tables land in M0.2)."""


def make_engine(database_url: str) -> AsyncEngine:
    """Create the async engine. ``pool_pre_ping`` keeps connections healthy."""
    return create_async_engine(database_url, pool_pre_ping=True)
