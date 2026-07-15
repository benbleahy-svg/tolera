"""M2.12 — Part Library page contract: tabs, search, cards, merge (spec `#partlib`).

The `/parts` listing gains ``tab`` (team | archived — deleted parts never
list), ``q`` (name/number/revision/filename + full-text over ``pdf_text`` —
the "string that exists only in a PDF title block" acceptance case) and card
fields (primary filename/type, latest quoted process). Merge Parts as
Supporting Files (KB `navigate-and-manage-the-part-library`): source parts'
files move to the chosen primary part as SUPPORTING; sources leave the
library; a source that has been quoted refuses the merge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import MembershipRole
from app.storage import MemoryStorage
from tests.conftest import Seeder, authed

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
STEP_BYTES = (FIXTURES / "cad" / "cube-20mm.step").read_bytes()
PDF_BYTES = (FIXTURES / "drawings" / "halter-4711-rev-b.pdf").read_bytes()

ADMIN = [MembershipRole.admin]


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


def _list_ids(client: TestClient, **params: Any) -> list[str]:
    resp = client.get("/api/parts", params=params)
    assert resp.status_code == 200, resp.text
    return [p["id"] for p in resp.json()]


class TestTabsAndCards:
    def test_team_tab_excludes_archived_archived_tab_only_archived(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-pl1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            active = _new_part(app_client)
            archived = _new_part(app_client)
            deleted = _new_part(app_client)
            for pid in (archived, deleted):
                assert app_client.post(f"/api/parts/{pid}/archive").status_code == 200
            assert app_client.delete(f"/api/parts/{deleted}").status_code == 204

            assert _list_ids(app_client) == [active]
            assert _list_ids(app_client, tab="team") == [active]
            assert _list_ids(app_client, tab="archived") == [archived]
            # A deleted part is gone from every tab, and its routes 404.
            assert app_client.get(f"/api/parts/{deleted}").status_code == 404

    def test_cards_carry_primary_file_and_process(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-pl2")
        seeder.catalog(org)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            quote_id = seeder.quote(org, "Q-2026-0300")
            detail = app_client.post(f"/api/quotes/{quote_id}/items").json()
            item = detail["items"][-1]
            _upload(app_client, item["part_id"], "Halter-4711.step", STEP_BYTES)
            processes = app_client.get("/api/processes").json()
            assert processes, "catalog seed provides processes"
            assert (
                app_client.patch(
                    f"/api/components/{item['root_component_id']}/process",
                    json={"process_id": processes[0]["id"], "keep_operations": True},
                ).status_code
                == 200
            )
            [card] = [p for p in app_client.get("/api/parts").json() if p["id"] == item["part_id"]]
        assert card["primary_filename"] == "Halter-4711.step"
        assert card["primary_file_type"] == "brep_cad"
        assert card["process"] == processes[0]["name"]

    def test_card_without_files_or_process_has_nulls(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-pl3")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = _new_part(app_client)
            [card] = [p for p in app_client.get("/api/parts").json() if p["id"] == part]
        assert card["primary_filename"] is None
        assert card["primary_file_type"] is None
        assert card["process"] is None


class TestPartLifecycle:
    def test_delete_requires_archived_first(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-lc1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = _new_part(app_client)
            resp = app_client.delete(f"/api/parts/{part}")
            assert resp.status_code == 409
            assert resp.json()["code"] == "not_archived"

    def test_restore_returns_part_to_team_tab(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-lc2")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = _new_part(app_client)
            assert app_client.post(f"/api/parts/{part}/archive").json()["archived"] is True
            restored = app_client.post(f"/api/parts/{part}/restore").json()
            assert restored["archived"] is False
            assert _list_ids(app_client, tab="team") == [part]
            assert _list_ids(app_client, tab="archived") == []

    def test_delete_purges_files_but_quote_costing_survives(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """The spec#partlib lifecycle claim: 'all dimensions and costing are
        preserved' — deleting a part purges its files (rows + blobs) while the
        quote keeps its router and prices ('File Deleted' placeholder UX)."""
        org, admin = _org_with_admin(seeder, "org-lc3")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            quote_id = seeder.quote(org, "Q-2026-0500")
            item = app_client.post(f"/api/quotes/{quote_id}/items").json()["items"][-1]
            part_id, component_id = item["part_id"], item["root_component_id"]
            _upload(app_client, part_id, "Halter.step", STEP_BYTES)
            resp = app_client.post(
                f"/api/components/{component_id}/operations",
                json={"name": "Saegen", "run_rate": "60"},
            )
            assert resp.status_code == 201

            storage = cast(MemoryStorage, cast(FastAPI, app_client.app).state.storage)
            keys_before = [k for k in storage._objects if part_id in k]
            assert keys_before, "the upload stored a blob"

            assert app_client.post(f"/api/parts/{part_id}/archive").status_code == 200
            assert app_client.delete(f"/api/parts/{part_id}").status_code == 204

            # Files gone — rows and blobs; the part's routes 404.
            assert app_client.get(f"/api/parts/{part_id}").status_code == 404
            assert all(part_id not in k for k in storage._objects)
            # The quote's costing is intact: router row still there.
            costing = app_client.get(f"/api/components/{component_id}/costing").json()
            assert [o["name"] for o in costing["operations"]] == ["Saegen"]


class TestLibrarySearch:
    def test_search_by_identity_fields(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-pl4")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            by_number = _new_part(app_client, part_number="HALTER-4711", revision="B")
            by_name = _new_part(app_client, name="Grundplatte gefräst")
            _noise = _new_part(app_client, part_number="DECKEL-0815")

            assert _list_ids(app_client, q="halter-47") == [by_number]
            assert _list_ids(app_client, q="grundplatte") == [by_name]
            assert _list_ids(app_client, q="4711") == [by_number]

    def test_search_by_filename(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-pl5")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = _new_part(app_client)
            _upload(app_client, part, "Offset-Connector.step", STEP_BYTES)
            _noise = _new_part(app_client)
            assert _list_ids(app_client, q="offset-connector") == [part]

    def test_search_finds_string_only_inside_pdf(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        """The M2 exit check: a title-block-only string finds the part."""
        org, admin = _org_with_admin(seeder, "org-pl6")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = _new_part(app_client)  # identity stays empty
            _upload(app_client, part, "zeichnung-0815.pdf", PDF_BYTES)
            _noise = _new_part(app_client, part_number="ANDERES-TEIL")
            # "X5CrNi18-10" exists ONLY inside the drawing's title block.
            assert _list_ids(app_client, q="X5CrNi18-10") == [part]
            # Werkstoffnummer with tsquery-hostile punctuation still matches.
            assert part in _list_ids(app_client, q="1.4301")

    def test_search_is_org_scoped(self, app_client: TestClient, seeder: Seeder) -> None:
        org_a, admin_a = _org_with_admin(seeder, "org-pl7a")
        org_b, admin_b = _org_with_admin(seeder, "org-pl7b")
        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            _new_part(app_client, part_number="GEHEIM-4711")
        with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
            assert _list_ids(app_client, q="GEHEIM") == []


class TestMergeParts:
    def test_merge_moves_files_as_supporting_and_removes_sources(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-pl8")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            # The KB example: 5-X-9.STEP and 5-X-9__B.pdf came in as two parts.
            model = _new_part(app_client)
            _upload(app_client, model, "5-X-9.step", STEP_BYTES)
            print_part = _new_part(app_client)
            pdf_file = _upload(app_client, print_part, "5-X-9__B.pdf", PDF_BYTES)

            resp = app_client.post(
                "/api/parts/merge",
                json={"part_ids": [model, print_part], "primary_part_id": model},
            )
            assert resp.status_code == 200, resp.text
            merged = resp.json()
            files = app_client.get(f"/api/parts/{model}/files").json()

            assert merged["id"] == model
            by_name = {f["filename"]: f for f in files}
            assert by_name["5-X-9.step"]["role"] == "primary"
            assert by_name["5-X-9__B.pdf"]["role"] == "supporting"
            assert by_name["5-X-9__B.pdf"]["id"] == pdf_file
            # The emptied source part is gone from the library.
            assert print_part not in _list_ids(app_client)
            assert print_part not in _list_ids(app_client, tab="archived")
            assert app_client.get(f"/api/parts/{print_part}").status_code == 404

    def test_merge_promotes_cad_primary_on_fileless_target(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-pl9")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            target = _new_part(app_client, name="Sammelteil")
            source = _new_part(app_client)
            _upload(app_client, source, "Wuerfel.step", STEP_BYTES)
            resp = app_client.post(
                "/api/parts/merge",
                json={"part_ids": [target, source], "primary_part_id": target},
            )
            assert resp.status_code == 200, resp.text
            files = app_client.get(f"/api/parts/{target}/files").json()
        [step] = files
        assert step["role"] == "primary"  # best moved file takes PRIMARY

    def test_merge_refuses_quoted_source(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-pl10")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            quote_id = seeder.quote(org, "Q-2026-0400")
            item = app_client.post(f"/api/quotes/{quote_id}/items").json()["items"][-1]
            target = _new_part(app_client)
            resp = app_client.post(
                "/api/parts/merge",
                json={"part_ids": [target, item["part_id"]], "primary_part_id": target},
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "part_in_use"

    def test_merge_validates_input(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-pl11")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            lone = _new_part(app_client)
            other = _new_part(app_client)
            # Primary must be among the merged parts.
            assert (
                app_client.post(
                    "/api/parts/merge",
                    json={"part_ids": [lone], "primary_part_id": other},
                ).status_code
                == 422
            )
            # Fewer than two parts is not a merge.
            assert (
                app_client.post(
                    "/api/parts/merge",
                    json={"part_ids": [lone], "primary_part_id": lone},
                ).status_code
                == 422
            )
