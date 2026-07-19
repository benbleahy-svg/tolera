"""Tests for M6.4 — Vendor RFQ batch-send (compose modal, ranking, blind multi-send,
per-vendor file scoping, Buy mode).

Layers, mirroring the M6.2/M6.3 vendor tests:

* **Pure ranking** — the documented vendor order (spec ``#vendor-rfq``: most-recent
  accepted → historical acceptance rate → process match → material match) and the
  ``New`` label for zero-history vendors, as a total order over plain dataclasses.
* **Pricing math (mandatory, CLAUDE.md §9)** — Buy mode disables internal costing and
  the vendor price becomes the cost; the outside-service ``manual``/``calc`` pair
  resolves ``COALESCE(manual, calc)`` and a reprice never clobbers the override.
* **API against real RLS Postgres** — capability filtering, N-isolated batches with
  per-vendor tokens and file allowlists, the awaiting chip, the soft warning, and the
  M6.3 seams (Active-RFQ count, RFQ History) this block was meant to fill.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient

from app.models import MembershipRole, OpCategory
from app.vendor_rfq_ranking import VendorSignals, rank_vendors
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_quote_item(client: TestClient, quantities: list[int] | None = None) -> dict[str, Any]:
    """A quote with one line item; returns ``{quote_id, item_id, component_id}``."""
    quote_id = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
    if quantities:
        res = client.put(
            f"/api/quotes/{quote_id}/items/{item['id']}/quantities",
            json={"quantities": quantities},
        )
        assert res.status_code == 200, res.text
    return {
        "quote_id": str(quote_id),
        "item_id": str(item["id"]),
        "component_id": str(item["root_component_id"]),
    }


def _add_manual_op(
    client: TestClient, component_id: str, name: str, cost: str, quantity: int = 1, **extra: Any
) -> str:
    created = client.post(
        f"/api/components/{component_id}/operations", json={"name": name, **extra}
    )
    assert created.status_code == 201, created.text
    op = next(o for o in created.json()["operations"] if o["name"] == name)
    res = client.patch(f"/api/operations/{op['id']}/cells/{quantity}", json={"manual_cost": cost})
    assert res.status_code == 200, res.text
    return str(op["id"])


def _costing_row(client: TestClient, component_id: str, quantity: int = 1) -> dict[str, Any]:
    res = client.get(f"/api/components/{component_id}/pricing")
    assert res.status_code == 200, res.text
    return cast(dict[str, Any], next(c for c in res.json()["costing"] if c["quantity"] == quantity))


def _create_vendor(client: TestClient, name: str, **capabilities: list[str]) -> str:
    res = client.post(
        "/api/vendors",
        json={
            "name": name,
            "capabilities": {
                "processes": capabilities.get("processes", []),
                "materials": capabilities.get("materials", []),
            },
            "primary_contact": {
                "name": f"{name} Vertrieb",
                "email": f"rfq@{name}.example".lower().replace(" ", ""),
            },
        },
    )
    assert res.status_code == 201, res.text
    return cast(str, res.json()["id"])


# --------------------------------------------------------------------------- #
# Pure ranking — spec #vendor-rfq "AI suggestions"
# --------------------------------------------------------------------------- #
def _signals(name: str, **kw: Any) -> VendorSignals:
    base: dict[str, Any] = {
        "vendor_id": uuid.uuid4(),
        "name": name,
        "last_accepted_at": None,
        "acceptance_rate": None,
        "process_match": False,
        "material_match": False,
    }
    base.update(kw)
    return VendorSignals(**base)


def test_rank_puts_most_recent_accepted_first() -> None:
    """Signal 1 outranks everything below it — even a perfect capability match."""
    older = _signals("Aelter", last_accepted_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _signals("Neuer", last_accepted_at=datetime(2026, 6, 1, tzinfo=UTC))
    perfect = _signals("Passend", process_match=True, material_match=True, acceptance_rate=1.0)

    assert [v.name for v in rank_vendors([perfect, older, newer])] == [
        "Neuer",
        "Aelter",
        "Passend",
    ]


def test_rank_falls_through_acceptance_then_process_then_material() -> None:
    """Signals 2→4, each only breaking a tie in the one above it."""
    ranked = rank_vendors(
        [
            _signals("NurMaterial", material_match=True),
            _signals("NurProzess", process_match=True),
            _signals("Quote50", acceptance_rate=0.5),
            _signals("Quote90", acceptance_rate=0.9),
            _signals("Nichts"),
        ]
    )
    assert [v.name for v in ranked] == [
        "Quote90",
        "Quote50",
        "NurProzess",
        "NurMaterial",
        "Nichts",
    ]


def test_rank_labels_zero_history_vendors_new_without_hiding_them() -> None:
    """Spec: "New vendors (zero history) shown with New label, not hidden"."""
    ranked = rank_vendors(
        [
            _signals("Neuling", process_match=True),
            _signals("Bekannt", acceptance_rate=0.2),
        ]
    )
    by_name = {v.name: v for v in ranked}
    assert by_name["Neuling"].is_new is True
    assert by_name["Bekannt"].is_new is False
    # ...and a *rate of zero* is history, not newness.
    assert rank_vendors([_signals("Abgelehnt", acceptance_rate=0.0)])[0].is_new is False


def test_rank_is_deterministic_for_identical_signals() -> None:
    """Two vendors with nothing to separate them tie-break by name, never by chance."""
    ranked = rank_vendors([_signals("Zeta"), _signals("Alpha")])
    assert [v.name for v in ranked] == ["Alpha", "Zeta"]


# --------------------------------------------------------------------------- #
# Buy mode + the outside-service calc-vs-override pair (money math)
# --------------------------------------------------------------------------- #
def test_outside_override_replaces_calc_without_destroying_it(
    app_client: TestClient, seeder: Seeder
) -> None:
    """``outside_cost = COALESCE(manual, calc)`` — CLAUDE.md §5 calc-vs-override."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        component = line["component_id"]
        _add_manual_op(app_client, component, "CNC Bearbeitung", "100.0000")
        _add_manual_op(app_client, component, "Eloxieren", "40.0000", is_outside_service=True)

        before = _costing_row(app_client, component)
        assert Decimal(before["outside"]) == Decimal("40.0000")
        assert Decimal(before["calc_outside"]) == Decimal("40.0000")
        assert before["manual_outside"] is None

        res = app_client.patch(
            f"/api/components/{component}/outside-cost/1",
            json={"manual_outside_cost": "55.0000"},
        )
        assert res.status_code == 200, res.text

        after = _costing_row(app_client, component)
        assert Decimal(after["outside"]) == Decimal("55.0000")  # override wins
        assert Decimal(after["calc_outside"]) == Decimal("40.0000")  # calc survives
        assert Decimal(after["total"]) == Decimal("155.0000")  # 100 inside + 55 outside


