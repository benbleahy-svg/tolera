"""M2.12 — matching buckets + historical import (spec `#partlib`).

The "N Matching Parts" modal contract: four buckets computed now (Exact File /
File Name / Part Number / Historical), two stubbed ``pending_m4`` (Exact
Geometric / Similar Geometries — they need the M4 geometry signature/vector).
Selecting a match copies the historical router (operations incl. manual
overrides + Kalk variable overrides) onto the current component and reprices.
Everything is org-scoped: another org's identical file must never surface.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
STEP_BYTES = (FIXTURES / "cad" / "cube-20mm.step").read_bytes()
PLATE_BYTES = (FIXTURES / "cad" / "plate-hole-20x20x10-d8.step").read_bytes()

ADMIN = [MembershipRole.admin]

BUCKET_KEYS = [
    "exact_file",
    "exact_geometric",
    "file_name",
    "part_number",
    "similar_geometries",
    "historical",
]


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[Any, Any]:
    org = seeder.org(slug)
    user = seeder.user(f"{slug}-admin")
    seeder.membership(user, org, roles=ADMIN)
    return org, user


def _new_part(client: TestClient, **identity: Any) -> str:
    part_id: str = client.post("/api/parts").json()["id"]
    if identity:
        assert client.patch(f"/api/parts/{part_id}", json=identity).status_code == 200
    return part_id


def _upload(client: TestClient, part_id: str, name: str, body: bytes) -> str:
    ctype = "application/pdf" if name.lower().endswith(".pdf") else "application/step"
    resp = client.post(f"/api/parts/{part_id}/files", files=[("files", (name, body, ctype))])
    assert resp.status_code == 201, resp.text
    return str(resp.json()[0]["id"])


def _matches(client: TestClient, part_id: str) -> dict[str, Any]:
    resp = client.get(f"/api/parts/{part_id}/matches")
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _bucket(body: dict[str, Any], key: str) -> dict[str, Any]:
    [bucket] = [b for b in body["buckets"] if b["key"] == key]
    return dict(bucket)


def _quoted_item(client: TestClient, seeder: Seeder, org: Any, number: str) -> dict[str, Any]:
    """A quote with one line item → {quote_id, item, part_id, component_id}."""
    quote_id = seeder.quote(org, number)
    detail = client.post(f"/api/quotes/{quote_id}/items").json()
    item = detail["items"][-1]
    return {
        "quote_id": str(quote_id),
        "part_id": item["part_id"],
        "component_id": item["root_component_id"],
    }


class TestMatchBuckets:
    def test_bucket_catalogue_shape(self, app_client: TestClient, seeder: Seeder) -> None:
        """All six buckets ready-and-empty for a bare part (the geometry
        buckets went live with M4.11 — a part without a CAD primary has no
        geometry indexes by design, spec ``#partlib`` pipeline step 2)."""
        org, admin = _org_with_admin(seeder, "org-mb0")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = _new_part(app_client)
            body = _matches(app_client, part)
        assert [b["key"] for b in body["buckets"]] == BUCKET_KEYS
        for key in BUCKET_KEYS:
            bucket = _bucket(body, key)
            assert bucket["status"] == "ready"
            assert bucket["count"] == 0

    def test_exact_file_match_on_byte_identical_uploads(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-mb1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _new_part(app_client)
            _upload(app_client, subject, "Wuerfel-A.step", STEP_BYTES)
            twin = _new_part(app_client)
            _upload(app_client, twin, "Wuerfel-B.step", STEP_BYTES)  # same bytes
            other = _new_part(app_client)
            _upload(app_client, other, "Platte.step", PLATE_BYTES)  # different bytes
            body = _matches(app_client, subject)
        bucket = _bucket(body, "exact_file")
        assert bucket["count"] == 1
        assert [m["part_id"] for m in bucket["matches"]] == [twin]
        # The subject itself is never its own match.
        assert subject not in [m["part_id"] for m in bucket["matches"]]

    def test_file_name_match_on_normalized_stem(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-mb2")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _new_part(app_client)
            _upload(app_client, subject, "5-X-9.step", STEP_BYTES)
            same_name = _new_part(app_client)
            # Different bytes, same normalized stem (case/separator-insensitive).
            _upload(app_client, same_name, "5_x_9.STEP", PLATE_BYTES)
            body = _matches(app_client, subject)
        assert [m["part_id"] for m in _bucket(body, "file_name")["matches"]] == [same_name]

    def test_part_number_match_manual_and_extracted(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-mb3")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _new_part(app_client, part_number="4711-K")
            manual_twin = _new_part(app_client, part_number="4711-K")
            # This part's STEP carries PRODUCT('cube-20mm') → part_number_extracted;
            # a subject with manual part# "cube-20mm" must find it.
            extracted_twin = _new_part(app_client)
            _upload(app_client, extracted_twin, "irgendwas.step", STEP_BYTES)
            subject2 = _new_part(app_client, part_number="cube-20mm")

            body = _matches(app_client, subject)
            ids = [m["part_id"] for m in _bucket(body, "part_number")["matches"]]
            assert ids == [manual_twin]

            body2 = _matches(app_client, subject2)
            ids2 = [m["part_id"] for m in _bucket(body2, "part_number")["matches"]]
            assert extracted_twin in ids2

    def test_historical_bucket_lists_prior_quotes(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-mb4")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            hist = _quoted_item(app_client, seeder, org, "Q-2026-0100")
            assert (
                app_client.patch(
                    f"/api/parts/{hist['part_id']}", json={"part_number": "HALTER-4711"}
                ).status_code
                == 200
            )
            # Same part number, never quoted → part_number bucket only.
            unquoted = _new_part(app_client, part_number="HALTER-4711")
            subject = _new_part(app_client, part_number="halter-4711")  # case-insensitive
            body = _matches(app_client, subject)
        bucket = _bucket(body, "historical")
        assert [m["part_id"] for m in bucket["matches"]] == [hist["part_id"]]
        [card] = bucket["matches"]
        assert card["quote_count"] == 1
        assert card["quotes"][0]["number"] == "Q-2026-0100"
        assert card["quotes"][0]["component_id"] == hist["component_id"]
        # The never-quoted twin still shows under part_number.
        pn_ids = [m["part_id"] for m in _bucket(body, "part_number")["matches"]]
        assert set(pn_ids) == {hist["part_id"], unquoted}

    def test_archived_parts_still_match_deleted_parts_never(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-mb5")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _new_part(app_client, part_number="RM-1")
            archived = _new_part(app_client, part_number="RM-1")
            deleted = _new_part(app_client, part_number="RM-1")
            assert app_client.post(f"/api/parts/{archived}/archive").status_code == 200
            assert app_client.post(f"/api/parts/{deleted}/archive").status_code == 200
            assert app_client.delete(f"/api/parts/{deleted}").status_code == 204
            body = _matches(app_client, subject)
        bucket = _bucket(body, "part_number")
        cards = {m["part_id"]: m for m in bucket["matches"]}
        assert set(cards) == {archived}
        assert cards[archived]["archived"] is True

    def test_cross_org_isolation_no_foreign_matches(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org_a, admin_a = _org_with_admin(seeder, "org-mb6a")
        org_b, admin_b = _org_with_admin(seeder, "org-mb6b")
        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            foreign = _new_part(app_client, part_number="GEHEIM-1")
            _upload(app_client, foreign, "Wuerfel.step", STEP_BYTES)
        with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
            subject = _new_part(app_client, part_number="GEHEIM-1")
            _upload(app_client, subject, "Wuerfel.step", STEP_BYTES)
            body = _matches(app_client, subject)
        for key in ("exact_file", "file_name", "part_number", "historical"):
            assert _bucket(body, key)["count"] == 0, key

    def test_matches_404_for_unknown_or_deleted_part(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-mb7")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            assert app_client.get(f"/api/parts/{uuid.uuid4()}/matches").status_code == 404


class TestImportRouter:
    def _historical_with_router(
        self, client: TestClient, seeder: Seeder, org: Any
    ) -> dict[str, Any]:
        """A quoted component carrying two ops with manual + Kalk overrides."""
        hist = _quoted_item(client, seeder, org, "Q-2026-0200")
        cid = hist["component_id"]
        resp = client.post(
            f"/api/components/{cid}/operations",
            json={"name": "Saegen", "run_rate": "60", "calculation_mode": "labour_only"},
        )
        assert resp.status_code == 201, resp.text
        [op1] = [o for o in resp.json()["operations"] if o["name"] == "Saegen"]
        # A manual override (drawer PRIMARY: Override) — must survive the copy.
        assert (
            client.patch(
                f"/api/operations/{op1['id']}", json={"manual_setup_mins": "12.5"}
            ).status_code
            == 200
        )
        resp = client.post(
            f"/api/components/{cid}/operations",
            json={"name": "Fraesen", "run_rate": "90"},
        )
        assert resp.status_code == 201
        [op2] = [o for o in resp.json()["operations"] if o["name"] == "Fraesen"]
        assert (
            client.put(
                f"/api/operations/{op2['id']}/variables",
                json={"overrides": {"vorschub": 250}},
            ).status_code
            == 200
        )
        hist["op_ids"] = [op1["id"], op2["id"]]
        return hist

    def test_import_copies_router_with_manual_and_variable_overrides(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-imp1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            hist = self._historical_with_router(app_client, seeder, org)
            target = _quoted_item(app_client, seeder, org, "Q-2026-0201")
            # Pre-existing op on the target is REPLACED by the imported router.
            resp = app_client.post(
                f"/api/components/{target['component_id']}/operations",
                json={"name": "Alt-Op"},
            )
            assert resp.status_code == 201

            resp = app_client.post(
                f"/api/components/{target['component_id']}/import-router",
                json={"source_component_id": hist["component_id"]},
            )
            assert resp.status_code == 200, resp.text
            ops = resp.json()["operations"]

        assert [o["name"] for o in ops] == ["Saegen", "Fraesen"]
        by_name = {o["name"]: o for o in ops}
        # New rows on the target — not references to the source rows.
        assert not {o["id"] for o in ops} & set(hist["op_ids"])
        # Manual override survived: the COALESCE(manual, calc) "source: manual"
        # semantics — the UI highlights exactly these yellow.
        assert by_name["Saegen"]["manual_setup_mins"] == "12.50"
        assert by_name["Fraesen"]["variable_overrides"] == {"vorschub": 250}
        # Costing was recalculated for the target's own quantity breaks.
        assert all(len(o["cells"]) >= 1 for o in ops)

    def test_import_source_untouched(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-imp2")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            hist = self._historical_with_router(app_client, seeder, org)
            target = _quoted_item(app_client, seeder, org, "Q-2026-0202")
            assert (
                app_client.post(
                    f"/api/components/{target['component_id']}/import-router",
                    json={"source_component_id": hist["component_id"]},
                ).status_code
                == 200
            )
            source = app_client.get(f"/api/components/{hist['component_id']}/costing").json()
        assert [o["id"] for o in source["operations"]] == hist["op_ids"]

    def test_import_rejects_self_and_unknown_source(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-imp3")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            target = _quoted_item(app_client, seeder, org, "Q-2026-0203")
            cid = target["component_id"]
            assert (
                app_client.post(
                    f"/api/components/{cid}/import-router",
                    json={"source_component_id": cid},
                ).status_code
                == 422
            )
            assert (
                app_client.post(
                    f"/api/components/{cid}/import-router",
                    json={"source_component_id": str(uuid.uuid4())},
                ).status_code
                == 404
            )

    def test_import_cross_org_source_is_404(self, app_client: TestClient, seeder: Seeder) -> None:
        org_a, admin_a = _org_with_admin(seeder, "org-imp4a")
        org_b, admin_b = _org_with_admin(seeder, "org-imp4b")
        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            foreign = self._historical_with_router(app_client, seeder, org_b)
        with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
            target = _quoted_item(app_client, seeder, org_a, "Q-2026-0204")
            resp = app_client.post(
                f"/api/components/{target['component_id']}/import-router",
                json={"source_component_id": foreign["component_id"]},
            )
        assert resp.status_code == 404
