"""M6.2 — Vendor RFQ portal (unauthenticated, recipient-scoped token).

Three layers, mirroring the buyer-portal suite (M5.1):

* **Token crypto** (`app.quote_tokens`): a ``vendor_rfq`` token round-trips with an
  ``rfq`` subject claim and **no ``quote``** claim, carries no ``exp`` (soft expiry —
  the portal never closes), and a tampered/wrongly-signed token is rejected.
* **Projection + validation** (`app.vendor_portal`): the file allowlist fails closed;
  the payload is an allowlist that never carries a price or another vendor.
* **The public endpoints** (real RLS-bound Postgres, through the API): a valid token
  renders only its batch; tampered/revoked/wrong-scope is 401; a **partial** response
  (some lines "cannot quote") submits; a **late** submission still succeeds and is
  stamped; a token cannot reach another batch's line, another org's data, or the buyer
  portal.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    MembershipRole,
    QuoteToken,
    QuoteTokenScope,
    VendorRfq,
    VendorRfqLine,
    VendorRfqRecipient,
)
from app.quote_tokens import (
    InvalidToken,
    create_vendor_rfq_token,
    decode_jwt,
    mint_jwt,
)
from app.vendor_portal import _allowed_file_ids
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
SECRET = "unit-test-secret-at-least-32-bytes-long-key"


def _app_secret(app_client: TestClient) -> str:
    secret = cast(Any, app_client.app).state.settings.resolve_quote_token_secret()
    return cast(str, secret)


# --------------------------------------------------------------------------- #
# Token crypto — pure, no DB
# --------------------------------------------------------------------------- #
def test_vendor_token_round_trips_with_rfq_subject() -> None:
    token_id, org_id, recipient_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = mint_jwt(
        SECRET,
        token_id=token_id,
        org_id=org_id,
        rfq_recipient_id=recipient_id,
        scope=QuoteTokenScope.vendor_rfq,
    )
    claims = decode_jwt(SECRET, token)
    assert claims.token_id == token_id
    assert claims.org_id == org_id
    assert claims.rfq_recipient_id == recipient_id
    assert claims.scope is QuoteTokenScope.vendor_rfq
    # A vendor token is scoped to a recipient, never to a quote.
    assert claims.quote_id is None


def test_vendor_token_omits_quote_and_exp_claims() -> None:
    """No ``exp`` (the portal never closes) and no ``quote`` (recipient-scoped)."""
    token = mint_jwt(
        SECRET,
        token_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        rfq_recipient_id=uuid.uuid4(),
        scope=QuoteTokenScope.vendor_rfq,
    )
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert "exp" not in payload
    assert "quote" not in payload


def test_buyer_token_still_omits_the_rfq_claim() -> None:
    """The generalised mint must not start emitting an ``rfq`` claim for buyers."""
    token = mint_jwt(
        SECRET,
        token_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        quote_id=uuid.uuid4(),
        scope=QuoteTokenScope.buyer_portal,
    )
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert "rfq" not in payload
    assert decode_jwt(SECRET, token).rfq_recipient_id is None


def test_vendor_token_tampered_or_wrongly_signed_is_rejected() -> None:
    token = mint_jwt(
        SECRET,
        token_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        rfq_recipient_id=uuid.uuid4(),
        scope=QuoteTokenScope.vendor_rfq,
    )
    with pytest.raises(InvalidToken):
        decode_jwt(SECRET, token[:-3] + "xyz")
    with pytest.raises(InvalidToken):
        decode_jwt("a-different-secret-also-at-least-32-bytes-long", token)


# --------------------------------------------------------------------------- #
# File allowlist — pure, no DB
# --------------------------------------------------------------------------- #
def test_file_allowlist_fails_closed() -> None:
    """No ``file_permissions`` → no downloads. Security defaults are never 'all'."""
    assert _allowed_file_ids(QuoteToken(file_permissions=None)) == set()
    assert _allowed_file_ids(QuoteToken(file_permissions={})) == set()
    assert _allowed_file_ids(QuoteToken(file_permissions={"part_file_ids": []})) == set()


def test_file_allowlist_ignores_malformed_entries() -> None:
    """A junk entry grants nothing — it must never widen the grant."""
    good = uuid.uuid4()
    token = QuoteToken(file_permissions={"part_file_ids": [str(good), "not-a-uuid"]})
    assert _allowed_file_ids(token) == {good}


# --------------------------------------------------------------------------- #
# The public endpoints — real RLS-bound Postgres
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


def _quote_with_item(client: TestClient) -> tuple[str, str, str]:
    """A one-line quote with a 10-off quantity break. Returns (quote, item, component)."""
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    component_id = str(item["root_component_id"])
    # A 10-off break, so "quantity 999 was not requested" has something to be wrong about.
    client.put(f"/api/quotes/{qid}/items/{item['id']}/quantities", json={"quantities": [1, 10]})
    return qid, str(item["id"]), component_id


def _seed_rfq(
    seeder: Seeder,
    app_client: TestClient,
    org: uuid.UUID,
    quote_id: str,
    item_ids: list[str],
    *,
    number: str = "RFQ-1001",
    need_by: date | None = None,
    part_file_ids: list[uuid.UUID] | None = None,
) -> tuple[str, list[str], uuid.UUID]:
    """Plant an RFQ batch + one recipient and mint its portal token.

    Returns ``(token, rfq_line_ids, token_row_id)``. Written through the owner engine
    (the compose modal that creates a batch is M6.4)."""
    secret = _app_secret(app_client)

    async def _run() -> tuple[str, list[str], uuid.UUID]:
        async with AsyncSession(seeder._engine) as session, session.begin():
            rfq = VendorRfq(
                org_id=org,
                quote_id=uuid.UUID(quote_id),
                number=number,
                need_by_date=need_by,
                message="Bitte um Angebot für Eloxieren.",
            )
            session.add(rfq)
            await session.flush()
            line_ids = []
            for position, item_id in enumerate(item_ids):
                line = VendorRfqLine(
                    org_id=org,
                    rfq_id=rfq.id,
                    quote_item_id=uuid.UUID(item_id),
                    position=position,
                    estimator_notes="Schichtdicke 20 µm",
                )
                session.add(line)
                await session.flush()
                line_ids.append(str(line.id))
            recipient = VendorRfqRecipient(
                org_id=org,
                rfq_id=rfq.id,
                vendor_name="Eloxal Schmidt GmbH",
                contact_email="angebot@eloxal-schmidt.example",
            )
            session.add(recipient)
            await session.flush()
            row, token = await create_vendor_rfq_token(
                session, secret, recipient, part_file_ids=part_file_ids
            )
            return token, line_ids, row.id

    return seeder._loop.run_until_complete(_run())


def _all_keys(node: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(node, list):
        for v in node:
            keys |= _all_keys(v)
    return keys


def test_valid_token_renders_only_its_batch(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "vrfq-load")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
        # A second line item that is NOT in the batch — it must not be rendered.
        client.post(f"/api/quotes/{qid}/items")
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])

    # No Authorization header — the token is the only credential.
    res = app_client.get(f"/api/public/vendor-rfq/{token}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rfq_number"] == "RFQ-1001"
    assert body["vendor"]["name"] == "Eloxal Schmidt GmbH"
    assert body["shop"]["name"]
    assert [ln["id"] for ln in body["lines"]] == line_ids
    assert body["lines"][0]["estimator_notes"] == "Schichtdicke 20 µm"
    assert 10 in body["lines"][0]["quantities"]
    assert body["response"] is None


def test_no_price_or_customer_field_reaches_the_vendor(
    seeder: Seeder, app_client: TestClient
) -> None:
    """A vendor is a different counterparty: it must not learn the shop's prices."""
    org, user = _org_admin(seeder, "vrfq-gate")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])
    body = app_client.get(f"/api/public/vendor-rfq/{token}").json()
    leaked = _all_keys(body) & {
        "unit_price",
        "total_price",
        "unit_cost",
        "costing",
        "pricing_items",
        "profit_margin_pct",
        "account",
        "customer",
        "contact_email",
        "recipients",
    }
    assert leaked == set(), f"internal/other-party fields leaked to the vendor: {leaked}"