def test_outside_override_survives_a_reprice(app_client: TestClient, seeder: Seeder) -> None:
    """A recalculation must never destroy human input (CLAUDE.md §5)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        component = line["component_id"]
        _add_manual_op(app_client, component, "Eloxieren", "40.0000", is_outside_service=True)
        app_client.patch(
            f"/api/components/{component}/outside-cost/1",
            json={"manual_outside_cost": "55.0000"},
        )
        # Any edit triggers a reprice; add another op and re-read.
        _add_manual_op(app_client, component, "Entgraten", "10.0000")

        row = _costing_row(app_client, component)
        assert Decimal(row["outside"]) == Decimal("55.0000")
        assert Decimal(row["calc_outside"]) == Decimal("40.0000")


def test_outside_override_clears_back_to_calc(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_quote_item(app_client)["component_id"]
        _add_manual_op(app_client, component, "Eloxieren", "40.0000", is_outside_service=True)
        app_client.patch(
            f"/api/components/{component}/outside-cost/1",
            json={"manual_outside_cost": "55.0000"},
        )
        res = app_client.patch(
            f"/api/components/{component}/outside-cost/1", json={"manual_outside_cost": None}
        )
        assert res.status_code == 200, res.text
        assert Decimal(_costing_row(app_client, component)["outside"]) == Decimal("40.0000")


def test_buy_mode_disables_internal_costing_and_uses_the_vendor_price(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Spec ``#vendor-rfq``: Buy mode hides/disables internal costing; the vendor price
    becomes the cost. The pricing layer above it stays live."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        component = line["component_id"]
        _add_manual_op(
            app_client, component, "Rohmaterial", "30.0000", category=OpCategory.material.value
        )
        _add_manual_op(app_client, component, "CNC Bearbeitung", "100.0000")

        make = _costing_row(app_client, component)
        assert Decimal(make["total"]) == Decimal("130.0000")

        res = app_client.patch(
            f"/api/quote-items/{line['item_id']}/costing-mode", json={"costing_mode": "buy"}
        )
        assert res.status_code == 200, res.text
        assert res.json()["costing_mode"] == "buy"

        # No vendor price yet: internal costing is off, so the line is unpriced —
        # not silently 130 € of machine time the shop is no longer spending.
        buy = _costing_row(app_client, component)
        assert Decimal(buy["material"]) == Decimal("0.0000")
        assert Decimal(buy["inside"]) == Decimal("0.0000")
        assert Decimal(buy["total"]) == Decimal("0.0000")
        assert buy["buy_awaiting_vendor_price"] is True

        app_client.patch(
            f"/api/components/{component}/outside-cost/1",
            json={"manual_outside_cost": "210.0000"},
        )
        priced = _costing_row(app_client, component)
        assert Decimal(priced["outside"]) == Decimal("210.0000")
        assert Decimal(priced["total"]) == Decimal("210.0000")
        assert priced["buy_awaiting_vendor_price"] is False


def test_buy_mode_flips_back_to_make_and_restores_internal_costing(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Buy is a reversible view of the same router — flipping back must not have
    destroyed the operations (the estimator may lose the make/buy argument)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        component = line["component_id"]
        _add_manual_op(app_client, component, "CNC Bearbeitung", "100.0000")
        app_client.patch(
            f"/api/quote-items/{line['item_id']}/costing-mode", json={"costing_mode": "buy"}
        )
        app_client.patch(
            f"/api/quote-items/{line['item_id']}/costing-mode", json={"costing_mode": "make"}
        )
        assert Decimal(_costing_row(app_client, component)["total"]) == Decimal("100.0000")


# --------------------------------------------------------------------------- #
# Compose — capability filtering + pre-check
# --------------------------------------------------------------------------- #
def test_compose_offers_only_vendors_matching_the_lines_process_types(
    app_client: TestClient, seeder: Seeder
) -> None:
    """AC: "the vendor selector only offers vendors whose capabilities match the
    selected lines' process types"."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        _add_manual_op(
            app_client,
            line["component_id"],
            "Eloxieren",
            "40.0000",
            is_outside_service=True,
        )
        _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        _create_vendor(app_client, "Haerterei Sued", processes=["haerten"])

        res = app_client.get(
            "/api/vendor-rfqs/compose",
            params={"quote_id": line["quote_id"], "quote_item_ids": line["item_id"]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert [v["name"] for v in body["vendors"]] == ["Eloxal Nord"]
        assert body["required_processes"] == ["eloxieren"]

        # ...and the escape hatch still shows everyone, explicitly asked for.
        every = app_client.get(
            "/api/vendor-rfqs/compose",
            params={
                "quote_id": line["quote_id"],
                "quote_item_ids": line["item_id"],
                "include_all_vendors": True,
            },
        ).json()
        assert {v["name"] for v in every["vendors"]} == {"Eloxal Nord", "Haerterei Sued"}


def test_compose_pre_checks_ranked_vendors_and_labels_new_ones(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        _add_manual_op(
            app_client, line["component_id"], "Eloxieren", "40.0000", is_outside_service=True
        )
        _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])

        body = app_client.get(
            "/api/vendor-rfqs/compose",
            params={"quote_id": line["quote_id"], "quote_item_ids": line["item_id"]},
        ).json()
        vendor = body["vendors"][0]
        assert vendor["suggested"] is True
        assert vendor["is_new"] is True  # zero history
        assert vendor["contact_email"] == "rfq@eloxalnord.example"


def test_compose_excludes_inactive_and_archived_vendors(
    app_client: TestClient, seeder: Seeder
) -> None:
    """An *inactive* vendor is "deliberately excluded from RFQ suggestions" (M6.3)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        _add_manual_op(
            app_client, line["component_id"], "Eloxieren", "40.0000", is_outside_service=True
        )
        keep = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        dormant = _create_vendor(app_client, "Eloxal Ruhend", processes=["eloxieren"])
        archived = _create_vendor(app_client, "Eloxal Alt", processes=["eloxieren"])
        app_client.patch(f"/api/vendors/{dormant}", json={"status": "inactive"})
        app_client.post(f"/api/vendors/{archived}/archive")

        body = app_client.get(
            "/api/vendor-rfqs/compose",
            params={"quote_id": line["quote_id"], "quote_item_ids": line["item_id"]},
        ).json()
        assert [v["id"] for v in body["vendors"]] == [keep]


def test_compose_lists_the_lines_files_including_redacted_variants(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The per-vendor files toggle must be able to offer the M2.4 redacted copy."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        part_id = _part_of(app_client, line)
        original = seeder.part_file(org, part_id, "zeichnung.pdf")
        redacted = seeder.part_file(org, part_id, "zeichnung-redacted.pdf", is_redacted=True)

        body = app_client.get(
            "/api/vendor-rfqs/compose",
            params={"quote_id": line["quote_id"], "quote_item_ids": line["item_id"]},
        ).json()
        files = {f["id"]: f for f in body["lines"][0]["files"]}
        assert str(original) in files and str(redacted) in files
        assert files[str(redacted)]["is_redacted"] is True
        # Default selection prefers the redacted copy — never leak more than asked.
        assert body["lines"][0]["default_file_ids"] == [str(redacted)]


def _part_of(client: TestClient, line: dict[str, Any]) -> uuid.UUID:
    """The part behind a line item, read off the quote detail (no components GET)."""
    res = client.get(f"/api/quotes/{line['quote_id']}")
    assert res.status_code == 200, res.text
    item = next(i for i in res.json()["items"] if i["id"] == line["item_id"])
    return uuid.UUID(item["part_id"])


# --------------------------------------------------------------------------- #
# Blind multi-send
# --------------------------------------------------------------------------- #
def _stored_file(
    client: TestClient,
    seeder: Seeder,
    org: uuid.UUID,
    part_id: uuid.UUID,
    filename: str,
    *,
    is_redacted: bool = False,
) -> str:
    """A seeded ``part_file`` **with a blob behind it**, so an authorised download
    reaches the object store instead of 500-ing on a missing key."""
    file_id = seeder.part_file(org, part_id, filename, is_redacted=is_redacted)
    # `TestClient.app` is typed as the ASGI callable; the FastAPI instance behind it
    # is what carries `.state` (the in-memory storage backend the tests run on).
    storage = cast(Any, client.app).state.storage
    storage._objects[f"seed/{org}/{part_id}/{filename}"] = b"%PDF-1.7\n"
    return str(file_id)


def _send(
    client: TestClient, line: dict[str, Any], recipients: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    res = client.post(
        "/api/vendor-rfqs/batch",
        json={
            "quote_id": line["quote_id"],
            "quote_item_ids": [line["item_id"]],
            "need_by_date": str(date.today() + timedelta(days=7)),
            "message": "Bitte um Angebot.",
            "recipients": recipients,
            **extra,
        },
    )
    assert res.status_code == 201, res.text
    return cast(dict[str, Any], res.json())


def test_send_creates_one_isolated_batch_per_vendor(app_client: TestClient, seeder: Seeder) -> None:
    """AC: "sending N vendors creates N ``VendorRFQ``s with isolated tokens (no vendor
    sees another's recipient)"."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        _add_manual_op(
            app_client, line["component_id"], "Eloxieren", "40.0000", is_outside_service=True
        )
        a = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        b = _create_vendor(app_client, "Eloxal Sued", processes=["eloxieren"])

        body = _send(app_client, line, [{"vendor_id": a}, {"vendor_id": b}])
        assert len(body["rfqs"]) == 2
        assert len({r["number"] for r in body["rfqs"]}) == 2  # distinct per-org numbers
        assert all(r["status"] == "open" for r in body["rfqs"])

    # Each token sees exactly its own vendor — and never the other recipient.
    tokens = [r["portal_token"] for r in body["rfqs"]]
    assert len(set(tokens)) == 2
    seen = []
    for token in tokens:
        res = app_client.get(f"/api/public/vendor-rfq/{token}")
        assert res.status_code == 200, res.text
        payload = res.json()
        seen.append(payload["vendor"]["name"])
        assert "recipients" not in payload
        assert "Eloxal" in str(payload["vendor"]["name"])
    assert set(seen) == {"Eloxal Nord", "Eloxal Sued"}


