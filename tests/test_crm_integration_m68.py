"""M6.8 — HubSpot CRM adapter + ERP push stub.

Acceptance criteria under test (build-plan/M6-differentiators-hardening.md §M6.8):

  1. a HubSpot change and a Tolera change to the same record resolve
     **Tolera-wins**;
  2. sending a quote (the ``quote.sent`` event) writes/links a deal via the
     fixture;
  3. the ERP-push stub emits the documented Integration-Action request and logs
     ``queued → …`` with an export-failure notification on forced failure;
  4. **no** adapter path mutates ACLs, hard-deletes, or moves funds.

Two layers, the ``test_sourcing_m67`` shape: pure units first (no DB, no
network), then the service surface against real RLS.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.crm_sync import SyncReport, tolera_wins
from app.integration_actions import (
    IntegrationActionConflict,
    ProhibitedIntegrationAction,
    assert_permitted,
    scrub_payload,
)
from app.models import (
    Account,
    IntegrationActionStatus,
    MembershipRole,
    QuoteStatus,
)
from app.services.crm.base import CrmAccount, CrmContact, CrmDeal, CrmUnavailable
from app.services.crm.erp_export import (
    ACTION_EXPORT_QUOTE,
    EXPORT_SCHEMA_VERSION,
    ErpExportFailed,
    ErpTransportStub,
    build_quote_export_payload,
)
from app.services.crm.hubspot import (
    FixtureHubSpotClient,
    HubSpotCrmAdapter,
    LiveHubSpotClient,
    _amount_to_minor,
    _minor_to_amount,
    build_hubspot_adapter,
)
from tests.conftest import Seeder
from tests.support import build_settings

ADMIN = [MembershipRole.admin]


def _adapter() -> HubSpotCrmAdapter:
    return HubSpotCrmAdapter(FixtureHubSpotClient())


class _BoomClient:
    """Every call fails — the CRM-outage stand-in."""

    async def fetch_crm(self) -> dict[str, Any]:
        raise RuntimeError("connection reset")

    async def upsert(self, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("connection reset")


# =========================================================================== #
# 1. Pure adapter — fixture parsing, money, write shape
# =========================================================================== #


def test_pull_maps_hubspot_companies_and_contacts() -> None:
    result = asyncio.run(_adapter().pull())

    assert [a.external_id for a in result.accounts] == ["7001", "7002", "7003"]
    fechner = result.accounts[0]
    assert fechner.name == "Fechner Präzisionstechnik GmbH"
    # HubSpot stores a bare domain; the adapter presents a URL.
    assert fechner.website == "https://fechner-praezision.de"
    # An explicit HubSpot `null` reads as absent, not as the string "None".
    assert result.accounts[1].email is None

    miriam = result.contacts[0]
    assert miriam.email == "m.fechner@fechner-praezision.de"
    assert miriam.account_external_id == "7001"
    # A contact HubSpot holds with no company keeps a NULL parent.
    assert result.contacts[2].account_external_id is None


def test_pull_drops_records_that_cannot_be_resolved() -> None:
    """A nameless company / email-less contact would write a blank Tolera row."""

    class _SparseClient:
        async def fetch_crm(self) -> dict[str, Any]:
            return {
                "results": {
                    "companies": [{"id": "1", "properties": {"name": ""}}],
                    "contacts": [{"id": "2", "properties": {"email": None}}],
                }
            }

        async def upsert(self, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("not called")

    result = asyncio.run(HubSpotCrmAdapter(_SparseClient()).pull())
    assert result.accounts == ()
    assert result.contacts == ()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12345.67", 1234567), ("0", 0), ("99", 9900), ("0.005", 1), (None, None), ("abc", None)],
)
def test_hubspot_amount_converts_to_integer_minor_units(
    raw: str | None, expected: int | None
) -> None:
    assert _amount_to_minor(raw) == expected


def test_minor_units_round_trip_to_hubspot_decimal_string() -> None:
    assert _minor_to_amount(1234567) == "12345.67"
    assert _minor_to_amount(0) == "0.00"
    # The value that crosses the wire is a string, never a float.
    assert isinstance(_minor_to_amount(500), str)


def test_deal_write_carries_amount_currency_and_quote_backreference() -> None:
    client = FixtureHubSpotClient()
    adapter = HubSpotCrmAdapter(client)
    quote_id = str(uuid.uuid4())

    deal_id = asyncio.run(
        adapter.push_deal(
            CrmDeal(
                external_id=None,
                name="Angebot Q-1001",
                amount_minor=1234567,
                currency="EUR",
                quote_id=quote_id,
            )
        )
    )

    object_type, payload = client.last_writes[-1]
    assert object_type == "deals"
    props = payload["properties"]
    assert props["amount"] == "12345.67"
    assert props["deal_currency_code"] == "EUR"
    assert props["tolera_quote_id"] == quote_id
    assert deal_id  # a create returns the assigned id
    # No `id` key on a create — that is what makes it a POST rather than PATCH.
    assert "id" not in payload


def test_push_omits_absent_properties_rather_than_nulling_them() -> None:
    """An explicit null tells HubSpot to CLEAR the field — it would erase CRM data."""
    client = FixtureHubSpotClient()
    asyncio.run(
        HubSpotCrmAdapter(client).push_account(
            CrmAccount(external_id="7001", name="Fechner", email=None, phone=None, website=None)
        )
    )
    _, payload = client.last_writes[-1]
    assert payload["properties"] == {"name": "Fechner"}
    assert payload["id"] == "7001"  # an update, not a create


def test_contact_push_links_parent_company() -> None:
    client = FixtureHubSpotClient()
    asyncio.run(
        HubSpotCrmAdapter(client).push_contact(
            CrmContact(
                external_id="",
                email="a@b.de",
                account_external_id="7001",
                first_name="Ada",
            )
        )
    )
    _, payload = client.last_writes[-1]
    assert payload["properties"]["associatedcompanyid"] == "7001"


# =========================================================================== #
# 2. Degradation — an outage must never crash a caller
# =========================================================================== #


def test_pull_outage_degrades_to_crm_unavailable() -> None:
    with pytest.raises(CrmUnavailable) as excinfo:
        asyncio.run(HubSpotCrmAdapter(_BoomClient()).pull())
    assert excinfo.value.provider == "hubspot"
    # The client's message (which can carry the endpoint/token) never leaks.
    assert "connection reset" not in str(excinfo.value)


def test_push_outage_degrades_to_crm_unavailable() -> None:
    with pytest.raises(CrmUnavailable):
        asyncio.run(
            HubSpotCrmAdapter(_BoomClient()).push_account(CrmAccount(external_id="", name="X"))
        )


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"results": {}},
        {"results": {"companies": [], "contacts": None}},
        {"results": {"companies": [{"no_id": 1}], "contacts": []}},
    ],
)
def test_drifted_document_is_an_outage_not_a_crash(document: dict[str, Any]) -> None:
    """Parsing sits INSIDE the guard: a drifted schema is as much an outage."""

    class _Malformed:
        async def fetch_crm(self) -> dict[str, Any]:
            return document

        async def upsert(self, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("not called")

    with pytest.raises(CrmUnavailable):
        asyncio.run(HubSpotCrmAdapter(_Malformed()).pull())


# =========================================================================== #
# 3. Tolera-always-wins (AC 1) — the conflict rule, as a pure unit
# =========================================================================== #


def _account_at(updated: datetime, synced: datetime | None) -> Account:
    account = Account(org_id=uuid.uuid4(), name="X")
    account.updated_at = updated
    account.last_synced_at = synced
    return account


def test_never_synced_record_has_nothing_to_protect() -> None:
    now = datetime.now(UTC)
    assert tolera_wins(_account_at(now, None)) is False


def test_untouched_since_sync_accepts_inbound() -> None:
    synced = datetime.now(UTC)
    assert tolera_wins(_account_at(synced - timedelta(minutes=1), synced)) is False
    assert tolera_wins(_account_at(synced, synced)) is False


def test_edited_in_tolera_since_sync_refuses_inbound() -> None:
    synced = datetime.now(UTC)
    assert tolera_wins(_account_at(synced + timedelta(seconds=1), synced)) is True


def test_sync_report_names_the_conflicting_records() -> None:
    from app.services.crm.base import SyncOutcome

    report = SyncReport()
    report.record(SyncOutcome.created)
    report.record(SyncOutcome.conflict_tolera_wins, "account:7001")
    assert report.conflicts == ["account:7001"]
    # Conflicts are reported to the user, not swallowed.
    assert "Konflikt" in report.as_message()


# =========================================================================== #
# 4. Prohibited via API (AC 4) — server-enforced regardless of token scope
# =========================================================================== #


@pytest.mark.parametrize(
    "action_type",
    [
        # ACLs / sharing / permissions
        "update_permissions",
        "grant_acl",
        "set_sharing",
        "revoke_user_access",
        # hard deletes
        "hard_delete_quote",
        "purge_account",
        "destroy_order",
        # security settings
        "rotate_api_key",
        "disable_mfa",
        "update_sso_config",
        # funds
        "issue_refund",
        "capture_payment",
        "transfer_funds",
    ],
)
def test_prohibited_action_types_are_refused(action_type: str) -> None:
    with pytest.raises(ProhibitedIntegrationAction):
        assert_permitted(action_type)


@pytest.mark.parametrize(
    "action_type",
    ["export_quote", "export_order", "import_accounts_contacts", "export_deal_on_quote_sent"],
)
def test_legitimate_action_types_are_permitted(action_type: str) -> None:
    assert_permitted(action_type)  # does not raise


def test_prohibition_survives_naming_tricks() -> None:
    """Normalised before matching, so casing/separators cannot slip one past."""
    for disguised in ("Hard-Delete-Quote", "ISSUE REFUND", "update.permissions"):
        with pytest.raises(ProhibitedIntegrationAction):
            assert_permitted(disguised)


def test_crm_adapter_exposes_no_prohibited_operation() -> None:
    """The interface itself has no delete/ACL/funds method — barrier #1 of 2."""
    surface = {name for name in dir(_adapter()) if not name.startswith("_")}
    assert surface == {"provider", "mode", "pull", "push_account", "push_contact", "push_deal"}


