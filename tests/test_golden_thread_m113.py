"""M1.13 — golden-thread close + golden-test harness (spec #acceptance /
#milestones M1 exit).

* One parametrized test per ``fixtures/parts/*.json``: the harness seeds a
  clean org, builds the fixture quote through the API, and diffs the observed
  pricing **exactly** against ``fixtures/golden/*.pricing.json`` — all six
  Demo E figures (incl. 2.160,84 €), the Zuschlagskalkulation chain, and the
  CH/CHF region fixture.
* The golden-thread integration test: **since M3.4 the thread enters through
  real intake** — the fixture ``.eml`` hits the Mailgun webhook (M3.3), the
  Lens body-parse suggestion prefills Bulk Create, the explicit Accept creates
  the line item (M3.4) — then seeded material + ops → costing → pricing → VAT
  totals reproduce the same figures as the M1 direct-create entry.
* Determinism: re-running a fixture on a fresh org reproduces the figure.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lens import RawLineItem
from app.main import create_app
from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed
from tests.golden_harness import (
    FIXTURES_DIR,
    assert_matches_golden,
    fixture_names,
    load_golden,
    run_pricing_fixture,
)
from tests.support import build_settings, eager_celery, post_mailgun_webhook

ADMIN = [MembershipRole.admin]

THREAD_SIGNING_KEY = "golden-thread-signing-key"


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


class _ThreadPartsListProvider:
    """The thread's scripted Lens body parse: suggests the fixture's one part
    (its number exists only in the attachment filename — guard-legal) with the
    body's "Losgroessen 1, 5 und 20 Stueck" quantities."""

    async def parse_email_parts_list(
        self, body_text: str, attachment_filenames: list[str]
    ) -> list[RawLineItem]:
        return [RawLineItem(part_number="cube-20mm", quantities=[1, 5, 20], confidence=0.9)]


@pytest.fixture
def thread_intake_client(tenancy_db: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An app client with real intake wired: Mailgun key set, Celery eager,
    the vision extraction stubbed (M3.1's suite owns it), and the scripted
    parts-list provider registered."""
    from app import lens_provider

    monkeypatch.setattr(
        "app.email_ingest._enqueue_lens_extract",
        lambda org_id, part_id, file_id: None,
    )
    lens_provider.register(_ThreadPartsListProvider())  # type: ignore[arg-type]
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.mailgun_webhook_signing_key = THREAD_SIGNING_KEY
    try:
        with eager_celery(), TestClient(create_app(settings)) as client:
            yield client
    finally:
        lens_provider.register(None)


def test_golden_thread_end_to_end(thread_intake_client: TestClient, seeder: Seeder) -> None:
    """The golden thread, entering through REAL intake since M3.4: the fixture
    ``.eml`` → Mailgun webhook → draft quote (M3.3) → Lens prefill → explicit
    Bulk-Create Accept (M3.4) → seeded material + op → costing → pricing
    (Zuschlag chain) → net + MwSt. + gross — the same Demo E figures as the
    M1 direct-create entry."""
    app_client = thread_intake_client
    org = seeder.org("golden-thread-close")
    user = seeder.user("thread@golden.example")
    seeder.membership(user, org, ADMIN)
    seeder.configure_catalog(org)

    # Intake: the RFQ email (1.4301, Losgroessen 1/5/20, print attached).
    eml = (FIXTURES_DIR / "email" / "rfq-sample.eml").read_bytes()
    ingest = post_mailgun_webhook(
        app_client,
        eml,
        recipient="golden-thread-close@rfq.tolera.eu",
        sender="einkauf@kunde-beispiel.de",
        signing_key=THREAD_SIGNING_KEY,
    )
    assert ingest.status_code == 200, ingest.text
    quote_id = ingest.json()["quote_id"]
    assert quote_id is not None

    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        # Lens prefilled the Bulk Create dialog from the email body…
        prefill = app_client.get(f"/api/quotes/{quote_id}/bulk-create").json()
        assert prefill["status"] == "completed"
        assert prefill["found_in"] == "original-rfq.eml"
        [row] = prefill["rows"]
        assert row["quantities"] == [1, 5, 20]
        assert row["matched_filenames"] == ["cube-20mm-print.pdf"]

        # …and only the explicit Accept creates the line item (AI-Governor).
        accepted: dict[str, Any] = app_client.post(
            f"/api/quotes/{quote_id}/bulk-create",
            json={"rows": [{"part_number": row["part_number"], "quantities": row["quantities"]}]},
        ).json()
        item = accepted["items"][0]
        assert [b["quantity"] for b in item["quantities"]] == [1, 5, 20]
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

        # M4.1 — the thread's dims become REAL: the STEP body is uploaded and
        # promoted to PRIMARY (the print arrived first via intake, so the swap
        # is the trigger), interrogation runs, and the part's geometry now
        # comes from GeometryService.analyze(), not hand-entered dims. The
        # material set above (1.4301 @ 7.90 g/cm3) resolves weight.
        part_id = item["part_id"]
        step = (FIXTURES_DIR / "cad" / "cube-20mm.step").read_bytes()
        with eager_celery():
            up = app_client.post(
                f"/api/parts/{part_id}/files",
                files=[("files", ("cube-20mm.step", step, "application/step"))],
            )
            assert up.status_code == 201, up.text
            [step_file] = [f for f in up.json() if f["filename"] == "cube-20mm.step"]
            promoted = app_client.post(f"/api/parts/{part_id}/files/{step_file['id']}/primary")
            assert promoted.status_code == 200, promoted.text
        interrogation = app_client.get(f"/api/parts/{part_id}/interrogation").json()
        assert interrogation["status"] == "succeeded"
        geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
        # Geometry asserts use the Part-2 relative tolerance (0.1%), never
        # exact float equality — kernel/platform rounding is not a failure.
        assert (geom["size_x"], geom["size_y"], geom["size_z"]) == pytest.approx(
            (20.0, 20.0, 20.0), rel=1e-3
        )
        assert geom["volume"] == pytest.approx(8000.0, rel=1e-3)
        assert geom["area"] == pytest.approx(2400.0, rel=1e-3)
        # 8000 mm3 / 1000 x 7.90 g/cm3
        assert geom["weight"] == pytest.approx(63.2, rel=1e-3)

        # pricing: the seeded Zuschlagskalkulation chain prices the thread —
        # the SAME figures as before interrogation (the geometry→Kalk contract
        # held; the thread only got more real).
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