def test_tampered_garbage_and_revoked_tokens_are_401(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "vrfq-reject")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, _, token_id = _seed_rfq(seeder, app_client, org, qid, [item_id])

    assert app_client.get("/api/public/vendor-rfq/not-a-real-token").status_code == 401
    assert app_client.get(f"/api/public/vendor-rfq/{token[:-3]}xyz").status_code == 401

    async def _revoke() -> None:
        async with AsyncSession(seeder._engine) as session, session.begin():
            row = await session.get(QuoteToken, token_id)
            assert row is not None
            row.revoked_at = datetime.now(UTC)

    seeder._loop.run_until_complete(_revoke())
    assert app_client.get(f"/api/public/vendor-rfq/{token}").status_code == 401


def test_buyer_scope_token_cannot_open_the_vendor_portal(
    seeder: Seeder, app_client: TestClient
) -> None:
    """Cross-scope denial in both directions — a validly signed buyer token is not a
    vendor credential, and a vendor token is not a buyer credential."""
    org, user = _org_admin(seeder, "vrfq-scope")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    secret = _app_secret(app_client)
    forged_buyer = mint_jwt(
        secret,
        token_id=uuid.uuid4(),
        org_id=org,
        quote_id=uuid.UUID(qid),
        scope=QuoteTokenScope.buyer_portal,
    )
    assert app_client.get(f"/api/public/vendor-rfq/{forged_buyer}").status_code == 401

    vendor_token, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])
    assert app_client.get(f"/api/public/quotes/{vendor_token}").status_code == 401


