"""Shared pytest fixtures.

The tenancy fixtures (``tenancy_db`` / ``app_client`` / ``seeder`` / ``authed``)
provision a real Postgres so the M0.2 RLS spine is exercised end-to-end:

* ``tenancy_db`` (session) ensures the restricted ``tolera_app`` role exists with
  a known password and runs ``alembic upgrade head`` against ``TEST_DATABASE_URL``
  (the owner DSN). It self-provisions, so CI needs no extra migration step.
* ``app_client`` serves requests as the *restricted* role — the same boundary as
  production, so RLS is genuinely in force.
* ``seeder`` writes fixtures through the *owner* (superuser) connection, which
  bypasses RLS — the only way to plant rows across orgs for an isolation test.
* ``authed`` swaps ``get_principal`` so a test acts as a chosen user/org/roles
  without involving Clerk.

All tenancy fixtures skip cleanly when ``TEST_DATABASE_URL`` is unset/unreachable.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from alembic import command
from app.auth import Principal, get_principal
from app.main import create_app
from app.models import AppUser, MembershipRole, Note, Organization, UserOrgMembership
from tests.support import build_settings

APP_ROLE_PASSWORD = "tolera_app"


# --------------------------------------------------------------------------- #
# M0.1 fixtures (no auth/tenancy)
# --------------------------------------------------------------------------- #
@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient over a fresh app. Used as a context manager so lifespan runs."""
    with TestClient(create_app(build_settings())) as test_client:
        yield test_client


@pytest.fixture
def db_client() -> Iterator[TestClient]:
    """A TestClient wired to a real Postgres via ``TEST_DATABASE_URL``.

    Skips when the variable is unset or the database is unreachable, so the
    suite stays green locally without a database while still exercising the
    round-trip in CI (where a Postgres service is provided).
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — Postgres round-trip skipped")
    try:
        with TestClient(create_app(build_settings(database_url=url))) as test_client:
            if test_client.get("/readyz").json().get("db") != "ok":
                pytest.skip("TEST_DATABASE_URL not reachable")
            yield test_client
    except Exception:
        pytest.skip("TEST_DATABASE_URL not reachable")


# --------------------------------------------------------------------------- #
# M0.2 tenancy fixtures
# --------------------------------------------------------------------------- #
def _owner_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


def app_role_url(owner_url: str) -> str:
    """The restricted-role DSN, derived from the owner DSN."""
    return (
        make_url(owner_url)
        .set(username="tolera_app", password=APP_ROLE_PASSWORD)
        .render_as_string(hide_password=False)
    )


async def _ping(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def _set_app_role_password(owner_url: str) -> None:
    engine = create_async_engine(owner_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(f"ALTER ROLE tolera_app WITH LOGIN PASSWORD '{APP_ROLE_PASSWORD}'")
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def tenancy_db() -> Iterator[str]:
    """Ensure the test DB is migrated and the app role is usable; yield the owner DSN."""
    # Fail closed in CI: the RLS/auth exit gate must never silently skip there,
    # or a broken DB service could let the security suite "pass" untested.
    in_ci = bool(os.environ.get("CI"))
    owner = _owner_url()
    if not owner:
        if in_ci:
            pytest.fail("TEST_DATABASE_URL not set — tenancy gate cannot be skipped in CI")
        pytest.skip("TEST_DATABASE_URL not set — tenancy tests skipped")
    try:
        asyncio.run(_ping(owner))
    except Exception as exc:
        if in_ci:
            pytest.fail(f"TEST_DATABASE_URL unreachable in CI — cannot skip the gate: {exc!r}")
        pytest.skip("TEST_DATABASE_URL not reachable — tenancy tests skipped")

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", owner)
    command.upgrade(cfg, "head")  # creates the role (if absent) + schema + grants + RLS
    asyncio.run(_set_app_role_password(owner))
    yield owner


@pytest.fixture
def app_client(tenancy_db: str) -> Iterator[TestClient]:
    """A TestClient whose app serves requests as the restricted (RLS-bound) role."""
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    with TestClient(create_app(settings)) as test_client:
        yield test_client


class Seeder:
    """Plants fixture rows via the owner connection (superuser → bypasses RLS)."""

    def __init__(self, loop: asyncio.AbstractEventLoop, engine: AsyncEngine) -> None:
        self._loop = loop
        self._engine = engine

    def org(self, slug: str, name: str | None = None) -> uuid.UUID:
        return self._loop.run_until_complete(self._org(slug, name))

    def user(self, email: str) -> uuid.UUID:
        return self._loop.run_until_complete(self._user(email))

    def membership(
        self, user_id: uuid.UUID, org_id: uuid.UUID, roles: list[MembershipRole]
    ) -> uuid.UUID:
        return self._loop.run_until_complete(self._membership(user_id, org_id, roles))

    def note(self, org_id: uuid.UUID, body: str) -> uuid.UUID:
        return self._loop.run_until_complete(self._note(org_id, body))

    async def _org(self, slug: str, name: str | None) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Organization(slug=slug, name=name or slug)
            session.add(row)
            await session.flush()
            return row.id

    async def _user(self, email: str) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = AppUser(email=email)
            session.add(row)
            await session.flush()
            return row.id

    async def _membership(
        self, user_id: uuid.UUID, org_id: uuid.UUID, roles: list[MembershipRole]
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = UserOrgMembership(user_id=user_id, org_id=org_id, roles=roles)
            session.add(row)
            await session.flush()
            return row.id

    async def _note(self, org_id: uuid.UUID, body: str) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Note(org_id=org_id, body=body)
            session.add(row)
            await session.flush()
            return row.id


async def _truncate(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text("TRUNCATE note, user_org_membership, app_user, organization CASCADE")
        )
        await conn.commit()


@pytest.fixture
def seeder(tenancy_db: str) -> Iterator[Seeder]:
    """Owner-connection seeding; truncates tenant tables after each test."""
    loop = asyncio.new_event_loop()
    engine = create_async_engine(tenancy_db)
    try:
        yield Seeder(loop, engine)
    finally:
        loop.run_until_complete(_truncate(engine))
        loop.run_until_complete(engine.dispose())
        loop.close()


@contextmanager
def authed(
    client: TestClient,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    roles: list[MembershipRole],
) -> Iterator[None]:
    """Act as the given principal for the duration of the block (no Clerk)."""
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=user_id, active_org_id=org_id, roles=tuple(roles)
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_principal, None)