def test_send_scopes_files_per_vendor(app_client: TestClient, seeder: Seeder) -> None:
    """AC: "per-vendor file toggle controls which files that vendor's token can fetch"."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        part_id = _part_of(app_client, line)
        original = _stored_file(app_client, seeder, org, part_id, "zeichnung.pdf")
        redacted = _stored_file(
            app_client, seeder, org, part_id, "zeichnung-redacted.pdf", is_redacted=True
        )
        _add_manual_op(
            app_client, line["component_id"], "Eloxieren", "40.0000", is_outside_service=True
        )
        trusted = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        arms_length = _create_vendor(app_client, "Eloxal Sued", processes=["eloxieren"])

        body = _send(
            app_client,
            line,
            [
                {"vendor_id": trusted, "part_file_ids": [original]},
                {"vendor_id": arms_length, "part_file_ids": [redacted]},
            ],
        )
    by_vendor = {r["vendor_name"]: r["portal_token"] for r in body["rfqs"]}

    trusted_token, redacted_token = by_vendor["Eloxal Nord"], by_vendor["Eloxal Sued"]

    def status(token: str, file_id: str) -> int:
        res = app_client.get(f"/api/public/vendor-rfq/{token}/files/{file_id}")
        return int(res.status_code)

    # The assertion is about *authorization*, not delivery: a seeded PartFile row has
    # no blob behind it, so an allowed fetch gets past the token gate and then fails
    # in storage. 401 vs not-401 is exactly the line this test defends.
    assert status(trusted_token, original) != 401
    assert status(redacted_token, redacted) != 401
    # The arms-length vendor is refused the un-redacted original by its *token*,
    # not by a UI that merely failed to offer it.
    assert status(redacted_token, original) == 401


def test_send_with_no_files_grants_no_downloads(app_client: TestClient, seeder: Seeder) -> None:
    """The allowlist fails closed (M6.2): an empty toggle is not "everything"."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        part_id = _part_of(app_client, line)
        original = str(seeder.part_file(org, part_id, "zeichnung.pdf"))
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        body = _send(app_client, line, [{"vendor_id": vendor, "part_file_ids": []}])

    token = body["rfqs"][0]["portal_token"]
    assert app_client.get(f"/api/public/vendor-rfq/{token}/files/{original}").status_code == 401


