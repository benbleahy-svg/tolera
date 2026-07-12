"""The golden-fixtures runner (SEED-AND-FIXTURES Part 2; M1.13).

Loads a declarative fixture from ``fixtures/parts/<name>.json``, seeds a
**clean org** for it (unique slug per fixture; optionally the full M1.7 +
M1.12 catalog), builds the quote through the real API, and returns the
observed pricing in the golden schema so the test can diff it **exactly**
against ``fixtures/golden/<name>.pricing.json``.

BOM children are planted via the owner-side :class:`~tests.conftest.Seeder`
until the M4 BOM Builder API exists — the same stand-in the M1.10 goldens
use. Money is compared as :class:`~decimal.Decimal`, never as floats.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from app.models import MembershipRole, ObtainMethod, OpCategory
from tests.conftest import Seeder, authed

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

ADMIN = [MembershipRole.admin]


def fixture_names() -> list[str]:
    return sorted(path.stem for path in (FIXTURES_DIR / "parts").glob("*.json"))


def load_fixture(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((FIXTURES_DIR / "parts" / f"{name}.json").read_text(encoding="utf-8")),
    )


def load_golden(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((FIXTURES_DIR / "golden" / f"{name}.pricing.json").read_text(encoding="utf-8")),
    )


def _plant_children(
    seeder: Seeder, org: uuid.UUID, component_id: str, children: list[dict[str, Any]]
) -> None:
    for child in children:
        obtain = ObtainMethod[child.get("obtain_method", "manufactured")]
        piece_price = child.get("piece_price")
        child_id = seeder.bom_child(
            org,
            uuid.UUID(component_id),
            obtain_method=obtain,
            piece_price=Decimal(piece_price) if piece_price is not None else None,
            material_display=child.get("material_display"),
            qty_relative_to_parent=child.get("qty_relative_to_parent", 1),
        )
        for position, op in enumerate(child.get("operations", ())):
            seeder.operation(
                org,
                child_id,
                op["name"],
                category=OpCategory(op.get("category", "operation")),
                cost_formula=op.get("cost_formula"),
                is_outside_service=op.get("is_outside_service", False),
                is_finish=op.get("is_finish", False),
                position=position,
            )


def _build_root_operations(
    client: TestClient, component_id: str, operations: list[dict[str, Any]]
) -> None:
    for op in operations:
        body: dict[str, Any] = {"name": op["name"]}
        if op.get("category"):
            body["category"] = op["category"]
        if op.get("is_outside_service"):
            body["is_outside_service"] = True
        if op.get("is_finish"):
            body["is_finish"] = True
        created = client.post(f"/api/components/{component_id}/operations", json=body)
        assert created.status_code == 201, created.text
        row = next(o for o in created.json()["operations"] if o["name"] == op["name"])
        for quantity, cost in op.get("manual_costs", {}).items():
            res = client.patch(
                f"/api/operations/{row['id']}/cells/{quantity}", json={"manual_cost": cost}
            )
            assert res.status_code == 200, res.text
        if op.get("variable_overrides"):
            res = client.put(
                f"/api/operations/{row['id']}/variables",
                json={"overrides": op["variable_overrides"]},
            )
            assert res.status_code == 200, res.text


def run_pricing_fixture(app_client: TestClient, seeder: Seeder, name: str) -> dict[str, Any]:
    """Build one fixture on a clean org; return the observed golden document."""
    fixture = load_fixture(name)
    org_spec = fixture.get("org", {})
    # a CLEAN org per run: unique slug so re-runs and the determinism test
    # never collide — the figures must not depend on org identity
    run_id = uuid.uuid4().hex[:8]
    org = seeder.org(
        f"golden-{name[:40]}-{run_id}",
        country=org_spec.get("country", "DE"),
        currency=org_spec.get("currency", "EUR"),
    )
    user = seeder.user(f"harness-{run_id}@{name[:40]}.example")
    seeder.membership(user, org, ADMIN)
    if org_spec.get("configure_catalog"):
        seeder.configure_catalog(org)

    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        item = app_client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
        component_id = str(item["root_component_id"])
        quantities = fixture.get("quantities", [1])
        if quantities != [1]:
            res = app_client.put(
                f"/api/quotes/{quote_id}/items/{item['id']}/quantities",
                json={"quantities": quantities},
            )
            assert res.status_code == 200, res.text

        _build_root_operations(app_client, component_id, fixture.get("root_operations", []))
        _plant_children(seeder, org, component_id, fixture.get("children", []))
        for payload in fixture.get("pricing_items", []):
            res = app_client.post(f"/api/components/{component_id}/pricing-items", json=payload)
            assert res.status_code == 201, res.text
        # a Seeder-planted child changes costs outside the API's reprice
        # triggers — one refresh re-runs the whole calc chain deterministically
        res = app_client.post(f"/api/quotes/{quote_id}/refresh-pricing")
        assert res.status_code == 200, res.text

        summary = app_client.get(f"/api/components/{component_id}/pricing").json()
        observed: dict[str, Any] = {
            "currency": app_client.get(f"/api/quotes/{quote_id}").json()["currency"],
            "breaks": [
                {
                    "quantity": row["quantity"],
                    "unit_price": row["unit_price"],
                    "total_price": row["total_price"],
                }
                for row in summary["totals"]
            ],
        }
        if fixture.get("check_totals"):
            totals = app_client.get(f"/api/quotes/{quote_id}/totals").json()
            observed["totals"] = {
                "vat_label": totals["vat_label"],
                "vat_rate_pct": totals["vat_rate_pct"],
                "net_minor": totals["net_minor"],
                "vat_minor": totals["vat_minor"],
                "gross_minor": totals["gross_minor"],
            }
        return observed


def assert_matches_golden(observed: dict[str, Any], golden: dict[str, Any], name: str) -> None:
    """Exact pricing diff — Decimal-compared money, serialization-agnostic."""
    assert observed["currency"] == golden["currency"], name
    assert len(observed["breaks"]) == len(golden["breaks"]), name
    for got, want in zip(observed["breaks"], golden["breaks"], strict=True):
        assert got["quantity"] == want["quantity"], name
        for field in ("unit_price", "total_price"):
            assert Decimal(str(got[field])) == Decimal(str(want[field])), (
                f"{name}: {field} at qty {want['quantity']} — "
                f"got {got[field]}, golden {want[field]}"
            )
    if "totals" in golden:
        got_totals = observed["totals"]
        want_totals = golden["totals"]
        assert got_totals["vat_label"] == want_totals["vat_label"], name
        assert Decimal(str(got_totals["vat_rate_pct"])) == Decimal(
            str(want_totals["vat_rate_pct"])
        ), name
        for field in ("net_minor", "vat_minor", "gross_minor"):
            assert got_totals[field] == want_totals[field], (
                f"{name}: {field} — got {got_totals[field]}, golden {want_totals[field]}"
            )
