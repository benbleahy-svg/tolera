"""Tests for M6.5 — vendor RFQ outbound email + email-reply ingest.

The block's acceptance criteria, one test each:

* the outbound email's part fields match the **accepted** Lens extractions for those
  lines, and carry the correct per-vendor portal link (and only that vendor's files);
* a reply is matched to the right open RFQ **by reference number** even from a
  different sender address;
* extracted prices/lead-times appear flagged for verification and are **never** applied;
* the vendor's attached PDF lands in Quote Files.

Plus the invariants around them that would be silent if broken: a *suggested* finding
must not be mailed to a third party, a reply must not overwrite a human's portal
submission, a redelivery must be idempotent, and an unmatched reference must still fall
through to the ordinary customer-RFQ pipeline.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from email.message import EmailMessage
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app import lens_provider
from app.email_providers import PlatformSender, SendResult, SyncResult
from app.main import create_app
from app.models import MembershipRole
from app.vendor_reply import RawVendorPrice, RawVendorQuoteLine
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings, post_mailgun_webhook

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]
SIGNING_KEY = "test-signing-key"
ORG_SLUG = "org-a"
RECIPIENT = f"{ORG_SLUG}@rfq.tolera.eu"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class MockProvider:
    """Captures outbound mail instead of sending it (the M5.5 pattern)."""

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.fail = False

    async def send(
        self, credentials: Any, *, from_address: str, from_name: Any, message: Any
    ) -> SendResult:
        if self.fail:
            raise RuntimeError("provider down")
        self.sent.append(message)
        return SendResult(message_id=f"<out-{len(self.sent)}@acme.de>", provider_thread_id=None)

    async def fetch_new(self, credentials: Any, *, cursor: str | None) -> SyncResult:
        return SyncResult([], None)

    async def baseline_cursor(self, credentials: Any) -> str | None:
        return None


class FakeVendorLens:
    """A scripted vendor-reply reader. Returns whatever the test hands it — the guard,
    not the fake, is what decides which of it survives."""

    def __init__(self, lines: list[RawVendorQuoteLine] | None = None) -> None:
        self.lines = lines or []
        self.calls: list[tuple[str, list[str], bool]] = []

    async def parse_vendor_reply(
        self, body_text: str, part_numbers: list[str], pdf: bytes | None = None
    ) -> list[RawVendorQuoteLine]:
        self.calls.append((body_text, part_numbers, pdf is not None))
        return self.lines


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> MockProvider:
    """Install a platform sender backed by the mock provider."""
    mock = MockProvider()
    monkeypatch.setattr(
        "app.vendor_rfq_email.get_platform_sender",
        lambda _s: PlatformSender(
            provider=cast(Any, mock), from_address="quotes@acme.de", from_name="Acme"
        ),
    )
    return mock


@pytest.fixture
def app_client(tenancy_db: str) -> Any:
    """The restricted-role app **with the Mailgun signing key configured**.

    Overrides the shared fixture: this block drives both halves of the round trip —
    the authenticated send and the unauthenticated inbound webhook — so one client
    has to speak both."""
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    settings.mailgun_webhook_signing_key = SIGNING_KEY
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def vendor_lens() -> Any:
    """Register a scripted Lens provider for the vendor-reply slice."""
    fake = FakeVendorLens()
    lens_provider.register(cast(Any, fake))
    yield fake
    lens_provider.register(None)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _org_admin(seeder: Seeder, slug: str = ORG_SLUG) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_line(client: TestClient, quantities: list[int] | None = None) -> dict[str, Any]:
    quote_id = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{quote_id}/items").json()["items"][0]
    if quantities:
        client.put(
            f"/api/quotes/{quote_id}/items/{item['id']}/quantities",
            json={"quantities": quantities},
        )
    return {"quote_id": str(quote_id), "item_id": str(item["id"])}


def _part_of(client: TestClient, line: dict[str, Any]) -> uuid.UUID:
    res = client.get(f"/api/quotes/{line['quote_id']}")
    item = next(i for i in res.json()["items"] if i["id"] == line["item_id"])
    return uuid.UUID(item["part_id"])


def _create_vendor(client: TestClient, name: str) -> str:
    res = client.post(
        "/api/vendors",
        json={
            "name": name,
            "capabilities": {"processes": [], "materials": []},
            "primary_contact": {"name": f"{name} Vertrieb", "email": f"rfq@{name}.example"},
        },
    )
    assert res.status_code == 201, res.text
    return cast(str, res.json()["id"])


def _stored_file(
    client: TestClient, seeder: Seeder, org: uuid.UUID, part_id: uuid.UUID, filename: str
) -> str:
    file_id = seeder.part_file(org, part_id, filename)
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


def _set_part_number(client: TestClient, part_id: uuid.UUID, number: str) -> None:
    res = client.patch(f"/api/parts/{part_id}", json={"part_number": number})
    assert res.status_code == 200, res.text


def _seed_finding(
    seeder: Seeder,
    org: uuid.UUID,
    file_id: str,
    *,
    value: str,
    status: str,
    kind: str = "material",
) -> None:
    """An ``extraction_finding`` in a given review state, hung off a part file."""
    seeder.sql(
        "INSERT INTO extraction_finding "
        "(id, org_id, source_file_id, category, type, value, normalized_value, "
        " confidence, status) "
        "VALUES (gen_random_uuid(), :org, :file, 'requirements', :kind, :value, :value, "
        " 0.9, :status)",
        {"org": str(org), "file": file_id, "kind": kind, "value": value, "status": status},
    )


def _reply_eml(
    *, subject: str, sender: str, body: str, pdf: bytes | None = None, filename: str = "angebot.pdf"
) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = RECIPIENT
    msg["Subject"] = subject
    msg.set_content(body)
    if pdf is not None:
        msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    return msg.as_bytes()


def _post_reply(client: TestClient, raw: bytes, sender: str = "vertrieb@fremd.example") -> Any:
    return post_mailgun_webhook(
        client, raw, recipient=RECIPIENT, sender=sender, signing_key=SIGNING_KEY
    )


def _quoted_line(part_number: str | None, price_raw: str, quantity: int = 10) -> RawVendorQuoteLine:
    return RawVendorQuoteLine(
        part_number=part_number,
        cannot_quote=False,
        notes=None,
        prices=[
            RawVendorPrice(
                quantity=quantity,
                unit_price_raw=price_raw,
                lead_time_days=10,
                lead_time_raw="10 Arbeitstage",
            )
        ],
    )


# --------------------------------------------------------------------------- #
# Outbound
# --------------------------------------------------------------------------- #
def test_each_vendor_is_mailed_its_own_portal_link_and_can_reply_by_email(
    app_client: TestClient, seeder: Seeder, mail: MockProvider, eager_celery: None
) -> None:
    """AC: the email carries the correct per-vendor portal link.

    Also pins ``Reply-To``: without it a vendor's reply never reaches the ingest
    domain and the whole email channel is unreachable."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_line(app_client)
        a = _create_vendor(app_client, "Alpha")
        b = _create_vendor(app_client, "Beta")
        body = _send(
            app_client,
            line,
            [{"vendor_id": a, "part_file_ids": []}, {"vendor_id": b, "part_file_ids": []}],
        )

    assert [r["email_queued"] for r in body["rfqs"]] == [True, True]
    assert len(mail.sent) == 2
    for rfq, message in zip(body["rfqs"], mail.sent, strict=True):
        assert message.to == [f"rfq@{rfq['vendor_name']}.example".lower()]
        # The reference leads the subject — it is what a reply is matched on.
        assert f"RFQ-{rfq['number']}" in message.subject
        assert rfq["portal_token"] in message.body_html
        assert f"/vendor-rfq/{rfq['portal_token']}" in message.body_text
        assert message.reply_to == RECIPIENT
        # Blind send: no vendor's address appears in another's mail.
        others = [r["contact_email"] for r in body["rfqs"] if r["number"] != rfq["number"]]
        for other in others:
            assert other not in (message.body_html or "")


