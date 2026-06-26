"""API/DB tests for the M1.4 quote lifecycle — create, detail, line items,
transitions, trash, and org isolation. Runs against a real RLS-bound Postgres
(``app_client``); the state-machine *rules* are unit-tested in
``test_quote_lifecycle.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models import AccountType, MembershipRole, QuoteStatus
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
ESTIMATOR = [MembershipRole.estimator]


def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _member(seeder: Seeder, org: uuid.UUID, roles: list[MembershipRole], email: str) -> uuid.UUID:
    user = seeder.user(email)
    seeder.membership(user, org, roles)
    return user


def _create(client: TestClient, **body: Any) -> Any:
    return client.post("/api/quotes", json=body)


def _transition(client: TestClient, qid: str, to_status: str, note: str | None = None) -> Any:
    payload: dict[str, Any] = {"to_status": to_status}
    if note is not None:
        payload["note"] = note
    return client.post(f"/api/quotes/{qid}/transition", json=payload)


# --------------------------------------------------------------------------- #
# Create + numbering + detail
# --------------------------------------------------------------------------- #
def test_create_opens_draft_with_tracker(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Fechner GmbH")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = _create(app_client, account_id=str(acct))
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "draft"
    assert body["number"] == "1"
    assert body["account_id"] == str(acct)
    assert body["currency"] == "EUR"
    assert body["items"] == []
    assert body["workflow"]["rfq_received_at"] is not None
    assert body["workflow"]["quote_started_at"] is None
    assert body["workflow"]["incomplete_item_count"] == 0
    assert set(body["allowed_transitions"]) == {"sent", "no_quote", "on_hold", "cancelled"}


def test_quote_numbers_are_sequential_per_org(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b, admin_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        a1 = _create(app_client).json()["number"]
        a2 = _create(app_client).json()["number"]
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        b1 = _create(app_client).json()["number"]
    assert (a1, a2, b1) == ("1", "2", "1")  # per-org counter, gaps allowed


def test_create_rejects_vendor_account(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    vendor = seeder.account(org, "Supplier AG", type=AccountType.vendor)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = _create(app_client, account_id=str(vendor))
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_account"


def test_create_rejects_unknown_account(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = _create(app_client, account_id=str(uuid.uuid4()))
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_account"


# --------------------------------------------------------------------------- #
# Line items
# --------------------------------------------------------------------------- #
def test_add_root_item_builds_line_item_and_marks_started(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client).json()["id"]
        first = app_client.post(f"/api/quotes/{qid}/items")
        second = app_client.post(f"/api/quotes/{qid}/items").json()
    body = first.json()
    assert first.status_code == 201
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["position"] == 1
    assert item["workflow_status"] == "not_started"
    assert item["part_id"] is not None  # part → component → quote_item all created
    assert item["was_won"] is False
    assert body["workflow"]["quote_started_at"] is not None  # estimator work began
    assert body["workflow"]["incomplete_item_count"] == 1
    assert [i["position"] for i in second["items"]] == [1, 2]
    assert second["workflow"]["incomplete_item_count"] == 2


# --------------------------------------------------------------------------- #
# Lifecycle transitions (the acceptance headline)
# --------------------------------------------------------------------------- #
def test_legal_transition_succeeds_illegal_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Acme")
    contact = seeder.contact(org, acct, "buyer@acme.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client, account_id=str(acct), contact_id=str(contact)).json()["id"]
        sent = _transition(app_client, qid, "sent")
        back_to_draft = _transition(app_client, qid, "draft")  # sent → draft is illegal
        to_no_quote = _transition(app_client, qid, "no_quote")  # sent → no_quote is illegal
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["sent_at"] is not None
    assert back_to_draft.status_code == 409
    assert back_to_draft.json()["code"] == "invalid_transition"
    assert to_no_quote.status_code == 409


def test_send_requires_contact(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Acme")
    contact = seeder.contact(org, acct, "buyer@acme.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client, account_id=str(acct)).json()["id"]  # no contact yet
        blocked = _transition(app_client, qid, "sent")
        app_client.patch(f"/api/quotes/{qid}", json={"contact_id": str(contact)})
        ok = _transition(app_client, qid, "sent")
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "missing_contact"
    assert ok.status_code == 200
    assert ok.json()["status"] == "sent"


def test_on_hold_returns_to_draft(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client).json()["id"]
        held = _transition(app_client, qid, "on_hold")
        wrong = _transition(app_client, qid, "sent")  # may only return to prior (draft)
        restored = _transition(app_client, qid, "draft")
    assert held.json()["status"] == "on_hold"
    assert held.json()["allowed_transitions"] == ["draft"]
    assert wrong.status_code == 409
    assert restored.json()["status"] == "draft"


def test_on_hold_from_sent_returns_to_sent(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Acme")
    contact = seeder.contact(org, acct, "buyer@acme.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client, account_id=str(acct), contact_id=str(contact)).json()["id"]
        _transition(app_client, qid, "sent")
        held = _transition(app_client, qid, "on_hold")
        restored = _transition(app_client, qid, "sent")
    assert held.json()["allowed_transitions"] == ["sent"]
    assert restored.json()["status"] == "sent"


def test_expired_quote_can_still_be_won(app_client: TestClient, seeder: Seeder) -> None:
    """Soft-expiry (spec + DACH): acceptance is not blocked past expiry."""
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Acme")
    contact = seeder.contact(org, acct, "buyer@acme.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client, account_id=str(acct), contact_id=str(contact)).json()["id"]
        _transition(app_client, qid, "sent")
        _transition(app_client, qid, "expired")
        won = _transition(app_client, qid, "won")
    assert won.status_code == 200
    assert won.json()["status"] == "won"


def test_status_events_record_each_transition(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Acme")
    contact = seeder.contact(org, acct, "buyer@acme.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client, account_id=str(acct), contact_id=str(contact)).json()["id"]
        _transition(app_client, qid, "sent")
        _transition(app_client, qid, "lost", note="Lost to incumbent")
    assert seeder.status_events(org, uuid.UUID(qid)) == [
        (None, "draft", None),
        ("draft", "sent", None),
        ("sent", "lost", "Lost to incumbent"),
    ]


def test_unhold_from_sent_preserves_original_sent_at(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Un-holding a Sent→On-Hold quote restores Sent without **re-stamping** the
    original ``sent_at`` (CodeRabbit 2026-06-26 — un-hold is a restore, not a re-send)."""
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Acme")
    contact = seeder.contact(org, acct, "buyer@acme.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client, account_id=str(acct), contact_id=str(contact)).json()["id"]
        original_sent_at = _transition(app_client, qid, "sent").json()["sent_at"]
        _transition(app_client, qid, "on_hold")
        restored = _transition(app_client, qid, "sent")
    assert restored.status_code == 200
    assert restored.json()["status"] == "sent"
    assert restored.json()["sent_at"] == original_sent_at  # not re-stamped


def test_unhold_to_sent_skips_contact_precondition(app_client: TestClient, seeder: Seeder) -> None:
    """Restoring On-Hold→Sent must not re-run the send contact-precondition: a quote
    that was validly sent and is now on hold (even without a current contact) can be
    un-held back to Sent (CodeRabbit 2026-06-26)."""
    org, admin = _org_admin(seeder)
    qid = seeder.quote(
        org,
        "1",
        status=QuoteStatus.on_hold,
        status_before_hold=QuoteStatus.sent,  # came from sent
        contact_id=None,  # no current contact — must NOT block the restore
    )
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        restored = _transition(app_client, str(qid), "sent")
    assert restored.status_code == 200
    assert restored.json()["status"] == "sent"


# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #
def test_cancel_requires_delete_permission(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    estimator = _member(seeder, org, ESTIMATOR, "est@org-a.example")
    with authed(app_client, user_id=estimator, org_id=org, roles=ESTIMATOR):
        qid = _create(app_client).json()["id"]  # estimator can create (quote_edit)
        forbidden = _transition(app_client, qid, "cancelled")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        ok = _transition(app_client, qid, "cancelled")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden"
    assert ok.status_code == 200
    assert ok.json()["status"] == "cancelled"


def test_trash_requires_delete_permission(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    estimator = _member(seeder, org, ESTIMATOR, "est@org-a.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client).json()["id"]
    with authed(app_client, user_id=estimator, org_id=org, roles=ESTIMATOR):
        res = app_client.post(f"/api/quotes/{qid}/trash")
    assert res.status_code == 403


def test_sent_quote_is_locked_for_edits(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    acct = seeder.account(org, "Acme")
    contact = seeder.contact(org, acct, "buyer@acme.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client, account_id=str(acct), contact_id=str(contact)).json()["id"]
        _transition(app_client, qid, "sent")
        locked = app_client.patch(f"/api/quotes/{qid}", json={"rfq_number": "X"})
        no_item = app_client.post(f"/api/quotes/{qid}/items")
    assert locked.status_code == 409
    assert locked.json()["code"] == "quote_locked"
    assert no_item.status_code == 409


# --------------------------------------------------------------------------- #
# Trash / restore
# --------------------------------------------------------------------------- #
def test_trash_hides_from_list_and_blocks_transition(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client).json()["id"]
        trashed = app_client.post(f"/api/quotes/{qid}/trash").json()
        listed = app_client.post("/api/quotes/search", json={}).json()
        blocked = _transition(app_client, qid, "sent")
        restored = app_client.post(f"/api/quotes/{qid}/restore").json()
        listed_again = app_client.post("/api/quotes/search", json={}).json()
    assert trashed["trashed"] is True
    assert qid not in {r["id"] for r in listed["rows"]}
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "quote_trashed"
    assert restored["trashed"] is False
    assert qid in {r["id"] for r in listed_again["rows"]}


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #
def test_cross_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_admin(seeder, "org-a")
    org_b, admin_b = _org_admin(seeder, "org-b")
    acct_b = seeder.account(org_b, "B Co")
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        qid_b = _create(app_client, account_id=str(acct_b)).json()["id"]
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        got = app_client.get(f"/api/quotes/{qid_b}")
        trans = _transition(app_client, qid_b, "sent")
        cross_ref = _create(app_client, account_id=str(acct_b))  # B's account invisible to A
    assert got.status_code == 404
    assert trans.status_code == 404
    assert cross_ref.status_code == 422
    assert cross_ref.json()["code"] == "invalid_account"


# --------------------------------------------------------------------------- #
# Golden thread
# --------------------------------------------------------------------------- #
def test_golden_thread_quote_and_root_item(app_client: TestClient, seeder: Seeder) -> None:
    """Opens the M1 golden thread: a Fechner draft quote + its root line item, ready
    for the rest of M1 to price."""
    org, admin = _org_admin(seeder, "fechner")
    acct = seeder.account(org, "Fechner GmbH")
    contact = seeder.contact(org, acct, "rfq@fechner.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        created = _create(
            app_client,
            account_id=str(acct),
            contact_id=str(contact),
            rfq_number="D-783423",
        ).json()
        with_item = app_client.post(f"/api/quotes/{created['id']}/items").json()
    assert created["number"] == "1"
    assert created["rfq_number"] == "D-783423"
    assert created["status"] == "draft"
    assert len(with_item["items"]) == 1
    assert with_item["status"] == "draft"


# --------------------------------------------------------------------------- #
# Same-org member guard (salesperson / estimator) + edit
# --------------------------------------------------------------------------- #
def test_create_rejects_non_member_estimator(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    outsider = seeder.user("outsider@elsewhere.example")  # exists, but not a member here
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        res = _create(app_client, estimator_id=str(outsider))
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_estimator"


def test_create_with_assigned_estimator(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    estimator = _member(seeder, org, ESTIMATOR, "est@org-a.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        body = _create(app_client, estimator_id=str(estimator)).json()
    assert body["estimator_id"] == str(estimator)


def test_patch_reassigns_people_and_fields(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    sales = _member(seeder, org, [MembershipRole.salesperson], "sales@org-a.example")
    acct = seeder.account(org, "Acme")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client).json()["id"]
        patched = app_client.patch(
            f"/api/quotes/{qid}",
            json={"salesperson_id": str(sales), "account_id": str(acct), "rfq_number": "RFQ-9"},
        ).json()
    assert patched["salesperson_id"] == str(sales)
    assert patched["account_id"] == str(acct)
    assert patched["rfq_number"] == "RFQ-9"


def test_patch_rejects_non_member_salesperson(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_admin(seeder)
    outsider = seeder.user("outsider2@elsewhere.example")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client).json()["id"]
        res = app_client.patch(f"/api/quotes/{qid}", json={"salesperson_id": str(outsider)})
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_salesperson"


def test_trashed_quote_is_not_editable(app_client: TestClient, seeder: Seeder) -> None:
    """A trashed quote rejects edits and line-item adds — it must be restored first
    (CodeRabbit 2026-06-26; matches the transition/list paths)."""
    org, admin = _org_admin(seeder)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        qid = _create(app_client).json()["id"]
        app_client.post(f"/api/quotes/{qid}/trash")
        patched = app_client.patch(f"/api/quotes/{qid}", json={"rfq_number": "X"})
        added = app_client.post(f"/api/quotes/{qid}/items")
    assert patched.status_code == 409
    assert patched.json()["code"] == "quote_locked"
    assert added.status_code == 409
    assert added.json()["code"] == "quote_locked"


def test_quote_inherits_org_currency(app_client: TestClient, seeder: Seeder) -> None:
    """A new quote carries its org's currency — CHF for a Swiss org, not the bare
    EUR default (DACH money convention; CodeRabbit 2026-06-26)."""
    org = seeder.org("helvetia", currency="CHF", country="CH")
    admin = seeder.user("admin@helvetia.example")
    seeder.membership(admin, org, ADMIN)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        body = _create(app_client).json()
    assert body["currency"] == "CHF"
