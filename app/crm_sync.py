"""Two-way CRM sync with the **Tolera-always-wins** conflict rule (M6.8).

Spec ``#crm``: Tolera is the system of record for *all* objects; the CRM is a
sync peer. DECISIONS.md 2026-07-17 settles v1 as **Tolera-always-wins**, no
field-level merge — field-level resolution is a post-pilot upgrade.

**How "Tolera wins" is decided.** Not by comparing clocks across two systems
(their clocks are unrelated, and HubSpot's ``hs_lastmodifieddate`` bumps on
changes we caused ourselves — a sync would fight itself). Instead each synced
record carries a ``last_synced_at`` watermark, and the rule reads:

    inbound applies  ⟺  the Tolera row has not been edited since we last synced
                        it  (``updated_at <= last_synced_at``)

* Never synced (``last_synced_at IS NULL``) and no CRM id → this is a *new*
  record from the CRM: create it. Nothing to conflict with.
* Synced, untouched since → the CRM is the only side that moved: apply.
* Synced, but a human edited it in Tolera afterwards → **both** sides moved.
  Tolera wins: the inbound write is refused and reported as
  ``conflict_tolera_wins``. It is reported rather than swallowed so the action
  log tells the user exactly which records diverged.

The outbound half is unconditional by the same rule: Tolera's value is
authoritative, so a push overwrites the CRM without asking.

Nothing here writes money or costing. The one money field in this subsystem is
the deal amount, handled in :func:`sync_deal_for_quote`, which reads an already
computed quote total and never recomputes one.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Account, Contact, Quote
from .services.crm.base import (
    CrmAccount,
    CrmAdapter,
    CrmContact,
    CrmDeal,
    CrmPullResult,
    SyncOutcome,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SyncReport:
    """What one inbound sync did — the body of the action's status_message."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: list[str] = field(default_factory=list)
    skipped: int = 0

    def record(self, outcome: SyncOutcome, label: str | None = None) -> None:
        if outcome is SyncOutcome.created:
            self.created += 1
        elif outcome is SyncOutcome.updated:
            self.updated += 1
        elif outcome is SyncOutcome.unchanged:
            self.unchanged += 1
        elif outcome is SyncOutcome.skipped:
            self.skipped += 1
        else:
            self.conflicts.append(label or "?")

    def as_message(self) -> str:
        """Human-readable, for the ``completed`` status_message (§2)."""
        parts = [
            f"{self.created} angelegt",
            f"{self.updated} aktualisiert",
            f"{self.unchanged} unverändert",
        ]
        if self.conflicts:
            parts.append(f"{len(self.conflicts)} Konflikt(e) — Tolera hat Vorrang")
        if self.skipped:
            parts.append(f"{self.skipped} übersprungen")
        return ", ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "conflicts": list(self.conflicts),
        }


def tolera_wins(record: Account | Contact) -> bool:
    """True when the Tolera row must NOT be overwritten from the CRM.

    A row that has never been synced has no watermark and therefore nothing to
    protect — it is either brand new or being adopted by the CRM for the first
    time, and in both cases the inbound value is the only value there is."""
    if record.last_synced_at is None:
        return False
    # updated_at bumps on every Tolera-side write (``_updated_ts`` onupdate), so
    # "after the watermark" means precisely "a human touched this since sync".
    return record.updated_at > record.last_synced_at


def _apply(record: Account | Contact, values: dict[str, Any], *, source: str) -> bool:
    """Write the non-null inbound fields; return whether anything changed.

    ``None`` never overwrites: the CRM not holding a phone number is not a claim
    that Tolera's phone number is wrong."""
    changed = False
    for attribute, value in values.items():
        if value is None:
            continue
        if getattr(record, attribute) != value:
            setattr(record, attribute, value)
            changed = True
    record.crm_source = source
    return changed


async def sync_accounts_in(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    source: str,
    accounts: tuple[CrmAccount, ...],
    now: datetime | None = None,
) -> SyncReport:
    """Pull CRM companies into ``account`` under the Tolera-wins rule."""
    stamp = now or datetime.now(UTC)
    report = SyncReport()
    for incoming in accounts:
        existing = await _find_by_crm_id(session, Account, org_id, source, incoming.external_id)
        if existing is None:
            existing = await _find_account_by_name(session, org_id, incoming.name)
        if existing is None:
            session.add(
                Account(
                    org_id=org_id,
                    name=incoming.name,
                    email=incoming.email,
                    phone=incoming.phone,
                    website=incoming.website,
                    external_crm_id=incoming.external_id,
                    crm_source=source,
                    last_synced_at=stamp,
                )
            )
            report.record(SyncOutcome.created)
            continue
        if tolera_wins(existing):
            report.record(SyncOutcome.conflict_tolera_wins, f"account:{incoming.external_id}")
            continue
        changed = _apply(
            existing,
            {
                "name": incoming.name,
                "email": incoming.email,
                "phone": incoming.phone,
                "website": incoming.website,
                "external_crm_id": incoming.external_id,
            },
            source=source,
        )
        existing.last_synced_at = stamp
        report.record(SyncOutcome.updated if changed else SyncOutcome.unchanged)
    await session.flush()
    return report