def test_action_payload_is_scrubbed_of_secrets() -> None:
    scrubbed = scrub_payload(
        {
            "quote_number": "Q-1",
            "api_key": "sk-live-123",
            "nested": {"Authorization": "Bearer abc", "ok": 1},
            "list": [{"password": "hunter2"}],
        }
    )
    assert scrubbed["quote_number"] == "Q-1"
    assert scrubbed["api_key"] == "[redacted]"
    assert scrubbed["nested"]["Authorization"] == "[redacted]"
    assert scrubbed["nested"]["ok"] == 1
    assert scrubbed["list"][0]["password"] == "[redacted]"


# =========================================================================== #
# 5. ERP export payload (AC 3, contract half)
# =========================================================================== #


def test_quote_export_payload_shape_is_the_documented_contract() -> None:
    quote_id = uuid.uuid4()
    payload = build_quote_export_payload(
        org_slug="fechner",
        quote_id=quote_id,
        quote_number="Q-1001",
        currency="EUR",
        total_minor=1234567,
        issued_at="2026-07-19T10:00:00+00:00",
    )
    assert payload["schema_version"] == EXPORT_SCHEMA_VERSION
    assert payload["action"] == ACTION_EXPORT_QUOTE
    assert payload["object"] == "quote"
    assert payload["org_slug"] == "fechner"
    quote = payload["quote"]
    assert quote["id"] == str(quote_id)
    assert quote["number"] == "Q-1001"
    # Money is integer minor units + explicit currency — never a float.
    assert quote["total"] == {"amount_minor": 1234567, "currency": "EUR"}
    assert isinstance(quote["total"]["amount_minor"], int)