def test_send_records_buy_mode_lines(app_client: TestClient, seeder: Seeder) -> None:
    """Part-level (Buy) vs operation-level is recorded at send so M6.6 maps the
    response to the right cost (spec "Operation-level vs part-level distinction")."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        vendor = _create_vendor(app_client, "Dreherei Ost", processes=["drehen"])
        _send(app_client, line, [{"vendor_id": vendor}], costing_mode="buy")

        res = app_client.get(f"/api/quotes/{line['quote_id']}")
        item = next(i for i in res.json()["items"] if i["id"] == line["item_id"])
        assert item["costing_mode"] == "buy"


def test_send_with_buy_mode_reprices_the_line_immediately(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Flipping to Buy as part of the send must reprice then and there — otherwise the
    line persists as Buy while still carrying make-mode internal cost, and the total
    drops silently the next time something unrelated triggers a reprice."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        _add_manual_op(app_client, line["component_id"], "CNC Bearbeitung", "100.0000")
        vendor = _create_vendor(app_client, "Dreherei Ost", processes=["drehen"])
        _send(app_client, line, [{"vendor_id": vendor}], costing_mode="buy")

        row = _costing_row(app_client, line["component_id"])
        assert Decimal(row["inside"]) == Decimal("0.0000")
        assert Decimal(row["total"]) == Decimal("0.0000")
        assert row["buy_awaiting_vendor_price"] is True


def test_buy_line_without_a_vendor_price_counts_as_unpriced_on_the_quote(
    app_client: TestClient, seeder: Seeder
) -> None:
    """A Buy line's only cost source is the vendor's price. Without it the quote must
    say **unpriced**, never quietly total 0,00 € for a part nobody has quoted yet."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        _add_manual_op(app_client, line["component_id"], "CNC Bearbeitung", "100.0000")

        priced = app_client.get(f"/api/quotes/{line['quote_id']}/totals").json()
        assert priced["has_unpriced_lines"] is False
        assert priced["net_minor"] == 10000

        app_client.patch(
            f"/api/quote-items/{line['item_id']}/costing-mode", json={"costing_mode": "buy"}
        )
        awaiting = app_client.get(f"/api/quotes/{line['quote_id']}/totals").json()
        assert awaiting["has_unpriced_lines"] is True
        assert awaiting["items"][0]["unpriced"] is True

        # ...and the vendor's price makes it priced again.
        app_client.patch(
            f"/api/components/{line['component_id']}/outside-cost/1",
            json={"manual_outside_cost": "210.0000"},
        )
        settled = app_client.get(f"/api/quotes/{line['quote_id']}/totals").json()
        assert settled["has_unpriced_lines"] is False
        assert settled["net_minor"] == 21000