async def sync_contacts_in(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    source: str,
    contacts: tuple[CrmContact, ...],
    now: datetime | None = None,
) -> SyncReport:
    """Pull CRM contacts into ``contact`` under the Tolera-wins rule."""
    stamp = now or datetime.now(UTC)
    report = SyncReport()
    for incoming in contacts:
        existing = await _find_by_crm_id(session, Contact, org_id, source, incoming.external_id)
        if existing is None:
            existing = (
                (
                    await session.execute(
                        select(Contact).where(
                            Contact.org_id == org_id,
                            Contact.email == incoming.email,
                            Contact.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .first()
            )
        # The contact's parent account must already exist in THIS org — the
        # composite FK enforces same-org, and an unresolvable parent is left
        # NULL rather than guessed (account-less contacts are legal, M1.1).
        account_id = await _resolve_account_id(
            session, org_id, source, incoming.account_external_id
        )
        if existing is None:
            session.add(
                Contact(
                    org_id=org_id,
                    account_id=account_id,
                    email=incoming.email,
                    first_name=incoming.first_name,
                    last_name=incoming.last_name,
                    phone=incoming.phone,
                    external_crm_id=incoming.external_id,
                    crm_source=source,
                    last_synced_at=stamp,
                )
            )
            report.record(SyncOutcome.created)
            continue
        if tolera_wins(existing):
            report.record(SyncOutcome.conflict_tolera_wins, f"contact:{incoming.external_id}")
            continue
        changed = _apply(
            existing,
            {
                "email": incoming.email,
                "first_name": incoming.first_name,
                "last_name": incoming.last_name,
                "phone": incoming.phone,
                "account_id": account_id,
                "external_crm_id": incoming.external_id,
            },
            source=source,
        )
        existing.last_synced_at = stamp
        report.record(SyncOutcome.updated if changed else SyncOutcome.unchanged)
    await session.flush()
    return report


async def sync_in(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    source: str,
    pulled: CrmPullResult,
    now: datetime | None = None,
) -> SyncReport:
    """Both inbound halves; accounts first so contacts can resolve parents."""
    stamp = now or datetime.now(UTC)
    accounts = await sync_accounts_in(
        session, org_id=org_id, source=source, accounts=pulled.accounts, now=stamp
    )
    contacts = await sync_contacts_in(
        session, org_id=org_id, source=source, contacts=pulled.contacts, now=stamp
    )
    return SyncReport(
        created=accounts.created + contacts.created,
        updated=accounts.updated + contacts.updated,
        unchanged=accounts.unchanged + contacts.unchanged,
        conflicts=[*accounts.conflicts, *contacts.conflicts],
        skipped=accounts.skipped + contacts.skipped,
    )


async def push_account_out(
    session: AsyncSession,
    adapter: CrmAdapter,
    account: Account,
    *,
    now: datetime | None = None,
) -> str:
    """Push a Tolera account to the CRM — unconditional (Tolera is SoR)."""
    external_id = await adapter.push_account(
        CrmAccount(
            external_id=account.external_crm_id or "",
            name=account.name,
            email=account.email,
            phone=account.phone,
            website=account.website,
        )
    )
    account.external_crm_id = external_id
    account.crm_source = adapter.provider
    account.last_synced_at = now or datetime.now(UTC)
    await session.flush()
    return external_id


async def push_contact_out(
    session: AsyncSession,
    adapter: CrmAdapter,
    contact: Contact,
    *,
    now: datetime | None = None,
) -> str:
    """Push a Tolera contact to the CRM — unconditional (Tolera is SoR)."""
    parent_external_id: str | None = None
    if contact.account_id is not None:
        parent = await session.get(Account, contact.account_id)
        parent_external_id = parent.external_crm_id if parent else None
    external_id = await adapter.push_contact(
        CrmContact(
            external_id=contact.external_crm_id or "",
            email=contact.email,
            account_external_id=parent_external_id,
            first_name=contact.first_name,
            last_name=contact.last_name,
            phone=contact.phone,
        )
    )
    contact.external_crm_id = external_id
    contact.crm_source = adapter.provider
    contact.last_synced_at = now or datetime.now(UTC)
    await session.flush()
    return external_id


async def sync_deal_for_quote(
    session: AsyncSession,
    adapter: CrmAdapter,
    quote: Quote,
    *,
    amount_minor: int,
) -> str:
    """Write/link the CRM deal for a sent quote (spec ``#crm`` advanced tier).

    ``amount_minor`` is passed in, already computed, in the quote's own
    currency: this module never derives a price. The returned external id is
    stored on ``quote.crm_opportunity_id`` so a re-send updates the same deal
    instead of creating a second one."""
    external_id = await adapter.push_deal(
        CrmDeal(
            external_id=quote.crm_opportunity_id,
            name=f"Angebot {quote.number}",
            amount_minor=amount_minor,
            currency=quote.currency,
            quote_id=str(quote.id),
        )
    )
    quote.crm_opportunity_id = external_id
    await session.flush()
    return external_id


async def _find_by_crm_id(
    session: AsyncSession,
    model: type[Account] | type[Contact],
    org_id: uuid.UUID,
    source: str,
    external_id: str,
) -> Any:
    stmt = select(model).where(
        model.org_id == org_id,
        model.crm_source == source,
        model.external_crm_id == external_id,
        model.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalars().first()


async def _find_account_by_name(
    session: AsyncSession, org_id: uuid.UUID, name: str
) -> Account | None:
    """Adopt an existing unsynced account rather than creating a duplicate.

    Day-one sync against a shop that already typed its customers in by hand
    would otherwise double every account."""
    stmt = select(Account).where(
        Account.org_id == org_id,
        Account.name == name,
        Account.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalars().first()


async def _resolve_account_id(
    session: AsyncSession, org_id: uuid.UUID, source: str, external_id: str | None
) -> uuid.UUID | None:
    if not external_id:
        return None
    parent = await _find_by_crm_id(session, Account, org_id, source, external_id)
    return parent.id if parent else None