def test_outbound_autofills_material_from_an_accepted_finding(
    app_client: TestClient, seeder: Seeder, mail: MockProvider, eager_celery: None
) -> None:
    """AC: "the outbound email's part fields match the Lens extractions for those lines"."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_line(app_client)
        part_id = _part_of(app_client, line)
        file_id = _stored_file(app_client, seeder, org, part_id, "zeichnung.pdf")
        _seed_finding(seeder, org, file_id, value="1.4301", status="accepted")
        vendor = _create_vendor(app_client, "Alpha")
        _send(app_client, line, [{"vendor_id": vendor, "part_file_ids": []}])

    assert "1.4301" in mail.sent[0].body_html
    assert "1.4301" in mail.sent[0].body_text


def test_a_merely_suggested_finding_is_never_mailed_to_a_vendor(
    app_client: TestClient, seeder: Seeder, mail: MockProvider, eager_celery: None
) -> None:
    """The suggestion-only invariant at its sharpest: auto-filling an unreviewed AI
    guess into an outward disclosure is exactly what CLAUDE.md §5 forbids."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_line(app_client)
        part_id = _part_of(app_client, line)
        file_id = _stored_file(app_client, seeder, org, part_id, "zeichnung.pdf")
        _seed_finding(seeder, org, file_id, value="Titan Grade 5", status="suggested")
        vendor = _create_vendor(app_client, "Alpha")
        _send(app_client, line, [{"vendor_id": vendor, "part_file_ids": []}])

    assert "Titan Grade 5" not in mail.sent[0].body_html
    assert "Titan Grade 5" not in mail.sent[0].body_text