def test_send_rejects_a_quoting_contact_from_another_vendor(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The composite FK pins the contact to the same *org*, not the same *vendor* — so
    without an explicit check a client-supplied id could address this vendor's RFQ, and
    the portal token carrying its file allowlist, to a competing supplier's inbox."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        mine = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        rival = _create_vendor(app_client, "Eloxal Sued", processes=["eloxieren"])
        rival_contact = app_client.get(f"/api/vendors/{rival}/contacts").json()[0]["id"]

        res = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": line["quote_id"],
                "quote_item_ids": [line["item_id"]],
                "recipients": [{"vendor_id": mine, "vendor_contact_id": rival_contact}],
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["code"] == "unknown_vendor_contact"


def test_default_files_keep_an_unredacted_sibling_of_another_type(
    app_client: TestClient, seeder: Seeder
) -> None:
    """A redacted PDF supersedes *its own* original, not every file sharing the stem —
    the STEP/DXF nobody redacted is still what the vendor needs to quote."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        part_id = _part_of(app_client, line)
        seeder.part_file(org, part_id, "zeichnung.pdf")
        cad = seeder.part_file(org, part_id, "zeichnung.dxf")
        redacted = seeder.part_file(org, part_id, "zeichnung-redacted.pdf", is_redacted=True)

        body = app_client.get(
            "/api/vendor-rfqs/compose",
            params={"quote_id": line["quote_id"], "quote_item_ids": line["item_id"]},
        ).json()
        assert set(body["lines"][0]["default_file_ids"]) == {str(cad), str(redacted)}


def test_send_rejects_a_vendor_from_another_org(app_client: TestClient, seeder: Seeder) -> None:
    """Tenancy: a vendor id from org B must not attach to org A's batch."""
    org_a, user_a = _org_admin(seeder, "org-a")
    org_b, user_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        foreign = _create_vendor(app_client, "Fremd GmbH", processes=["eloxieren"])
    with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
        line = _new_quote_item(app_client)
        res = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": line["quote_id"],
                "quote_item_ids": [line["item_id"]],
                "recipients": [{"vendor_id": foreign}],
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["code"] == "unknown_vendor"


def test_send_rejects_a_line_from_another_quote(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        other = _new_quote_item(app_client)
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        res = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": line["quote_id"],
                "quote_item_ids": [other["item_id"]],
                "recipients": [{"vendor_id": vendor}],
            },
        )
        assert res.status_code == 422, res.text


