"""Idempotent golden-thread CRM seed — the Fechner pilot account + its contact.

The M1 golden thread attaches its quote to a Fechner account/contact (M1.1 → the
M1.13 harness). ``OrgService``'s scope is frozen to org identity + users +
memberships (DECISIONS.md 2026-06-24 "M0.5 seed scope"), so rather than widen
``OrgSpec`` we seed the CRM rows here, as a hook the M1.13 harness builds on.

Idempotent like the org seed: each row is matched on its natural key (account by
``(org_id, name)``, contact by its live ``(org_id, email)``) and inserted only if
absent, so re-running reconciles rather than duplicating. Runs on the **owner**
connection (a superuser that bypasses RLS) the same way ``scripts.seed_demo``
provisions across orgs; the explicit ``org_id`` filter is what scopes the writes.

These are **placeholder demo values** until Benjamin's anonymised Fechner packages
land (DECISIONS.md "Fixture packages", target 2026-06-23); the harness will pin
exact figures then. Keep this seed deterministic in the meantime.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountType, Contact

#: The pilot org whose CRM gets the golden account/contact (CLAUDE.md pilot slug).
FECHNER_SLUG = "fechner"
FECHNER_ACCOUNT_NAME = "Fechner GmbH"
FECHNER_CONTACT_EMAIL = "einkauf@fechner.example"
FECHNER_CONTACT_FIRST_NAME = "Erika"
FECHNER_CONTACT_LAST_NAME = "Fechner"
FECHNER_CONTACT_ROLE = "Einkauf"


@dataclass(frozen=True)
class CrmSeedResult:
    """Outcome of seeding the pilot CRM (ids + created-vs-reconciled flags). No
    email is carried — it is customer-adjacent PII (CLAUDE.md §5)."""

    account_id: uuid.UUID
    contact_id: uuid.UUID
    account_created: bool
    contact_created: bool


async def seed_pilot_crm(session: AsyncSession, *, org_id: uuid.UUID) -> CrmSeedResult:
    """Idempotently ensure the Fechner golden account + its primary contact exist."""
    account_id = await session.scalar(
        select(Account.id).where(
            Account.org_id == org_id,
            Account.name == FECHNER_ACCOUNT_NAME,
            Account.deleted_at.is_(None),
        )
    )
    account_created = account_id is None
    if account_id is None:
        account = Account(org_id=org_id, name=FECHNER_ACCOUNT_NAME, type=AccountType.customer)
        session.add(account)
        await session.flush()
        account_id = account.id

    contact = await session.scalar(
        select(Contact).where(
            Contact.org_id == org_id,
            Contact.email == FECHNER_CONTACT_EMAIL,
            Contact.deleted_at.is_(None),
        )
    )
    contact_created = contact is None
    if contact is None:
        contact = Contact(
            org_id=org_id,
            account_id=account_id,
            email=FECHNER_CONTACT_EMAIL,
            first_name=FECHNER_CONTACT_FIRST_NAME,
            last_name=FECHNER_CONTACT_LAST_NAME,
            role=FECHNER_CONTACT_ROLE,
        )
        session.add(contact)
    else:
        # Reconcile a pre-existing contact back onto the golden account + seed
        # profile, so a re-run can't leave the thread's contact attached elsewhere.
        contact.account_id = account_id
        contact.first_name = FECHNER_CONTACT_FIRST_NAME
        contact.last_name = FECHNER_CONTACT_LAST_NAME
        contact.role = FECHNER_CONTACT_ROLE
    await session.flush()

    return CrmSeedResult(
        account_id=account_id,
        contact_id=contact.id,
        account_created=account_created,
        contact_created=contact_created,
    )
