"""M3.2 — Found-in-Files actions: click-to-fill + corrections (training labels).

Deterministic tests gate this PR (build-plan M3.2 test plan): the click-to-fill
test (suggestion → explicit accept → part field set) and the correction-
persistence tests asserting the ``{predicted, corrected}`` row + per-tenant
scope. The model is never involved — findings are planted directly (the
``Seeder.sql`` escape hatch exists for exactly this).

Invariants under test (CLAUDE.md §5 + block acceptance criteria):
* a part field is written ONLY by the explicit accept call — never by
  extraction, never by listing;
* ``mark_inaccurate`` / ``replace`` / add-missing each persist one
  ``extraction_correction`` row with the source region, org-scoped;
* corrections survive the deletion of their finding (training data outlives
  the suggestion row);
* cross-org access 404s (RLS + org-scoped lookups).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole

from .conftest import Seeder, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _create_part(client: TestClient) -> str:
    created = client.post("/api/parts")
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _upload_pdf(client: TestClient, part_id: str) -> str:
    # Findings are planted directly; the file just anchors them, so a tiny
    # valid-enough PDF body is fine (never parsed by these tests).
    resp = client.post(
        f"/api/parts/{part_id}/files",
        files=[("files", ("print.pdf", b"%PDF-1.4 test", "application/pdf"))],
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()[0]["id"])


def _plant_finding(
    seeder: Seeder,
    org_id: uuid.UUID,
    file_id: str,
    *,
    category: str = "quote_setup",
    type_: str = "part_number",
    value: str | None = "PP-1212-006",
    raw_text: str | None = None,
    normalized_value: str | None = None,
    units: str | None = None,
    page: int | None = 1,
    bbox: dict[str, Any] | None = None,
    confidence: float = 0.93,
    status: str = "suggested",
) -> str:
    finding_id = uuid.uuid4()
    seeder.sql(
        """
        INSERT INTO extraction_finding
            (id, org_id, source_file_id, page, category, type, raw_text, value,
             normalized_value, units, bbox, confidence, status)
        VALUES
            (:id, :org_id, :file_id, :page, :category, :type, :raw_text, :value,
             :normalized_value, :units, CAST(:bbox AS jsonb), :confidence, :status)
        """,
        {
            "id": finding_id,
            "org_id": org_id,
            "file_id": uuid.UUID(file_id),
            "page": page,
            "category": category,
            "type": type_,
            "raw_text": raw_text,
            "value": value,
            "normalized_value": normalized_value,
            "units": units,
            "bbox": json.dumps(bbox) if bbox is not None else None,
            "confidence": confidence,
            "status": status,
        },
    )
    return str(finding_id)


def _setup(
    app_client: TestClient, seeder: Seeder, slug: str = "lens-m32"
) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    org, admin = _org_with_admin(seeder, slug)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        file_id = _upload_pdf(app_client, part_id)
    return org, admin, part_id, file_id


BBOX = {"x": 10.0, "y": 20.0, "width": 80.0, "height": 12.0}


# --------------------------------------------------------------------------- #
# Click-to-fill: suggestion → explicit accept → part field set
# --------------------------------------------------------------------------- #
class TestAcceptClickToFill:
    def test_accept_part_number_fills_part_field(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-accept-num")
        finding_id = _plant_finding(seeder, org, file_id, bbox=BBOX)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            # The suggestion alone never touches the part (AI-Governor).
            before = app_client.get(f"/api/parts/{part_id}")
            assert before.json()["part_number"] is None

            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["finding"]["status"] == "accepted"
            assert body["applied_field"] == "part_number"

            after = app_client.get(f"/api/parts/{part_id}")
            assert after.json()["part_number"] == "PP-1212-006"

    def test_accept_revision_and_description(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-accept-rev")
        rev = _plant_finding(seeder, org, file_id, type_="revision", value="A")
        desc = _plant_finding(seeder, org, file_id, type_="description", value="BRKT")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            for finding_id in (rev, desc):
                resp = app_client.post(
                    f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
                )
                assert resp.status_code == 200, resp.text
            part = app_client.get(f"/api/parts/{part_id}").json()
            assert part["revision"] == "A"
            assert part["description"] == "BRKT"

    def test_accept_dimension_fills_geometry_axis_with_units(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """A dimension finding in inches lands metric in the geometry override
        (stored value is ALWAYS mm — parts.py DimInput contract)."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-accept-dim")
        finding_id = _plant_finding(
            seeder,
            org,
            file_id,
            category="dimensions",
            type_="length",
            value="3.500",
            normalized_value="3.500",
            units="in",
        )
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept",
                json={"apply_to": "size_x"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["applied_field"] == "size_x"
            geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
            assert geom["size_x"] == pytest.approx(88.9)  # 3.5 in → mm
            assert geom["overrides"]["size_x"]["unit"] == "in"

    def test_accept_dimension_without_axis_is_422(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-dim-noaxis")
        finding_id = _plant_finding(
            seeder, org, file_id, category="dimensions", type_="length", value="12", units="mm"
        )
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
            )
            assert resp.status_code == 422
            assert resp.json()["code"] == "apply_target_required"

    def test_accept_mismatched_apply_target_is_422(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """A part_number finding cannot be applied to a geometry axis."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-mismatch")
        finding_id = _plant_finding(seeder, org, file_id)  # part_number
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept",
                json={"apply_to": "size_x"},
            )
            assert resp.status_code == 422
            assert resp.json()["code"] == "apply_mismatch"

    def test_accept_angle_to_axis_is_422(self, app_client: TestClient, seeder: Seeder) -> None:
        """An angle is not a length — 90° must never land as 90 mm."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-angle")
        finding_id = _plant_finding(
            seeder, org, file_id, category="dimensions", type_="angle", value="90", units="deg"
        )
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept",
                json={"apply_to": "size_x"},
            )
            assert resp.status_code == 422
            assert resp.json()["code"] == "apply_mismatch"
            # A bare accept of an angle is a plain acknowledge, no axis demanded.
            plain = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
            )
            assert plain.status_code == 200, plain.text
            assert plain.json()["applied_field"] is None

    def test_replace_then_accept_applies_corrected_value(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """The corrected value must not dead-end: an edited finding still fills."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-edit-apply")
        finding_id = _plant_finding(
            seeder, org, file_id, category="dimensions", type_="length", value="3.500", units="mm"
        )
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            base = f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}"
            assert app_client.post(f"{base}/replace", json={"value": "35"}).status_code == 200
            resp = app_client.post(f"{base}/accept", json={"apply_to": "size_z"})
            assert resp.status_code == 200, resp.text
            assert resp.json()["finding"]["status"] == "edited"  # stays human-edited
            geom = app_client.get(f"/api/parts/{part_id}/geometry").json()
            assert geom["size_z"] == pytest.approx(35.0)

    def test_accept_non_fill_finding_just_accepts(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """A control frame has no fill target — accept records the decision only."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-accept-cf")
        finding_id = _plant_finding(
            seeder, org, file_id, category="features", type_="control_frame", value="0.001"
        )
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["applied_field"] is None
            assert resp.json()["finding"]["status"] == "accepted"

    def test_reaccept_is_idempotent(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-reaccept")
        finding_id = _plant_finding(seeder, org, file_id)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            url = f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
            assert app_client.post(url).status_code == 200
            resp = app_client.post(url)
            assert resp.status_code == 200
            assert resp.json()["finding"]["status"] == "accepted"

    def test_accept_rejected_finding_is_409(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-acc-rej")
        finding_id = _plant_finding(seeder, org, file_id, status="rejected")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
            )
            assert resp.status_code == 409
            assert resp.json()["code"] == "invalid_status"


# --------------------------------------------------------------------------- #
# Corrections: mark_inaccurate / replace / add-missing → training label rows
# --------------------------------------------------------------------------- #
class TestCorrections:
    def _corrections(self, client: TestClient, part_id: str, file_id: str) -> list[dict[str, Any]]:
        resp = client.get(f"/api/parts/{part_id}/files/{file_id}/corrections")
        assert resp.status_code == 200, resp.text
        return list(resp.json())

    def test_mark_inaccurate_rejects_and_persists_label(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-reject")
        finding_id = _plant_finding(seeder, org, file_id, bbox=BBOX, raw_text="PP-1212-006")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/reject"
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["finding"]["status"] == "rejected"

            rows = self._corrections(app_client, part_id, file_id)
            assert len(rows) == 1
            row = rows[0]
            assert row["correction_type"] == "mark_inaccurate"
            assert row["finding_id"] == finding_id
            # False-positive label: the prediction snapshot, no corrected value.
            assert row["predicted"]["value"] == "PP-1212-006"
            assert row["predicted"]["type"] == "part_number"
            assert row["corrected"] is None
            # Source region rides along for retraining/QA (spec #wingman §3).
            assert row["page"] == 1
            assert row["bbox"] == BBOX

    def test_reject_is_idempotent_no_duplicate_label(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-reject-idem")
        finding_id = _plant_finding(seeder, org, file_id)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            url = f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/reject"
            assert app_client.post(url).status_code == 200
            assert app_client.post(url).status_code == 200
            assert len(self._corrections(app_client, part_id, file_id)) == 1

    def test_replace_edits_finding_and_persists_pair(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-replace")
        finding_id = _plant_finding(seeder, org, file_id, value="PP-1212-OO6", bbox=BBOX)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/replace",
                json={"value": "PP-1212-006"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["finding"]["status"] == "edited"
            assert body["finding"]["value"] == "PP-1212-006"

            rows = self._corrections(app_client, part_id, file_id)
            assert len(rows) == 1
            assert rows[0]["correction_type"] == "replace"
            assert rows[0]["predicted"]["value"] == "PP-1212-OO6"
            assert rows[0]["corrected"]["value"] == "PP-1212-006"

    def test_replace_rejected_finding_is_409(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-repl-rej")
        finding_id = _plant_finding(seeder, org, file_id, status="rejected")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/replace",
                json={"value": "X"},
            )
            assert resp.status_code == 409

    def test_add_missing_creates_accepted_finding_and_label(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """False-negative label: the user types a callout Lens missed."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-addmiss")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings",
                json={
                    "category": "requirements",
                    "type": "process_keywords",
                    "value": "passivieren",
                    "raw_text": "NACH ASTM A967 PASSIVIEREN",
                    "page": 2,
                    "bbox": BBOX,
                },
            )
            assert resp.status_code == 201, resp.text
            created = resp.json()
            # Human ground truth: born accepted at full confidence, so a Lens
            # re-run (replace-suggested) can never wipe it (M3.1 contract).
            assert created["status"] == "accepted"
            assert created["confidence"] == pytest.approx(1.0)

            findings = app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings").json()
            assert any(f["id"] == created["id"] for f in findings)

            rows = self._corrections(app_client, part_id, file_id)
            assert len(rows) == 1
            assert rows[0]["correction_type"] == "add_missing"
            assert rows[0]["predicted"] is None
            assert rows[0]["corrected"]["value"] == "passivieren"
            assert rows[0]["page"] == 2
            assert rows[0]["bbox"] == BBOX

    def test_add_missing_rejects_unknown_category(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-addmiss-bad")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings",
                json={"category": "nonsense", "type": "x", "value": "y"},
            )
            assert resp.status_code == 422

    def test_correction_survives_finding_deletion(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """The training label outlives its finding row (finding_id → NULL,
        predicted snapshot intact) — a Lens re-run or cleanup must not eat
        the eval set (sub-spec §7)."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-survive")
        finding_id = _plant_finding(seeder, org, file_id, value="WRONG")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            app_client.post(f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/reject")
        seeder.sql("DELETE FROM extraction_finding WHERE id = :id", {"id": uuid.UUID(finding_id)})
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            rows = self._corrections(app_client, part_id, file_id)
            assert len(rows) == 1
            assert rows[0]["finding_id"] is None
            assert rows[0]["predicted"]["value"] == "WRONG"


# --------------------------------------------------------------------------- #
# Tenancy: per-tenant scope, cross-org 404 (block AC)
# --------------------------------------------------------------------------- #
class TestTenancy:
    def test_cross_org_finding_action_404(self, app_client: TestClient, seeder: Seeder) -> None:
        org_a, _admin_a, part_id, file_id = _setup(app_client, seeder, "m32-org-a")
        finding_id = _plant_finding(seeder, org_a, file_id)
        org_b, admin_b = _org_with_admin(seeder, "m32-org-b")
        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            for action in ("accept", "reject"):
                resp = app_client.post(
                    f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/{action}"
                )
                assert resp.status_code == 404, action
            assert (
                app_client.get(f"/api/parts/{part_id}/files/{file_id}/corrections").status_code
                == 404
            )

    def test_corrections_are_org_scoped(self, app_client: TestClient, seeder: Seeder) -> None:
        """Two orgs correct findings; each sees only its own labels (per-tenant
        storage — DECISIONS.md correction-storage scope)."""
        org_a, admin_a, part_a, file_a = _setup(app_client, seeder, "m32-scope-a")
        org_b, admin_b, part_b, file_b = _setup(app_client, seeder, "m32-scope-b")
        fa = _plant_finding(seeder, org_a, file_a, value="A-VALUE")
        fb = _plant_finding(seeder, org_b, file_b, value="B-VALUE")
        with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
            app_client.post(f"/api/parts/{part_a}/files/{file_a}/findings/{fa}/reject")
        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            app_client.post(f"/api/parts/{part_b}/files/{file_b}/findings/{fb}/reject")
            rows = app_client.get(f"/api/parts/{part_b}/files/{file_b}/corrections").json()
            assert len(rows) == 1
            assert rows[0]["predicted"]["value"] == "B-VALUE"

    def test_finding_of_other_file_404(self, app_client: TestClient, seeder: Seeder) -> None:
        """A finding id must belong to the addressed file — no drive-by accepts."""
        org, admin, part_id, file_id = _setup(app_client, seeder, "m32-otherfile")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            other_file = _upload_pdf(app_client, part_id)
        finding_id = _plant_finding(seeder, org, other_file)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                f"/api/parts/{part_id}/files/{file_id}/findings/{finding_id}/accept"
            )
            assert resp.status_code == 404