def test_forged_recipient_id_is_401(seeder: Seeder, app_client: TestClient) -> None:
    """A correctly signed token naming a recipient with no matching row is rejected —
    the row, not the signature, is the authority."""
    org, user = _org_admin(seeder, "vrfq-forge")
    with _as_admin(app_client, org, user) as client:
        _quote_with_item(client)
    forged = mint_jwt(
        _app_secret(app_client),
        token_id=uuid.uuid4(),
        org_id=org,
        rfq_recipient_id=uuid.uuid4(),
        scope=QuoteTokenScope.vendor_rfq,
    )
    assert app_client.get(f"/api/public/vendor-rfq/{forged}").status_code == 401


def test_partial_response_submits(seeder: Seeder, app_client: TestClient) -> None:
    """Spec: "Cannot quote this part" makes a partial response first-class."""
    org, user = _org_admin(seeder, "vrfq-partial")
    with _as_admin(app_client, org, user) as client:
        qid, item_a, _ = _quote_with_item(client)
        item_b = client.post(f"/api/quotes/{qid}/items").json()["items"][-1]["id"]
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_a, str(item_b)])

    res = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={
            "currency": "EUR",
            "valid_until": "2026-09-30",
            "notes": "Preise gültig ab Werk.",
            "lines": [
                {
                    "rfq_line_id": line_ids[0],
                    "prices": [{"quantity": 10, "unit_price": "12.5000", "lead_time_days": 7}],
                },
                {"rfq_line_id": line_ids[1], "cannot_quote": True, "notes": "Kein Titan."},
            ],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_late"] is False

    body = app_client.get(f"/api/public/vendor-rfq/{token}").json()
    saved = body["response"]
    assert saved["currency"] == "EUR"
    assert saved["valid_until"] == "2026-09-30"
    by_line = {ln["rfq_line_id"]: ln for ln in saved["lines"]}
    assert by_line[line_ids[0]]["prices"][0]["unit_price"] == "12.5000"
    assert by_line[line_ids[0]]["prices"][0]["lead_time_days"] == 7
    assert by_line[line_ids[1]]["cannot_quote"] is True


def test_late_submission_still_succeeds_and_is_stamped(
    seeder: Seeder, app_client: TestClient
) -> None:
    """Soft cutoff: the portal never closes; lateness is recorded, never refused."""
    org, user = _org_admin(seeder, "vrfq-late")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_id], need_by=yesterday)

    page = app_client.get(f"/api/public/vendor-rfq/{token}").json()
    assert page["is_past_due"] is True  # informational only

    res = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={"lines": [{"rfq_line_id": line_ids[0], "prices": [{"quantity": 10}]}]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_late"] is True


def test_resubmit_replaces_the_prior_answer(seeder: Seeder, app_client: TestClient) -> None:
    """One live response per vendor — a correction must not leave M6.6's Apply
    choosing between two contradictory rows."""
    org, user = _org_admin(seeder, "vrfq-resubmit")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])

    for price in ("9.0000", "11.0000"):
        res = app_client.post(
            f"/api/public/vendor-rfq/{token}/response",
            json={
                "lines": [
                    {"rfq_line_id": line_ids[0], "prices": [{"quantity": 10, "unit_price": price}]}
                ]
            },
        )
        assert res.status_code == 200, res.text

    saved = app_client.get(f"/api/public/vendor-rfq/{token}").json()["response"]
    assert len(saved["lines"]) == 1
    assert [p["unit_price"] for p in saved["lines"][0]["prices"]] == ["11.0000"]
    assert seeder.count("vendor_rfq_response", "org_id = :o", {"o": org}) == 1