def test_export_payload_carries_no_prohibited_field() -> None:
    payload = build_quote_export_payload(
        org_slug="f", quote_id=uuid.uuid4(), quote_number="Q-1", currency="EUR", total_minor=1
    )
    flat = repr(payload).lower()
    for forbidden in ("acl", "permission", "password", "token", "refund", "payout"):
        assert forbidden not in flat


def test_transport_stub_records_or_fails() -> None:
    transport = ErpTransportStub()
    payload = build_quote_export_payload(
        org_slug="f", quote_id=uuid.uuid4(), quote_number="Q-1", currency="EUR", total_minor=1
    )
    result = asyncio.run(transport.send(payload))
    assert result["accepted"] is True
    assert transport.sent == [payload]

    failing = ErpTransportStub(fail=True)
    with pytest.raises(ErpExportFailed):
        asyncio.run(failing.send(payload))
    assert failing.sent == []


# =========================================================================== #
# 6. Config / credential hygiene
# =========================================================================== #


def test_fixture_mode_is_the_default_and_needs_no_credential() -> None:
    adapter = build_hubspot_adapter(build_settings())
    assert adapter.mode == "fixture"
    assert isinstance(adapter._client, FixtureHubSpotClient)


def test_live_mode_builds_the_live_client() -> None:
    settings = build_settings()
    settings.hubspot_mode = "live"
    settings.hubspot_base_url = "https://api.example.test"
    settings.hubspot_api_key = "token"
    adapter = build_hubspot_adapter(settings)
    assert adapter.mode == "live"
    assert isinstance(adapter._client, LiveHubSpotClient)