def test_a_vendor_is_only_offered_the_files_scoped_to_it(
    app_client: TestClient, seeder: Seeder, mail: MockProvider, eager_celery: None
) -> None:
    """A forwarded email must not even name a drawing scoped to a different vendor."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_line(app_client)
        part_id = _part_of(app_client, line)
        original = _stored_file(app_client, seeder, org, part_id, "zeichnung.pdf")
        redacted = _stored_file(app_client, seeder, org, part_id, "zeichnung-redacted.pdf")
        trusted = _create_vendor(app_client, "Alpha")
        arms_length = _create_vendor(app_client, "Beta")
        _send(
            app_client,
            line,
            [
                {"vendor_id": trusted, "part_file_ids": [original]},
                {"vendor_id": arms_length, "part_file_ids": [redacted]},
            ],
        )

    trusted_mail, arms_length_mail = mail.sent
    assert original in trusted_mail.body_html and redacted not in trusted_mail.body_html
    assert redacted in arms_length_mail.body_html and original not in arms_length_mail.body_html


def test_a_failed_send_is_reported_per_recipient_and_keeps_the_batch(
    app_client: TestClient, seeder: Seeder, mail: MockProvider, eager_celery: None
) -> None:
    """A provider outage must not destroy batches whose tokens and file scoping are
    already correct — the estimator sees which vendor did not get its mail."""
    mail.fail = True
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_line(app_client)
        vendor = _create_vendor(app_client, "Alpha")
        body = _send(app_client, line, [{"vendor_id": vendor, "part_file_ids": []}])
        rfq_id = body["rfqs"][0]["rfq_id"]
        history = app_client.get(f"/api/vendors/{vendor}/rfq-history")

    assert body["rfqs"][0]["portal_token"]  # the batch survived intact
    assert mail.sent == []
    # An unmailed recipient is visibly one whose sent_at is still NULL — which is
    # exactly the state M6.6's follow-up nudge reads.
    row = seeder.fetch(
        "SELECT sent_at FROM vendor_rfq_recipient WHERE id = :rid",
        {"rid": body["rfqs"][0]["recipient_id"]},
    )[0]
    assert row.sent_at is None
    assert history.status_code == 200
    assert any(str(r["rfq_id"]) == rfq_id for r in history.json())


# --------------------------------------------------------------------------- #
# Inbound
# --------------------------------------------------------------------------- #
def _open_batch(
    app_client: TestClient, seeder: Seeder, mail: MockProvider, *, part_number: str = "P-1"
) -> dict[str, Any]:
    """One sent RFQ to reply to, with a named part."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        line = _new_line(app_client, quantities=[10])
        part_id = _part_of(app_client, line)
        _set_part_number(app_client, part_id, part_number)
        vendor = _create_vendor(app_client, "Alpha")
        body = _send(app_client, line, [{"vendor_id": vendor, "part_file_ids": []}])
    out = cast(dict[str, Any], body["rfqs"][0])
    out.update({"org": org, "user": user, "part_id": part_id, "line": line})
    return out