def test_line_from_another_batch_is_refused(seeder: Seeder, app_client: TestClient) -> None:
    """The batch's own lines are the allowlist — one vendor cannot write into another
    RFQ by supplying its line id."""
    org, user = _org_admin(seeder, "vrfq-crossbatch")
    with _as_admin(app_client, org, user) as client:
        qid, item_a, _ = _quote_with_item(client)
        item_b = client.post(f"/api/quotes/{qid}/items").json()["items"][-1]["id"]
    token_a, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_a], number="RFQ-A")
    _, lines_b, _ = _seed_rfq(seeder, app_client, org, qid, [str(item_b)], number="RFQ-B")

    res = app_client.post(
        f"/api/public/vendor-rfq/{token_a}/response",
        json={"lines": [{"rfq_line_id": lines_b[0], "prices": []}]},
    )
    assert res.status_code == 422, res.text


def test_cannot_quote_with_prices_is_refused(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "vrfq-contradiction")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])
    res = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={
            "lines": [
                {
                    "rfq_line_id": line_ids[0],
                    "cannot_quote": True,
                    "prices": [{"quantity": 10, "unit_price": "5"}],
                }
            ]
        },
    )
    assert res.status_code == 422, res.text


def test_unrequested_quantity_and_negative_price_are_refused(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "vrfq-badprice")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])

    unrequested = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={"lines": [{"rfq_line_id": line_ids[0], "prices": [{"quantity": 999}]}]},
    )
    assert unrequested.status_code == 422, unrequested.text

    negative = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={
            "lines": [
                {"rfq_line_id": line_ids[0], "prices": [{"quantity": 10, "unit_price": "-1"}]}
            ]
        },
    )
    assert negative.status_code == 422, negative.text


def test_file_download_is_gated_by_the_token_allowlist(
    seeder: Seeder, app_client: TestClient
) -> None:
    """A file not on the token's allowlist is 401 — the credential, not the UI, is the
    gate (this is what makes M6.4's per-vendor redacted-variant choice enforceable)."""
    org, user = _org_admin(seeder, "vrfq-files")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    part_id = seeder.part(org)
    granted = seeder.part_file(org, part_id, "zeichnung.pdf")
    withheld = seeder.part_file(org, part_id, "intern.pdf")

    token, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_id], part_file_ids=[granted])
    assert app_client.get(f"/api/public/vendor-rfq/{token}/files/{withheld}").status_code == 401
    # ``granted`` hangs off a different part than the batch's line, so the second
    # (batch-membership) check must also refuse it — belt and braces, still 401.
    assert app_client.get(f"/api/public/vendor-rfq/{token}/files/{granted}").status_code == 401