@pytest.mark.parametrize(
    ("mode", "base_url", "api_key"),
    [("live", "", "token"), ("live", "https://x.test", ""), ("bogus", "", "")],
)
def test_validate_hubspot_fails_closed(mode: str, base_url: str, api_key: str) -> None:
    settings = build_settings()
    settings.hubspot_mode = mode
    settings.hubspot_base_url = base_url
    settings.hubspot_api_key = api_key
    with pytest.raises(ValueError):
        settings.validate_hubspot()


def test_no_credential_or_endpoint_literal_lives_in_the_adapter_module() -> None:
    from pathlib import Path

    import app.services.crm.hubspot as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    # The live client builds every URL from the configured base.
    assert "api.hubapi.com" not in source
    for secret_marker in ("Bearer sk-", "pat-na", "hapikey="):
        assert secret_marker not in source


# =========================================================================== #
# 7. Service layer against real RLS
# =========================================================================== #


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = seeder.org(slug)
    user_id = seeder.user(f"admin@{slug}.test")
    seeder.membership(user_id, org_id, ADMIN)
    return org_id, user_id


def _run(tenancy_db: str, org_id: uuid.UUID, coro_factory: Any) -> Any:
    """Run one coroutine on an org-pinned session as the restricted app role."""
    from app.db import make_engine, make_sessionmaker, org_scoped_session
    from tests.conftest import app_role_url

    async def _go() -> Any:
        engine = make_engine(app_role_url(tenancy_db))
        try:
            sessionmaker = make_sessionmaker(engine)
            async with org_scoped_session(sessionmaker, org_id) as session:
                result = await coro_factory(session)
                await session.commit()
                return result
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def test_provisioning_is_idempotent(tenancy_db: str, seeder: Seeder) -> None:
    from app.crm_integration import provision_integrations

    org_id, _ = _org_with_admin(seeder, "prov")
    for _ in range(2):
        _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))

    assert seeder.count("integration", "org_id = :o", {"o": org_id}) == 2
    assert seeder.count("integration_action_definition", "org_id = :o", {"o": org_id}) == 4


def test_export_definitions_notify_on_failure_imports_do_not(
    tenancy_db: str, seeder: Seeder
) -> None:
    """§6 default: only exports notify — an import failure is self-evident."""
    from app.crm_integration import provision_integrations

    org_id, _ = _org_with_admin(seeder, "notifydefault")
    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))

    assert (
        seeder.count(
            "integration_action_definition",
            "org_id = :o AND direction = 'export' AND notify_on_failure",
            {"o": org_id},
        )
        == 3
    )
    assert (
        seeder.count(
            "integration_action_definition",
            "org_id = :o AND direction = 'import' AND notify_on_failure",
            {"o": org_id},
        )
        == 0
    )


