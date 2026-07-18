"""M5.4 — quote/order PDF download endpoints (DB → render → store → refetch).

Exercises the Clerk-authenticated shop-side downloads against a real RLS-bound
Postgres: a priced quote renders to a stored, re-fetchable ``application/pdf``;
the buyer-portal checkout's Order renders the confirmation variant; a cross-org
id 404s. Skipped wholesale when WeasyPrint's native libs are unavailable (the
render is exercised in CI, where libpango is installed).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Organization, Quote
from app.pdf import weasyprint_available
from app.vat_service import VIESClient, ViesResult, get_vies_client
from tests.conftest import Seeder
from tests.test_buyer_portal_m51 import _as_admin, _mint, _org_admin, _priced_quote

pytestmark = pytest.mark.skipif(
    not weasyprint_available(), reason="WeasyPrint native libs unavailable"
)


def _set_branding(seeder: Seeder, org_id: uuid.UUID) -> None:
    """Give the org its white-label Facility Information (M5.4 renders it)."""

    async def _run() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            org = await session.get(Organization, org_id)
            assert org is not None
            org.brand_accent_color = "#1a3c5e"
            org.facility_phone = "+49 89 111"
            org.facility_website = "www.fechner.example"
            org.facility_address = "Musterstr. 1\n80331 München"
            org.ust_id_nr = "DE123456789"

    seeder._loop.run_until_complete(_run())


class _StubVies:
    async def check(self, ust_id_nr: str) -> ViesResult:
        return ViesResult(valid=True, checked_at=datetime.now(UTC), name="ACME")


def _pdf_object_key(seeder: Seeder, model: Any, row_id: str, org_id: uuid.UUID) -> str | None:
    """Read a row's ``pdf_object_key``, asserting it belongs to ``org_id`` (the
    seeder session bypasses RLS, so the lookup is org-scoped by hand)."""

    async def _run() -> str | None:
        async with AsyncSession(seeder._engine) as session:
            row = await session.get(model, uuid.UUID(row_id))
            if row is None:
                return None
            assert row.org_id == org_id
            return cast(str | None, row.pdf_object_key)

    return seeder._loop.run_until_complete(_run())


# --------------------------------------------------------------------------- #
# Quote PDF
# --------------------------------------------------------------------------- #
def test_quote_pdf_preview_downloads(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "pdf-quote")
    _set_branding(seeder, org)
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
        res = client.get(f"/api/quotes/{qid}/pdf")

    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:5] == b"%PDF-"
    assert "Angebot" in res.headers["content-disposition"]

    # The quote endpoint is a LIVE PREVIEW — it must not persist pdf_object_key
    # (that key is the M5.5 send-time snapshot).
    assert _pdf_object_key(seeder, Quote, qid, org) is None


def test_quote_pdf_missing_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "pdf-quote-404")
    with _as_admin(app_client, org, user) as client:
        res = client.get(f"/api/quotes/{uuid.uuid4()}/pdf")
    assert res.status_code == 404


def test_quote_pdf_cross_org_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "pdf-a")
    org_b, user_b = _org_admin(seeder, "pdf-b")
    with _as_admin(app_client, org_a, user_a) as client:
        qid, _ = _priced_quote(client)
    # Org B cannot see Org A's quote (RLS).
    with _as_admin(app_client, org_b, user_b) as client:
        res = client.get(f"/api/quotes/{qid}/pdf")
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
# Order-confirmation PDF (via a real buyer-portal checkout)
# --------------------------------------------------------------------------- #
def _checkout_to_order(
    seeder: Seeder, app_client: TestClient, org: uuid.UUID, user: uuid.UUID
) -> str:
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)

    cast(FastAPI, app_client.app).dependency_overrides[get_vies_client] = lambda: cast(
        VIESClient, _StubVies()
    )
    try:
        portal = app_client.get(f"/api/public/quotes/{token}").json()
        item = portal["line_items"][0]
        qty = item["breaks"][0]["quantity"]
        res = app_client.post(
            f"/api/public/quotes/{token}/checkout",
            json={
                "selections": [{"quote_item_id": item["quote_item_id"], "quantity": qty}],
                "po_number": "PO-9001",
                "company_name": "Muster GmbH",
                "billing_address": "Musterstr. 9\n10115 Berlin",
                "shipping_method": "bill_at_shipment",
            },
        )
    finally:
        cast(FastAPI, app_client.app).dependency_overrides.pop(get_vies_client, None)
    assert res.status_code == 201, res.text
    return cast(str, res.json()["order_id"])


def test_order_pdf_downloads_confirmation_variant(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "pdf-order")
    _set_branding(seeder, org)
    order_id = _checkout_to_order(seeder, app_client, org, user)

    with _as_admin(app_client, org, user) as client:
        res = client.get(f"/api/orders/{order_id}/pdf")

    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:5] == b"%PDF-"
    assert "Auftragsbestaetigung" in res.headers["content-disposition"]

    # Stored + re-fetchable: the order artifact is persisted and streams back.
    key = _pdf_object_key(seeder, Order, order_id, org)
    assert key is not None
    storage = cast(FastAPI, app_client.app).state.storage

    async def _fetch() -> bytes:
        return b"".join([chunk async for chunk in storage.stream(key)])

    stored = seeder._loop.run_until_complete(_fetch())
    assert stored[:5] == b"%PDF-"


def test_order_pdf_missing_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "pdf-order-404")
    with _as_admin(app_client, org, user) as client:
        res = client.get(f"/api/orders/{uuid.uuid4()}/pdf")
    assert res.status_code == 404


def test_order_pdf_cross_org_is_404(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "pdf-order-a")
    _set_branding(seeder, org_a)
    order_id = _checkout_to_order(seeder, app_client, org_a, user_a)
    org_b, user_b = _org_admin(seeder, "pdf-order-b")
    # Org B cannot fetch Org A's order PDF (RLS).
    with _as_admin(app_client, org_b, user_b) as client:
        res = client.get(f"/api/orders/{order_id}/pdf")
    assert res.status_code == 404
