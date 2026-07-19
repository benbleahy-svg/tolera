"""M6.1 — the Dashboard work queue: merged sources, urgency ordering,
explainability, recents, KPI row, and tenancy.

Spec ``#newscope`` §2. The block's acceptance criteria drive these tests
one-for-one:

* the queue merges all five source types for the signed-in user/role;
* reordering the org weights re-sorts deterministically, and each row carries
  its per-factor contribution;
* the same seed yields a stable ordering (nothing time-of-render beyond
  ``days_to_due``);
* a cross-org row is labelled (and is the only cross-org source — mentions,
  per DECISIONS 2026-06-19 E4-a);
* the "Workflows" saved view still renders the classic table.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole, QuoteStatus
from tests.conftest import Seeder, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]
ESTIMATOR = [MembershipRole.estimator]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _org_user(
    seeder: Seeder, slug: str, *, roles: list[MembershipRole] | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"user@{slug}.example")
    seeder.membership(user, org, roles or ADMIN)
    return org, user


def _due(days_from_today: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days_from_today)


def _plant_task(
    seeder: Seeder, org: uuid.UUID, user: uuid.UUID, *, quote_id: uuid.UUID | None = None
) -> uuid.UUID:
    task_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO task (id, org_id, quote_id, assignee_id, created_by, message, status) "
        "VALUES (:id, :org, :quote, :user, :user, 'Prüfen', 'open')",
        {"id": task_id, "org": org, "quote": quote_id, "user": user},
    )
    return task_id


def _plant_review_item(
    client: TestClient, seeder: Seeder, org: uuid.UUID, user: uuid.UUID, quote_id: uuid.UUID
) -> uuid.UUID:
    """One open review item assigned to *user*, produced by the real M3.8
    generator (a rule that matches any part with no print) so the row under test
    is shaped exactly like a production one. Each call adds its own line item, so
    calling it N times leaves N unresolved items on the quote."""
    line_item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
    component_id = str(line_item["root_component_id"])
    name = f"Fehlende Zeichnung {uuid.uuid4().hex[:8]}"
    rules = [
        {
            "uuid": str(uuid.uuid4()),
            "name": name,
            "description": "",
            "logical_operator": "OR",
            "signals": [
                {
                    "logical_operator": "AND",
                    "groups": [
                        {
                            "document_path": "files",
                            "logical_operator": "AND",
                            "queries": [
                                {
                                    "field_name": ["has_print"],
                                    "operator": "equals",
                                    "value": False,
                                    "value_type": "boolean",
                                    "filter_type": "boolean",
                                    "units": None,
                                }
                            ],
                            "count_query": None,
                        }
                    ],
                }
            ],
            "resolutions": [
                {"type": "RESOLVE", "parameters": [], "custom_label": "Kunde kontaktiert"}
            ],
            "default_assignee_id": None,
        }
    ]
    res = client.post("/api/rules/import", json={"rules_json": json.dumps(rules)})
    assert res.status_code == 200, res.text
    created = client.post(f"/api/components/{component_id}/review-items/generate")
    assert created.status_code in (200, 201), created.text
    item_id = uuid.UUID(str(created.json()[0]["id"]))
    seeder.sql(
        "UPDATE review_item SET assignee_id = :user WHERE id = :id",
        {"user": user, "id": item_id},
    )
    return item_id


def _plant_mention(
    seeder: Seeder, org: uuid.UUID, user: uuid.UUID, *, quote_id: uuid.UUID | None = None
) -> uuid.UUID:
    note_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO notification (id, org_id, user_id, kind, payload) "
        "VALUES (:id, :org, :user, 'mention', :payload)",
        {
            "id": note_id,
            "org": org,
            "user": user,
            "payload": json.dumps({"quote_id": str(quote_id)} if quote_id else {}),
        },
    )
    return note_id


def _price_quote(client: TestClient, seeder: Seeder, quote_id: uuid.UUID, total: str) -> None:
    """Give a quote a value by planting a priced quantity on its single item."""
    item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
    seeder.sql(
        "UPDATE component_quantity SET total_price = :total WHERE component_id = :cid",
        {"total": Decimal(total), "cid": uuid.UUID(str(item["root_component_id"]))},
    )


def _rows(client: TestClient) -> list[dict[str, Any]]:
    res = client.get("/api/work-queue")
    assert res.status_code == 200, res.text
    rows: list[dict[str, Any]] = res.json()["rows"]
    return rows


# --------------------------------------------------------------------------- #
# Source merge
# --------------------------------------------------------------------------- #
def test_queue_merges_every_source_for_the_signed_in_user(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_user(seeder, "merge-org")
    quote = seeder.quote(org, "1001", estimator_id=user, due_date=_due(2))
    _plant_task(seeder, org, user, quote_id=quote)
    _plant_mention(seeder, org, user, quote_id=quote)

    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        _plant_review_item(app_client, seeder, org, user, quote)
        rows = _rows(app_client)

    assert {r["source"] for r in rows} == {"quote_action", "task", "review_item", "mention"}
    assert all(r["deep_link"].startswith("/quotes/") for r in rows)


def test_only_my_rows_surface(app_client: TestClient, seeder: Seeder) -> None:
    """Someone else's quote / task / review item is not my work."""
    org, me = _org_user(seeder, "mine-org")
    other = seeder.user("colleague@mine-org.example")
    seeder.membership(other, org, ADMIN)
    theirs = seeder.quote(org, "2001", estimator_id=other, due_date=_due(1))
    _plant_task(seeder, org, other, quote_id=theirs)
    with authed(app_client, user_id=other, org_id=org, roles=ADMIN):
        _plant_review_item(app_client, seeder, org, other, theirs)

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        assert _rows(app_client) == []