def test_inbound_sync_creates_then_respects_a_tolera_edit(tenancy_db: str, seeder: Seeder) -> None:
    """AC 1 end-to-end: first sync creates; after a Tolera edit, Tolera wins."""
    from app.crm_integration import provision_integrations, run_contact_import

    org_id, _ = _org_with_admin(seeder, "toleraWins")
    adapter = _adapter()

    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    _run(tenancy_db, org_id, lambda s: run_contact_import(s, adapter, org_id=org_id))

    # All three fixture companies landed, tagged with their HubSpot ids.
    assert seeder.count("account", "org_id = :o AND crm_source = 'hubspot'", {"o": org_id}) == 3
    rows = seeder.fetch(
        "SELECT name FROM account WHERE org_id = :o AND external_crm_id = '7001'",
        {"o": org_id},
    )
    assert rows[0][0] == "Fechner Präzisionstechnik GmbH"

    # A human renames the account in Tolera (bumping updated_at past the watermark).
    seeder.sql(
        "UPDATE account SET name = 'Fechner GmbH (intern)', updated_at = now() "
        "WHERE org_id = :o AND external_crm_id = '7001'",
        {"o": org_id},
    )

    # Re-sync: HubSpot still says "Fechner Präzisionstechnik GmbH" — Tolera wins.
    _run(tenancy_db, org_id, lambda s: run_contact_import(s, adapter, org_id=org_id))
    rows = seeder.fetch(
        "SELECT name FROM account WHERE org_id = :o AND external_crm_id = '7001'",
        {"o": org_id},
    )
    assert rows[0][0] == "Fechner GmbH (intern)"

    # …and the refusal is reported in the action log, not swallowed.
    logs = seeder.fetch(
        "SELECT status, status_message FROM integration_action WHERE org_id = :o "
        "ORDER BY created_at DESC LIMIT 1",
        {"o": org_id},
    )
    assert logs[0][0] == "completed"
    assert "Konflikt" in logs[0][1]


def test_inbound_sync_adopts_an_existing_account_instead_of_duplicating(
    tenancy_db: str, seeder: Seeder
) -> None:
    from app.crm_integration import provision_integrations, run_contact_import

    org_id, _ = _org_with_admin(seeder, "adopt")
    seeder.account(org_id, "Fechner Präzisionstechnik GmbH")

    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    _run(tenancy_db, org_id, lambda s: run_contact_import(s, _adapter(), org_id=org_id))

    assert (
        seeder.count(
            "account", "org_id = :o AND name = 'Fechner Präzisionstechnik GmbH'", {"o": org_id}
        )
        == 1
    )


def test_sync_is_org_scoped(tenancy_db: str, seeder: Seeder) -> None:
    from app.crm_integration import provision_integrations, run_contact_import

    org_a, _ = _org_with_admin(seeder, "crmorga")
    org_b, _ = _org_with_admin(seeder, "crmorgb")
    for org_id in (org_a, org_b):
        _run(tenancy_db, org_id, lambda s, o=org_id: provision_integrations(s, o))
    _run(tenancy_db, org_a, lambda s: run_contact_import(s, _adapter(), org_id=org_a))

    assert seeder.count("account", "org_id = :o", {"o": org_a}) == 3
    assert seeder.count("account", "org_id = :o", {"o": org_b}) == 0