def test_no_allowlist_means_no_files_in_the_payload(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "vrfq-nofiles")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_id], part_file_ids=None)
    body = app_client.get(f"/api/public/vendor-rfq/{token}").json()
    assert body["lines"][0]["files"] == []


def test_open_and_submit_are_instrumented(seeder: Seeder, app_client: TestClient) -> None:
    """Usage instrumentation from day one (block scope): the open→submit funnel is
    recorded as domain events, and the load is written to the token access log."""
    org, user = _org_admin(seeder, "vrfq-funnel")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, line_ids, token_id = _seed_rfq(seeder, app_client, org, qid, [item_id])

    app_client.get(f"/api/public/vendor-rfq/{token}")
    app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={"lines": [{"rfq_line_id": line_ids[0], "prices": [{"quantity": 10}]}]},
    )
    assert (
        seeder.count("domain_event", "org_id = :o AND event_type = 'vendor_rfq.opened'", {"o": org})
        == 1
    )
    assert (
        seeder.count(
            "domain_event", "org_id = :o AND event_type = 'vendor_rfq.submitted'", {"o": org}
        )
        == 1
    )
    assert seeder.count("quote_token_access", "quote_token_id = :t", {"t": token_id}) == 1


def test_another_orgs_token_cannot_read_this_orgs_batch(
    seeder: Seeder, app_client: TestClient
) -> None:
    """Tenancy: a valid token from org B, re-signed against org A's id, still reads
    nothing of A — RLS is opened from the *signed* org claim, and the recipient row
    then has to exist in it."""
    org_a, user_a = _org_admin(seeder, "vrfq-tenant-a")
    org_b, _ = _org_admin(seeder, "vrfq-tenant-b")
    with _as_admin(app_client, org_a, user_a) as client:
        qid, item_id, _ = _quote_with_item(client)
    _, _, _ = _seed_rfq(seeder, app_client, org_a, qid, [item_id])

    async def _recipient_id() -> uuid.UUID:
        async with AsyncSession(seeder._engine) as session:
            recipient = (
                await session.execute(
                    select(VendorRfqRecipient).where(VendorRfqRecipient.org_id == org_a)
                )
            ).scalar_one()
            return recipient.id

    recipient_id = seeder._loop.run_until_complete(_recipient_id())
    cross_org = mint_jwt(
        _app_secret(app_client),
        token_id=uuid.uuid4(),
        org_id=org_b,  # claim points at the *other* org
        rfq_recipient_id=recipient_id,
        scope=QuoteTokenScope.vendor_rfq,
    )
    assert app_client.get(f"/api/public/vendor-rfq/{cross_org}").status_code == 401


# --------------------------------------------------------------------------- #
# The RFQ record sheet — template render only (WeasyPrint natives not required)
# --------------------------------------------------------------------------- #
def test_rfq_pdf_template_renders_the_batch_without_any_price() -> None:
    """The sheet is fed the portal payload, so it cannot print more than the page
    the vendor may already read — and it has no price column at all."""
    from app.pdf import render_vendor_rfq_html

    html = render_vendor_rfq_html(
        {
            "rfq_number": "RFQ-1001",
            "need_by_date": "2026-09-01",
            "is_past_due": False,
            "message": "Bitte um Angebot für Eloxieren.",
            "shop": {"name": "Fechner GmbH", "slug": "fechner", "country": "DE", "locale": "de-DE"},
            "vendor": {"name": "Eloxal Schmidt GmbH"},
            "lines": [
                {
                    "id": "line-1",
                    "part_number": "PN-1000",
                    "revision": "B",
                    "description": "Halterung",
                    "process": "Eloxieren",
                    "quantities": [1, 10],
                    "estimator_notes": "Schichtdicke 20 µm",
                    "files": [{"id": "f1", "filename": "zeichnung.pdf", "size_bytes": 12}],
                }
            ],
            "response": None,
        }
    )
    assert "RFQ-1001" in html
    # The shop's internal quote reference is not the vendor's business either.
    assert "Q-2026-0007" not in html
    assert "Eloxal Schmidt GmbH" in html
    assert "PN-1000" in html
    assert "zeichnung.pdf" in html
    # No price/total column, and no platform branding (white-label).
    for forbidden in ("Gesamtpreis", "Stückpreis", "Tolera", "MwSt"):
        assert forbidden not in html, f"vendor sheet must not print {forbidden!r}"