def test_a_reply_from_a_different_address_is_matched_by_its_reference(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """AC: matched by reference number even from a different sender address.

    The vendor answers from a shared inbox that we have never seen — the spec's own
    reason for not matching on the sender."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = [_quoted_line("P-1", "12,50")]

    res = _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']} Anfrage",
            sender="zentrale@ganz-andere-domain.example",
            body="Fuer 10 Stueck: 12,50 EUR/Stueck, Lieferzeit 10 Arbeitstage.",
        ),
        sender="zentrale@ganz-andere-domain.example",
    )

    assert res.status_code == 200, res.text
    assert res.json()["channel"] == "vendor_rfq_reply"
    with authed(app_client, user_id=rfq["user"], org_id=rfq["org"], roles=ADMIN):
        history = app_client.get(f"/api/vendors/{rfq['vendor_id']}/rfq-history").json()
    assert any(str(r["rfq_id"]) == rfq["rfq_id"] for r in history)


def test_extracted_prices_are_flagged_for_verification_and_never_applied(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """AC: extracted prices/lead-times appear flagged "verify" (never applied
    automatically) — the Lens-never-auto-feeds-costing invariant."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = [_quoted_line("P-1", "12,50")]

    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Fuer 10 Stueck: 12,50 EUR/Stueck, Lieferzeit 10 Arbeitstage.",
        ),
    )

    row = seeder.fetch(
        "SELECT source, ai_extracted, verified, applied_at FROM vendor_rfq_response "
        "WHERE recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert row.source == "email"
    assert row.ai_extracted is True
    assert row.verified is False
    assert row.applied_at is None

    price = seeder.fetch(
        "SELECT p.quantity, p.unit_price, p.lead_time_days "
        "FROM vendor_rfq_response_price p "
        "JOIN vendor_rfq_response_line l ON l.id = p.response_line_id "
        "JOIN vendor_rfq_response r ON r.id = l.response_id "
        "WHERE r.recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert price.quantity == 10
    assert price.unit_price == Decimal("12.5000")
    assert price.lead_time_days == 10

    # Nothing reached costing: that is M6.6's Apply, behind an explicit confirmation.
    outside = seeder.fetch(
        "SELECT manual_outside_cost FROM component_quantity cq "
        "JOIN quote_item qi ON qi.root_component_id = cq.component_id "
        "WHERE qi.id = :item",
        {"item": rfq["line"]["item_id"]},
    )
    assert all(r.manual_outside_cost is None for r in outside)


def test_a_hallucinated_price_is_dropped_before_it_reaches_the_estimator(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """Never-hallucinate, end to end: a price that is nowhere in the reply is refused."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = [_quoted_line("P-1", "999,00")]

    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Fuer 10 Stueck: 12,50 EUR/Stueck.",
        ),
    )

    count = seeder.fetch(
        "SELECT count(*) AS n FROM vendor_rfq_response_price p "
        "JOIN vendor_rfq_response_line l ON l.id = p.response_line_id "
        "JOIN vendor_rfq_response r ON r.id = l.response_id "
        "WHERE r.recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert count.n == 0


def test_the_vendors_attached_pdf_lands_in_quote_files(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """AC: "the vendor's attached PDF lands in Quote Files" — i.e. as a supporting
    ``part_file`` on the batch's part, never promoted over the customer's drawing."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = []

    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Unser Angebot finden Sie im Anhang.",
            pdf=b"%PDF-1.7\nAngebot\n",
            filename="angebot-alpha.pdf",
        ),
    )

    with authed(app_client, user_id=rfq["user"], org_id=rfq["org"], roles=ADMIN):
        files = app_client.get(f"/api/parts/{rfq['part_id']}/files").json()
    stored = [f for f in files if f["filename"] == "angebot-alpha.pdf"]
    assert len(stored) == 1
    assert stored[0]["role"] == "supporting"

    response = seeder.fetch(
        "SELECT attachment_filename FROM vendor_rfq_response WHERE recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert response.attachment_filename == "angebot-alpha.pdf"


def test_a_redelivered_reply_is_idempotent(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """Mailgun retries any non-2xx — the same reply must not become two responses."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = [_quoted_line("P-1", "12,50")]
    raw = _reply_eml(
        subject=f"AW: RFQ-{rfq['number']}",
        sender="vertrieb@fremd.example",
        body="Fuer 10 Stueck: 12,50 EUR/Stueck, Lieferzeit 10 Arbeitstage.",
    )

    first = _post_reply(app_client, raw)
    second = _post_reply(app_client, raw)

    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "duplicate"
    count = seeder.fetch(
        "SELECT count(*) AS n FROM vendor_rfq_response WHERE recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert count.n == 1


def test_a_reply_never_overwrites_a_humans_portal_submission(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """A vendor who submitted on the portal and then also mailed us: the numbers they
    typed win over the numbers a model read."""
    rfq = _open_batch(app_client, seeder, mail)
    payload = app_client.get(f"/api/public/vendor-rfq/{rfq['portal_token']}").json()
    submitted = app_client.post(
        f"/api/public/vendor-rfq/{rfq['portal_token']}/response",
        json={
            "currency": "EUR",
            "lines": [
                {
                    "rfq_line_id": payload["lines"][0]["id"],
                    "cannot_quote": False,
                    "notes": None,
                    "prices": [{"quantity": 10, "unit_price": "20.00", "lead_time_days": 5}],
                }
            ],
        },
    )
    assert submitted.status_code in (200, 201), submitted.text

    vendor_lens.lines = [_quoted_line("P-1", "12,50")]
    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Fuer 10 Stueck: 12,50 EUR/Stueck.",
        ),
    )

    row = seeder.fetch(
        "SELECT source, verified FROM vendor_rfq_response WHERE recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert row.source == "portal"
    assert row.verified is True
    price = seeder.fetch(
        "SELECT p.unit_price FROM vendor_rfq_response_price p "
        "JOIN vendor_rfq_response_line l ON l.id = p.response_line_id "
        "JOIN vendor_rfq_response r ON r.id = l.response_id "
        "WHERE r.recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert price.unit_price == Decimal("20.0000")


def test_an_unknown_reference_still_becomes_an_ordinary_customer_rfq(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """A customer may well write "RFQ-4711" in their enquiry. That must not vanish."""
    _org_admin(seeder)
    res = _post_reply(
        app_client,
        _reply_eml(
            subject="Anfrage RFQ-4711",
            sender="einkauf@kunde.example",
            body="Bitte um ein Angebot fuer 10 Stueck.",
        ),
        sender="einkauf@kunde.example",
    )

    assert res.status_code == 200, res.text
    assert res.json().get("channel") != "vendor_rfq_reply"


def test_the_reply_extraction_sees_the_attached_pdf(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """DACH suppliers answer with "Angebot im Anhang" and nothing else, so the PDF has
    to reach the model alongside the body."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = []

    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Unser Angebot finden Sie im Anhang.",
            pdf=b"%PDF-1.7\nAngebot\n",
        ),
    )

    assert vendor_lens.calls, "the extraction task never ran"
    _body, part_numbers, had_pdf = vendor_lens.calls[-1]
    assert had_pdf is True
    assert part_numbers == ["P-1"]


def test_reference_matching_is_scoped_to_the_org_that_owns_the_inbox(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """Tenancy: RFQ-1 exists in both orgs; a reply to one inbox may only ever reach
    that org's batch."""
    rfq = _open_batch(app_client, seeder, mail)

    other_org = seeder.org("org-b")
    other_user = seeder.user("admin@org-b.example")
    seeder.membership(other_user, other_org, ADMIN)
    with authed(app_client, user_id=other_user, org_id=other_org, roles=ADMIN):
        line = _new_line(app_client, quantities=[10])
        vendor = _create_vendor(app_client, "Gamma")
        other = _send(app_client, line, [{"vendor_id": vendor, "part_file_ids": []}])["rfqs"][0]

    vendor_lens.lines = [_quoted_line("P-1", "12,50")]
    res = post_mailgun_webhook(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{other['number']}",
            sender="vertrieb@fremd.example",
            body="Fuer 10 Stueck: 12,50 EUR/Stueck.",
        ),
        recipient=RECIPIENT,  # org-a's inbox
        sender="vertrieb@fremd.example",
        signing_key=SIGNING_KEY,
    )
    assert res.status_code == 200, res.text

    # org-b's batch is untouched; only org-a's same-numbered batch could have matched.
    count = seeder.fetch(
        "SELECT count(*) AS n FROM vendor_rfq_response WHERE recipient_id = :rid",
        {"rid": other["recipient_id"]},
    )[0]
    assert count.n == 0
    assert rfq["number"] == other["number"], "both orgs allocate from 1 — the point of the test"


# --------------------------------------------------------------------------- #
# Review-driven regressions
# --------------------------------------------------------------------------- #
def test_a_customer_writing_the_reference_in_prose_still_gets_a_draft_quote(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """RFQ numbers are small per-org integers, so "unsere Anfrage RFQ 12" in a customer's
    body would collide with a real open batch. Matching reads the **subject** (and the
    thread), never the body — otherwise the customer's RFQ is silently swallowed."""
    rfq = _open_batch(app_client, seeder, mail)

    res = _post_reply(
        app_client,
        _reply_eml(
            subject="Anfrage Drehteile",  # no reference here
            sender="einkauf@kunde.example",
            body=f"Guten Tag, bezugnehmend auf RFQ-{rfq['number']} bitten wir um Angebot.",
        ),
        sender="einkauf@kunde.example",
    )

    assert res.status_code == 200, res.text
    assert res.json().get("channel") != "vendor_rfq_reply"
    count = seeder.fetch(
        "SELECT count(*) AS n FROM vendor_rfq_response WHERE recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert count.n == 0


def test_a_reply_is_matched_when_it_threads_onto_the_message_we_sent(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """The corroboration that a customer can never accidentally carry: our own
    Message-ID coming back in In-Reply-To, even with the reference gone from the subject."""
    rfq = _open_batch(app_client, seeder, mail)
    sent_message_id = seeder.fetch(
        "SELECT sent_message_id FROM vendor_rfq_recipient WHERE id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0].sent_message_id
    assert sent_message_id

    msg = EmailMessage()
    msg["From"] = "zentrale@fremd.example"
    msg["To"] = RECIPIENT
    msg["Subject"] = "Unser Angebot"  # the reference did not survive
    msg["In-Reply-To"] = sent_message_id
    msg.set_content("Fuer 10 Stueck: 12,50 EUR/Stueck.")
    vendor_lens.lines = [_quoted_line("P-1", "12,50")]

    res = _post_reply(app_client, msg.as_bytes())

    assert res.json()["channel"] == "vendor_rfq_reply"
    price = seeder.fetch(
        "SELECT p.unit_price FROM vendor_rfq_response_price p "
        "JOIN vendor_rfq_response_line l ON l.id = p.response_line_id "
        "JOIN vendor_rfq_response r ON r.id = l.response_id "
        "WHERE r.recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert price.unit_price == Decimal("12.5000")


def test_a_vendors_quote_pdf_is_never_offered_to_another_vendor(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """The filed reply attachment is a competitor's price sheet. It lands in Quote Files
    for the estimator, but the compose modal must not list it — otherwise the next
    batch send pre-selects it and mails vendor B vendor A's prices."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = []
    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Angebot im Anhang.",
            pdf=b"%PDF-1.7\nPreise\n",
            filename="angebot-alpha.pdf",
        ),
    )

    with authed(app_client, user_id=rfq["user"], org_id=rfq["org"], roles=ADMIN):
        compose = app_client.get(
            "/api/vendor-rfqs/compose",
            params={"quote_id": rfq["line"]["quote_id"], "quote_item_ids": rfq["line"]["item_id"]},
        )
        assert compose.status_code == 200, compose.text
        offered = [f["filename"] for line in compose.json()["lines"] for f in line["files"]]

        # It is a Quote File...
        part_files = app_client.get(f"/api/parts/{rfq['part_id']}/files").json()
        assert any(f["filename"] == "angebot-alpha.pdf" for f in part_files)
        # ...but never an offerable one.
        assert "angebot-alpha.pdf" not in offered

        # And a hand-rolled request naming it is refused outright.
        stray = seeder.fetch(
            "SELECT id FROM part_file WHERE filename = :n", {"n": "angebot-alpha.pdf"}
        )[0].id
        other = _create_vendor(app_client, "Beta")
        res = app_client.post(
            "/api/vendor-rfqs/batch",
            json={
                "quote_id": rfq["line"]["quote_id"],
                "quote_item_ids": [rfq["line"]["item_id"]],
                "recipients": [{"vendor_id": other, "part_file_ids": [str(stray)]}],
            },
        )
    assert res.status_code == 422, res.text


def test_an_export_controlled_line_never_sends_the_reply_to_a_model(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """Defence in depth, mirroring ``lens_extract``: a vendor quoting a dual-use drawing
    back at us must not push it to an external provider."""
    rfq = _open_batch(app_client, seeder, mail)
    seeder.sql(
        "UPDATE quote_item SET export_controlled = true WHERE id = :item",
        {"item": rfq["line"]["item_id"]},
    )
    vendor_lens.lines = [_quoted_line("P-1", "12,50")]

    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Fuer 10 Stueck: 12,50 EUR/Stueck.",
        ),
    )

    assert vendor_lens.calls == []
    count = seeder.fetch(
        "SELECT count(*) AS n FROM vendor_rfq_response_price p "
        "JOIN vendor_rfq_response_line l ON l.id = p.response_line_id "
        "JOIN vendor_rfq_response r ON r.id = l.response_id "
        "WHERE r.recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert count.n == 0
    # The reply itself is still filed and readable — only the model call was refused.
    filed = seeder.fetch(
        "SELECT email_body_text FROM vendor_rfq_response WHERE recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )[0]
    assert "12,50" in filed.email_body_text


def test_two_model_items_for_one_line_are_merged_not_crashed(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
) -> None:
    """``(response_id, rfq_line_id)`` is unique — a model splitting one part's breaks
    across two objects must not cost the estimator every suggestion in the reply."""
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = [
        _quoted_line("P-1", "12,50", quantity=10),
        _quoted_line("P-1", "11,00", quantity=10),  # same break, second opinion
    ]

    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Fuer 10 Stueck: 12,50 EUR/Stueck oder 11,00 EUR/Stueck, 10 Arbeitstage.",
        ),
    )

    rows = seeder.fetch(
        "SELECT p.unit_price FROM vendor_rfq_response_price p "
        "JOIN vendor_rfq_response_line l ON l.id = p.response_line_id "
        "JOIN vendor_rfq_response r ON r.id = l.response_id "
        "WHERE r.recipient_id = :rid",
        {"rid": rfq["recipient_id"]},
    )
    assert [r.unit_price for r in rows] == [Decimal("12.5000")]


def test_the_vendors_inbound_pdf_is_queued_for_virus_scanning(
    app_client: TestClient,
    seeder: Seeder,
    mail: MockProvider,
    vendor_lens: Any,
    eager_celery: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M3.13's gate only helps if this file enters it. The reply attachment arrives
    from outside the shop over an unauthenticated channel and is written straight to
    ``part_file`` (not through the upload pipeline), so it has to be enqueued for
    scanning explicitly — otherwise it sits ``pending`` forever, undownloadable, and
    the one inbound path that most needs scanning is the one that skips it."""
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.vendor_reply_ingest.enqueue_scan",
        lambda _session, _settings, org_id, file_id: queued.append((str(org_id), str(file_id))),
    )
    rfq = _open_batch(app_client, seeder, mail)
    vendor_lens.lines = []

    _post_reply(
        app_client,
        _reply_eml(
            subject=f"AW: RFQ-{rfq['number']}",
            sender="vertrieb@fremd.example",
            body="Angebot im Anhang.",
            pdf=b"%PDF-1.7\nAngebot\n",
            filename="angebot-alpha.pdf",
        ),
    )

    stored = seeder.fetch(
        "SELECT id FROM part_file WHERE filename = :n", {"n": "angebot-alpha.pdf"}
    )[0]
    assert queued == [(str(rfq["org"]), str(stored.id))]