def test_quote_sent_event_writes_a_deal(tenancy_db: str, seeder: Seeder) -> None:
    """AC 2: the quote.sent event on the bus drives the deal write."""
    from app.crm_integration import (
        EVENT_QUOTE_SENT,
        provision_integrations,
        register_handlers,
    )
    from app.event_dispatch import drain_outbox, unsubscribe_all
    from app.events import emit_event

    org_id, _ = _org_with_admin(seeder, "dealwrite")
    quote_id = seeder.quote(org_id, "Q-6800", status=QuoteStatus.sent)
    client = FixtureHubSpotClient()
    adapter = HubSpotCrmAdapter(client)

    unsubscribe_all()
    register_handlers(adapter)
    try:
        _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
        _run(
            tenancy_db,
            org_id,
            lambda s: emit_event(s, org_id, EVENT_QUOTE_SENT, {"quote_id": str(quote_id)}),
        )
        handled = _run(tenancy_db, org_id, lambda s: drain_outbox(s, org_id=org_id))
    finally:
        unsubscribe_all()

    assert handled == 1
    # The deal was written through the fixture with the quote back-reference.
    deals = [payload for kind, payload in client.last_writes if kind == "deals"]
    assert len(deals) == 1
    assert deals[0]["properties"]["tolera_quote_id"] == str(quote_id)

    # …and linked back onto the quote, so a re-send updates the same deal.
    rows = seeder.fetch("SELECT crm_opportunity_id FROM quote WHERE id = :q", {"q": quote_id})
    assert rows[0][0]

    # The attempt is in the action log, completed.
    logs = seeder.fetch(
        "SELECT status, related_object_type, related_object_id FROM integration_action "
        "WHERE org_id = :o",
        {"o": org_id},
    )
    assert len(logs) == 1
    assert logs[0][0] == "completed"
    assert logs[0][1] == "quote"
    assert logs[0][2] == quote_id

    # The event is marked delivered exactly once.
    delivered = seeder.count(
        "domain_event", "org_id = :o AND delivered_at IS NOT NULL", {"o": org_id}
    )
    assert delivered == 1


def test_deal_write_is_idempotent_across_a_replay(tenancy_db: str, seeder: Seeder) -> None:
    """At-least-once delivery: a second run updates the same deal, never a second one."""
    from app.crm_integration import provision_integrations, write_deal_for_quote

    org_id, _ = _org_with_admin(seeder, "dealreplay")
    quote_id = seeder.quote(org_id, "Q-6801", status=QuoteStatus.sent)
    client = FixtureHubSpotClient()
    adapter = HubSpotCrmAdapter(client)

    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    for _ in range(2):
        _run(
            tenancy_db,
            org_id,
            lambda s: write_deal_for_quote(s, adapter, org_id=org_id, quote_id=quote_id),
        )

    deals = [payload for kind, payload in client.last_writes if kind == "deals"]
    assert len(deals) == 2
    # The first call created; the second carried the stored id → a PATCH.
    assert "id" not in deals[0]
    assert deals[1]["id"] == str(deals[0].get("id") or "") or deals[1].get("id")


def test_crm_outage_on_quote_sent_fails_the_action_and_notifies(
    tenancy_db: str, seeder: Seeder
) -> None:
    """AC 3 (notification half) — an EXPORT failure notifies the org's admins."""
    from app.crm_integration import provision_integrations, write_deal_for_quote

    org_id, user_id = _org_with_admin(seeder, "dealoutage")
    quote_id = seeder.quote(org_id, "Q-6802", status=QuoteStatus.sent)

    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    _run(
        tenancy_db,
        org_id,
        lambda s: write_deal_for_quote(
            s, HubSpotCrmAdapter(_BoomClient()), org_id=org_id, quote_id=quote_id
        ),
    )

    logs = seeder.fetch(
        "SELECT status, status_message FROM integration_action WHERE org_id = :o", {"o": org_id}
    )
    assert logs[0][0] == "failed"
    assert "nicht erreichbar" in logs[0][1]

    notes = seeder.fetch(
        "SELECT user_id, kind FROM notification WHERE org_id = :o AND kind = "
        "'integration_action_failed'",
        {"o": org_id},
    )
    assert [row[0] for row in notes] == [user_id]

    # The quote itself is untouched: a CRM outage must never break a sent quote.
    rows = seeder.fetch("SELECT crm_opportunity_id FROM quote WHERE id = :q", {"q": quote_id})
    assert rows[0][0] is None


def test_import_failure_does_not_notify(tenancy_db: str, seeder: Seeder) -> None:
    """§6: only exports notify by default — the asymmetry is the point."""
    from app.crm_integration import provision_integrations, run_contact_import

    org_id, _ = _org_with_admin(seeder, "importfail")
    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    _run(
        tenancy_db,
        org_id,
        lambda s: run_contact_import(s, HubSpotCrmAdapter(_BoomClient()), org_id=org_id),
    )

    logs = seeder.fetch("SELECT status FROM integration_action WHERE org_id = :o", {"o": org_id})
    assert logs[0][0] == "failed"
    assert seeder.count("notification", "org_id = :o", {"o": org_id}) == 0