def test_rfq_pdf_template_escapes_untrusted_text() -> None:
    """Autoescaping is on — an estimator note is untrusted text, never markup."""
    from app.pdf import render_vendor_rfq_html

    html = render_vendor_rfq_html(
        {
            "rfq_number": "RFQ-1",
            "need_by_date": None,
            "message": "<script>alert(1)</script>",
            "shop": {"name": "Shop", "slug": "s", "country": "DE", "locale": "de-DE"},
            "vendor": {"name": "V"},
            "lines": [],
            "response": None,
        }
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --------------------------------------------------------------------------- #
# Submission validation — every rejection below would otherwise be a 500 on an
# UNAUTHENTICATED endpoint (the column could not store the value).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("prices", "why"),
    [
        ([{"quantity": 10, "unit_price": "5"}, {"quantity": 10, "unit_price": "7"}], "duplicate"),
        ([{"quantity": 10, "unit_price": "NaN"}], "not-a-number"),
        ([{"quantity": 10, "unit_price": "Infinity"}], "infinite"),
        ([{"quantity": 10, "unit_price": "1E30"}], "out of numeric(14,4) range"),
        ([{"quantity": 10, "unit_price": "1.00005"}], "more than 4 dp — must not be rounded"),
    ],
)
def test_unstorable_prices_are_422_not_500(
    seeder: Seeder, app_client: TestClient, prices: list[dict[str, Any]], why: str
) -> None:
    org, user = _org_admin(seeder, f"vrfq-bad-{abs(hash(why)) % 100000}")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])

    res = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={"lines": [{"rfq_line_id": line_ids[0], "prices": prices}]},
    )
    assert res.status_code == 422, f"{why}: {res.status_code} {res.text}"
    # Nothing was written — validation fully precedes persistence.
    assert seeder.count("vendor_rfq_response", "org_id = :o", {"o": org}) == 0


def test_a_bad_price_on_a_later_line_writes_nothing(seeder: Seeder, app_client: TestClient) -> None:
    """Validation must precede persistence: a valid first line cannot be left behind
    by a rejected second one."""
    org, user = _org_admin(seeder, "vrfq-atomic")
    with _as_admin(app_client, org, user) as client:
        qid, item_a, _ = _quote_with_item(client)
        item_b = client.post(f"/api/quotes/{qid}/items").json()["items"][-1]["id"]
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_a, str(item_b)])

    res = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={
            "lines": [
                {"rfq_line_id": line_ids[0], "prices": [{"quantity": 10, "unit_price": "9.00"}]},
                {"rfq_line_id": line_ids[1], "prices": [{"quantity": 1, "unit_price": "NaN"}]},
            ]
        },
    )
    assert res.status_code == 422, res.text
    assert seeder.count("vendor_rfq_response", "org_id = :o", {"o": org}) == 0


# --------------------------------------------------------------------------- #
# Attachment, PDF and the file-download happy path
# --------------------------------------------------------------------------- #
def _submit_minimal(app_client: TestClient, token: str, line_id: str) -> None:
    res = app_client.post(
        f"/api/public/vendor-rfq/{token}/response",
        json={"lines": [{"rfq_line_id": line_id, "prices": [{"quantity": 10}]}]},
    )
    assert res.status_code == 200, res.text


