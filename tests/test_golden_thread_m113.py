"""M1.13 — golden-thread close + golden-test harness (spec #acceptance /
#milestones M1 exit).

* One parametrized test per ``fixtures/parts/*.json``: the harness seeds a
  clean org, builds the fixture quote through the API, and diffs the observed
  pricing **exactly** against ``fixtures/golden/*.pricing.json`` — all six
  Demo E figures (incl. 2.160,84 €), the Zuschlagskalkulation chain, and the
  CH/CHF region fixture.
* The golden-thread integration test: seed org (M1.12 catalog) → create
  quote → line item → seeded material + ops → costing → pricing → VAT
  totals — the thread M3/M4/M5 make progressively more real.
* Determinism: re-running a fixture on a fresh org reproduces the figure.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed
from tests.golden_harness import (
    FIXTURES_DIR,
    assert_matches_golden,
    fixture_names,
    load_golden,
    run_pricing_fixture,
)

ADMIN = [MembershipRole.admin]


@pytest.mark.parametrize("name", fixture_names())
def test_pricing_golden(name: str, app_client: TestClient, seeder: Seeder) -> None:
    observed = run_pricing_fixture(app_client, seeder, name)
    assert_matches_golden(observed, load_golden(name), name)


def test_goldens_are_deterministic(app_client: TestClient, seeder: Seeder) -> None:
    """Same fixture, two fresh orgs → the identical exact figure (harness AC)."""
    name = "demo-e-ex1-difficult-material"
    golden = load_golden(name)
    assert_matches_golden(run_pricing_fixture(app_client, seeder, name), golden, name)
    assert_matches_golden(run_pricing_fixture(app_client, seeder, name), golden, f"{name}-rerun")


def test_golden_thread_end_to_end(app_client: TestClient, seeder: Seeder) -> None:
    """The M1 exit thread: seeded catalog → quote → line → seeded material +
    op → costing → pricing (Zuschlag chain) → net + MwSt. + gross."""
    org = seeder.org("golden-thread-close")
    user = seeder.user("thread@golden.example")
    seeder.membership(user, org, ADMIN)
    seeder.configure_catalog(org)

    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        item = app_client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
        component_id = str(item["root_component_id"])

        # seeded material: 1.4301 → X5CrNi18-10 (AISI 304)
        material = app_client.get("/api/materials?q=1.4301").json()[0]
        res = app_client.patch(
            f"/api/components/{component_id}/material", json={"material_id": material["id"]}
        )
        assert res.status_code == 200, res.text

        # seeded ops from the 54-op library, with pilot-entered costs
        for def_name, cost in (("Material | Bar (Round)", "100.0000"), ("Fräsen", "100.0000")):
            op_def = next(
                d
                for d in app_client.get("/api/operation-defs", params={"q": def_name}).json()
                if d["name"] == def_name
            )
            created = app_client.post(
                f"/api/components/{component_id}/operations",
                json={"operation_def_id": op_def["id"]},
            )
            assert created.status_code == 201, created.text
            row = next(o for o in created.json()["operations"] if o["name"] == def_name)
            res = app_client.patch(
                f"/api/operations/{row['id']}/cells/1", json={"manual_cost": cost}
            )
            assert res.status_code == 200, res.text

        # pricing: the seeded Zuschlagskalkulation chain prices the thread
        summary = app_client.get(f"/api/components/{component_id}/pricing").json()
        row = next(t for t in summary["totals"] if t["quantity"] == 1)
        assert Decimal(row["unit_price"]) == Decimal("261.80")

        # and the quote-level VAT boundary closes it: net + MwSt. 19 % + gross
        totals = app_client.get(f"/api/quotes/{quote_id}/totals").json()
        assert totals["vat_label"] == "MwSt."
        assert (totals["net_minor"], totals["vat_minor"], totals["gross_minor"]) == (
            26180,
            4974,
            31154,
        )
        assert totals["has_unpriced_lines"] is False


def test_synthetic_samples_present() -> None:
    """The Part-2 layout ships with synthetic STEP/PDF/email samples so the
    M3/M4 pipelines have inputs before the Fechner packages land."""
    assert (FIXTURES_DIR / "cad" / "cube-20mm.step").read_text().startswith("ISO-10303-21;")
    assert (FIXTURES_DIR / "drawings" / "cube-20mm-print.pdf").read_bytes()[:5] == b"%PDF-"
    assert (FIXTURES_DIR / "email" / "rfq-sample.eml").exists()
    assert (FIXTURES_DIR / "seed.json").exists()
