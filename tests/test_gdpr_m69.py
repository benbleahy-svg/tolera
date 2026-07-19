"""Data-subject export + erasure, reconciled with GoBD (M6.9).

The block's acceptance criterion is the reconciliation itself: *"an export request
returns a subject's data scoped to the org; an erasure request removes/anonymizes
lawful data while **preserving GoBD-mandated immutable records**."*

So the load-bearing assertions here are the negative ones — what erasure does
**not** touch (orders, quotes, the append-only event/correspondence tables) and
what it cannot see (another tenant's rows).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole
from app.retention import ANONYMOUS_EMAIL_DOMAIN, ANONYMOUS_NAME
from tests.conftest import Seeder, authed

pytestmark = pytest.mark.usefixtures("tenancy_db")

ADMIN = [MembershipRole.admin]
MANAGER = [MembershipRole.manager]

SUBJECT = "anna.beispiel@kunde.de"


def _org_with(
    seeder: Seeder, slug: str, roles: list[MembershipRole]
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = seeder.org(slug)
    user_id = seeder.user(f"{slug}-admin@tolera.eu")
    seeder.membership(user_id, org_id, roles)
    return org_id, user_id


def _seed_subject(seeder: Seeder, org_id: uuid.UUID, email: str = SUBJECT) -> uuid.UUID:
    """A customer contact at an account — the archetypal data subject."""
    account_id = seeder.account(org_id, "Kunde GmbH")
    contact_id = seeder.contact(org_id, account_id, email)
    seeder.sql(
        "UPDATE contact SET first_name = 'Anna', last_name = 'Beispiel', "
        "phone = '+49 89 123456', notes = 'Ruft gern vormittags an.' WHERE id = :id",
        {"id": contact_id},
    )
    return contact_id


# --------------------------------------------------------------------------- #
# Authorisation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/settings/privacy/subject-export", {"email": SUBJECT}),
        (
            "post",
            "/api/settings/privacy/subject-erasure",
            {"email": SUBJECT, "confirm_email": SUBJECT},
        ),
        ("get", "/api/settings/privacy/retention-policy", None),
    ],
)
def test_privacy_surfaces_are_admin_only_not_manager(
    app_client: TestClient, seeder: Seeder, method: str, path: str, body: Any
) -> None:
    """Export returns a person's complete personal data and erasure destroys it —
    neither is a manager-level capability, and ``settings_edit`` reaches managers."""
    org_id, manager = _org_with(seeder, "fechner", MANAGER)
    with authed(app_client, user_id=manager, org_id=org_id, roles=MANAGER):
        resp = getattr(app_client, method)(path, **({"json": body} if body else {}))
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Auskunft / export
# --------------------------------------------------------------------------- #
def test_export_returns_the_subjects_records(app_client: TestClient, seeder: Seeder) -> None:
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    _seed_subject(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.post("/api/settings/privacy/subject-export", json={"email": SUBJECT})

    assert resp.status_code == 200
    body = resp.json()
    assert body["record_count"] == 1
    [contact] = body["records"]["contact"]
    assert contact["email"] == SUBJECT
    assert contact["first_name"] == "Anna"
    assert contact["phone"] == "+49 89 123456"
    # The answer is transparent about what it deliberately did not return.
    assert any(r["table"] == "order_" for r in body["retained_categories"])


def test_export_of_an_unknown_address_is_an_empty_answer_not_a_404(
    app_client: TestClient, seeder: Seeder
) -> None:
    """ "We hold nothing about you" is a complete Art. 15 answer; a 404 would leak
    whether an address is a customer of this shop."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.post(
            "/api/settings/privacy/subject-export", json={"email": "niemand@nirgends.de"}
        )
    assert resp.status_code == 200
    assert resp.json()["records"] == {}
    assert resp.json()["record_count"] == 0


def test_export_never_crosses_the_org_boundary(app_client: TestClient, seeder: Seeder) -> None:
    """E4-a: export must respect per-org membership — no cross-org leakage. The
    same person is a contact at two tenants; each admin sees only their own."""
    fechner, admin = _org_with(seeder, "fechner", ADMIN)
    other = seeder.org("other")
    _seed_subject(seeder, other)  # the subject exists ONLY at the other tenant

    with authed(app_client, user_id=admin, org_id=fechner, roles=ADMIN):
        resp = app_client.post("/api/settings/privacy/subject-export", json={"email": SUBJECT})
    assert resp.json()["records"] == {}


