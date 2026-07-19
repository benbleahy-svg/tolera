"""Wiring: HubSpot + ERP-push as *managed integrations* on the event bus (M6.8).

Three things live here, all of them glue between parts that are deliberately
ignorant of each other:

1. **Provisioning** (:func:`provision_integrations`) — creates the ``hubspot``
   and ``erp_push`` :class:`~app.models.Integration` rows and their action
   definitions for an org. Idempotent, so it can run on org seed and again on
   any later boot without duplicating.
2. **The ``quote.sent`` handler** (:func:`handle_quote_sent`) — the deal write.
   Spec ``#crm``: the advanced tier links a CRM Deal to the Tolera quote and
   writes the quoted amount back so the pipeline stays live; the trigger is
   *on quote send*.
3. **The ERP export runner** (:func:`run_quote_export`) — drives one
   Integration-Action through ``queued → in_progress → completed|failed`` over
   the stubbed transport, which is what makes the export contract and its
   failure notification real today.

Every path here is **degrade-don't-fail**: a CRM or ERP outage records a failed
action (and, for exports, notifies) but never propagates out of the dispatcher
into the quote-send request that emitted the event. Sending a quote to a
customer must not depend on HubSpot being up.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .addons import quote_net_minor
from .crm_sync import sync_deal_for_quote, sync_in
from .event_dispatch import EventHandler, subscribe
from .integration_actions import (
    get_definition,
    request_action,
    transition_action,
)
from .models import (
    DomainEvent,
    Integration,
    IntegrationActionDefinition,
    IntegrationActionDirection,
    IntegrationActionStatus,
    Organization,
    Quote,
)
from .services.crm.base import CrmAdapter, CrmUnavailable
from .services.crm.erp_export import (
    ACTION_EXPORT_ORDER,
    ACTION_EXPORT_QUOTE,
    ERP_INTEGRATION_KEY,
    ErpExportFailed,
    ErpTransportStub,
    build_quote_export_payload,
)
from .services.crm.hubspot import PROVIDER as HUBSPOT_PROVIDER

logger = logging.getLogger(__name__)

#: Capability keys on the HubSpot integration.
ACTION_SYNC_CONTACTS = "import_accounts_contacts"
ACTION_WRITE_DEAL = "export_deal_on_quote_sent"

#: The event the deal write rides (INTEGRATION-API-CONTRACT §3 catalog).
EVENT_QUOTE_SENT = "quote.sent"


# --------------------------------------------------------------------------- #
# 1. Provisioning
# --------------------------------------------------------------------------- #

#: ``(integration_key, name, author, support_contact)`` + its definitions.
#: ``notify_on_failure`` is TRUE for exports and FALSE for the import, which is
#: exactly the §6 default — not an arbitrary per-row choice.
_BLUEPRINT: tuple[tuple[str, str, str, str, tuple[dict[str, object], ...]], ...] = (
    (
        HUBSPOT_PROVIDER,
        "HubSpot CRM",
        "Tolera",
        "support@tolera.eu",
        (
            {
                "type": ACTION_SYNC_CONTACTS,
                "display_title": "Accounts & Kontakte importieren",
                "display_description": (
                    "Holt Firmen und Kontakte aus HubSpot. Bei Konflikten "
                    "gewinnt immer Tolera (Systemführung)."
                ),
                "direction": IntegrationActionDirection.import_,
                "has_tolera_entity": False,
                "entity_type": None,
                "can_be_requested": True,
                "notify_on_failure": False,
            },
            {
                "type": ACTION_WRITE_DEAL,
                "display_title": "Deal beim Angebotsversand schreiben",
                "display_description": (
                    "Legt beim Versand eines Angebots einen HubSpot-Deal an "
                    "bzw. aktualisiert ihn mit der Angebotssumme."
                ),
                "direction": IntegrationActionDirection.export,
                "has_tolera_entity": True,
                "entity_type": "quote",
                # Event-driven, not manually requestable.
                "can_be_requested": False,
                "notify_on_failure": True,
            },
        ),
    ),
    (
        ERP_INTEGRATION_KEY,
        "ERP-Export (Stub)",
        "Tolera",
        "support@tolera.eu",
        (
            {
                "type": ACTION_EXPORT_QUOTE,
                "display_title": "Angebot exportieren",
                "display_description": "Exportiert ein Angebot an das ERP-System.",
                "direction": IntegrationActionDirection.export,
                "has_tolera_entity": True,
                "entity_type": "quote",
                "can_be_requested": True,
                "notify_on_failure": True,
            },
            {
                "type": ACTION_EXPORT_ORDER,
                "display_title": "Auftrag exportieren",
                "display_description": "Exportiert einen Auftrag an das ERP-System.",
                "direction": IntegrationActionDirection.export,
                "has_tolera_entity": True,
                "entity_type": "order",
                "can_be_requested": True,
                "notify_on_failure": True,
            },
        ),
    ),
)


async def provision_integrations(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Create the org's integrations + action definitions. Idempotent."""
    for key, name, author, support, definitions in _BLUEPRINT:
        integration = (
            (
                await session.execute(
                    select(Integration).where(Integration.org_id == org_id, Integration.key == key)
                )
            )
            .scalars()
            .first()
        )
        if integration is None:
            integration = Integration(
                org_id=org_id,
                key=key,
                name=name,
                author=author,
                support_contact=support,
            )
            session.add(integration)
            await session.flush()
        for spec in definitions:
            existing = (
                (
                    await session.execute(
                        select(IntegrationActionDefinition).where(
                            IntegrationActionDefinition.org_id == org_id,
                            IntegrationActionDefinition.integration_id == integration.id,
                            IntegrationActionDefinition.type == spec["type"],
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing is not None:
                continue
            session.add(
                IntegrationActionDefinition(
                    org_id=org_id,
                    integration_id=integration.id,
                    **spec,
                )
            )
    await session.flush()


# --------------------------------------------------------------------------- #
# 2. quote.sent → CRM deal
# --------------------------------------------------------------------------- #


async def write_deal_for_quote(
    session: AsyncSession,
    adapter: CrmAdapter,
    *,
    org_id: uuid.UUID,
    quote_id: uuid.UUID,
) -> uuid.UUID | None:
    """Open an action log, push the deal, close the log. Returns the action id.

    Returns ``None`` when the org has not provisioned the HubSpot integration
    (nothing to log against) — a no-op, not an error."""
    definition = await get_definition(
        session, org_id=org_id, integration_key=HUBSPOT_PROVIDER, action_type=ACTION_WRITE_DEAL
    )
    if definition is None:
        return None
    integration = await session.get(Integration, definition.integration_id)
    if integration is None or not integration.enabled:
        # Pause/Play (§2): a disabled integration receives no dispatch.
        return None

    quote = await session.get(Quote, quote_id)
    if quote is None or quote.org_id != org_id:
        return None

    amount_minor, has_unpriced = await quote_net_minor(session, quote_id)
    action = await request_action(
        session,
        org_id=org_id,
        definition=definition,
        related_object_type="quote",
        related_object_id=quote_id,
        request_payload={
            "quote_number": quote.number,
            "amount_minor": amount_minor,
            "currency": quote.currency,
            "has_unpriced_lines": has_unpriced,
        },
    )
    await transition_action(session, action, IntegrationActionStatus.in_progress)
    try:
        deal_id = await sync_deal_for_quote(session, adapter, quote, amount_minor=amount_minor)
    except CrmUnavailable:
        await transition_action(
            session,
            action,
            IntegrationActionStatus.failed,
            status_message="HubSpot ist nicht erreichbar — Deal wurde nicht geschrieben.",
        )
        return action.id
    await transition_action(
        session,
        action,
        IntegrationActionStatus.completed,
        status_message=f"HubSpot-Deal {deal_id} für Angebot {quote.number} aktualisiert.",
    )
    return action.id


def make_quote_sent_handler(adapter: CrmAdapter) -> EventHandler:
    """Bind an adapter into a handler the dispatcher can call.

    A factory rather than a module-level function because the adapter is
    constructed from settings (fixture vs live) and tests substitute their own."""

    async def handler(session: AsyncSession, event: DomainEvent) -> None:
        quote_id = (event.payload or {}).get("quote_id")
        if not quote_id:
            return
        await write_deal_for_quote(
            session, adapter, org_id=event.org_id, quote_id=uuid.UUID(str(quote_id))
        )

    return handler


def register_handlers(adapter: CrmAdapter) -> None:
    """Subscribe the CRM handlers to the event bus."""
    subscribe(EVENT_QUOTE_SENT, make_quote_sent_handler(adapter))


# --------------------------------------------------------------------------- #
# 3. Inbound sync + the ERP export runner
# --------------------------------------------------------------------------- #


async def run_contact_import(
    session: AsyncSession,
    adapter: CrmAdapter,
    *,
    org_id: uuid.UUID,
    requested_by: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Pull accounts + contacts from the CRM under the Tolera-wins rule."""
    definition = await get_definition(
        session,
        org_id=org_id,
        integration_key=HUBSPOT_PROVIDER,
        action_type=ACTION_SYNC_CONTACTS,
    )
    if definition is None:
        return None
    action = await request_action(
        session, org_id=org_id, definition=definition, requested_by=requested_by
    )
    await transition_action(session, action, IntegrationActionStatus.in_progress)
    try:
        pulled = await adapter.pull()
    except CrmUnavailable:
        await transition_action(
            session,
            action,
            IntegrationActionStatus.failed,
            status_message="HubSpot ist nicht erreichbar — Import abgebrochen.",
        )
        return action.id
    report = await sync_in(session, org_id=org_id, source=adapter.provider, pulled=pulled)
    await transition_action(
        session,
        action,
        IntegrationActionStatus.completed,
        status_message=report.as_message(),
    )
    return action.id


async def run_quote_export(
    session: AsyncSession,
    transport: ErpTransportStub,
    *,
    org_id: uuid.UUID,
    quote_id: uuid.UUID,
    requested_by: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Drive one "Export Quote" action end-to-end over the stubbed transport."""
    definition = await get_definition(
        session,
        org_id=org_id,
        integration_key=ERP_INTEGRATION_KEY,
        action_type=ACTION_EXPORT_QUOTE,
    )
    if definition is None:
        return None
    quote = await session.get(Quote, quote_id)
    if quote is None or quote.org_id != org_id:
        return None
    org = await session.get(Organization, org_id)
    amount_minor, _ = await quote_net_minor(session, quote_id)

    payload = build_quote_export_payload(
        org_slug=org.slug if org else "",
        quote_id=quote_id,
        quote_number=quote.number,
        currency=quote.currency,
        total_minor=amount_minor,
        issued_at=quote.sent_at.isoformat() if quote.sent_at else None,
    )
    action = await request_action(
        session,
        org_id=org_id,
        definition=definition,
        related_object_type="quote",
        related_object_id=quote_id,
        requested_by=requested_by,
        request_payload=payload,
    )
    await transition_action(session, action, IntegrationActionStatus.in_progress)
    try:
        result = await transport.send(payload)
    except ErpExportFailed as exc:
        await transition_action(
            session,
            action,
            IntegrationActionStatus.failed,
            status_message=str(exc),
        )
        return action.id
    await transition_action(
        session,
        action,
        IntegrationActionStatus.completed,
        status_message=f"An ERP übergeben (Referenz {result['reference']}).",
    )
    return action.id