def test_sent_and_closed_quotes_are_not_my_action(app_client: TestClient, seeder: Seeder) -> None:
    """A sent quote is waiting on the *customer*; a won/lost one on nobody."""
    org, me = _org_user(seeder, "status-org")
    for i, status in enumerate((QuoteStatus.sent, QuoteStatus.won, QuoteStatus.lost)):
        seeder.quote(org, f"30{i}", estimator_id=me, status=status, due_date=_due(1))
    open_quote = seeder.quote(org, "3099", estimator_id=me, due_date=_due(1))

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        rows = _rows(app_client)

    assert [r["id"] for r in rows] == [str(open_quote)]


def test_resolved_work_leaves_the_queue(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "resolved-org")
    # A draft owned by nobody: only the (resolved) task + review item could surface.
    quote = seeder.quote(org, "4001")
    task = _plant_task(seeder, org, me, quote_id=quote)
    seeder.sql("UPDATE task SET status = 'resolved' WHERE id = :id", {"id": task})

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        item = _plant_review_item(app_client, seeder, org, me, quote)
        resolved = app_client.post(
            f"/api/review-items/{item}/resolve", json={"resolution_type": "RESOLVE"}
        )
        assert resolved.status_code == 200, resolved.text
        assert _rows(app_client) == []


def test_read_mentions_leave_the_queue(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "readmention-org")
    note = _plant_mention(seeder, org, me)
    seeder.sql("UPDATE notification SET read_at = now() WHERE id = :id", {"id": note})

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        assert _rows(app_client) == []


def test_vendor_rfq_source_is_flagged_off_until_m62(app_client: TestClient, seeder: Seeder) -> None:
    """The fifth source's entities arrive in M6.2 — the flag exists, defaults
    off, and turning it on is inert rather than an error."""
    org, me = _org_user(seeder, "vendorflag-org")
    seeder.quote(org, "5001", estimator_id=me, due_date=_due(1))

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        settings = app_client.get("/api/work-queue/settings").json()
        assert settings["vendor_rfq_queue_enabled"] is False
        enabled = app_client.put(
            "/api/work-queue/settings", json={"vendor_rfq_queue_enabled": True}
        )
        assert enabled.status_code == 200
        rows = _rows(app_client)

    assert {r["source"] for r in rows} == {"quote_action"}


# --------------------------------------------------------------------------- #
# Urgency ordering + explainability
# --------------------------------------------------------------------------- #
def test_ordering_matches_the_hand_computed_urgency(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "order-org")
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        # due in 4 days, unpriced, no flags        -> 0.25*0.40           = 0.1000
        low = seeder.quote(org, "6001", estimator_id=me, due_date=_due(4))
        # due in 2 days, unpriced, no flags        -> 0.50*0.40           = 0.2000
        mid = seeder.quote(org, "6002", estimator_id=me, due_date=_due(2))
        # overdue 5 days, unpriced, no flags       -> 1.50*0.40           = 0.6000
        high = seeder.quote(org, "6003", estimator_id=me, due_date=_due(-5))
        rows = _rows(app_client)

    assert [r["id"] for r in rows] == [str(high), str(mid), str(low)]
    assert [r["urgency"] for r in rows] == ["0.6000", "0.2000", "0.1000"]


