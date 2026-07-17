"""M4.9 — BOM Builder: split PDF → detect → extract → child BOMs → publish.

The M4 exit criterion (build-plan M4.9): a fixture assembly PDF → a published
multi-level BOM. These tests drive the whole staging flow against a seeded
Demo-D-style package — the root ``bom_tables`` finding, split pages with
title-block part numbers, a child-BOM finding on a subassembly page — and
assert the published ``node`` tree against the golden file
``fixtures/golden/demo_d_assembly.bom.json`` (levels, qtys, types, flat qty).

Invariants under test (CLAUDE.md §5 + block acceptance criteria):
* the builder is a **staging area** — GET/PUT/check never mutate the tree;
  only CHECK AND PUBLISH commits, in one transaction, and deletes the draft;
* Lens output stays suggestion-only: extraction seeds the *initial* doc the
  client edits, child-BOM rows enter the draft only via the client's explicit
  accept — nothing here feeds Kalk;
* rows with the same part#+rev link as ONE part (unique-parts counter,
  repeated parts quoted once — KB ``The-BOM-Builder`` §Multiple instances);
* flat qty is DERIVED (qty multiplied down the tree), never stored;
* cross-org access 404s (RLS + org-scoped lookups).

The model is never involved — findings are planted directly (the
``Seeder.sql`` escape hatch, the M3.2 precedent).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole, QuoteStatus

from .conftest import Seeder, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "golden"


# --------------------------------------------------------------------------- #
# Scenario builders
# --------------------------------------------------------------------------- #
def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _plant_finding(
    seeder: Seeder,
    org_id: uuid.UUID,
    file_id: str,
    *,
    type_: str,
    value: str | None,
    page: int | None = 1,
    status: str = "suggested",
) -> str:
    finding_id = uuid.uuid4()
    seeder.sql(
        """
        INSERT INTO extraction_finding
            (id, org_id, source_file_id, page, category, type, value, confidence, status)
        VALUES
            (:id, :org, :file, :page, 'quote_setup', :type, :value, 0.92, :status)
        """,
        {
            "id": finding_id,
            "org": org_id,
            "file": file_id,
            "page": page,
            "type": type_,
            "value": value,
            "status": status,
        },
    )
    return str(finding_id)


def _set_extracted_pn(seeder: Seeder, file_id: str, part_number: str) -> None:
    seeder.sql(
        "UPDATE part_file SET part_number_extracted = :pn WHERE id = :id",
        {"pn": part_number, "id": file_id},
    )


def _upload_pdf(client: TestClient, part_id: str, filename: str) -> str:
    resp = client.post(
        f"/api/parts/{part_id}/files",
        files=[("files", (filename, b"%PDF-1.4 test", "application/pdf"))],
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()[0]["id"])


ROOT_BOM_VALUE = json.dumps(
    {
        "root_part_number": "002-00001",
        "rows": [
            {
                "item_no": "1",
                "part_number": "002-00008-000",
                "revision": "000",
                "qty": 1,
                "description": "Frame weldment",
                "type_hint": "manufactured",
            },
            {
                "item_no": "2",
                "part_number": "002-00025-000",
                "revision": "000",
                "qty": 2,
                "description": "Side panel",
                "type_hint": "manufactured",
            },
            {
                "item_no": "3",
                "part_number": "002-00006-000",
                "revision": None,
                "qty": 16,
                "description": "Hex nut M6",
                "type_hint": "purchased",
            },
            {
                "item_no": "4",
                "part_number": "002-00014-000",
                "revision": None,
                "qty": 12,
                "description": "Washer M6",
                "type_hint": "purchased",
            },
        ],
    }
)

CHILD_BOM_VALUE = json.dumps(
    {
        "root_part_number": "002-00008-000",
        "rows": [
            {
                "item_no": "1",
                "part_number": "002-00009-000",
                "revision": "000",
                "qty": 2,
                "description": "Corner bracket",
                "type_hint": "manufactured",
            },
            {
                "item_no": "2",
                "part_number": "002-00006-000",
                "revision": None,
                "qty": 14,
                "description": "Hex nut M6",
                "type_hint": "purchased",
            },
        ],
    }
)


class Scenario:
    """A quote line item with the Demo-D-style package planted on its root part."""

    def __init__(self, client: TestClient, seeder: Seeder, org: uuid.UUID) -> None:
        quote = client.post("/api/quotes", json={})
        assert quote.status_code == 201, quote.text
        self.quote_id = str(quote.json()["id"])
        item = client.post(f"/api/quotes/{self.quote_id}/items").json()["items"][0]
        self.item_id = str(item["id"])
        self.root_component_id = str(item["root_component_id"])
        self.root_part_id = str(item["part_id"])
        # The assembly package: root drawing + split pages (M2.5 output shape).
        self.root_file_id = _upload_pdf(client, self.root_part_id, "002-00001 Assembly.pdf")
        seeder.sql(
            "UPDATE part_file SET role = 'primary' WHERE id = :id", {"id": self.root_file_id}
        )
        self.page_files: dict[str, str] = {}
        for pn in ("002-00008-000", "002-00025-000", "002-00009-000"):
            fid = _upload_pdf(client, self.root_part_id, f"{pn} drawing.pdf")
            _set_extracted_pn(seeder, fid, pn)
            self.page_files[pn] = fid
        # Lens findings: root BOM table (page 1) + a child BOM on the sub's page.
        self.root_finding_id = _plant_finding(
            seeder, org, self.root_file_id, type_="bom_tables", value=ROOT_BOM_VALUE
        )
        self.child_finding_id = _plant_finding(
            seeder,
            org,
            self.page_files["002-00008-000"],
            type_="bom_tables",
            value=CHILD_BOM_VALUE,
        )


def _row(
    part_number: str | None,
    *,
    row_type: str = "manufactured",
    qty: int = 1,
    revision: str | None = None,
    description: str | None = None,
    primary_file_id: str | None = None,
    children: list[dict[str, Any]] | None = None,
    row_id: str | None = None,
) -> dict[str, Any]:
    return {
        "row_id": row_id or f"r-{uuid.uuid4().hex[:8]}",
        "row_type": row_type,
        "part_number": part_number,
        "revision": revision,
        "description": description,
        "qty": qty,
        "primary_file_id": primary_file_id,
        "supporting_file_ids": [],
        "children": children or [],
    }


def _doc(root_children: list[dict[str, Any]], *, root_pn: str = "002-00001") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "root": _row(
            root_pn,
            row_type="assembly_root",
            qty=1,
            revision="000",
            children=root_children,
            row_id="r-root",
        ),
    }


def _full_doc(sc: Scenario) -> dict[str, Any]:
    """The Demo-D flow's end state: root BOM + accepted child BOM + matched files."""
    sub = _row(
        "002-00008-000",
        row_type="subassembly",
        revision="000",
        description="Frame weldment",
        primary_file_id=sc.page_files["002-00008-000"],
        children=[
            _row(
                "002-00009-000",
                revision="000",
                qty=2,
                description="Corner bracket",
                primary_file_id=sc.page_files["002-00009-000"],
            ),
            _row("002-00006-000", row_type="purchased", qty=14, description="Hex nut M6"),
        ],
    )
    return _doc(
        [
            sub,
            _row(
                "002-00025-000",
                revision="000",
                qty=2,
                description="Side panel",
                primary_file_id=sc.page_files["002-00025-000"],
            ),
            _row("002-00006-000", row_type="purchased", qty=16, description="Hex nut M6"),
            _row("002-00014-000", row_type="purchased", qty=12, description="Washer M6"),
        ]
    )


