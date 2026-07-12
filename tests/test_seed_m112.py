"""Tests for M1.12 — the Configure seed catalog.

* **Counts + content** — the spec `#oplibrary` 54-op German library (32
  machine_plus_operator + 22 labour_only, numbered tables verbatim) plus the
  §3/§4 router-support entries; the §2 class set; Core-4 + Assembly + PC
  routers; §6 pricing/discount/add-on defaults; §7 workflow steps, custom
  tables, email templates. Rates stay NULL (never pre-seeded).
* **Idempotency** — a second run creates nothing and changes nothing.
* **End-to-end** — a quote picks a seeded op + material (the block's AC).
* **Zuschlagskalkulation golden** — the seeded MGK/VwGK/VtGK/Gewinn chain
  (spec `#zuschlagskalkulation` defaults 10/8/6/10) prices a 100 € material +
  100 € inside line to exactly 261,80 € via the get_herstellkosten()/
  get_selbstkosten() Kalk helpers (DACH Costing Mode on).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]

# spec #oplibrary numbered tables: 32 + 22 = 54 German ops; +10 support entries
GERMAN_OPS = 54
SUPPORT_OPS = 10


@contextmanager
def _as_admin(client: TestClient, org: uuid.UUID, user: uuid.UUID) -> Iterator[TestClient]:
    with authed(client, user_id=user, org_id=org, roles=ADMIN):
        yield client


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def test_seed_counts_and_content(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "seed-counts")
    result = seeder.configure_catalog(org)
    assert result.operation_defs_created == GERMAN_OPS + SUPPORT_OPS
    assert result.classes_created == 7  # Metall is M1.7's; §2 adds the rest
    assert result.materials_created == 3  # POM / PA6 / PEEK
    assert result.processes_created == 2  # Assembly + PC; Core-4 exist from M1.7
    assert result.router_rows_created == 18
    # DACH orgs get the pure Zuschlagskalkulation chain — no Standardaufschlag
    # on top (its Gewinn item carries the profit; a general markup would
    # double-count and pollute get_selbstkosten())
    assert result.pricing_item_defs_created == 4
    assert result.discount_defs_created == 1
    assert result.add_on_defs_created == 7  # #addons types + Minimum Order Charge
    assert result.workflow_steps_created == 5  # incl. "No Quote" (§7)
    assert result.custom_tables_created == 3
    assert result.email_templates_created == 3  # incl. follow-up (§7)

    with _as_admin(app_client, org, user) as client:

        def op_def(name: str) -> dict[str, Any]:
            hits = client.get("/api/operation-defs", params={"q": name}).json()
            return cast(dict[str, Any], next(d for d in hits if d["name"] == name))

        # spec rows keep their mode; rates are never pre-seeded
        assert op_def("Fräsen")["calculation_mode"] == "machine_plus_operator"
        assert op_def("Fräsen")["run_rate"] is None
        assert op_def("Entgraten")["calculation_mode"] == "labour_only"
        assert op_def("Outside Service | General")["is_outside_service"] is True
        assert op_def("Material | Sheet (Nesting)")["category"] == "material"

        # §2 classes browsable in the picker tree
        tree = client.get("/api/materials/tree").json()
        class_names = {c["name"] for c in tree}
        assert {
            "Metall",
            "Kunststoff",
            "Verbundwerkstoff",
            "Sand",
            "Wachs",
            "Additiv",
            "Holz",
            "Sonstige",
        } <= class_names

        # Werkstoffnummer lookup: 1.4301 → 304 (DIN↔AISI crosswalk)
        hits = client.get("/api/materials?q=1.4301").json()
        assert any(h["aisi_alias"] == "304" for h in hits)

        # add-on types feed the M1.11 dropdown
        add_on_defs = {d["name"] for d in client.get("/api/add-on-defs").json()}
        assert "First Article Inspection (FAI)" in add_on_defs
        assert "Tooling Charge" in add_on_defs


def test_seed_is_idempotent(seeder: Seeder) -> None:
    org, _ = _org_admin(seeder, "seed-idempotent")
    first = seeder.configure_catalog(org)
    assert first.operation_defs_created == GERMAN_OPS + SUPPORT_OPS
    second = seeder.configure_catalog(org)
    assert all(v == 0 for v in asdict(second).values()), asdict(second)


def test_quote_picks_seeded_op_and_material(seeder: Seeder, app_client: TestClient) -> None:
    """The block's AC: a quote uses a seeded op/material end-to-end."""
    org, user = _org_admin(seeder, "seed-endtoend")
    seeder.configure_catalog(org)
    with _as_admin(app_client, org, user) as client:
        qid = client.post("/api/quotes", json={}).json()["id"]
        item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
        component_id = str(item["root_component_id"])
        # pick the seeded Fräsen from the library (typeahead path)
        fraesen = next(
            d for d in client.get("/api/operation-defs?q=Fräsen").json() if d["name"] == "Fräsen"
        )
        res = client.post(
            f"/api/components/{component_id}/operations",
            json={"operation_def_id": fraesen["id"]},
        )
        assert res.status_code == 201, res.text
        assert any(op["name"] == "Fräsen" for op in res.json()["operations"])
        # pick the seeded 1.4301 material
        material = client.get("/api/materials?q=1.4301").json()[0]
        res = client.patch(
            f"/api/components/{component_id}/material", json={"material_id": material["id"]}
        )
        assert res.status_code == 200, res.text