def test_value_band_and_flags_enter_the_score(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "value-org")
    account = seeder.account(org, "Schlüsselkunde GmbH")
    seeder.sql("UPDATE account SET is_vip = true WHERE id = :id", {"id": account})
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        quote = seeder.quote(org, "7001", estimator_id=me, account_id=account, due_date=_due(2))
        _price_quote(app_client, seeder, quote, "60000.00")  # -> band 3 of 4
        rows = _rows(app_client)

    # due 0.5*0.40 = 0.2000 · value 0.75*0.25 = 0.1875 · flags (VIP) 1/3*0.10 = 0.0333
    assert rows[0]["urgency"] == "0.4208"
    factors = {f["key"]: f for f in rows[0]["factors"]}
    assert factors["value"]["raw"] == "3"
    assert factors["flags"]["raw"] == "1"
    assert factors["due"]["contribution"] == "0.2000"


def test_every_row_is_explainable(app_client: TestClient, seeder: Seeder) -> None:
    """The hover panel's contract: four factors, contributions summing to the
    score (spec ``#newscope`` "show the contributing factors on hover")."""
    org, me = _org_user(seeder, "explain-org")
    quote = seeder.quote(org, "8001", estimator_id=me, due_date=_due(3))

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        _plant_review_item(app_client, seeder, org, me, quote)
        rows = _rows(app_client)

    for row in rows:
        assert [f["key"] for f in row["factors"]] == ["due", "value", "unresolved", "flags"]
        total = sum(Decimal(f["contribution"]) for f in row["factors"])
        assert total == Decimal(row["urgency"])
        assert all({"raw", "normalized", "weight"} <= set(f) for f in row["factors"])


def test_reason_chips_say_why_the_row_surfaced(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "chips-org")
    quote = seeder.quote(org, "9001", estimator_id=me, due_date=_due(-3))

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        for _ in range(3):
            _plant_review_item(app_client, seeder, org, me, quote)
        rows = _rows(app_client)

    quote_row = next(r for r in rows if r["source"] == "quote_action")
    chips = {c["key"]: c["params"] for c in quote_row["reason_chips"]}
    assert chips["work_queue.chip.overdue"] == {"count": 3}
    assert chips["work_queue.chip.unresolved"] == {"count": 3}
    # Chips are i18n keys + params — no server-rendered prose crosses the wire.
    assert all(c["key"].startswith("work_queue.chip.") for c in quote_row["reason_chips"])


def test_weight_change_re_sorts_deterministically(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "weights-org")
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        near = seeder.quote(org, "1101", estimator_id=me, due_date=_due(1))
        rich = seeder.quote(org, "1102", estimator_id=me, due_date=_due(30))
        _price_quote(app_client, seeder, rich, "900000.00")  # top band

        assert [r["id"] for r in _rows(app_client)] == [str(near), str(rich)]

        res = app_client.put(
            "/api/work-queue/settings",
            json={
                "weight_due": "0.1",
                "weight_value": "0.9",
                "weight_unresolved": "0",
                "weight_flags": "0",
            },
        )
        assert res.status_code == 200, res.text
        assert [r["id"] for r in _rows(app_client)] == [str(rich), str(near)]
        # The weights the score used are echoed back with the queue.
        assert app_client.get("/api/work-queue").json()["weights"]["weight_value"] == "0.9000"


def test_ordering_is_stable_across_calls(app_client: TestClient, seeder: Seeder) -> None:
    """Same seed, same order — including for the all-zero rows a naive
    implementation would leave to the database's whim."""
    org, me = _org_user(seeder, "stable-org")
    for i in range(6):
        seeder.quote(org, f"120{i}", estimator_id=me)  # no due date -> score 0

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        first = [r["id"] for r in _rows(app_client)]
        second = [r["id"] for r in _rows(app_client)]

    assert first == second
    assert len(first) == 6


def test_settings_rejects_a_negative_weight(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "negweight-org")
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        res = app_client.put("/api/work-queue/settings", json={"weight_due": "-0.5"})
    assert res.status_code == 422