def _tree_shape(node: dict[str, Any]) -> dict[str, Any]:
    """Project a published tree node onto the golden-file shape."""
    return {
        "part_number": node["part_number"],
        "revision": node["revision"],
        "row_type": node["row_type"],
        "qty": node["qty_relative_to_parent"],
        "flat_qty": node["flat_qty"],
        "children": [_tree_shape(child) for child in node["children"]],
    }


# --------------------------------------------------------------------------- #
# Builder state (GET) — extraction seeds the initial doc
# --------------------------------------------------------------------------- #
def test_builder_state_seeds_root_bom_from_finding(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-state-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        res = app_client.get(f"/api/quote-items/{sc.item_id}/bom-builder")
        assert res.status_code == 200, res.text
        state = res.json()

        assert state["draft"] is None
        assert state["suggestion"]["file_id"] == sc.root_file_id
        assert state["suggestion"]["page"] == 1
        root = state["initial"]["root"]
        assert root["row_type"] == "assembly_root"
        assert root["part_number"] == "002-00001"
        assert [r["part_number"] for r in root["children"]] == [
            "002-00008-000",
            "002-00025-000",
            "002-00006-000",
            "002-00014-000",
        ]
        assert [r["qty"] for r in root["children"]] == [1, 2, 16, 12]
        assert [r["row_type"] for r in root["children"]] == [
            "manufactured",
            "manufactured",
            "purchased",
            "purchased",
        ]
        # 1 root + 4 unique children
        assert state["unique_parts"] == 5
        assert state["cap"] == 1000

        # Quote-files pane data: split pages carry their title-block part number
        # (the Add-Files matching key) and the child-BOM flag for the sparkle.
        files = {f["id"]: f for f in state["quote_files"]}
        page = files[sc.page_files["002-00008-000"]]
        assert page["part_number_extracted"] == "002-00008-000"
        assert page["has_bom_table"] is True
        assert files[sc.page_files["002-00025-000"]]["has_bom_table"] is False

        # Child-BOM suggestions ride per-file findings (explicit accept happens
        # client-side; the rows are parsed server-side once).
        child = next(
            s for s in state["child_suggestions"] if s["file_id"] == sc.page_files["002-00008-000"]
        )
        assert child["finding_id"] == sc.child_finding_id
        assert [r["part_number"] for r in child["rows"]] == ["002-00009-000", "002-00006-000"]


def test_builder_state_without_finding_is_bare_root(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-bare-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        quote_id = str(app_client.post("/api/quotes", json={}).json()["id"])
        item = app_client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
        res = app_client.get(f"/api/quote-items/{item['id']}/bom-builder")
        assert res.status_code == 200, res.text
        state = res.json()
        assert state["suggestion"] is None
        assert state["initial"]["root"]["children"] == []
        assert state["unique_parts"] == 1


# --------------------------------------------------------------------------- #
# Draft autosave / discard — staging only, never the tree
# --------------------------------------------------------------------------- #
def test_draft_autosave_roundtrip_and_discard(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-draft-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        doc = _doc([_row("002-00025-000", qty=2)])
        saved = app_client.put(
            f"/api/quote-items/{sc.item_id}/bom-builder/draft", json={"payload": doc}
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["unique_parts"] == 2
        first_updated = saved.json()["updated_at"]

        # Autosave upserts the single row per quote item.
        doc["root"]["children"].append(_row("002-00014-000", row_type="purchased", qty=12))
        saved2 = app_client.put(
            f"/api/quote-items/{sc.item_id}/bom-builder/draft", json={"payload": doc}
        )
        assert saved2.status_code == 200
        assert saved2.json()["unique_parts"] == 3
        assert saved2.json()["updated_at"] >= first_updated

        state = app_client.get(f"/api/quote-items/{sc.item_id}/bom-builder").json()
        assert state["draft"] is not None
        assert len(state["draft"]["payload"]["root"]["children"]) == 2

        # Draft never touches the tree.
        tree = app_client.get(f"/api/parts/{sc.root_part_id}/bom").json()
        assert tree["children"] == []

        gone = app_client.delete(f"/api/quote-items/{sc.item_id}/bom-builder/draft")
        assert gone.status_code == 204
        state = app_client.get(f"/api/quote-items/{sc.item_id}/bom-builder").json()
        assert state["draft"] is None


def test_draft_rejects_malformed_payload(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-badpay-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        res = app_client.put(
            f"/api/quote-items/{sc.item_id}/bom-builder/draft",
            json={"payload": {"schema_version": 1, "root": {"bogus": True}}},
        )
        assert res.status_code == 422


# --------------------------------------------------------------------------- #
# CHECK BOM — validates, flags, never commits
# --------------------------------------------------------------------------- #
def test_check_bom_flags_without_commit(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-check-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        incomplete = _row(None, description="mystery row")  # no part# AND no file
        dup_a = _row("002-00025-000", qty=1)
        dup_b = _row("002-00025-000", qty=2)  # same part twice at one level
        no_file = _row("002-00031-000", qty=4)  # manufactured, no primary file
        doc = _doc([incomplete, dup_a, dup_b, no_file])

        res = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/check", json={"payload": doc}
        )
        assert res.status_code == 200, res.text
        result = res.json()
        codes = {e["code"] for e in result["errors"]}
        assert "row_incomplete" in codes
        assert "duplicate_at_level" in codes
        notice_codes = {n["code"] for n in result["notices"]}
        assert "missing_primary_file" in notice_codes

        by_code = {e["code"]: e for e in result["errors"]}
        assert incomplete["row_id"] in by_code["row_incomplete"]["row_ids"]
        assert {dup_a["row_id"], dup_b["row_id"]} <= set(by_code["duplicate_at_level"]["row_ids"])

        # Validate-only: nothing committed.
        tree = app_client.get(f"/api/parts/{sc.root_part_id}/bom").json()
        assert tree["children"] == []


def test_check_bom_conflicting_linked_rows(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-conflict-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        # Same part#+rev, conflicting descriptions → cannot link as one part.
        sub = _row(
            "002-00008-000",
            row_type="subassembly",
            children=[
                _row("002-00006-000", row_type="purchased", qty=14, description="Hex nut M6"),
            ],
        )
        clash = _row("002-00006-000", row_type="purchased", qty=16, description="Wing nut M6")
        doc = _doc([sub, clash])
        result = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/check", json={"payload": doc}
        ).json()
        assert "part_conflict" in {e["code"] for e in result["errors"]}


def test_check_bom_purchased_with_children_is_error(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-pchild-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        bad = _row(
            "002-00006-000",
            row_type="purchased",
            children=[_row("002-00009-000")],
        )
        result = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/check", json={"payload": _doc([bad])}
        ).json()
        assert "purchased_with_children" in {e["code"] for e in result["errors"]}


def test_check_bom_capacity_cap(
    app_client: TestClient, seeder: Seeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, admin = _org_with_admin(seeder, f"bom-cap-{uuid.uuid4().hex[:6]}")
    import app.bom_builder as bb

    monkeypatch.setattr(bb, "UNIQUE_PARTS_CAP", 3)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        doc = _doc([_row(f"PN-{i:03d}") for i in range(4)])
        result = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/check", json={"payload": doc}
        ).json()
        assert "capacity_exceeded" in {e["code"] for e in result["errors"]}


def test_unique_counter_links_same_part_across_levels(
    app_client: TestClient, seeder: Seeder
) -> None:
    """KB FAQ: a part in two subassemblies counts once toward N/1000."""
    org, admin = _org_with_admin(seeder, f"bom-uniq-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        sub_a = _row(
            "SUB-A",
            row_type="subassembly",
            children=[
                _row("SHARED-01", row_type="purchased", qty=2),
            ],
        )
        sub_b = _row(
            "SUB-B",
            row_type="subassembly",
            children=[
                _row("SHARED-01", row_type="purchased", qty=3),
            ],
        )
        saved = app_client.put(
            f"/api/quote-items/{sc.item_id}/bom-builder/draft",
            json={"payload": _doc([sub_a, sub_b])},
        )
        # root + SUB-A + SUB-B + SHARED-01 (once)
        assert saved.json()["unique_parts"] == 4


# --------------------------------------------------------------------------- #
# CHECK AND PUBLISH — the golden tree
# --------------------------------------------------------------------------- #
def test_publish_writes_golden_tree(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-golden-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        doc = _full_doc(sc)
        res = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/publish", json={"payload": doc}
        )
        assert res.status_code == 200, res.text
        tree = res.json()["tree"]

        golden = json.loads((GOLDEN_PATH / "demo_d_assembly.bom.json").read_text())
        assert _tree_shape(tree) == golden

        # The repeated purchased part (002-00006-000) is ONE part with two nodes.
        def collect(node: dict[str, Any]) -> list[dict[str, Any]]:
            return [node] + [n for c in node["children"] for n in collect(c)]

        nodes = collect(tree)
        nut_nodes = [n for n in nodes if n["part_number"] == "002-00006-000"]
        assert len(nut_nodes) == 2
        assert len({n["part_id"] for n in nut_nodes}) == 1
        # flat qty derived: 16 at root + 14 x 1 in the sub = shares the part.
        assert {n["flat_qty"] for n in nut_nodes} == {16, 14}

        # Root part became an assembly; obtain methods mirror row types.
        root_part = app_client.get(f"/api/parts/{sc.root_part_id}").json()
        assert root_part["is_assembly"] is True
        assert root_part["part_number"] == "002-00001"

        # Matched files moved to their child parts as primaries.
        sub_node = next(n for n in nodes if n["part_number"] == "002-00008-000")
        sub_files = app_client.get(f"/api/parts/{sub_node['part_id']}/files").json()
        assert any(
            f["id"] == sc.page_files["002-00008-000"] and f["role"] == "primary" for f in sub_files
        )

        # Publishing consumed the draft (if any) and the DB tree matches.
        state = app_client.get(f"/api/quote-items/{sc.item_id}/bom-builder").json()
        assert state["draft"] is None
        db_tree = app_client.get(f"/api/parts/{sc.root_part_id}/bom").json()
        assert len(db_tree["children"]) == 4

        # Status endpoint now reports children (the persistent banner state).
        bom_status = app_client.get(f"/api/quote-items/{sc.item_id}/bom-status").json()
        assert bom_status["has_children"] is True
        assert bom_status["suggestion"]["file_id"] == sc.root_file_id


def test_publish_blocks_on_validation_errors(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-block-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        doc = _doc([_row(None, description="incomplete")])
        res = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/publish", json={"payload": doc}
        )
        assert res.status_code == 409
        assert res.json()["code"] == "bom_invalid"
        tree = app_client.get(f"/api/parts/{sc.root_part_id}/bom").json()
        assert tree["children"] == []


def test_publish_uses_stored_draft_when_no_payload(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-stored-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        app_client.put(
            f"/api/quote-items/{sc.item_id}/bom-builder/draft",
            json={"payload": _doc([_row("002-00025-000", qty=2)])},
        )
        res = app_client.post(f"/api/quote-items/{sc.item_id}/bom-builder/publish", json={})
        assert res.status_code == 200, res.text
        assert len(res.json()["tree"]["children"]) == 1


def test_publish_without_draft_or_payload_409s(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-nodraft-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        res = app_client.post(f"/api/quote-items/{sc.item_id}/bom-builder/publish", json={})
        assert res.status_code == 409
        assert res.json()["code"] == "no_draft"


def test_republish_reuses_parts_by_part_number(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-repub-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        first = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/publish",
            json={"payload": _full_doc(sc)},
        ).json()["tree"]

        def find(node: dict[str, Any], pn: str) -> dict[str, Any] | None:
            if node["part_number"] == pn:
                return node
            for child in node["children"]:
                hit = find(child, pn)
                if hit:
                    return hit
            return None

        panel_before = find(first, "002-00025-000")
        assert panel_before is not None

        # Re-edit: bump the panel qty, drop the washers.
        doc = _full_doc(sc)
        doc["root"]["children"][1]["qty"] = 3
        doc["root"]["children"] = [
            c for c in doc["root"]["children"] if c["part_number"] != "002-00014-000"
        ]
        second = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/publish", json={"payload": doc}
        )
        assert second.status_code == 200, second.text
        tree = second.json()["tree"]

        panel_after = find(tree, "002-00025-000")
        assert panel_after is not None
        assert panel_after["qty_relative_to_parent"] == 3
        # Same part#+rev → the SAME part row survives the republish.
        assert panel_after["part_id"] == panel_before["part_id"]
        assert find(tree, "002-00014-000") is None


def test_publish_locked_quote_409s(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-locked-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        seeder.sql(
            "UPDATE quote SET status = :st WHERE id = :id",
            {"st": QuoteStatus.sent.value, "id": sc.quote_id},
        )
        res = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/publish",
            json={"payload": _doc([_row("002-00025-000")])},
        )
        assert res.status_code == 409
        assert res.json()["code"] == "quote_locked"


def test_publish_rejects_file_outside_scope(app_client: TestClient, seeder: Seeder) -> None:
    """A draft may only assign files that live on this line item's tree."""
    org, admin = _org_with_admin(seeder, f"bom-fscope-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        foreign_part = str(app_client.post("/api/parts").json()["id"])
        foreign_file = _upload_pdf(app_client, foreign_part, "elsewhere.pdf")
        doc = _doc([_row("002-00025-000", primary_file_id=foreign_file)])
        res = app_client.post(
            f"/api/quote-items/{sc.item_id}/bom-builder/publish", json={"payload": doc}
        )
        assert res.status_code == 409
        assert res.json()["code"] == "bom_invalid"
        details = res.json()["details"]
        assert "file_not_in_scope" in {e["code"] for e in details["errors"]}


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #
def test_cross_org_access_404s(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, f"bom-tenant-a-{uuid.uuid4().hex[:6]}")
    org_b, admin_b = _org_with_admin(seeder, f"bom-tenant-b-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        sc = Scenario(app_client, seeder, org_a)
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        for method, url, body in (
            ("get", f"/api/quote-items/{sc.item_id}/bom-builder", None),
            ("get", f"/api/quote-items/{sc.item_id}/bom-status", None),
            ("put", f"/api/quote-items/{sc.item_id}/bom-builder/draft", {"payload": _doc([])}),
            ("post", f"/api/quote-items/{sc.item_id}/bom-builder/check", {"payload": _doc([])}),
            ("post", f"/api/quote-items/{sc.item_id}/bom-builder/publish", {}),
            ("delete", f"/api/quote-items/{sc.item_id}/bom-builder/draft", None),
        ):
            res = getattr(app_client, method)(url, **({"json": body} if body else {}))
            assert res.status_code == 404, f"{method} {url} → {res.status_code}"


# --------------------------------------------------------------------------- #
# The bom_tables value contract — tolerant parsing (no DB)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not json",
        "[1, 2]",
        '{"rows": "nope"}',
        '{"root_part_number": "X"}',  # no rows
        '{"rows": []}',  # empty table carries no suggestion
    ],
)
def test_parse_bom_table_value_tolerates_garbage(value: str | None) -> None:
    from app.bom_builder import parse_bom_table_value

    assert parse_bom_table_value(value) is None


def test_parse_bom_table_value_reads_contract() -> None:
    from app.bom_builder import parse_bom_table_value

    table = parse_bom_table_value(ROOT_BOM_VALUE)
    assert table is not None
    assert table.root_part_number == "002-00001"
    assert [r.qty for r in table.rows] == [1, 2, 16, 12]
    assert table.rows[2].type_hint == "purchased"
    # Unknown keys are ignored, defaults fill gaps (never an error).
    loose = parse_bom_table_value('{"rows": [{"part_number": "A", "extra": 1}]}')
    assert loose is not None
    assert loose.rows[0].qty == 1


# --------------------------------------------------------------------------- #
# bom-status — the line-item banner
# --------------------------------------------------------------------------- #
def test_bom_status_reports_suggestion_and_draft(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, f"bom-status-{uuid.uuid4().hex[:6]}")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        sc = Scenario(app_client, seeder, org)
        status0 = app_client.get(f"/api/quote-items/{sc.item_id}/bom-status").json()
        assert status0["suggestion"]["file_id"] == sc.root_file_id
        assert status0["suggestion"]["page"] == 1
        assert status0["has_children"] is False
        assert status0["has_draft"] is False

        app_client.put(
            f"/api/quote-items/{sc.item_id}/bom-builder/draft",
            json={"payload": _doc([_row("X-1")])},
        )
        status1 = app_client.get(f"/api/quote-items/{sc.item_id}/bom-status").json()
        assert status1["has_draft"] is True
