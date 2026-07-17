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
from datetime import datetime
from decimal import Decimal
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
from app.catalog_seed import CatalogSeedResult, seed_material_catalog
from app.configure_seed import ConfigureSeedResult, seed_configure_catalog
from app.main import create_app
from app.models import (
    Account,
    AccountType,
    AppUser,
    Component,
    Contact,
    FileRole,
    Material,
    MaterialClass,
    MaterialFamily,
    MembershipRole,
    MembershipStatus,
    Node,
    Note,
    ObtainMethod,
    OpCategory,
    Operation,
    Organization,
    OrgCountry,
    Part,
    PartFile,
    Quote,
    QuoteStatus,
    SavedView,
    SavedViewScope,
    SavedViewVisibility,
    UserOrgMembership,
)
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

    def org(
        self,
        slug: str,
        name: str | None = None,
        *,
        country: str = "DE",
        currency: str = "EUR",
        locale: str = "de-DE",
    ) -> uuid.UUID:
        return self._loop.run_until_complete(
            self._org(slug, name, country=country, currency=currency, locale=locale)
        )

    def user(self, email: str) -> uuid.UUID:
        return self._loop.run_until_complete(self._user(email))

    def membership(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        roles: list[MembershipRole],
        *,
        status: MembershipStatus = MembershipStatus.active,
    ) -> uuid.UUID:
        return self._loop.run_until_complete(self._membership(user_id, org_id, roles, status))

    def note(self, org_id: uuid.UUID, body: str) -> uuid.UUID:
        return self._loop.run_until_complete(self._note(org_id, body))

    def account(
        self,
        org_id: uuid.UUID,
        name: str = "Acme GmbH",
        *,
        salesperson_id: uuid.UUID | None = None,
        type: AccountType = AccountType.customer,
    ) -> uuid.UUID:
        return self._loop.run_until_complete(
            self._account(org_id, name, salesperson_id=salesperson_id, type=type)
        )

    def contact(self, org_id: uuid.UUID, account_id: uuid.UUID | None, email: str) -> uuid.UUID:
        return self._loop.run_until_complete(self._contact(org_id, account_id, email))

    def part(self, org_id: uuid.UUID) -> uuid.UUID:
        return self._loop.run_until_complete(self._part(org_id))

    def sql(self, statement: str, params: dict[str, object] | None = None) -> None:
        """Run one raw statement as the owner (bypasses RLS) — for planting
        states no API mutates yet (e.g. an accepted finding before M3.2).

        This connection sees every org: callers must self-scope the statement
        (target rows by primary key, or filter by the intended ``org_id``) —
        the same convention ``_status_events`` follows on the owner engine."""

        async def _run() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(text(statement), params or {})

        self._loop.run_until_complete(_run())

    def bom_child(
        self,
        org_id: uuid.UUID,
        root_component_id: uuid.UUID,
        *,
        obtain_method: ObtainMethod = ObtainMethod.manufactured,
        piece_price: Decimal | None = None,
        manual_override_cost: Decimal | None = None,
        material_display: str | None = None,
        qty_relative_to_parent: int = 1,
    ) -> uuid.UUID:
        """Plant a BOM child under a root component: Part + Node + Component.
        The BOM Builder API is M4 — until then the pricing engine's tree
        roll-up (M1.10) is exercised via directly-seeded children."""
        return self._loop.run_until_complete(
            self._bom_child(
                org_id,
                root_component_id,
                obtain_method=obtain_method,
                piece_price=piece_price,
                manual_override_cost=manual_override_cost,
                material_display=material_display,
                qty_relative_to_parent=qty_relative_to_parent,
            )
        )

    def operation(
        self,
        org_id: uuid.UUID,
        component_id: uuid.UUID,
        name: str,
        *,
        category: OpCategory = OpCategory.operation,
        cost_formula: str | None = None,
        is_outside_service: bool = False,
        is_finish: bool = False,
        variable_overrides: dict[str, object] | None = None,
        position: int = 0,
    ) -> uuid.UUID:
        """Plant an operation row directly — used for **child** components,
        whose ops have no API until the M4 BOM Builder."""
        return self._loop.run_until_complete(
            self._operation(
                org_id,
                component_id,
                name,
                category=category,
                cost_formula=cost_formula,
                is_outside_service=is_outside_service,
                is_finish=is_finish,
                variable_overrides=variable_overrides or {},
                position=position,
            )
        )

    def part_file(
        self,
        org_id: uuid.UUID,
        part_id: uuid.UUID,
        filename: str = "bracket.step",
        *,
        role: FileRole = FileRole.supporting,
        file_type: str = "brep_cad",
    ) -> uuid.UUID:
        return self._loop.run_until_complete(
            self._part_file(org_id, part_id, filename, role=role, file_type=file_type)
        )

    def quote(
        self,
        org_id: uuid.UUID,
        number: str,
        *,
        status: QuoteStatus = QuoteStatus.draft,
        account_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        salesperson_id: uuid.UUID | None = None,
        estimator_id: uuid.UUID | None = None,
        rfq_number: str | None = None,
        due_date: datetime | None = None,
        status_before_hold: QuoteStatus | None = None,
    ) -> uuid.UUID:
        return self._loop.run_until_complete(
            self._quote(
                org_id,
                number,
                status=status,
                account_id=account_id,
                contact_id=contact_id,
                salesperson_id=salesperson_id,
                estimator_id=estimator_id,
                rfq_number=rfq_number,
                due_date=due_date,
                status_before_hold=status_before_hold,
            )
        )

    def saved_view(
        self,
        org_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
        *,
        view_scope: SavedViewScope = SavedViewScope.quotes,
        filters: list[dict[str, object]] | None = None,
        sort: list[dict[str, object]] | None = None,
        visibility: SavedViewVisibility = SavedViewVisibility.private,
    ) -> uuid.UUID:
        return self._loop.run_until_complete(
            self._saved_view(
                org_id,
                owner_id,
                name,
                view_scope=view_scope,
                filters=filters or [],
                sort=sort or [],
                visibility=visibility,
            )
        )

    def status_events(
        self, org_id: uuid.UUID, quote_id: uuid.UUID
    ) -> list[tuple[str | None, str, str | None]]:
        """Read a quote's append-only status-transition audit (from, to, note). The
        owner connection bypasses RLS, so the read is scoped to ``org_id`` explicitly
        (join through ``quote.org_id``) to match the org-scoped convention."""
        return self._loop.run_until_complete(self._status_events(org_id, quote_id))

    def catalog(self, org_id: uuid.UUID) -> CatalogSeedResult:
        """Run the M1.7 material-catalog + Core-4 process seed for an org."""
        return self._loop.run_until_complete(self._catalog(org_id))

    async def _catalog(self, org_id: uuid.UUID) -> CatalogSeedResult:
        async with AsyncSession(self._engine) as session, session.begin():
            return await seed_material_catalog(session, org_id=org_id)

    def configure_catalog(self, org_id: uuid.UUID) -> ConfigureSeedResult:
        """Run the M1.12 Configure seed (54-op library, routers, pricing
        defaults, …) for an org — the material catalog seeds first."""
        return self._loop.run_until_complete(self._configure_catalog(org_id))

    async def _configure_catalog(self, org_id: uuid.UUID) -> ConfigureSeedResult:
        async with AsyncSession(self._engine) as session, session.begin():
            await seed_material_catalog(session, org_id=org_id)
        async with AsyncSession(self._engine) as session, session.begin():
            return await seed_configure_catalog(session, org_id=org_id)

    def process_router_ops(self, org_id: uuid.UUID, *, family: str) -> list[uuid.UUID]:
        """The op-def ids a seeded process of ``family`` routes, in router
        order (M4.8 op-link tests need real process→op wiring)."""
        return self._loop.run_until_complete(self._process_router_ops(org_id, family))

    async def _process_router_ops(self, org_id: uuid.UUID, family: str) -> list[uuid.UUID]:
        from sqlalchemy import select

        from app.models import Process, ProcessOperation

        async with AsyncSession(self._engine) as session:
            process_id = await session.scalar(
                select(Process.id)
                .where(Process.org_id == org_id, Process.family == family)
                .order_by(Process.name)
                .limit(1)
            )
            if process_id is None:
                return []
            return list(
                (
                    await session.scalars(
                        select(ProcessOperation.operation_def_id)
                        .where(ProcessOperation.process_id == process_id)
                        .order_by(ProcessOperation.position)
                    )
                ).all()
            )

    async def _org(
        self, slug: str, name: str | None, *, country: str, currency: str, locale: str
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Organization(
                slug=slug,
                name=name or slug,
                country=OrgCountry(country),
                currency=currency,
                locale=locale,
            )
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
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        roles: list[MembershipRole],
        status: MembershipStatus,
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = UserOrgMembership(user_id=user_id, org_id=org_id, roles=roles, status=status)
            session.add(row)
            await session.flush()
            return row.id

    async def _note(self, org_id: uuid.UUID, body: str) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Note(org_id=org_id, body=body)
            session.add(row)
            await session.flush()
            return row.id

    async def _account(
        self,
        org_id: uuid.UUID,
        name: str,
        *,
        salesperson_id: uuid.UUID | None,
        type: AccountType,
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Account(org_id=org_id, name=name, salesperson_id=salesperson_id, type=type)
            session.add(row)
            await session.flush()
            return row.id

    async def _contact(
        self, org_id: uuid.UUID, account_id: uuid.UUID | None, email: str
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Contact(org_id=org_id, account_id=account_id, email=email)
            session.add(row)
            await session.flush()
            return row.id

    async def _part(self, org_id: uuid.UUID) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Part(org_id=org_id)
            session.add(row)
            await session.flush()
            return row.id

    async def _bom_child(
        self,
        org_id: uuid.UUID,
        root_component_id: uuid.UUID,
        *,
        obtain_method: ObtainMethod,
        piece_price: Decimal | None,
        manual_override_cost: Decimal | None,
        material_display: str | None,
        qty_relative_to_parent: int,
    ) -> uuid.UUID:
        from sqlalchemy import select

        async with AsyncSession(self._engine) as session, session.begin():
            root_component = await session.get(Component, root_component_id)
            assert root_component is not None
            root_node = await session.scalar(
                select(Node).where(
                    Node.part_id == root_component.part_id, Node.parent_node_id.is_(None)
                )
            )
            assert root_node is not None
            part = Part(org_id=org_id)
            session.add(part)
            await session.flush()
            session.add(
                Node(
                    org_id=org_id,
                    part_id=part.id,
                    parent_node_id=root_node.id,
                    qty_relative_to_parent=qty_relative_to_parent,
                    root_part_id=root_component.part_id,
                )
            )
            material_id = None
            if material_display is not None:
                material_id = await self._material(session, org_id, material_display)
            child = Component(
                org_id=org_id,
                part_id=part.id,
                is_root_component=False,
                obtain_method=obtain_method,
                piece_price=piece_price,
                manual_override_cost=manual_override_cost,
                material_id=material_id,
            )
            session.add(child)
            await session.flush()
            return child.id

    async def _material(
        self, session: AsyncSession, org_id: uuid.UUID, display_name: str
    ) -> uuid.UUID:
        from sqlalchemy import select

        material = await session.scalar(
            select(Material).where(Material.org_id == org_id, Material.display_name == display_name)
        )
        if material is not None:
            return material.id
        cls = await session.scalar(
            select(MaterialClass).where(
                MaterialClass.org_id == org_id, MaterialClass.name == "Metall"
            )
        )
        if cls is None:
            cls = MaterialClass(org_id=org_id, name="Metall")
            session.add(cls)
            await session.flush()
        family = await session.scalar(
            select(MaterialFamily).where(
                MaterialFamily.org_id == org_id, MaterialFamily.class_id == cls.id
            )
        )
        if family is None:
            family = MaterialFamily(org_id=org_id, class_id=cls.id, name="Testfamilie")
            session.add(family)
            await session.flush()
        material = Material(org_id=org_id, family_id=family.id, display_name=display_name)
        session.add(material)
        await session.flush()
        return material.id

    async def _operation(
        self,
        org_id: uuid.UUID,
        component_id: uuid.UUID,
        name: str,
        *,
        category: OpCategory,
        cost_formula: str | None,
        is_outside_service: bool,
        is_finish: bool,
        variable_overrides: dict[str, object],
        position: int,
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Operation(
                org_id=org_id,
                component_id=component_id,
                name=name,
                category=category,
                cost_formula=cost_formula,
                is_outside_service=is_outside_service,
                is_finish=is_finish,
                variable_overrides=variable_overrides,
                position=position,
            )
            session.add(row)
            await session.flush()
            return row.id

    async def _part_file(
        self,
        org_id: uuid.UUID,
        part_id: uuid.UUID,
        filename: str,
        *,
        role: FileRole,
        file_type: str,
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = PartFile(
                org_id=org_id,
                part_id=part_id,
                storage_key=f"seed/{org_id}/{part_id}/{filename}",
                filename=filename,
                file_type=file_type,
                size_bytes=0,
                role=role,
            )
            session.add(row)
            await session.flush()
            if role == FileRole.primary:
                part = await session.get(Part, part_id)
                if part is not None:
                    part.primary_file_id = row.id
            return row.id

    async def _quote(
        self,
        org_id: uuid.UUID,
        number: str,
        *,
        status: QuoteStatus,
        account_id: uuid.UUID | None,
        contact_id: uuid.UUID | None,
        salesperson_id: uuid.UUID | None,
        estimator_id: uuid.UUID | None,
        rfq_number: str | None,
        due_date: datetime | None,
        status_before_hold: QuoteStatus | None,
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = Quote(
                org_id=org_id,
                number=number,
                status=status,
                account_id=account_id,
                contact_id=contact_id,
                salesperson_id=salesperson_id,
                estimator_id=estimator_id,
                rfq_number=rfq_number,
                due_date=due_date,
                status_before_hold=status_before_hold,
            )
            session.add(row)
            await session.flush()
            return row.id

    async def _saved_view(
        self,
        org_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
        *,
        view_scope: SavedViewScope,
        filters: list[dict[str, object]],
        sort: list[dict[str, object]],
        visibility: SavedViewVisibility,
    ) -> uuid.UUID:
        async with AsyncSession(self._engine) as session, session.begin():
            row = SavedView(
                org_id=org_id,
                owner_id=owner_id,
                name=name,
                view_scope=view_scope,
                filters=filters,
                sort=sort,
                visibility=visibility,
            )
            session.add(row)
            await session.flush()
            return row.id

    async def _status_events(
        self, org_id: uuid.UUID, quote_id: uuid.UUID
    ) -> list[tuple[str | None, str, str | None]]:
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text(
                    "SELECT e.from_status, e.to_status, e.note FROM quote_status_event e "
                    "JOIN quote q ON q.id = e.quote_id "
                    "WHERE e.quote_id = :q AND q.org_id = :org ORDER BY e.created_at"
                ),
                {"q": str(quote_id), "org": str(org_id)},
            )
            return [(r[0], r[1], r[2]) for r in result.all()]


async def _truncate(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "TRUNCATE review_item, rule, quote_cell, operation, operation_def, "
                "quote_status_event, quote_item, component_quantity, component, "
                "quote_counter, saved_view, quote, node, part_geometry, part_file, part, "
                "material, material_family, material_class, process, account, contact, "
                "note, user_org_membership, app_user, organization CASCADE"
            )
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


@pytest.fixture
def eager_celery() -> Iterator[None]:
    """Run Celery tasks eagerly in-process (M2.5/M2.12 async-work tests).

    Results land in an in-process memory backend: CI has no Redis, and a
    result-store ConnectionError would otherwise retry-and-raise straight
    through the eager ``.delay()`` into the request under test."""
    from app.celery_app import celery_app

    saved = {
        key: celery_app.conf[key]
        for key in (
            "task_always_eager",
            "task_store_eager_result",
            "task_eager_propagates",
            "result_backend",
        )
    }
    celery_app.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
        # Task errors surface as task state, never as an exception inside the
        # enqueuing request (the M2.5 posture; assertions read DB effects).
        task_eager_propagates=False,
        result_backend="cache+memory://",
    )
    # The backend is a cached property — drop any cached instance so the config
    # change takes effect now and can't leak into later tests after restore.
    celery_app.__dict__.pop("backend", None)
    try:
        yield
    finally:
        celery_app.conf.update(**saved)
        celery_app.__dict__.pop("backend", None)