def test_send_rejects_a_file_not_on_a_batch_part(app_client: TestClient, seeder: Seeder) -> None:
    """A per-vendor allowlist may only name files of the parts actually in the batch."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        elsewhere = _new_quote_item(app_client)
        stray = str(seeder.part_file(org, _part_of(app_client, elsewhere), "x.pdf"))
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        res = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": line["quote_id"],
                "quote_item_ids": [line["item_id"]],
                "recipients": [{"vendor_id": vendor, "part_file_ids": [stray]}],
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["code"] == "file_not_in_batch"


def test_send_requires_at_least_one_line_and_one_recipient(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        empty_lines = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": line["quote_id"],
                "quote_item_ids": [],
                "recipients": [{"vendor_id": vendor}],
            },
        )
        assert empty_lines.status_code == 422
        empty_vendors = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": line["quote_id"],
                "quote_item_ids": [line["item_id"]],
                "recipients": [],
            },
        )
        assert empty_vendors.status_code == 422


# --------------------------------------------------------------------------- #
# Awaiting chip + workflow soft warning + the M6.3 seams
# --------------------------------------------------------------------------- #
def test_awaiting_chip_counts_open_recipients_per_line(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Spec: "⏳ Awaiting N vendor response(s)" on the line, gone once applied/closed."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        a = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        b = _create_vendor(app_client, "Eloxal Sued", processes=["eloxieren"])
        assert _awaiting(app_client, line) == 0

        body = _send(app_client, line, [{"vendor_id": a}, {"vendor_id": b}])
        assert _awaiting(app_client, line) == 2

        # A vendor answers → one fewer outstanding.
        token = body["rfqs"][0]["portal_token"]
        rfq_line_id = app_client.get(f"/api/public/vendor-rfq/{token}").json()["lines"][0]["id"]
        submitted = app_client.post(
            f"/api/public/vendor-rfq/{token}/response",
            json={"lines": [{"rfq_line_id": rfq_line_id, "cannot_quote": True}]},
        )
        assert submitted.status_code in (200, 201), submitted.text
        assert _awaiting(app_client, line) == 1


def _awaiting(client: TestClient, line: dict[str, Any]) -> int:
    res = client.get(f"/api/quotes/{line['quote_id']}")
    assert res.status_code == 200, res.text
    item = next(i for i in res.json()["items"] if i["id"] == line["item_id"])
    return cast(int, item["awaiting_vendor_responses"])


def test_workflow_advance_warns_softly_and_still_advances(
    app_client: TestClient, seeder: Seeder
) -> None:
    """AC: "the workflow-advance warning is a soft override, not a hard block"."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        _send(app_client, line, [{"vendor_id": vendor}])

        detail = app_client.get(f"/api/quotes/{line['quote_id']}").json()
        assert detail["pending_vendor_rfq_item_count"] == 1

        # ...and the stage still advances. The warning lives in the payload the UI
        # reads, never in the transition's outcome (spec: "not a hard block").
        advanced = app_client.post(
            f"/api/quotes/{line['quote_id']}/transition", json={"to_status": "on_hold"}
        )
        assert advanced.status_code in (200, 201), advanced.text


