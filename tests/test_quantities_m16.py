"""API/DB tests for M1.6 — quantity breaks + ``ComponentQuantity`` cells.

Runs against a real RLS-bound Postgres (``app_client``). Covers: the default qty=1 break
on a new line item; "Change quantities" reshaping the per-qty grid (add/remove/reorder);
the root identity (make = deliver = quantity); the index-aligned ``part.*`` iterators
(``get_quantities`` / ``get_make_quantities`` / ``get_bom_quantities``) for a 1/5/20 set;
duplicate/empty/non-positive rejection; the ``quote_edit`` gate; draft-only locking; and
org isolation.

Acceptance (build-plan M1.6): adding/removing breaks reshapes the per-qty grid; make-qty
vs deliver-qty are distinct fields, index-aligned across the lists.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.errors import AppError
from app.models import MembershipRole
from app.quantities import (
    get_bom_quantities,
    get_make_quantities,
    get_quantities,
    set_quantity_breaks,
)
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
ENGINEER = [MembershipRole.engineer]  # has no quote_edit (read+annotate only, M0.3)


def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_line_item(client: TestClient) -> tuple[str, dict[str, Any]]:
    """Create a draft quote + one line item; return (quote_id, the item dict)."""
    qid = client.post("/api/quotes", json={}).json()["id"]
    detail = client.post(f"/api/quotes/{qid}/items")
    assert detail.status_code == 201, detail.text
    return qid, detail.json()["items"][0]


def _set_quantities(client: TestClient, qid: str, item_id: str, quantities: list[int]) -> Any:
    return client.put(
        f"/api/quotes/{qid}/items/{item_id}/quantities", json={"quantities": quantities}
    )


def _cols(grid: list[dict[str, Any]]) -> tuple[list[int], list[int], list[int]]:
    """Split a grid into the three column-wise lists (the index-aligned contract)."""
    return (
        [c["quantity"] for c in grid],
        [c["make_quantity"] for c in grid],
        [c["deliver_quantity"] for c in grid],
    )


# --------------------------------------------------------------------------- #
# Default break on line-item creation
# --------------------------------------------------------------------------- #
def test_new_line_item_has_default_qty_1_break(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        _, item = _new_line_item(app_client)
    assert item["quantities"] == [{"quantity": 1, "make_quantity": 1, "deliver_quantity": 1}]


# --------------------------------------------------------------------------- #
# "Change quantities" reshapes the grid (add / remove / reorder)
# --------------------------------------------------------------------------- #
def test_change_quantities_reshapes_grid(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        item_id = item["id"]
        added = _set_quantities(app_client, qid, item_id, [1, 5, 20])
        assert added.status_code == 200, added.text
        grid_after_add = added.json()["items"][0]["quantities"]
        # Remove down to a single, different break.
        removed = _set_quantities(app_client, qid, item_id, [10])
        grid_after_remove = removed.json()["items"][0]["quantities"]
    assert [c["quantity"] for c in grid_after_add] == [1, 5, 20]
    assert [c["quantity"] for c in grid_after_remove] == [10]


def test_change_quantities_canonical_ascending(app_client: TestClient, seeder: Seeder) -> None:
    # Order in the request is irrelevant — the server canonicalises ascending so the
    # three index-aligned lists share a stable index.
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        res = _set_quantities(app_client, qid, item["id"], [20, 1, 5])
    assert [c["quantity"] for c in res.json()["items"][0]["quantities"]] == [1, 5, 20]


def test_make_and_deliver_equal_quantity_for_root(app_client: TestClient, seeder: Seeder) -> None:
    # M1.6 root identity: no children, no scrap → make = deliver = quantity (real tree /
    # scrap math is M4). The fields are distinct columns, just equal in value here.
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        grid = _set_quantities(app_client, qid, item["id"], [1, 5, 20]).json()["items"][0][
            "quantities"
        ]
    for cell in grid:
        assert cell["make_quantity"] == cell["quantity"]
        assert cell["deliver_quantity"] == cell["quantity"]


# --------------------------------------------------------------------------- #
# The geometry↔Kalk iterators are index-aligned (the M1.6 fixture: 1/5/20)
# --------------------------------------------------------------------------- #
def test_iterators_align_for_multi_break(
    app_client: TestClient, seeder: Seeder, tenancy_db: str
) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        _set_quantities(app_client, qid, item["id"], [20, 1, 5])
    component_id = uuid.UUID(item["root_component_id"])

    async def _read() -> tuple[list[int], list[int], list[int]]:
        # Owner (superuser) session bypasses RLS — a direct read of the committed cells.
        engine = create_async_engine(tenancy_db)
        try:
            async with AsyncSession(engine) as session:
                return (
                    await get_quantities(session, org, component_id),
                    await get_make_quantities(session, org, component_id),
                    await get_bom_quantities(session, org, component_id),
                )
        finally:
            await engine.dispose()

    quantities, make, bom = asyncio.run(_read())
    assert quantities == [1, 5, 20]  # ascending, the canonical index order
    assert make == [1, 5, 20]
    assert bom == [1, 5, 20]
    # Index-aligned: same length, position i is the same break across all three lists.
    assert len(quantities) == len(make) == len(bom)


def test_set_quantity_breaks_guards_direct_callers(
    app_client: TestClient, seeder: Seeder, tenancy_db: str
) -> None:
    # The request layer (ChangeQuantitiesRequest) rejects empty/non-positive, but the
    # helper is reusable (M1.9 Kalk, M4 BOM). A direct caller must get a clean AppError —
    # not silently wipe all breaks ([]) or trip the raw DB CHECK ([0]).
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        _, item = _new_line_item(app_client)
    component_id = uuid.UUID(item["root_component_id"])

    async def _call(quantities: list[int]) -> None:
        engine = create_async_engine(tenancy_db)
        try:
            async with AsyncSession(engine) as session:
                await set_quantity_breaks(session, org, component_id, quantities)
        finally:
            await engine.dispose()

    with pytest.raises(AppError) as empty_exc:
        asyncio.run(_call([]))
    assert empty_exc.value.code == "invalid_quantity_breaks"
    with pytest.raises(AppError) as nonpos_exc:
        asyncio.run(_call([0, 5]))
    assert nonpos_exc.value.code == "invalid_quantity_breaks"


# --------------------------------------------------------------------------- #
# Validation — duplicate / empty / non-positive
# --------------------------------------------------------------------------- #
def test_duplicate_quantities_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        res = _set_quantities(app_client, qid, item["id"], [5, 5, 20])
    assert res.status_code == 422
    assert res.json()["code"] == "duplicate_quantity"


def test_empty_quantities_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        res = _set_quantities(app_client, qid, item["id"], [])
    assert res.status_code == 422  # min_length=1 — a line item must keep >=1 break
    assert res.json()["code"] == "validation_error"  # standard envelope, not a default body


def test_nonpositive_quantity_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        zero = _set_quantities(app_client, qid, item["id"], [0, 5])
        negative = _set_quantities(app_client, qid, item["id"], [-3])
    assert zero.status_code == 422  # per-item ge=1
    assert zero.json()["code"] == "validation_error"
    assert negative.status_code == 422
    assert negative.json()["code"] == "validation_error"


# --------------------------------------------------------------------------- #
# Permissions, draft-only locking, org isolation
# --------------------------------------------------------------------------- #
def test_change_quantities_requires_quote_edit(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    eng = seeder.user("eng@org-a.example")
    seeder.membership(eng, org, ENGINEER)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
    with authed(app_client, user_id=eng, org_id=org, roles=ENGINEER):
        res = _set_quantities(app_client, qid, item["id"], [1, 5])
    assert res.status_code == 403
    assert res.json()["code"] == "forbidden"


def test_change_quantities_locked_when_not_draft(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid, item = _new_line_item(app_client)
        # draft → cancelled (admin holds quote_delete); cancelled is not editable.
        cancel = app_client.post(f"/api/quotes/{qid}/transition", json={"to_status": "cancelled"})
        assert cancel.status_code == 200, cancel.text
        res = _set_quantities(app_client, qid, item["id"], [1, 5])
    assert res.status_code == 409
    assert res.json()["code"] == "quote_locked"


def test_change_quantities_item_must_belong_to_quote(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        _qid_a, item_a = _new_line_item(app_client)
        qid_b, _ = _new_line_item(app_client)
        # item_a's id under quote B is a 404 (the quote_id guard), not a cross-quote edit.
        res = _set_quantities(app_client, qid_b, item_a["id"], [1, 5])
    assert res.status_code == 404
    assert res.json()["code"] == "not_found"


def test_change_quantities_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b, admin_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        qid, item = _new_line_item(app_client)
    # Org B cannot see or reshape org A's line item (RLS → the quote is a 404).
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        res = _set_quantities(app_client, qid, item["id"], [1, 5])
    assert res.status_code == 404
    assert res.json()["code"] == "not_found"