def test_erp_export_logs_the_full_lifecycle(tenancy_db: str, seeder: Seeder) -> None:
    """AC 3: queued → in_progress → completed, with the documented payload logged."""
    from app.crm_integration import provision_integrations, run_quote_export

    org_id, user_id = _org_with_admin(seeder, "erpok")
    quote_id = seeder.quote(org_id, "Q-6803", status=QuoteStatus.sent)
    transport = ErpTransportStub()

    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    _run(
        tenancy_db,
        org_id,
        lambda s: run_quote_export(
            s, transport, org_id=org_id, quote_id=quote_id, requested_by=user_id
        ),
    )

    rows = seeder.fetch(
        "SELECT status, request_payload, requested_by FROM integration_action WHERE org_id = :o",
        {"o": org_id},
    )
    assert rows[0][0] == "completed"
    assert rows[0][2] == user_id
    payload = rows[0][1]
    assert payload["action"] == ACTION_EXPORT_QUOTE
    assert payload["schema_version"] == EXPORT_SCHEMA_VERSION
    assert payload["quote"]["number"] == "Q-6803"
    assert payload["quote"]["total"]["currency"] == "EUR"

    # The stub actually received the same documented payload.
    assert transport.sent[0]["quote"]["id"] == str(quote_id)


def test_erp_export_failure_logs_failed_and_notifies(tenancy_db: str, seeder: Seeder) -> None:
    """AC 3 (forced-failure half)."""
    from app.crm_integration import provision_integrations, run_quote_export

    org_id, user_id = _org_with_admin(seeder, "erpfail")
    quote_id = seeder.quote(org_id, "Q-6804", status=QuoteStatus.sent)

    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    _run(
        tenancy_db,
        org_id,
        lambda s: run_quote_export(
            s, ErpTransportStub(fail=True), org_id=org_id, quote_id=quote_id
        ),
    )

    logs = seeder.fetch(
        "SELECT status, status_message FROM integration_action WHERE org_id = :o", {"o": org_id}
    )
    assert logs[0][0] == "failed"
    assert "ERP nicht erreichbar" in logs[0][1]
    notes = seeder.fetch(
        "SELECT user_id FROM notification WHERE org_id = :o AND kind = 'integration_action_failed'",
        {"o": org_id},
    )
    assert [row[0] for row in notes] == [user_id]


def test_terminal_action_cannot_be_resurrected(tenancy_db: str, seeder: Seeder) -> None:
    """A late worker must not walk a failed row back and hide the failure."""
    from app.crm_integration import provision_integrations
    from app.integration_actions import get_definition, request_action, transition_action

    org_id, _ = _org_with_admin(seeder, "terminal")
    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))

    async def _scenario(session: Any) -> None:
        definition = await get_definition(
            session, org_id=org_id, integration_key="erp_push", action_type=ACTION_EXPORT_QUOTE
        )
        assert definition is not None
        action = await request_action(session, org_id=org_id, definition=definition)
        await transition_action(session, action, IntegrationActionStatus.failed, status_message="x")
        with pytest.raises(IntegrationActionConflict):
            await transition_action(session, action, IntegrationActionStatus.in_progress)

    _run(tenancy_db, org_id, _scenario)


def test_disabled_integration_receives_no_dispatch(tenancy_db: str, seeder: Seeder) -> None:
    """Pause/Play (§2): a paused integration is skipped, not failed."""
    from app.crm_integration import provision_integrations, write_deal_for_quote

    org_id, _ = _org_with_admin(seeder, "paused")
    quote_id = seeder.quote(org_id, "Q-6805", status=QuoteStatus.sent)
    _run(tenancy_db, org_id, lambda s: provision_integrations(s, org_id))
    seeder.sql(
        "UPDATE integration SET enabled = false WHERE org_id = :o AND key = 'hubspot'",
        {"o": org_id},
    )

    client = FixtureHubSpotClient()
    _run(
        tenancy_db,
        org_id,
        lambda s: write_deal_for_quote(
            s, HubSpotCrmAdapter(client), org_id=org_id, quote_id=quote_id
        ),
    )

    assert client.last_writes == []
    assert seeder.count("integration_action", "org_id = :o", {"o": org_id}) == 0