def test_attachment_upload_replaces_and_sanitises_the_filename(
    seeder: Seeder, app_client: TestClient
) -> None:
    """A crafted name must not escape the object-key prefix or reach a header verbatim."""
    org, user = _org_admin(seeder, "vrfq-attach")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, line_ids, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])
    _submit_minimal(app_client, token, line_ids[0])

    res = app_client.post(
        f"/api/public/vendor-rfq/{token}/response/attachment",
        files={"file": ("../../evil.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert res.status_code == 200, res.text
    assert res.json()["filename"] == "evil.pdf"  # traversal stripped
    body = app_client.get(f"/api/public/vendor-rfq/{token}").json()
    assert body["response"]["attachment_filename"] == "evil.pdf"

    # Re-uploading replaces rather than accumulating.
    again = app_client.post(
        f"/api/public/vendor-rfq/{token}/response/attachment",
        files={"file": ("angebot.pdf", b"%PDF-1.4 second", "application/pdf")},
    )
    assert again.status_code == 200, again.text
    body = app_client.get(f"/api/public/vendor-rfq/{token}").json()
    assert body["response"]["attachment_filename"] == "angebot.pdf"


def test_attachment_requires_a_submitted_response_and_a_valid_token(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_admin(seeder, "vrfq-attach-guard")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])

    # No response yet → 422, not a stray blob.
    early = app_client.post(
        f"/api/public/vendor-rfq/{token}/response/attachment",
        files={"file": ("angebot.pdf", b"x", "application/pdf")},
    )
    assert early.status_code == 422, early.text

    # Garbage token → 401, and the credential is checked before the body is buffered.
    bad = app_client.post(
        "/api/public/vendor-rfq/not-a-real-token/response/attachment",
        files={"file": ("angebot.pdf", b"x", "application/pdf")},
    )
    assert bad.status_code == 401, bad.text


def test_granted_file_on_a_batch_part_downloads_byte_identically(
    seeder: Seeder, app_client: TestClient
) -> None:
    """The allowlist + batch-membership gate must not also block the legitimate case."""
    org, user = _org_admin(seeder, "vrfq-file-ok")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
        part_id = uuid.UUID(client.get(f"/api/quotes/{qid}").json()["items"][0]["part_id"])
        # Uploaded through the authenticated route so a real blob exists to stream.
        uploaded = client.post(
            f"/api/parts/{part_id}/files",
            files={"files": ("zeichnung.pdf", b"%PDF-1.4 drawing", "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        file_id = uuid.UUID(uploaded.json()[0]["id"])
    token, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_id], part_file_ids=[file_id])

    body = app_client.get(f"/api/public/vendor-rfq/{token}").json()
    assert [f["filename"] for f in body["lines"][0]["files"]] == ["zeichnung.pdf"]
    res = app_client.get(f"/api/public/vendor-rfq/{token}/files/{file_id}")
    assert res.status_code == 200, res.text
    assert "zeichnung.pdf" in res.headers["content-disposition"]
    assert res.content == b"%PDF-1.4 drawing"  # byte-identical round trip


def test_rfq_pdf_route_is_token_gated(seeder: Seeder, app_client: TestClient) -> None:
    """401 before anything is rendered; with a valid token it is a PDF (or a clean 503
    where WeasyPrint's native libs are absent, as on a bare dev box)."""
    org, user = _org_admin(seeder, "vrfq-pdf")
    with _as_admin(app_client, org, user) as client:
        qid, item_id, _ = _quote_with_item(client)
    token, _, _ = _seed_rfq(seeder, app_client, org, qid, [item_id])

    assert app_client.get("/api/public/vendor-rfq/nope/pdf").status_code == 401
    res = app_client.get(f"/api/public/vendor-rfq/{token}/pdf")
    assert res.status_code in (200, 503), res.text
    if res.status_code == 200:
        assert res.content.startswith(b"%PDF")
    else:
        assert res.json()["code"] == "pdf_unavailable"
