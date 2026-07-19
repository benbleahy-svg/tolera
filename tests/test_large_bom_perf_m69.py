"""Large-assembly performance pass (M6.9).

The block requires the **>100-component assembly BOM** path (tree query, costing
roll-up, viewer) to stay "workable" at "acceptable interactive latency". No
document states a millisecond budget, so this suite asserts the property that
*causes* the latency instead: **the number of database round-trips must not grow
with the number of components.**

That choice is deliberate (ASSUMED, cheap to reverse — it is a test constant):

* A wall-clock ceiling on shared CI is flaky and tells you nothing about *why* a
  regression happened.
* Query count is deterministic, reproducible on any machine, and is the actual
  defect — the pre-M6.9 read path issued four-plus round-trips **per child**, so
  a 300-part assembly meant well over a thousand sequential queries.

The comparison is the assertion: the same endpoint is measured at a small and a
large component count, and the growth between them must be flat. A test that only
pinned an absolute number would pass forever by being loosened.

The correctness guard matters as much as the speed one: batching must not change
a single figure. :func:`test_costing_is_identical_before_and_after_batching` pins
the roll-up output against a hand-computed total, so a query-shape change can
never quietly move money (CLAUDE.md §5 tier-1).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models import MembershipRole, OpCategory
from tests.conftest import Seeder, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]

#: The block names ">100-component BOM"; 120 clears it with margin.
LARGE_BOM_SIZE = 120
#: The small control. The gap to LARGE_BOM_SIZE is what makes growth visible.
SMALL_BOM_SIZE = 10

#: Allowed extra round-trips when the assembly grows by 110 components. Not zero:
#: a few genuinely per-row statements are acceptable. Anything approaching one
#: query per component is the N+1 this pass exists to remove.
MAX_QUERY_GROWTH = 15


@contextmanager
def count_queries(client: TestClient) -> Iterator[list[str]]:
    """Record every SQL statement the app engine executes inside the block."""
    statements: list[str] = []
    engine = client.app.state.sessionmaker.kw["bind"].sync_engine  # type: ignore[attr-defined]

    def _before(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _assembly(
    client: TestClient, seeder: Seeder, org: uuid.UUID, *, children: int
) -> tuple[str, str]:
    """A root quote item with ``children`` manufactured children, each carrying one
    formula-costed material operation — the shape that made the old path issue a
    full Kalk environment load per child."""
    quote_id = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
    root_component = uuid.UUID(item["root_component_id"])

    for index in range(children):
        child = seeder.bom_child(org, root_component, material_display=f"Aluminium 6061 #{index}")
        seeder.operation(
            org,
            child,
            f"Rohmaterial {index}",
            category=OpCategory.material,
            cost_formula="COST = 10\nDAYS = 0\n",
        )
    return str(item["id"]), str(root_component)


def _measure(
    client: TestClient, seeder: Seeder, org: uuid.UUID, user: uuid.UUID, *, children: int
) -> int:
    with authed(client, user_id=user, org_id=org, roles=ADMIN):
        item_id, _ = _assembly(client, seeder, org, children=children)
        with count_queries(client) as statements:
            resp = client.get(f"/api/quote-items/{item_id}/assembly-components")
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["tree"]) == children
    return len(statements)


def test_assembly_read_does_not_scale_queries_with_component_count(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The core perf assertion: a 12x bigger assembly must not mean 12x the
    round-trips. Growth is flat, not linear."""
    org, user = _org_admin(seeder, "org-perf")

    small = _measure(app_client, seeder, org, user, children=SMALL_BOM_SIZE)
    large = _measure(app_client, seeder, org, user, children=LARGE_BOM_SIZE)

    growth = large - small
    assert growth <= MAX_QUERY_GROWTH, (
        f"{LARGE_BOM_SIZE - SMALL_BOM_SIZE} extra components added {growth} queries "
        f"({small} -> {large}) — the read path is still per-component."
    )


def test_large_bom_renders_every_component(app_client: TestClient, seeder: Seeder) -> None:
    """Workable means complete: a >100-component assembly returns all of them,
    with no cap silently clipping the tail."""
    org, user = _org_admin(seeder, "org-large")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        item_id, _ = _assembly(app_client, seeder, org, children=LARGE_BOM_SIZE)
        body = app_client.get(f"/api/quote-items/{item_id}/assembly-components").json()
    assert len(body["tree"]) == LARGE_BOM_SIZE


def test_costing_is_identical_before_and_after_batching(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The correctness guard on the perf pass. Batching changes *how* rows are
    fetched, never *what* they cost — so pin the roll-up against a hand-computed
    figure: 120 children x COST = 10 each = 1200,0000."""
    org, user = _org_admin(seeder, "org-money")
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        item_id, _ = _assembly(app_client, seeder, org, children=LARGE_BOM_SIZE)
        body = app_client.get(f"/api/quote-items/{item_id}/assembly-components").json()

    # The assembly summary is the roll-up over every child's costed operations.
    [total] = body["summary"]["totals"]
    assert Decimal(total) == Decimal(LARGE_BOM_SIZE) * Decimal(10)
    assert body["summary"]["flat_qty_total"] == LARGE_BOM_SIZE