def test_settings_write_needs_settings_edit(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "settingsauth-org", roles=ESTIMATOR)
    with authed(app_client, user_id=me, org_id=org, roles=ESTIMATOR):
        assert app_client.get("/api/work-queue/settings").status_code == 200
        assert app_client.put("/api/work-queue/settings", json={"weight_due": "1"}).status_code in (
            403,
        )


# --------------------------------------------------------------------------- #
# Tenancy — the queue is org-scoped; only mentions cross orgs (E4-a)
# --------------------------------------------------------------------------- #
def test_another_orgs_work_never_surfaces(app_client: TestClient, seeder: Seeder) -> None:
    org_a, me = _org_user(seeder, "tenant-a")
    org_b = seeder.org("tenant-b")
    other = seeder.user("stranger@tenant-b.example")
    seeder.membership(other, org_b, ADMIN)
    seeder.quote(org_b, "1301", estimator_id=other, due_date=_due(1))
    _plant_task(seeder, org_b, other)

    with authed(app_client, user_id=me, org_id=org_a, roles=ADMIN):
        assert _rows(app_client) == []


def test_cross_org_mention_is_labelled(app_client: TestClient, seeder: Seeder) -> None:
    """DECISIONS 2026-06-19 (E4-a): cross-org notifications are labelled +
    switch-on-select. The row names its org so the UI can label it and route the
    switch; nothing else about org B leaks."""
    org_a, me = _org_user(seeder, "home-org")
    org_b = seeder.org("other-org")
    seeder.membership(me, org_b, ADMIN)
    _plant_mention(seeder, org_b, me)

    with authed(app_client, user_id=me, org_id=org_a, roles=ADMIN):
        rows = _rows(app_client)

    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "mention"
    assert row["cross_org"] is True
    assert row["org_slug"] == "other-org"
    assert row["org_id"] == str(org_b)


def test_mention_from_an_org_i_left_does_not_surface(
    app_client: TestClient, seeder: Seeder
) -> None:
    org_a, me = _org_user(seeder, "current-org")
    org_b = seeder.org("former-org")
    seeder.membership(me, org_b, ADMIN)
    seeder.sql(
        "UPDATE user_org_membership SET status = 'disabled' WHERE user_id = :u AND org_id = :o",
        {"u": me, "o": org_b},
    )
    _plant_mention(seeder, org_b, me)

    with authed(app_client, user_id=me, org_id=org_a, roles=ADMIN):
        assert _rows(app_client) == []


def test_home_org_mention_is_not_labelled_cross_org(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "samemention-org")
    _plant_mention(seeder, org, me)

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        rows = _rows(app_client)

    assert rows[0]["cross_org"] is False


