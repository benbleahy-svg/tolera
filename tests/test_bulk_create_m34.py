"""M3.4 — Bulk Create Line Items prefill from email.

Two layers, per the block's test plan:

* **Pure units** — the parts-list never-hallucinate guard (a part# absent from
  the email body AND the attachment filenames is dropped; invented quantities
  are dropped) and the deterministic file→part matcher (normalized part-number
  key ⊆ normalized filename key, each part consumed at most once). No DB.
* **Integration** (real Postgres, eager Celery, fake text-LLM provider) — the
  7-part multi-qty fixture `.eml`: webhook ingest → body-parse task persists
  guarded suggestions on the RFQ row → the Bulk Create prefill returns them →
  explicit Accept creates 7 line items with the right quantity breaks and the
  attachments distributed to their matching parts. Line items are created
  ONLY on Accept (AI-Governor, spec #lens-accept); org-scoped throughout.
"""

from __future__ import annotations

import email
import uuid
from collections.abc import Iterator
from email import policy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.email_parts import (
    RawLineItem,
    match_rows_to_parts,
    parts_list_guard,
)
from app.lens_provider import LensProviderError
from app.main import create_app
from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings, post_mailgun_webhook
from tests.support import eager_celery as support_eager_celery

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "email"
SEVEN_PARTS_EML = FIXTURES / "rfq-seven-parts.eml"

SIGNING_KEY = "test-signing-key"
RECIPIENT = "fechner@rfq.tolera.eu"
SENDER = "einkauf@ccs-cnc.example"

#: The DemoB/04 fixture shape: 7 parts with their multi-quantity breaks.
SEVEN_PARTS: dict[str, list[int]] = {
    "3601215": [1, 5, 20],
    "2AX70001": [50, 100, 200],
    "7781210": [1, 10, 25],
    "PP-3635-001": [10, 25],
    "PP-722-01006": [1, 10, 25],
    "PP-2341-002": [25, 50, 100],
    "PP-330-410": [10, 25],
}

# The actual text/plain body — NOT the raw message: raw MIME would smuggle
# attachment headers + base64 into the guard tests' source text (CodeRabbit).
_msg = email.message_from_bytes(SEVEN_PARTS_EML.read_bytes(), policy=policy.default)
_body = _msg.get_body(preferencelist=("plain",))
assert _body is not None
BODY_TEXT = str(_body.get_content())


def _item(part_number: str, quantities: list[int], **kwargs: Any) -> RawLineItem:
    return RawLineItem(part_number=part_number, quantities=quantities, confidence=0.9, **kwargs)


# --------------------------------------------------------------------------- #
# Never-hallucinate guard (pure)
# --------------------------------------------------------------------------- #
FILENAMES = ["3601215_OFFSET CONNECTOR.pdf", "PP-3635-001_TUBE.step"]


def test_guard_keeps_part_numbers_from_body() -> None:
    kept, dropped = parts_list_guard([_item("2AX70001", [50, 100])], BODY_TEXT, [])
    assert [i.part_number for i in kept] == ["2AX70001"]
    assert dropped == []


def test_guard_drops_invented_part_number() -> None:
    kept, dropped = parts_list_guard(
        [_item("MADE-UP-999", [1]), _item("7781210", [1, 10])], BODY_TEXT, FILENAMES
    )
    assert [i.part_number for i in kept] == ["7781210"]
    assert [i.part_number for i in dropped] == ["MADE-UP-999"]


def test_guard_accepts_part_number_only_present_in_filenames() -> None:
    # Not in this body at all — but matches an attachment filename.
    kept, _ = parts_list_guard([_item("PP-3635-001", [10])], "kein Teil genannt", FILENAMES)
    assert [i.part_number for i in kept] == ["PP-3635-001"]


def test_guard_drops_invented_quantities_keeps_row() -> None:
    kept, dropped = parts_list_guard([_item("3601215", [1, 5, 999999])], BODY_TEXT, [])
    assert dropped == []
    assert kept[0].quantities == [1, 5]


def test_guard_clears_invented_revision_and_description() -> None:
    kept, _ = parts_list_guard(
        [_item("3601215", [1], revision="Z9", description="OFFSET CONNECTOR")],
        BODY_TEXT,
        [],
    )
    assert kept[0].revision is None  # "Z9" is nowhere in the email
    assert kept[0].description == "OFFSET CONNECTOR"  # literally present


def test_guard_clears_single_letter_invented_revision() -> None:
    """The tier-1 hole a substring check leaves open (fresh-eyes 🔴1): "B"
    occurs inside almost every word — only a token-bounded "B" is a source."""
    kept, _ = parts_list_guard([_item("3601215", [1], revision="B")], BODY_TEXT, [])
    assert kept[0].revision is None
    kept, _ = parts_list_guard([_item("3601215", [1], revision="B")], BODY_TEXT + "\nRev. B", [])
    assert kept[0].revision == "B"