def test_zuschlagskalkulation_chain_prices_the_spec_example(
    seeder: Seeder, app_client: TestClient
) -> None:
    """Material 100 € + Inside 100 € through the seeded chain
    (#zuschlagskalkulation defaults): MGK 10 % on MEK = 10,00 · VwGK 8 % on
    Herstellkosten (200) = 16,00 · VtGK 6 % on Herstellkosten = 12,00 ·
    Gewinn 10 % on Selbstkosten (238) = 23,80 → Angebotspreis netto 261,80."""
    org, user = _org_admin(seeder, "seed-zuschlag")
    seeder.configure_catalog(org)
    with _as_admin(app_client, org, user) as client:
        qid = client.post("/api/quotes", json={}).json()["id"]
        item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
        component_id = str(item["root_component_id"])
        # the seeded defaults ARE the pure Zuschlag chain — nothing to remove
        for name, category, cost in (
            ("Rohmaterial", "material", "100.0000"),
            ("Fräsen", None, "100.0000"),
        ):
            body: dict[str, Any] = {"name": name}
            if category:
                body["category"] = category
            created = client.post(f"/api/components/{component_id}/operations", json=body)
            assert created.status_code == 201, created.text
            op = next(o for o in created.json()["operations"] if o["name"] == name)
            res = client.patch(f"/api/operations/{op['id']}/cells/1", json={"manual_cost": cost})
            assert res.status_code == 200, res.text

        summary = client.get(f"/api/components/{component_id}/pricing").json()
        amounts = {
            i["name"]: cast(dict[str, Any], next(c for c in i["cells"] if c["quantity"] == 1))
            for i in summary["pricing_items"]
        }
        assert Decimal(amounts["Materialgemeinkosten (MGK)"]["amount"]) == Decimal("10.0000")
        assert Decimal(amounts["Verwaltungsgemeinkosten (VwGK)"]["amount"]) == Decimal("16.0000")
        assert Decimal(amounts["Vertriebsgemeinkosten (VtGK)"]["amount"]) == Decimal("12.0000")
        assert Decimal(amounts["Gewinnzuschlag"]["amount"]) == Decimal("23.8000")

        row = next(t for t in summary["totals"] if t["quantity"] == 1)
        assert Decimal(row["unit_price"]) == Decimal("261.80")
        assert Decimal(row["total_price"]) == Decimal("261.80")