# --------------------------------------------------------------------------- #
# Recently opened
# --------------------------------------------------------------------------- #
def test_recents_keeps_the_last_eight_most_recent_first(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, me = _org_user(seeder, "recents-org")
    quotes = [seeder.quote(org, f"140{i}") for i in range(9)]

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        for quote in quotes:
            res = app_client.post(
                "/api/work-queue/recents", json={"entity_type": "quote", "entity_id": str(quote)}
            )
            assert res.status_code == 204, res.text
        recents = app_client.get("/api/work-queue/recents").json()["rows"]

    assert len(recents) == 8
    assert [r["entity_id"] for r in recents] == [str(q) for q in reversed(quotes[1:])]
    assert recents[0]["label"] == "1408"
    assert recents[0]["status"] == "draft"


def test_reopening_moves_a_recent_to_the_front_without_duplicating(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, me = _org_user(seeder, "reopen-org")
    first = seeder.quote(org, "1501")
    second = seeder.quote(org, "1502")

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        for quote in (first, second, first):
            app_client.post(
                "/api/work-queue/recents", json={"entity_type": "quote", "entity_id": str(quote)}
            )
        recents = app_client.get("/api/work-queue/recents").json()["rows"]

    assert [r["entity_id"] for r in recents] == [str(first), str(second)]


def test_recents_are_per_user(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "recentsuser-org")
    other = seeder.user("other@recentsuser-org.example")
    seeder.membership(other, org, ADMIN)
    quote = seeder.quote(org, "1601")

    with authed(app_client, user_id=other, org_id=org, roles=ADMIN):
        app_client.post(
            "/api/work-queue/recents", json={"entity_type": "quote", "entity_id": str(quote)}
        )
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        assert app_client.get("/api/work-queue/recents").json()["rows"] == []


def test_recents_reject_an_entity_that_does_not_exist(
    app_client: TestClient, seeder: Seeder
) -> None:
    """A client must not be able to plant arbitrary ids (or another org's) into
    its own strip."""
    org_a, me = _org_user(seeder, "recentsghost-org")
    org_b = seeder.org("recentsother-org")
    stranger = seeder.user("stranger@recentsother-org.example")
    seeder.membership(stranger, org_b, ADMIN)
    other_orgs_quote = seeder.quote(org_b, "2201")

    with authed(app_client, user_id=me, org_id=org_a, roles=ADMIN):
        missing = app_client.post(
            "/api/work-queue/recents",
            json={"entity_type": "quote", "entity_id": str(uuid.uuid4())},
        )
        foreign = app_client.post(
            "/api/work-queue/recents",
            json={"entity_type": "quote", "entity_id": str(other_orgs_quote)},
        )
        assert app_client.get("/api/work-queue/recents").json()["rows"] == []

    assert missing.status_code == 404
    assert foreign.status_code == 404


def test_recents_are_pruned_so_the_table_is_not_a_browsing_history(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, me = _org_user(seeder, "recentsprune-org")
    quotes = [seeder.quote(org, f"23{i:02d}") for i in range(30)]

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        for quote in quotes:
            app_client.post(
                "/api/work-queue/recents", json={"entity_type": "quote", "entity_id": str(quote)}
            )
        recents = app_client.get("/api/work-queue/recents").json()["rows"]

    assert len(recents) == 8  # the strip
    stored = seeder.count("recent_view")
    assert stored <= 24  # the retained tail, not all 30


def test_recents_carry_a_type_correct_deep_link(app_client: TestClient, seeder: Seeder) -> None:
    """A part entry must not route into the quotes section."""
    org, me = _org_user(seeder, "recentslink-org")
    quote = seeder.quote(org, "2401")
    part = seeder.part(org)

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        for entity_type, entity_id in (("quote", quote), ("part", part)):
            res = app_client.post(
                "/api/work-queue/recents",
                json={"entity_type": entity_type, "entity_id": str(entity_id)},
            )
            assert res.status_code == 204, res.text
        rows = app_client.get("/api/work-queue/recents").json()["rows"]

    links = {r["entity_type"]: r["deep_link"] for r in rows}
    assert links == {"quote": f"/quotes/{quote}", "part": f"/parts/{part}"}


def test_recents_reject_an_unknown_entity_type(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "recentstype-org")
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/work-queue/recents",
            json={"entity_type": "invoice", "entity_id": str(uuid.uuid4())},
        )
    assert res.status_code == 422


def test_offered_expedite_tiers_are_not_an_urgency_flag(
    app_client: TestClient, seeder: Seeder
) -> None:
    """``quote.expedite_tiers`` is the *offered* expedite menu (every org ships
    two defaults, and Apply-to-all writes them onto the quote). Treating it as
    "the customer is paying for speed" would flag ordinary jobs as rush jobs and
    say so on the chip — the flag needs an accepted tier, not an offered one."""
    org, me = _org_user(seeder, "expedite-org")
    quote = seeder.quote(org, "1901", estimator_id=me, due_date=_due(2))
    seeder.sql(
        "UPDATE quote SET expedite_tiers = :tiers WHERE id = :id",
        {
            "tiers": json.dumps(
                {"standard_lead_time_days": 25, "tiers": [{"days_faster": 5, "markup_pct": "25"}]}
            ),
            "id": quote,
        },
    )

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        rows = _rows(app_client)

    factors = {f["key"]: f for f in rows[0]["factors"]}
    assert factors["flags"]["raw"] == "0"
    assert not [c for c in rows[0]["reason_chips"] if c["key"].endswith("expedite")]


def test_weight_above_the_column_bound_is_a_422_not_a_500(
    app_client: TestClient, seeder: Seeder
) -> None:
    """``numeric(6,4)`` tops out below 100 — reject at the edge rather than let
    the flush raise NumericValueOutOfRange."""
    org, me = _org_user(seeder, "weightbound-org")
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        assert (
            app_client.put("/api/work-queue/settings", json={"weight_due": "500"}).status_code
            == 422
        )
        assert (
            app_client.put("/api/work-queue/settings", json={"weight_due": "99"}).status_code == 200
        )


def test_chips_pass_i18next_count_so_german_can_singularise(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, me = _org_user(seeder, "plural-org")
    seeder.quote(org, "1951", estimator_id=me, due_date=_due(-1))

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        rows = _rows(app_client)

    chip = next(c for c in rows[0]["reason_chips"] if c["key"].endswith("overdue"))
    # ``count`` (i18next's plural selector), not a bare ``days``.
    assert chip["params"] == {"count": 1}


# --------------------------------------------------------------------------- #
# Manager KPI row
# --------------------------------------------------------------------------- #
def test_kpi_row_counts_open_due_and_win_rate(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "kpi-org")
    seeder.quote(org, "1701", due_date=_due(3))  # open + due this week
    seeder.quote(org, "1702", due_date=_due(20))  # open, not this week
    won = seeder.quote(org, "1703", status=QuoteStatus.won)
    lost = seeder.quote(org, "1704", status=QuoteStatus.lost)
    for quote, status in ((won, "won"), (lost, "lost")):
        seeder.sql(
            "INSERT INTO quote_status_event (id, org_id, quote_id, from_status, to_status) "
            "VALUES (:id, :org, :quote, 'sent', :status)",
            {"id": uuid.uuid4(), "org": org, "quote": quote, "status": status},
        )

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        kpis = app_client.get("/api/work-queue/kpis").json()

    assert kpis["open_quotes"] == 2
    assert kpis["due_this_week"] == 1
    assert kpis["win_rate_30d_pct"] == "50.0"


def test_win_rate_counts_each_quote_once_by_its_latest_outcome(
    app_client: TestClient, seeder: Seeder
) -> None:
    """A quote won, reopened, then lost inside the window is one loss — not a
    50% win rate off a single quote."""
    org, me = _org_user(seeder, "winrate-org")
    quote = seeder.quote(org, "2501", status=QuoteStatus.lost)
    for offset, to_status in ((5, "won"), (1, "lost")):
        seeder.sql(
            "INSERT INTO quote_status_event "
            "(id, org_id, quote_id, from_status, to_status, created_at) "
            "VALUES (:id, :org, :quote, 'sent', :status, now() - make_interval(days => :offset))",
            {
                "id": uuid.uuid4(),
                "org": org,
                "quote": quote,
                "status": to_status,
                "offset": offset,
            },
        )

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        kpis = app_client.get("/api/work-queue/kpis").json()

    assert kpis["win_rate_30d_pct"] == "0.0"


def test_kpi_counts_agree_with_the_workflows_view(app_client: TestClient, seeder: Seeder) -> None:
    """The glance row and the table it links to must mean the same thing by
    "open" — an on-hold quote belongs to both."""
    org, me = _org_user(seeder, "kpiagree-org")
    seeder.quote(org, "2601", due_date=_due(2))
    seeder.quote(org, "2602", status=QuoteStatus.on_hold, status_before_hold=QuoteStatus.draft)
    seeder.quote(org, "2603", status=QuoteStatus.won)

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        kpis = app_client.get("/api/work-queue/kpis").json()
        table = app_client.post("/api/quotes/search", json={"system_view": "workflows"}).json()

    assert kpis["open_quotes"] == table["total"] == 2


def test_kpi_row_is_manager_only(app_client: TestClient, seeder: Seeder) -> None:
    """The glance row is "for managers" (spec ``#newscope`` §2)."""
    org, me = _org_user(seeder, "kpiauth-org", roles=ESTIMATOR)
    with authed(app_client, user_id=me, org_id=org, roles=ESTIMATOR):
        assert app_client.get("/api/work-queue/kpis").status_code == 403


def test_win_rate_is_none_without_closed_quotes(app_client: TestClient, seeder: Seeder) -> None:
    org, me = _org_user(seeder, "kpiempty-org")
    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        kpis = app_client.get("/api/work-queue/kpis").json()
    assert kpis["win_rate_30d_pct"] is None


# --------------------------------------------------------------------------- #
# The classic table survives as a saved view
# --------------------------------------------------------------------------- #
def test_workflows_system_view_still_renders_the_classic_table(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, me = _org_user(seeder, "workflows-org")
    seeder.quote(org, "1801", estimator_id=me, due_date=_due(2))
    seeder.quote(org, "1802", status=QuoteStatus.sent)

    with authed(app_client, user_id=me, org_id=org, roles=ADMIN):
        views = app_client.get("/api/saved-views?scope=quotes").json()
        res = app_client.post("/api/quotes/search", json={"system_view": "workflows"})

    assert "workflows" in {v["key"] for v in views["system"]}
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 2