def test_guard_rejects_part_number_fragment_of_filename_token() -> None:
    # "635" is a substring of the token "3635" but never a whole token —
    # an invented fragment must not ride in on a real filename (🟡2).
    kept, dropped = parts_list_guard([_item("635", [1])], "kein Teil", FILENAMES)
    assert kept == []
    assert len(dropped) == 1


def test_guard_accepts_german_grouped_quantity() -> None:
    body = "Position X-77: 1.000 Stk. und 2'500 Stk."
    kept, _ = parts_list_guard([_item("X-77", [1000, 2500, 300])], body, [])
    # grouped forms resolve; the invented 300 drops (DACH delta, 🟡3).
    assert kept[0].quantities == [1000, 2500]


def test_guard_drops_requested_date_without_verbatim_source() -> None:
    kept, _ = parts_list_guard(
        [
            _item("3601215", [1], requested_date="2026-08-15", requested_date_raw="15.08.2026"),
            _item("7781210", [1], requested_date="2026-12-24", requested_date_raw="24.12.2026"),
        ],
        BODY_TEXT,
        [],
    )
    assert kept[0].requested_date == "2026-08-15"  # raw "15.08.2026" is in the body
    assert kept[1].requested_date is None  # raw not in the body → dropped


# --------------------------------------------------------------------------- #
# File→part matcher (pure)
# --------------------------------------------------------------------------- #
def test_match_rows_to_parts_by_normalized_key() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    candidates = [
        (a, ["3601215_OFFSET CONNECTOR.pdf"]),
        (b, ["PP-3635-001_TUBE.pdf", "PP-3635-001_TUBE.step"]),
    ]
    matches = match_rows_to_parts(["PP-3635-001", "3601215", "2AX70001"], candidates)
    assert matches == {0: b, 1: a}


def test_match_rows_consumes_each_part_once() -> None:
    a = uuid.uuid4()
    matches = match_rows_to_parts(["7781210", "7781210"], [(a, ["7781210_BRACKET.pdf"])])
    assert matches == {0: a}


# --------------------------------------------------------------------------- #
# Integration — webhook → parse task → prefill → explicit Accept
# --------------------------------------------------------------------------- #
class FakePartsListProvider:
    """Scripted text-LLM: echoes the fixture parts list + one invented row and
    one invented quantity (which the guard must remove)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.error: LensProviderError | None = None

    async def parse_email_parts_list(
        self, body_text: str, attachment_filenames: list[str]
    ) -> list[RawLineItem]:
        self.calls.append((body_text, list(attachment_filenames)))
        if self.error is not None:
            raise self.error
        items = [
            _item(pn, qtys + ([999999] if pn == "3601215" else []))
            for pn, qtys in SEVEN_PARTS.items()
        ]
        items.append(_item("INVENTED-000", [1]))
        return items


@pytest.fixture(name="eager_celery")
def eager_celery_fixture() -> Iterator[None]:
    """Run tasks inline (M3.3 precedent) so webhook enqueues execute."""
    with support_eager_celery():
        yield


@pytest.fixture
def lens_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Stub the per-file vision extraction (M3.1 owns it) — not under test here."""
    calls: list[tuple[str, str, str]] = []

    def record(org_id: uuid.UUID, part_id: uuid.UUID, file_id: uuid.UUID) -> None:
        calls.append((str(org_id), str(part_id), str(file_id)))

    monkeypatch.setattr("app.email_ingest._enqueue_lens_extract", record)
    return calls


@pytest.fixture
def parse_provider() -> Iterator[FakePartsListProvider]:
    from app import lens_provider

    provider = FakePartsListProvider()
    lens_provider.register(provider)  # type: ignore[arg-type]  # parts-list seam only
    try:
        yield provider
    finally:
        lens_provider.register(None)


@pytest.fixture
def ingest_client(tenancy_db: str) -> Iterator[TestClient]:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.mailgun_webhook_signing_key = SIGNING_KEY
    with TestClient(create_app(settings)) as client:
        yield client


def _post_webhook(client: TestClient, raw_eml: bytes) -> Any:
    return post_mailgun_webhook(
        client, raw_eml, recipient=RECIPIENT, sender=SENDER, signing_key=SIGNING_KEY
    )


def _seed_org_with_member(seeder: Seeder, slug: str = "fechner") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug, f"{slug.title()} GmbH")
    user = seeder.user(f"estimator@{slug}.example")
    seeder.membership(user, org, [MembershipRole.admin])
    return org, user


