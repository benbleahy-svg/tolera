"""Tests for M1.14 — config-completeness guard (spec #operation-rates-banner
+ #missing-rates-warning).

* Banner counts: unrated rate-bearing op defs + costless materials; material
  lines / outside processes / Kalk-priced defs never count.
* Quick-start APPLY TO ALL fills every unrated def in one write and never
  overwrites a configured rate.
* Quote-side: a line item using a rate-less operation flags — the quote
  detail carries ``missing_rates_item_count`` (the non-blocking banner), the
  costing view flags the row (amber highlight) — and setting the rate clears
  both. Deterministic, org-scoped.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]


@contextmanager
def _as_admin(client: TestClient, org: uuid.UUID, user: uuid.UUID) -> Iterator[TestClient]:
    with authed(client, user_id=user, org_id=org, roles=ADMIN):
        yield client


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _completeness(client: TestClient) -> dict[str, Any]:
    res = client.get("/api/config-completeness")
    assert res.status_code == 200, res.text
    return cast(dict[str, Any], res.json())


def _create_def(client: TestClient, name: str, **extra: Any) -> str:
    res = client.post("/api/operation-defs", json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def test_banner_counts_unrated_defs_and_clears_on_rate(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "m114-banner")
    with _as_admin(app_client, org, user) as client:
        def_id = _create_def(client, "Fräsen")
        # material lines, outside processes and Kalk-priced defs never count
        _create_def(client, "Rohmaterial", category="material")
        _create_def(client, "Eloxieren", calculation_mode="outside_process")
        kalk_def = _create_def(client, "Laser (Kalk)")
        res = client.patch(
            f"/api/operation-defs/{kalk_def}", json={"cost_formula": "COST = 5\nDAYS = 0"}
        )
        assert res.status_code == 200, res.text

        assert _completeness(client)["unrated_operation_defs"] == 1

        res = client.patch(f"/api/operation-defs/{def_id}", json={"run_rate": "85"})
        assert res.status_code == 200, res.text
        assert _completeness(client)["unrated_operation_defs"] == 0


def test_unrated_materials_count(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "m114-materials")
    seeder.catalog(org)  # the M1.7 tree seeds with costs NULL by design
    with _as_admin(app_client, org, user) as client:
        before = _completeness(client)["unrated_materials"]
        assert before > 0
        material = client.get("/api/materials?q=1.4301").json()[0]
        res = client.patch(f"/api/materials/{material['id']}", json={"cost_per_volume": "0.008"})
        assert res.status_code == 200, res.text
        assert _completeness(client)["unrated_materials"] == before - 1


def test_apply_to_all_fills_only_unrated_defs(seeder: Seeder, app_client: TestClient) -> None:
    """The quick-start banner: one write, configured rates never overwritten."""
    org, user = _org_admin(seeder, "m114-apply")
    with _as_admin(app_client, org, user) as client:
        _create_def(client, "Fräsen")
        _create_def(client, "Drehen")
        rated = _create_def(client, "Schleifen", run_rate="120")

        res = client.post("/api/operation-defs/apply-rate", json={"run_rate": "85"})
        assert res.status_code == 200, res.text
        assert res.json() == {"updated": 2, "unrated_operation_defs": 0}

        defs = {d["name"]: d for d in client.get("/api/operation-defs?q=").json()}
        assert defs["Fräsen"]["run_rate"] == "85.0000"
        assert defs["Drehen"]["run_rate"] == "85.0000"
        assert defs["Schleifen"]["run_rate"] == "120.0000", rated  # untouched


def test_quote_flags_line_items_using_rateless_ops(seeder: Seeder, app_client: TestClient) -> None:
    """AC: a quote using an unrated op flags the line; the rate clears it."""
    org, user = _org_admin(seeder, "m114-quote")
    with _as_admin(app_client, org, user) as client:
        qid = client.post("/api/quotes", json={}).json()["id"]
        item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
        component_id = str(item["root_component_id"])
        created = client.post(f"/api/components/{component_id}/operations", json={"name": "Fräsen"})
        assert created.status_code == 201, created.text
        assert created.json()["has_missing_rates"] is True
        row = next(o for o in created.json()["operations"] if o["name"] == "Fräsen")
        assert row["missing_rate"] is True

        detail = client.get(f"/api/quotes/{qid}").json()
        assert detail["missing_rates_item_count"] == 1

        # setting the rate on the quote's own row clears every surface
        res = client.patch(f"/api/operations/{row['id']}", json={"run_rate": "85"})
        assert res.status_code == 200, res.text
        costing = client.get(f"/api/components/{component_id}/costing").json()
        assert costing["has_missing_rates"] is False
        assert all(not op["missing_rate"] for op in costing["operations"])
        assert client.get(f"/api/quotes/{qid}").json()["missing_rates_item_count"] == 0


def test_counts_are_org_scoped(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "m114-org-a")
    org_b, user_b = _org_admin(seeder, "m114-org-b")
    with _as_admin(app_client, org_a, user_a) as client:
        _create_def(client, "Fräsen")
        assert _completeness(client)["unrated_operation_defs"] == 1
    with _as_admin(app_client, org_b, user_b) as client:
        assert _completeness(client)["unrated_operation_defs"] == 0