# --------------------------------------------------------------------------- #
# Löschung / erasure
# --------------------------------------------------------------------------- #
def test_erasure_requires_a_matching_confirmation(app_client: TestClient, seeder: Seeder) -> None:
    """Irreversible actions get a ceremony: a mistyped address must not anonymise
    a live customer."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    contact_id = _seed_subject(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": "anna.beispiel@kunde.com"},
        )
    assert resp.status_code == 422
    assert resp.json()["code"] == "confirmation_mismatch"
    [(email,)] = seeder.fetch("SELECT email FROM contact WHERE id = :id", {"id": contact_id})
    assert email == SUBJECT  # untouched


def test_erasure_anonymizes_the_contact_in_place(app_client: TestClient, seeder: Seeder) -> None:
    """``contact`` has no DELETE grant (0005) — erasure is anonymisation, and the
    row survives so the commercial relationships hanging off it stay intact."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    contact_id = _seed_subject(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": SUBJECT},
        )

    assert resp.status_code == 200
    assert resp.json()["anonymized"]["contact"] == 1

    [(email, first, last, phone, notes)] = seeder.fetch(
        "SELECT email, first_name, last_name, phone, notes FROM contact WHERE id = :id",
        {"id": contact_id},
    )
    # RFC 2606 reserves .invalid — a tombstone address can never be delivered to.
    assert email.endswith(f"@{ANONYMOUS_EMAIL_DOMAIN}")
    assert first == ANONYMOUS_NAME
    assert last == ANONYMOUS_NAME
    assert phone is None
    assert notes is None


def test_erasure_preserves_gobd_records(app_client: TestClient, seeder: Seeder) -> None:
    """**The block's central acceptance criterion.** DACH-DELTA §63 keeps
    order/quote records immutable for ~10 years; erasure may not reach them."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    contact_id = _seed_subject(seeder, org_id)
    quote_id = seeder.quote(org_id, "Q-GOBD-1", contact_id=contact_id)
    order_id = seeder.order(org_id, quote_id, "AB-0001", contact_id=contact_id)
    seeder.sql(
        "UPDATE order_ SET company_name = 'Kunde GmbH', notes = 'Lieferung an Rampe 2' "
        "WHERE id = :id",
        {"id": order_id},
    )
    events_before = seeder.fetch(
        "SELECT count(*) FROM quote_status_event WHERE quote_id = :q", {"q": quote_id}
    )[0][0]

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": SUBJECT},
        )
    assert resp.status_code == 200

    # The order survives verbatim — company, notes and the contact link.
    [(company, notes, linked_contact)] = seeder.fetch(
        "SELECT company_name, notes, contact_id FROM order_ WHERE id = :id", {"id": order_id}
    )
    assert company == "Kunde GmbH"
    assert notes == "Lieferung an Rampe 2"
    assert linked_contact == contact_id

    # The append-only audit trail is intact.
    events_after = seeder.fetch(
        "SELECT count(*) FROM quote_status_event WHERE quote_id = :q", {"q": quote_id}
    )[0][0]
    assert events_after == events_before

    # And the report says so, rather than quietly omitting it.
    retained_tables = {r["table"] for r in resp.json()["retained"]}
    assert {"order_", "quote", "quote_status_event", "email_message"} <= retained_tables


def test_erasure_never_crosses_the_org_boundary(app_client: TestClient, seeder: Seeder) -> None:
    """The same address at two tenants: erasing at one must leave the other's row
    untouched (E4-a — no cross-org data leakage)."""
    fechner, admin = _org_with(seeder, "fechner", ADMIN)
    other = seeder.org("other")
    mine = _seed_subject(seeder, fechner)
    theirs = _seed_subject(seeder, other)

    with authed(app_client, user_id=admin, org_id=fechner, roles=ADMIN):
        app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": SUBJECT},
        )

    [(mine_email,)] = seeder.fetch("SELECT email FROM contact WHERE id = :id", {"id": mine})
    [(their_email,)] = seeder.fetch("SELECT email FROM contact WHERE id = :id", {"id": theirs})
    assert mine_email.endswith(f"@{ANONYMOUS_EMAIL_DOMAIN}")
    assert their_email == SUBJECT


def test_erasure_is_idempotent(app_client: TestClient, seeder: Seeder) -> None:
    """A re-run finds nothing left to erase and says so — never an error, and
    never a second tombstone that collides on the live-unique index."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    _seed_subject(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        first = app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": SUBJECT},
        )
        second = app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": SUBJECT},
        )
    assert first.json()["anonymized_row_count"] == 1
    assert second.status_code == 200
    assert second.json()["anonymized_row_count"] == 0


