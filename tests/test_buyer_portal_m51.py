"""M5.1 — Digital Quote buyer portal (unauthenticated token).

Three layers:

* **Token crypto** (`app.quote_tokens`): mint/verify round-trip; a tampered or
  wrongly-signed token is rejected; the JWT carries **no ``exp``** (soft
  app-layer expiry — spec ``#digitalquote`` build-implications).
* **Field-gating projection** (`app.buyer_portal.build_line_item`): the buyer
  payload is an **allowlist** — internal cost/margin fields are absent from the
  payload (not just CSS-hidden), a toggled-off Display Setting removes its field,
  expedite surcharge is the per-unit delta, No-Quote lines carry no grid.
* **The public endpoint** (real RLS-bound Postgres, through the API): a valid
  token loads the quote with no auth; a revoked / garbage / wrong-scope token is
  401; a soft-expired quote shows EXPIRED yet stays selectable; access is logged.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.buyer_portal import DEFAULT_DISPLAY_SETTINGS, DisplaySettings, _ItemRow, build_line_item
from app.models import (
    Material,
    MembershipRole,
    Part,
    Process,
    QiWorkflowStatus,
    Quote,
    QuoteItem,
    QuoteToken,
    QuoteTokenAccess,
    QuoteTokenScope,
)
from app.quote_tokens import (
    InvalidToken,
    create_buyer_token,
    decode_jwt,
    mint_jwt,
)
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
SECRET = "unit-test-secret-at-least-32-bytes-long-key"


def _app_secret(app_client: TestClient) -> str:
    """The signing secret the running app resolves (test env → fixed dev key)."""
    secret = cast(Any, app_client.app).state.settings.resolve_quote_token_secret()
    return cast(str, secret)


# --------------------------------------------------------------------------- #
# Token crypto — pure, no DB
# --------------------------------------------------------------------------- #
def test_mint_verify_round_trip() -> None:
    token_id, org_id, quote_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = mint_jwt(
        SECRET,
        token_id=token_id,
        org_id=org_id,
        quote_id=quote_id,
        scope=QuoteTokenScope.buyer_portal,
    )
    claims = decode_jwt(SECRET, token)
    assert claims.token_id == token_id
    assert claims.org_id == org_id
    assert claims.quote_id == quote_id
    assert claims.scope is QuoteTokenScope.buyer_portal


def test_token_omits_exp_claim() -> None:
    """Soft expiry: the JWT itself must never carry ``exp`` (spec build-note)."""
    token = mint_jwt(
        SECRET,
        token_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        quote_id=uuid.uuid4(),
        scope=QuoteTokenScope.buyer_portal,
    )
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert "exp" not in payload


def test_wrong_secret_is_rejected() -> None:
    token = mint_jwt(
        SECRET,
        token_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        quote_id=uuid.uuid4(),
        scope=QuoteTokenScope.buyer_portal,
    )
    with pytest.raises(InvalidToken):
        decode_jwt("a-different-secret-also-at-least-32-bytes-long", token)


def test_tampered_and_garbage_tokens_are_rejected() -> None:
    token = mint_jwt(
        SECRET,
        token_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        quote_id=uuid.uuid4(),
        scope=QuoteTokenScope.buyer_portal,
    )
    with pytest.raises(InvalidToken):
        decode_jwt(SECRET, token[:-3] + "xyz")  # mutate the signature
    with pytest.raises(InvalidToken):
        decode_jwt(SECRET, "not-a-jwt")


# --------------------------------------------------------------------------- #
# Field-gating projection — pure, no DB
# --------------------------------------------------------------------------- #
def _row(*, status: QiWorkflowStatus = QiWorkflowStatus.completed) -> _ItemRow:
    return _ItemRow(
        quote_item=QuoteItem(id=uuid.uuid4(), position=0, workflow_status=status),
        part=Part(
            part_number="P-100",
            revision="B",
            description="Bracket",
            primary_file_id=uuid.uuid4(),
        ),
        process=Process(name="CNC Fräsen", external_name="CNC Milling"),
        material=Material(display_name="1.4301", werkstoffnummer="1.4301"),
        geometry=None,
    )


def _pricing(
    *,
    unit_price: str = "100.0000",
    expedite_unit: str | None = "110.0000",
    add_on_required: bool = True,
) -> dict[str, Any]:
    """A pricing-summary-shaped dict carrying BOTH buyer fields and internal
    cost/margin fields — the projection must copy only the former."""
    return {
        "component_id": "x",
        # internal — MUST be gated out of the buyer payload
        "costing": [{"quantity": 1, "material": "40.0000", "inside": "10.0000"}],
        "pricing_items": [{"pct": "150", "amount": "60.0000"}],
        "discounts": [{"name": "loyalty", "cells": [{"pct": "5"}]}],
        "totals": [
            {
                "quantity": 1,
                "unit_price": Decimal(unit_price),
                "total_price": Decimal(unit_price),
                "unit_cost": Decimal("50.0000"),
                "total_markup": Decimal("50.0000"),
                "total_profit": Decimal("50.0000"),
                "profit_margin_pct": Decimal("50"),
            }
        ],
        "lead_times": [
            {
                "quantity": 1,
                "lead_time_days": 10,
                "expedites": [
                    {
                        "id": "e1",
                        "days_faster": 3,
                        "markup_pct": Decimal("10"),
                        "lead_time_days": 7,
                        "unit_price": Decimal(expedite_unit) if expedite_unit else None,
                        "total_price": Decimal(expedite_unit) if expedite_unit else None,
                    }
                ],
            }
        ],
        "add_ons": [
            {
                "id": "a1",
                "display_name": "Zertifikat 3.1",
                "is_required": add_on_required,
                "cells": [{"quantity": 1, "price": Decimal("25.0000")}],
            }
        ],
    }


_FORBIDDEN_KEYS = {
    "costing",
    "pricing_items",
    "discounts",
    "unit_cost",
    "total_markup",
    "total_markup_pct",
    "total_profit",
    "profit_margin_pct",
    "total_discount",
    "calc_unit_price",
    "manual_unit_price",
    "material",  # only when show_material is off — see the dedicated test
}


def _all_keys(obj: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            keys |= _all_keys(v)
    return keys


def test_internal_cost_and_margin_fields_never_leak() -> None:
    card = build_line_item(_row(), _pricing(), DEFAULT_DISPLAY_SETTINGS)
    leaked = _all_keys(card) & (_FORBIDDEN_KEYS - {"material"})
    assert leaked == set(), f"internal fields leaked into buyer payload: {leaked}"


def test_buyer_fields_are_present() -> None:
    card = build_line_item(_row(), _pricing(), DEFAULT_DISPLAY_SETTINGS)
    assert card["part_number"] == "P-100"
    assert card["process"] == "CNC Milling"  # external_name wins
    assert card["material"] == "1.4301"
    brk = card["breaks"][0]
    assert brk["unit_price"] == "100.0000"
    assert brk["lead_time_days"] == 10
    assert card["add_ons"][0]["is_required"] is True


def test_toggled_off_field_is_absent_from_payload() -> None:
    settings = DisplaySettings(show_material=False, show_process=False)
    card = build_line_item(_row(), _pricing(), settings)
    assert "material" not in card
    assert "werkstoffnummer" not in card
    assert "process" not in card
    # the fields that stayed on are still present
    assert card["part_number"] == "P-100"


def test_expedite_surcharge_is_the_per_unit_delta() -> None:
    pricing = _pricing(unit_price="100.0000", expedite_unit="160.0000")
    card = build_line_item(_row(), pricing, DEFAULT_DISPLAY_SETTINGS)
    expedite = card["breaks"][0]["expedites"][0]
    assert expedite["unit_price"] == "160.0000"
    assert Decimal(expedite["unit_surcharge"]) == Decimal("60.0000")  # "+ €60,00 / ea"


def test_no_quote_line_has_no_pricing_grid() -> None:
    row = _row(status=QiWorkflowStatus.no_quote)
    card = build_line_item(row, _pricing(), DEFAULT_DISPLAY_SETTINGS)
    assert card["is_no_quote"] is True
    assert "breaks" not in card
    assert "add_ons" not in card


# --------------------------------------------------------------------------- #
# The public endpoint — real RLS-bound Postgres
# --------------------------------------------------------------------------- #
@contextmanager
def _as_admin(client: TestClient, org: uuid.UUID, user: uuid.UUID) -> Iterator[TestClient]:
    with authed(client, user_id=user, org_id=org, roles=ADMIN):
        yield client


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug, country="DE", currency="EUR")
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _priced_quote(client: TestClient) -> tuple[str, str]:
    """Build a one-item quote priced to a unit of 200,00 € with an expedite tier
    and one required + one optional add-on. Returns (quote_id, component_id)."""
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    component_id = str(item["root_component_id"])
    op = client.post(f"/api/components/{component_id}/operations", json={"name": "Fräsen"})
    op_id = next(o for o in op.json()["operations"] if o["name"] == "Fräsen")["id"]
    client.patch(f"/api/operations/{op_id}/cells/1", json={"manual_cost": "100.0000"})
    client.post(
        f"/api/components/{component_id}/pricing-items",
        json={
            "name": "Aufschlag",
            "calc_type": "markup",
            "category": "general",
            "default_pct": "100",
        },
    )
    client.patch(f"/api/components/{component_id}/lead-time/1", json={"manual_lead_time_days": 10})
    client.put(
        f"/api/components/{component_id}/expedite-options",
        json={"options": [{"days_faster": 3, "markup_pct": "10"}]},
    )
    client.post(
        f"/api/components/{component_id}/add-ons",
        json={"name": "Zertifikat", "default_price": "25", "is_required": True},
    )
    client.post(
        f"/api/components/{component_id}/add-ons",
        json={"name": "Express-Verpackung", "default_price": "15", "is_required": False},
    )
    return qid, component_id


def _mint(
    seeder: Seeder, app_client: TestClient, org_id: uuid.UUID, quote_id: str
) -> tuple[uuid.UUID, str]:
    """Mint a persisted buyer token via the owner engine; sign with the app's secret."""
    secret = _app_secret(app_client)

    async def _run() -> tuple[uuid.UUID, str]:
        async with AsyncSession(seeder._engine) as session, session.begin():
            quote = await session.get(Quote, uuid.UUID(quote_id))
            assert quote is not None
            row, token = await create_buyer_token(session, secret, quote)
            return row.id, token

    return seeder._loop.run_until_complete(_run())