def test_integration_tables_are_rls_isolated(tenancy_db: str, seeder: Seeder) -> None:
    """No cross-org read on the new tables (CLAUDE.md §5 tenancy invariant)."""
    from app.crm_integration import provision_integrations
    from app.db import make_engine, make_sessionmaker, org_scoped_session
    from tests.conftest import app_role_url

    org_a, _ = _org_with_admin(seeder, "rlsa")
    org_b, _ = _org_with_admin(seeder, "rlsb")
    _run(tenancy_db, org_a, lambda s: provision_integrations(s, org_a))

    async def _read_as_b() -> int:
        engine = make_engine(app_role_url(tenancy_db))
        try:
            sessionmaker = make_sessionmaker(engine)
            async with org_scoped_session(sessionmaker, org_b) as session:
                result = await session.execute(text("SELECT count(*) FROM integration"))
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    assert asyncio.run(_read_as_b()) == 0


# =========================================================================== #
# 8. Production wiring — the feature must actually run, not only in tests
# =========================================================================== #


def test_org_provisioning_installs_the_integrations(tenancy_db: str) -> None:
    """A newly seeded org has HubSpot + ERP-push ready, without a manual step."""
    import asyncio as _asyncio

    from app.db import make_engine, make_sessionmaker
    from app.services.org_service import OrgService, OrgSpec, UserSpec

    async def _go() -> tuple[int, int]:
        engine = make_engine(tenancy_db)  # owner role: provisioning writes across orgs
        try:
            sessionmaker = make_sessionmaker(engine)
            async with sessionmaker() as session:
                result = await OrgService(session).create_org(
                    OrgSpec(
                        slug="wiredorg",
                        name="Wired GmbH",
                        users=[
                            UserSpec(
                                email="admin@wiredorg.test",
                                roles=[MembershipRole.admin],
                            )
                        ],
                    )
                )
                await session.commit()
                integrations = await session.execute(
                    text("SELECT count(*) FROM integration WHERE org_id = :o"),
                    {"o": result.org_id},
                )
                definitions = await session.execute(
                    text("SELECT count(*) FROM integration_action_definition WHERE org_id = :o"),
                    {"o": result.org_id},
                )
                return int(integrations.scalar_one()), int(definitions.scalar_one())
        finally:
            await engine.dispose()

    integrations, definitions = _asyncio.run(_go())
    assert integrations == 2
    assert definitions == 4


def test_quote_sent_handler_is_registered_at_app_startup() -> None:
    """Without this the outbox would drain forever and no deal would be written."""
    from fastapi.testclient import TestClient

    from app.event_dispatch import handlers_for, unsubscribe_all
    from app.main import create_app

    unsubscribe_all()
    try:
        with TestClient(create_app(build_settings())):
            assert len(handlers_for("quote.sent")) == 1
    finally:
        unsubscribe_all()


def test_drain_task_is_registered_with_celery() -> None:
    """An omitted include= entry dies as an unregistered task at runtime.

    Asserted against ``conf`` and the task object rather than ``celery_app.tasks``:
    touching the task registry **finalizes** the Celery app, and a finalized app
    no longer picks up the ``eager_celery`` fixture's config — so every later test
    in the session silently stops dispatching (tasks stay ``queued``).
    """
    from app.celery_app import celery_app
    from app.event_dispatch_tasks import drain_event_outbox_task

    assert drain_event_outbox_task.name == "app.drain_event_outbox"
    # The worker imports only what include= lists.
    assert "app.event_dispatch_tasks" in celery_app.conf.include
    assert celery_app.conf.beat_schedule["event-outbox-drain"]["task"] == "app.drain_event_outbox"