def _ingest_seven_parts(
    ingest_client: TestClient, seeder: Seeder
) -> tuple[uuid.UUID, uuid.UUID, str]:
    org, user = _seed_org_with_member(seeder)
    resp = _post_webhook(ingest_client, SEVEN_PARTS_EML.read_bytes())
    assert resp.status_code == 200, resp.text
    quote_id = resp.json()["quote_id"]
    assert quote_id is not None  # eager mode ran the ingest inline
    return org, user, quote_id


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_parse_task_persists_guarded_suggestions(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)
    # The provider saw the body + the ingested attachment filenames.
    assert len(parse_provider.calls) == 1
    body, filenames = parse_provider.calls[0]
    assert "Losgroessen 1, 5, 20" in body
    assert "3601215_OFFSET CONNECTOR.pdf" in filenames

    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        prefill = ingest_client.get(f"/api/quotes/{quote_id}/bulk-create")
    assert prefill.status_code == 200, prefill.text
    payload = prefill.json()
    assert payload["status"] == "completed"
    assert payload["found_in"] == "original-rfq.eml"
    rows = payload["rows"]
    # The invented row is gone; the 7 real ones survive with guarded quantities.
    assert [r["part_number"] for r in rows] == list(SEVEN_PARTS)
    assert {r["part_number"]: r["quantities"] for r in rows} == SEVEN_PARTS
    # File distribution preview: matched rows carry their part's filenames.
    by_pn = {r["part_number"]: r for r in rows}
    assert "3601215_OFFSET CONNECTOR.pdf" in by_pn["3601215"]["matched_filenames"]
    assert sorted(by_pn["PP-3635-001"]["matched_filenames"]) == [
        "PP-3635-001_TUBE.pdf",
        "PP-3635-001_TUBE.step",
    ]
    assert by_pn["2AX70001"]["matched_filenames"] == []


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_accept_creates_line_items_with_breaks_and_files(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        # No line items exist before the explicit Accept (AI-Governor).
        detail = ingest_client.get(f"/api/quotes/{quote_id}").json()
        assert detail["items"] == []

        prefill = ingest_client.get(f"/api/quotes/{quote_id}/bulk-create").json()["rows"]
        # The dialog submits the editable columns + the reviewed binding.
        rows = [
            {
                "part_number": r["part_number"],
                "revision": r["revision"],
                "description": r["description"],
                "quantities": r["quantities"],
                "matched_part_id": r["matched_part_id"],
            }
            for r in prefill
        ]
        resp = ingest_client.post(f"/api/quotes/{quote_id}/bulk-create", json={"rows": rows})
        assert resp.status_code == 201, resp.text
        items = resp.json()["items"]
        assert len(items) == 7
        assert [i["position"] for i in items] == list(range(1, 8))

        # Quantity breaks per line item match the fixture.
        for item, (part_number, quantities) in zip(items, SEVEN_PARTS.items(), strict=True):
            assert [b["quantity"] for b in item["quantities"]] == quantities, part_number

        # Files were distributed: the matched parts carry their attachments.
        part_files = {
            pn: ingest_client.get(f"/api/parts/{item['part_id']}/files").json()
            for pn, item in zip(SEVEN_PARTS, items, strict=True)
        }
        assert sorted(f["filename"] for f in part_files["PP-3635-001"]) == [
            "PP-3635-001_TUBE.pdf",
            "PP-3635-001_TUBE.step",
        ]
        assert [f["filename"] for f in part_files["3601215"]] == ["3601215_OFFSET CONNECTOR.pdf"]
        assert part_files["2AX70001"] == []  # gap case: a row without files

        # Accept wrote the part identity the human confirmed.
        part = ingest_client.get(f"/api/parts/{items[0]['part_id']}").json()
        assert part["part_number"] == "3601215"


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_accept_defaults_blank_quantities_to_one(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = ingest_client.post(
            f"/api/quotes/{quote_id}/bulk-create",
            json={"rows": [{"part_number": "3601215", "quantities": []}]},
        )
        assert resp.status_code == 201, resp.text
        assert [b["quantity"] for b in resp.json()["items"][0]["quantities"]] == [1]


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_accept_rejects_invalid_rows(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        for rows in (
            [],  # no rows
            [{"part_number": "   ", "quantities": [1]}],  # blank part number
            [{"part_number": "3601215", "quantities": [0]}],  # zero quantity
            [{"part_number": "3601215", "quantities": list(range(1, 60))}],  # > 50 breaks
        ):
            resp = ingest_client.post(f"/api/quotes/{quote_id}/bulk-create", json={"rows": rows})
            assert resp.status_code == 422, rows
            # The single API error envelope (CLAUDE.md §5): {code, message, details}.
            envelope = resp.json()
            assert envelope["code"] == "validation_error", rows
            assert envelope["message"]
            assert envelope["details"], rows  # the redacted per-field errors


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_accept_requires_draft_quote(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        moved = ingest_client.post(f"/api/quotes/{quote_id}/transition", json={"to_status": "sent"})
        assert moved.status_code == 200, moved.text
        resp = ingest_client.post(
            f"/api/quotes/{quote_id}/bulk-create",
            json={"rows": [{"part_number": "3601215", "quantities": [1]}]},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "quote_locked"


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_second_accept_never_rebinds_a_part(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    """Accepting the same row twice is a human choice — it makes a NEW (file-less)
    line item; the ingested part stays bound to the first."""
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)
    row = {"part_number": "7781210", "quantities": [1, 10, 25]}
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        first = ingest_client.post(
            f"/api/quotes/{quote_id}/bulk-create", json={"rows": [row]}
        ).json()["items"]
        second = ingest_client.post(
            f"/api/quotes/{quote_id}/bulk-create", json={"rows": [row]}
        ).json()["items"]
        assert len(second) == 2
        first_part = first[0]["part_id"]
        second_part = next(i["part_id"] for i in second if i["part_id"] != first_part)
        files = ingest_client.get(f"/api/parts/{second_part}/files").json()
        assert files == []  # the bound part was not stolen from item 1


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_accept_honors_reviewed_matched_part_id(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    """The binding the human previewed is the binding Accept performs (🟡4);
    a stale/foreign matched_part_id is a 422, never a silent re-match."""
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        rows = ingest_client.get(f"/api/quotes/{quote_id}/bulk-create").json()["rows"]
        row = next(r for r in rows if r["part_number"] == "7781210")
        assert row["matched_part_id"] is not None
        resp = ingest_client.post(
            f"/api/quotes/{quote_id}/bulk-create",
            json={
                "rows": [
                    {
                        "part_number": "7781210",
                        "quantities": [1, 10, 25],
                        "matched_part_id": row["matched_part_id"],
                    }
                ]
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["items"][0]["part_id"] == row["matched_part_id"]

        # The part is now bound — replaying the same binding must 422.
        replay = ingest_client.post(
            f"/api/quotes/{quote_id}/bulk-create",
            json={
                "rows": [
                    {
                        "part_number": "7781210",
                        "quantities": [1],
                        "matched_part_id": row["matched_part_id"],
                    }
                ]
            },
        )
        assert replay.status_code == 422
        assert replay.json()["code"] == "invalid_matched_part"


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_prefill_is_org_scoped(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    _, _, quote_id = _ingest_seven_parts(ingest_client, seeder)
    other_org = seeder.org("acme", "Acme AG")
    intruder = seeder.user("intruder@acme.example")
    seeder.membership(intruder, other_org, [MembershipRole.admin])
    with authed(ingest_client, user_id=intruder, org_id=other_org, roles=[MembershipRole.admin]):
        resp = ingest_client.get(f"/api/quotes/{quote_id}/bulk-create")
        assert resp.status_code == 404


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_provider_failure_yields_failed_status_not_broken_ingest(
    ingest_client: TestClient,
    seeder: Seeder,
    parse_provider: FakePartsListProvider,
) -> None:
    parse_provider.error = LensProviderError("provider_refusal")
    org, user, quote_id = _ingest_seven_parts(ingest_client, seeder)  # ingest still 200
    with authed(ingest_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        payload = ingest_client.get(f"/api/quotes/{quote_id}/bulk-create").json()
    assert payload["status"] == "failed"
    assert payload["rows"] == []


@pytest.mark.usefixtures("eager_celery", "lens_calls")
def test_prefill_on_manually_created_quote_is_empty_dialog(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The dialog is also PP's generic paste-in tool: a quote with no ingested
    RFQ opens it empty (status none), no banner, still usable."""
    org, user = _seed_org_with_member(seeder, slug="manual")
    with authed(app_client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        quote_id = app_client.post("/api/quotes", json={}).json()["id"]
        payload = app_client.get(f"/api/quotes/{quote_id}/bulk-create").json()
        assert payload == {
            "status": "none",
            "found_in": None,
            "rfq_files": [],
            "rows": [],
        }
        resp = app_client.post(
            f"/api/quotes/{quote_id}/bulk-create",
            json={"rows": [{"part_number": "X-1", "quantities": [2, 4]}]},
        )
        assert resp.status_code == 201
        assert [b["quantity"] for b in resp.json()["items"][0]["quantities"]] == [2, 4]