def test_a_live_and_an_archived_contact_both_get_distinct_tombstones(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The reachable duplicate state. ``uq_contact_org_email_live`` is partial
    (``WHERE deleted_at IS NULL``), so one live + one archived row may share an
    address — and erasure must reach both. Per-row tombstones keep them distinct
    even if the archived row is later restored."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    account_b = seeder.account(org_id, "Zweite GmbH")
    b = seeder.contact(org_id, account_b, SUBJECT)
    seeder.sql("UPDATE contact SET deleted_at = now() WHERE id = :id", {"id": b})
    a = _seed_subject(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": SUBJECT},
        )
    assert resp.status_code == 200
    assert resp.json()["anonymized"]["contact"] == 2
    emails = {
        row[0]
        for row in seeder.fetch("SELECT email FROM contact WHERE id IN (:a, :b)", {"a": a, "b": b})
    }
    assert len(emails) == 2  # distinct, no unique-index violation


# --------------------------------------------------------------------------- #
# The policy itself
# --------------------------------------------------------------------------- #
def test_retention_policy_is_served_for_the_ropa(app_client: TestClient, seeder: Seeder) -> None:
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        rows = app_client.get("/api/settings/privacy/retention-policy").json()
    by_table = {(r["table"], r["column"]): r for r in rows}
    assert by_table[("contact", "email")]["disposition"] == "anonymize"
    assert by_table[("order_", "company_name")]["disposition"] == "retain"
    # Every rule carries a citation — a policy entry without a reason is not
    # reviewable, which is the whole point of keeping it as data.
    assert all(r["reason"].strip() for r in rows)


def test_the_two_policy_halves_do_not_contradict_each_other() -> None:
    """A column cannot be both erased and retained, and no erasure rule may target
    a table the policy declares wholly off-limits (a ``*`` retain entry — those are
    the append-only tables the app role structurally cannot rewrite). Either
    contradiction would make the erasure report a lie."""
    from app.retention import ERASURE_POLICY, RETENTION_POLICY

    erasable = {(r.table, r.column) for r in ERASURE_POLICY}
    retained = {(r.table, r.column) for r in RETENTION_POLICY}
    assert not erasable & retained

    wholly_retained = {r.table for r in RETENTION_POLICY if r.column == "*"}
    assert not {t for t, _ in erasable} & wholly_retained

    # request_for_quote is the one table split across both halves, deliberately:
    # the enquirer's identifiers go, the enquiry letter itself is a commercial
    # record that stays. Pin that, so the split is a decision and not an accident.
    assert ("request_for_quote", "email") in erasable
    assert ("request_for_quote", "description") in retained


# --------------------------------------------------------------------------- #
# Impressum + Datenschutzerklärung on the external portals
#
# DACH-DELTA §5: "Impressum + Datenschutzerklärung on all customer-facing
# surfaces"; §41 names the vendor portal too. M5.9 covered the quote PDF and the
# quote email — the two React portals were the remaining gap.
# --------------------------------------------------------------------------- #
def test_legal_block_renders_only_what_the_org_configured() -> None:
    """ "Render what's present, never invent" — the contract app/impressum.py
    already holds for a missing commercial register, extended to the privacy URL."""
    from dataclasses import dataclass

    from app.impressum import legal_block

    @dataclass
    class _Org:
        name: str | None = "Fechner Zerspanung GmbH"
        facility_address: str | None = "Musterstr. 1\n80331 München"
        commercial_register: str | None = "Amtsgericht München, HRB 123456"
        ust_id_nr: str | None = "DE123456789"
        privacy_policy_url: str | None = "https://fechner.de/datenschutz"

    full = legal_block(_Org())
    assert full["privacy_policy_url"] == "https://fechner.de/datenschutz"
    values = [line["value"] for line in full["impressum"]]
    assert "Amtsgericht München, HRB 123456" in values

    # A shop that has published no privacy policy gets a null, never a guess.
    assert legal_block(_Org(privacy_policy_url=None))["privacy_policy_url"] is None
    # And one with no register/VAT-ID emits no Impressum at all (M5.9 contract).
    bare = legal_block(_Org(commercial_register=None, ust_id_nr=None))
    assert bare["impressum"] == []


# --------------------------------------------------------------------------- #
# Ship-review fixes
# --------------------------------------------------------------------------- #
def test_erasure_matches_case_insensitively_on_plain_text_columns(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Four of the six subject tables use ``citext``; ``quote_token.recipient_email``
    and ``vendor_rfq_recipient.contact_email`` are plain ``text``. Without folding
    those, an address typed in different case erases the contact but silently
    skips the tokens — a 200 with a partial result that reads as complete."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    _seed_subject(seeder, org_id)
    quote_id = seeder.quote(org_id, "Q-CASE-1")
    token_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO quote_token (id, org_id, scope, quote_id, recipient_email, token) "
        "VALUES (:id, :org, 'buyer_portal', :q, :email, :token)",
        {
            "id": token_id,
            "org": org_id,
            "q": quote_id,
            "email": SUBJECT,
            "token": f"tok-{token_id}",
        },
    )

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        resp = app_client.post(
            "/api/settings/privacy/subject-erasure",
            # Same address, different case — as it would be pasted from a letter.
            json={"email": SUBJECT.upper(), "confirm_email": SUBJECT.upper()},
        )

    assert resp.status_code == 200
    assert resp.json()["anonymized"].get("quote_token") == 1
    [(recipient,)] = seeder.fetch(
        "SELECT recipient_email FROM quote_token WHERE id = :id", {"id": token_id}
    )
    assert recipient.endswith(f"@{ANONYMOUS_EMAIL_DOMAIN}")


def test_erasure_is_recorded_in_the_append_only_request_log(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The most destructive endpoint in the product must not be the one that
    leaves no trace. Tombstones name no actor, so without this "who erased whom"
    is unanswerable straight after the fact."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    _seed_subject(seeder, org_id)

    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        app_client.post(
            "/api/settings/privacy/subject-erasure",
            json={"email": SUBJECT, "confirm_email": SUBJECT},
        )

    [(kind, subject, actor, count)] = seeder.fetch(
        "SELECT kind::text, subject_email, actor_user_id, affected_row_count "
        "FROM gdpr_request_log WHERE org_id = :org",
        {"org": org_id},
    )
    assert kind == "erasure"
    assert subject == SUBJECT  # retained deliberately: an erasure log must say whose
    assert actor == admin
    assert count == 1


def test_subject_export_is_recorded_too(app_client: TestClient, seeder: Seeder) -> None:
    """An access request exposes a person's whole record — who ran it matters."""
    org_id, admin = _org_with(seeder, "fechner", ADMIN)
    _seed_subject(seeder, org_id)
    with authed(app_client, user_id=admin, org_id=org_id, roles=ADMIN):
        app_client.post("/api/settings/privacy/subject-export", json={"email": SUBJECT})
    [(kind,)] = seeder.fetch(
        "SELECT kind::text FROM gdpr_request_log WHERE org_id = :org", {"org": org_id}
    )
    assert kind == "export"


def test_the_request_log_is_append_only_for_the_app_role(tenancy_db: str, seeder: Seeder) -> None:
    """Same guarantee as the export-control log: the app role may not rewrite it."""
    import asyncio

    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import app_role_url

    org_id = seeder.org("fechner")
    seeder.sql(
        "INSERT INTO gdpr_request_log (org_id, kind, subject_email) "
        "VALUES (:org, 'erasure', :email)",
        {"org": org_id, "email": SUBJECT},
    )

    async def _attempt() -> None:
        engine = create_async_engine(app_role_url(tenancy_db))
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa_text("SELECT set_config('app.current_org_id', :org, true)"),
                    {"org": str(org_id)},
                )
                await conn.execute(sa_text("DELETE FROM gdpr_request_log"))
        finally:
            await engine.dispose()

    with pytest.raises(Exception, match=r"(?i)permission denied"):
        asyncio.run(_attempt())