def test_vendor_active_rfq_count_and_history_fill_the_m63_seams(
    app_client: TestClient, seeder: Seeder
) -> None:
    """M6.3 shipped both reading empty and named M6.4 as the block that fills them."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        assert _vendor_row(app_client, vendor)["active_rfq_count"] == 0

        body = _send(app_client, line, [{"vendor_id": vendor}])
        assert _vendor_row(app_client, vendor)["active_rfq_count"] == 1

        history = app_client.get(f"/api/vendors/{vendor}/rfq-history")
        assert history.status_code == 200, history.text
        rows = history.json()
        assert len(rows) == 1
        assert rows[0]["number"] == body["rfqs"][0]["number"]
        assert rows[0]["quote_id"] == line["quote_id"]
        assert rows[0]["status"] == "open"


def _vendor_row(client: TestClient, vendor_id: str) -> dict[str, Any]:
    res = client.get("/api/vendors")
    assert res.status_code == 200, res.text
    body = res.json()
    rows = body["vendors"] if isinstance(body, dict) else body
    return cast(dict[str, Any], next(v for v in rows if v["id"] == vendor_id))


def test_rfq_history_never_leaks_internal_vendor_notes(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Notes are "never visible to the vendor" — and RFQ History is estimator-facing,
    so this pins that the *batch* payload carries no internal note either."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        app_client.patch(f"/api/vendors/{vendor}", json={"notes": "Zahlt immer spaet"})
        body = _send(app_client, line, [{"vendor_id": vendor}])

    token = body["rfqs"][0]["portal_token"]
    payload = app_client.get(f"/api/public/vendor-rfq/{token}").text
    assert "Zahlt immer spaet" not in payload


# --------------------------------------------------------------------------- #
# M3.13 — the outbound forward gate: quarantined files never reach a vendor
# --------------------------------------------------------------------------- #
def _quarantine(seeder: Seeder, file_id: str) -> None:
    """Plant a clamd verdict the API has no route to write (M3.13 sets it async)."""
    seeder.sql(
        "UPDATE part_file SET scan_status = 'infected', "
        "scan_signature = 'Eicar-Test-Signature', scanned_at = now() WHERE id = :id",
        {"id": file_id},
    )


def test_send_rejects_a_quarantined_file(app_client: TestClient, seeder: Seeder) -> None:
    """Granting a vendor a token for an infected file *is* the outbound disclosure,
    so the send is refused up front — the estimator finds out now, not the vendor
    at download (M3.13; the same reasoning as the allowlist check)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        part_id = _part_of(app_client, line)
        infected = _stored_file(app_client, seeder, org, part_id, "malware.pdf")
        _quarantine(seeder, infected)
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])

        res = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": line["quote_id"],
                "quote_item_ids": [line["item_id"]],
                "recipients": [{"vendor_id": vendor, "part_file_ids": [infected]}],
            },
        )
        assert res.status_code == 409, res.text
        assert res.json()["code"] == "file_scan_not_clean"
        assert res.json()["details"]["part_file_ids"] == [infected]


def test_portal_download_of_a_file_quarantined_after_send_is_blocked(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The portal re-checks independently: a file that turns infected *after* the
    batch went out is still stopped at the door (M3.13)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_quote_item(app_client)
        part_id = _part_of(app_client, line)
        file_id = _stored_file(app_client, seeder, org, part_id, "zeichnung.pdf")
        vendor = _create_vendor(app_client, "Eloxal Nord", processes=["eloxieren"])
        body = _send(app_client, line, [{"vendor_id": vendor, "part_file_ids": [file_id]}])

    token = body["rfqs"][0]["portal_token"]
    assert app_client.get(f"/api/public/vendor-rfq/{token}/files/{file_id}").status_code == 200

    _quarantine(seeder, file_id)
    blocked = app_client.get(f"/api/public/vendor-rfq/{token}/files/{file_id}")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "file_quarantined"
