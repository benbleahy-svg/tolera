"""M5.8 — Finalized Quote Settings (Settings → Digital Quote + Checkout/Requotes).

Two layers:

* **Pure projection** (`app.quote_settings` / `app.buyer_portal`): the persisted
  ``QuoteSettings`` snapshot maps 1:1 onto the ``DisplaySettings`` view the portal
  + PDF read (radios → enums); the offered-shipping-methods helper honours "Allow
  Local Pickup" and per-method disabling; defaults never drift from the seams'
  own dataclass defaults.
* **The admin API + wiring** (real RLS-bound Postgres, through the API): GET
  returns all-defaults for a never-configured org; a PUT persists and is org
  isolated; writes need ``settings_edit`` (reads are ``view_all``); a saved
  Display Setting hides its field on the buyer portal; the Requotes toggle drives
  the portal flag; disabling a shipping option makes checkout reject it (422).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.buyer_portal import (
    DEFAULT_DISPLAY_SETTINGS,
    NotesPlacement,
    PreparerDisplay,
    TotalDisplay,
    display_from_quote_settings,
)
from app.models import MembershipRole
from app.quote_settings import (
    DEFAULT_QUOTE_SETTINGS,
    QuoteSettings,
    offered_shipping_methods,
)
from tests.conftest import Seeder, authed
from tests.test_buyer_portal_m51 import _as_admin, _mint, _org_admin, _priced_quote

SETTINGS_URL = "/api/settings/quote"


# --------------------------------------------------------------------------- #
# Pure projection — no DB
# --------------------------------------------------------------------------- #
def test_display_from_quote_settings_maps_toggles_and_radios() -> None:
    qs = QuoteSettings(
        show_material=False,
        show_dimensions=True,
        total_display="maximum_price",
        preparer="estimator",
        notes_placement="below",
    )
    display = display_from_quote_settings(qs)
    assert display.show_material is False
    assert display.show_dimensions is True
    # Radios are stored as strings and come back as the DisplaySettings enums.
    assert display.total_display is TotalDisplay.maximum_price
    assert display.preparer is PreparerDisplay.estimator
    assert display.notes_placement is NotesPlacement.below


def test_default_quote_settings_projects_to_display_defaults() -> None:
    # Guard against the two default sets drifting apart (one persisted row backs
    # the DisplaySettings seam, so their defaults must agree).
    assert display_from_quote_settings(DEFAULT_QUOTE_SETTINGS) == DEFAULT_DISPLAY_SETTINGS


def test_offered_shipping_methods_default_offers_all() -> None:
    offered = offered_shipping_methods(DEFAULT_QUOTE_SETTINGS)
    assert offered == [
        "bill_at_shipment",
        "use_my_shipping_account",
        "no_shipping_fees",
        "local_pickup",
    ]


def test_offered_shipping_methods_local_pickup_gated() -> None:
    offered = offered_shipping_methods(QuoteSettings(allow_local_pickup=False))
    assert "local_pickup" not in offered
    assert "bill_at_shipment" in offered


def test_offered_shipping_methods_respects_disabled_set() -> None:
    offered = offered_shipping_methods(
        QuoteSettings(disabled_shipping_methods=("no_shipping_fees",))
    )
    assert "no_shipping_fees" not in offered
    assert "bill_at_shipment" in offered


# --------------------------------------------------------------------------- #
# Admin API — real RLS-bound Postgres
# --------------------------------------------------------------------------- #
def _as_roles(
    client: TestClient, org: uuid.UUID, user: uuid.UUID, roles: list[MembershipRole]
) -> Any:
    return authed(client, user_id=user, org_id=org, roles=roles)


def test_get_returns_defaults_when_unconfigured(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-defaults")
    with _as_admin(app_client, org, user):
        res = app_client.get(SETTINGS_URL)
    assert res.status_code == 200, res.text
    body = res.json()
    # A brand-new org has no row → all-defaults (matches the seam dataclass).
    assert body["show_material"] is True
    assert body["show_dimensions"] is False
    assert body["requotes_enabled"] is True
    assert body["allow_local_pickup"] is True
    assert body["total_display"] == "price_range"
    assert body["disabled_shipping_methods"] == []


def test_put_persists_and_get_reflects(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-put")
    with _as_admin(app_client, org, user):
        put = app_client.put(
            SETTINGS_URL,
            json={
                "show_material": False,
                "terms": "Zahlbar innerhalb 30 Tagen.",
                "requotes_enabled": False,
                "disabled_shipping_methods": ["no_shipping_fees"],
                "default_tax_rate_pct": "19.00",
            },
        )
        assert put.status_code == 200, put.text
        got = app_client.get(SETTINGS_URL).json()
    assert got["show_material"] is False
    assert got["terms"] == "Zahlbar innerhalb 30 Tagen."
    assert got["requotes_enabled"] is False
    assert got["disabled_shipping_methods"] == ["no_shipping_fees"]
    assert got["default_tax_rate_pct"] == "19.00"
    # Untouched fields keep their defaults (partial update).
    assert got["show_part_number"] is True


def test_put_requires_settings_edit(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-authz")
    # A viewer may READ (view_all) but not WRITE (settings_edit).
    with _as_roles(app_client, org, user, [MembershipRole.viewer]):
        assert app_client.get(SETTINGS_URL).status_code == 200
        forbidden = app_client.put(SETTINGS_URL, json={"show_material": False})
    assert forbidden.status_code == 403, forbidden.text


def test_settings_are_org_scoped(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "qs-org-a")
    org_b, user_b = _org_admin(seeder, "qs-org-b")
    with _as_admin(app_client, org_a, user_a):
        written = app_client.put(
            SETTINGS_URL, json={"show_material": False, "requotes_enabled": False}
        )
        assert written.status_code == 200, written.text
        # Confirm org A actually persisted the change (else the isolation
        # assertion below would pass trivially on a failed write).
        body_a = app_client.get(SETTINGS_URL).json()
    assert body_a["show_material"] is False
    assert body_a["requotes_enabled"] is False
    # Org B never wrote a row → still sees defaults; org A's change did not leak.
    with _as_admin(app_client, org_b, user_b):
        body_b = app_client.get(SETTINGS_URL).json()
    assert body_b["show_material"] is True
    assert body_b["requotes_enabled"] is True


# --------------------------------------------------------------------------- #
# Wiring — the settings drive the portal + checkout
# --------------------------------------------------------------------------- #
def test_display_setting_hides_portal_field(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-portal")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
        client.put(SETTINGS_URL, json={"show_material": False, "requotes_enabled": False})
    _, token = _mint(seeder, app_client, org, qid)

    body = app_client.get(f"/api/public/quotes/{token}").json()
    item = body["line_items"][0]
    # show_material off → the field is absent from the payload (not just hidden).
    assert "material" not in item
    assert "werkstoffnummer" not in item
    # Requotes toggle flows into the portal-level flag.
    assert body["requotes_enabled"] is False
    # Checkout options are advertised for the buyer to pick.
    assert "local_pickup" in body["checkout"]["shipping_methods"]


def test_checkout_rejects_disabled_shipping_method(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-checkout")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
        client.put(SETTINGS_URL, json={"disabled_shipping_methods": ["no_shipping_fees"]})
    _, token = _mint(seeder, app_client, org, qid)
    portal = app_client.get(f"/api/public/quotes/{token}").json()
    item = portal["line_items"][0]
    ids = {"quote_item_id": item["quote_item_id"], "quantity": item["breaks"][0]["quantity"]}

    # The disabled option must not be offered...
    assert "no_shipping_fees" not in portal["checkout"]["shipping_methods"]
    # ...and the server rejects it even if a tampered client submits it.
    rejected = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [ids],
            "po_number": "PO-1",
            "shipping_method": "no_shipping_fees",
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["code"] == "invalid_selection"

    # A still-offered option goes through.
    ok = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [ids],
            "po_number": "PO-2",
            "shipping_method": "bill_at_shipment",
        },
    )
    assert ok.status_code == 201, ok.text


def test_local_pickup_gated_by_setting_at_checkout(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-pickup")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
        client.put(SETTINGS_URL, json={"allow_local_pickup": False})
    _, token = _mint(seeder, app_client, org, qid)
    portal = app_client.get(f"/api/public/quotes/{token}").json()
    item = portal["line_items"][0]
    ids = {"quote_item_id": item["quote_item_id"], "quantity": item["breaks"][0]["quantity"]}

    assert "local_pickup" not in portal["checkout"]["shipping_methods"]
    rejected = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={"selections": [ids], "po_number": "PO-3", "shipping_method": "local_pickup"},
    )
    assert rejected.status_code == 422, rejected.text


def test_checkout_requires_terms_acceptance_when_enabled(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "qs-terms")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
        client.put(SETTINGS_URL, json={"require_terms_acceptance": True})
    _, token = _mint(seeder, app_client, org, qid)
    portal = app_client.get(f"/api/public/quotes/{token}").json()
    item = portal["line_items"][0]
    ids = {"quote_item_id": item["quote_item_id"], "quantity": item["breaks"][0]["quantity"]}
    assert portal["checkout"]["require_terms_acceptance"] is True

    # Without accepting the T&Cs the checkout is rejected (server-enforced).
    rejected = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={"selections": [ids], "po_number": "PO-T", "shipping_method": "bill_at_shipment"},
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["code"] == "terms_not_accepted"

    # Accepting them lets the order through.
    ok = app_client.post(
        f"/api/public/quotes/{token}/checkout",
        json={
            "selections": [ids],
            "po_number": "PO-T",
            "shipping_method": "bill_at_shipment",
            "terms_accepted": True,
        },
    )
    assert ok.status_code == 201, ok.text


def test_put_rejects_explicit_null_on_non_nullable(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-null")
    with _as_admin(app_client, org, user):
        res = app_client.put(SETTINGS_URL, json={"requotes_enabled": None})
    assert res.status_code == 422, res.text


def test_put_rejects_unknown_notification_key(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "qs-notif")
    with _as_admin(app_client, org, user):
        res = app_client.put(SETTINGS_URL, json={"notification_recipients": {"bogus": "x@y.de"}})
    assert res.status_code == 422, res.text
    # A known key persists.
    with _as_admin(app_client, org, user):
        ok = app_client.put(
            SETTINGS_URL,
            json={"notification_recipients": {"order_confirmation": "ops@shop.de"}},
        )
        assert ok.status_code == 200, ok.text
        got = app_client.get(SETTINGS_URL).json()
    assert got["notification_recipients"] == {"order_confirmation": "ops@shop.de"}