def test_valid_token_loads_quote_with_no_auth(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "portal-load")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)

    # No Authorization header — the token is the only credential.
    res = app_client.get(f"/api/public/quotes/{token}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["shop"]["name"]
    assert body["currency"] == "EUR"
    assert body["is_expired"] is False
    item = body["line_items"][0]
    brk = item["breaks"][0]
    assert brk["unit_price"] == "200.0000"
    assert Decimal(brk["expedites"][0]["unit_surcharge"]) == Decimal("20.0000")
    # required + optional add-on both surfaced, with the required flag
    flags = sorted(a["is_required"] for a in item["add_ons"])
    assert flags == [False, True]
    # the range chip
    assert body["price_range"]["min_unit"] == "200.0000"


def test_internal_fields_absent_over_the_wire(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "portal-gate")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    _, token = _mint(seeder, app_client, org, qid)
    body = app_client.get(f"/api/public/quotes/{token}").json()
    leaked = _all_keys(body) & {
        "costing",
        "pricing_items",
        "unit_cost",
        "total_markup",
        "total_profit",
        "profit_margin_pct",
    }
    assert leaked == set(), f"internal fields leaked over the wire: {leaked}"


def test_revoked_token_is_401(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "portal-revoke")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    token_id, token = _mint(seeder, app_client, org, qid)

    async def _revoke() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            row = await session.get(QuoteToken, token_id)
            assert row is not None
            row.revoked_at = datetime.now(UTC)

    seeder._loop.run_until_complete(_revoke())
    res = app_client.get(f"/api/public/quotes/{token}")
    assert res.status_code == 401, res.text


def test_garbage_token_is_401(app_client: TestClient) -> None:
    assert app_client.get("/api/public/quotes/not-a-real-token").status_code == 401


def test_wrong_scope_token_is_401(seeder: Seeder, app_client: TestClient) -> None:
    """A token minted for a non-buyer scope (M6 vendor share) must not open the
    buyer portal even though the signature is valid."""
    org, user = _org_admin(seeder, "portal-scope")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    secret = _app_secret(app_client)
    forged = mint_jwt(
        secret,
        token_id=uuid.uuid4(),
        org_id=org,
        quote_id=uuid.UUID(qid),
        scope=QuoteTokenScope.vendor_share,
    )
    assert app_client.get(f"/api/public/quotes/{forged}").status_code == 401


def test_soft_expired_quote_is_reachable_and_selectable(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "portal-expired")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)

    async def _expire() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            quote = await session.get(Quote, uuid.UUID(qid))
            assert quote is not None
            quote.expiration_date = datetime.now(UTC) - timedelta(days=1)

    seeder._loop.run_until_complete(_expire())
    _, token = _mint(seeder, app_client, org, qid)

    body = app_client.get(f"/api/public/quotes/{token}").json()
    assert body["is_expired"] is True
    # soft expiry: selection stays available — the priced grid is still returned
    assert body["line_items"][0]["breaks"], "expired quote must remain selectable"


def test_access_is_logged(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "portal-audit")
    with _as_admin(app_client, org, user) as client:
        qid, _ = _priced_quote(client)
    token_id, token = _mint(seeder, app_client, org, qid)
    app_client.get(f"/api/public/quotes/{token}")
    app_client.get(f"/api/public/quotes/{token}")

    async def _count() -> int:
        async with AsyncSession(seeder._engine) as session:
            result = await session.scalar(
                select(func.count())
                .select_from(QuoteTokenAccess)
                .where(QuoteTokenAccess.quote_token_id == token_id)
            )
            return result or 0

    assert seeder._loop.run_until_complete(_count()) == 2
