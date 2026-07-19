"""The shared ``CrmAdapter`` interface (M6.8, spec ``#crm``).

**Tolera is the system of record for every object** — Accounts, Contacts, Parts,
Quotes, line items, Pricing, status. The CRM is a *sync peer*, not an authority:
the adapter pulls accounts/contacts in and pushes accounts/contacts/quotes out,
and on conflict Tolera wins (DECISIONS.md 2026-07-17). There is deliberately no
"merge" DTO here — v1 has no field-level resolution, so the only two outcomes an
inbound record can have are *applied* and *refused as conflicting*.

**Money.** A deal amount crossing this boundary is an integer in **minor units**
plus an explicit ISO-4217 ``currency`` (CLAUDE.md §5) — never a float. The CRM's
own wire format (HubSpot sends a decimal string) is converted at the client
seam, so nothing downstream of this module ever sees a float.

**Safety.** The interface exposes upserts and reads only. There is no method to
alter sharing/permissions/ACLs, hard-delete a record, or move funds — the
prohibited-via-API rules of INTEGRATION-API-CONTRACT §5, which are additionally
enforced server-side for the *request* path in
:func:`app.integration_actions.assert_permitted`, regardless of token scope.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class CrmObjectType(enum.StrEnum):
    """The three object families v1 syncs (spec ``#crm`` "Objects synced")."""

    account = "account"
    contact = "contact"
    deal = "deal"


class SyncOutcome(enum.StrEnum):
    """What happened to one inbound CRM record under the Tolera-wins rule.

    ``conflict_tolera_wins`` is the interesting one: the CRM had a newer value
    but a human had edited the Tolera record since the last sync, so the inbound
    write was **refused**, not merged. It is reported (not swallowed) so the
    action log shows the user which records diverged."""

    created = "created"
    updated = "updated"
    unchanged = "unchanged"
    conflict_tolera_wins = "conflict_tolera_wins"
    skipped = "skipped"


@dataclass(frozen=True, slots=True)
class CrmAccount:
    """A company as the CRM holds it (HubSpot calls it a *company*)."""

    external_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    #: When the CRM last modified it. Used only for reporting — the conflict
    #: rule keys on the Tolera side's watermark, never on the CRM's clock.
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CrmContact:
    """A person as the CRM holds it, optionally under a company."""

    external_id: str
    email: str
    account_external_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CrmDeal:
    """A deal/opportunity linked to a Tolera quote.

    ``amount_minor`` + ``currency`` are the whole reason this DTO exists: the
    "advanced tier" behaviour in spec ``#crm`` is writing the quoted amount back
    onto the deal so the CRM pipeline stays live, and that number must cross the
    boundary as integer minor units."""

    external_id: str | None
    name: str
    amount_minor: int
    currency: str
    quote_id: str
    stage: str | None = None


@dataclass(frozen=True, slots=True)
class CrmPullResult:
    """Everything one inbound sync fetched, before the Tolera-wins filter."""

    accounts: tuple[CrmAccount, ...] = ()
    contacts: tuple[CrmContact, ...] = ()


class CrmUnavailable(Exception):
    """The CRM could not be reached or answered in a shape we understand.

    Callers **degrade** — a CRM outage must never fail a quote send or block
    costing. Never re-raise the underlying client message to a user: it can
    carry the endpoint URL and token fragments."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"CRM provider {provider!r} is unavailable")
        self.provider = provider


@runtime_checkable
class CrmAdapter(Protocol):
    """One implementation per CRM (HubSpot here; Salesforce/SAP post-pilot)."""

    provider: str

    async def pull(self) -> CrmPullResult:
        """Fetch the CRM's companies + contacts (inbound half of the sync)."""
        ...

    async def push_account(self, account: CrmAccount) -> str:
        """Upsert a Tolera account into the CRM; returns its external id."""
        ...

    async def push_contact(self, contact: CrmContact) -> str:
        """Upsert a Tolera contact into the CRM; returns its external id."""
        ...

    async def push_deal(self, deal: CrmDeal) -> str:
        """Write/link the deal for a sent quote; returns its external id."""
        ...
