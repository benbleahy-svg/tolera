"""Golden-thread CRM seed (M1.1) — the Fechner account/contact the M1 thread uses.

Proves the seed is idempotent (re-running reconciles, never duplicates) and links
the contact to the account, so the M1.13 harness can build on a stable pair.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.crm_seed import (
    FECHNER_ACCOUNT_NAME,
    FECHNER_CONTACT_EMAIL,
    FECHNER_SLUG,
    seed_pilot_crm,
)
from app.models import Account, Contact
from tests.conftest import Seeder


def test_seed_pilot_crm_is_idempotent_and_linked(tenancy_db: str, seeder: Seeder) -> None:
    org_id = seeder.org(FECHNER_SLUG)

    async def _run() -> tuple[
        uuid.UUID, uuid.UUID, bool, bool, bool, bool, int, int, uuid.UUID | None
    ]:
        engine = create_async_engine(tenancy_db)  # owner conn (superuser bypasses RLS)
        try:
            async with AsyncSession(engine) as session, session.begin():
                first = await seed_pilot_crm(session, org_id=org_id)
            async with AsyncSession(engine) as session, session.begin():
                second = await seed_pilot_crm(session, org_id=org_id)
            async with AsyncSession(engine) as session:
                accounts = (
                    await session.execute(
                        select(func.count()).select_from(Account).where(Account.org_id == org_id)
                    )
                ).scalar_one()
                contacts = (
                    await session.execute(
                        select(func.count()).select_from(Contact).where(Contact.org_id == org_id)
                    )
                ).scalar_one()
                account_name = (
                    await session.execute(
                        select(Account.name).where(Account.id == first.account_id)
                    )
                ).scalar_one()
                contact = (
                    await session.execute(select(Contact).where(Contact.id == first.contact_id))
                ).scalar_one()
            assert account_name == FECHNER_ACCOUNT_NAME
            assert contact.email == FECHNER_CONTACT_EMAIL
            return (
                first.account_id,
                first.contact_id,
                first.account_created,
                first.contact_created,
                second.account_created,
                second.contact_created,
                accounts,
                contacts,
                contact.account_id,
            )
        finally:
            await engine.dispose()

    (
        first_account_id,
        first_contact_id,
        first_account_created,
        first_contact_created,
        second_account_created,
        second_contact_created,
        account_count,
        contact_count,
        contact_account_id,
    ) = asyncio.run(_run())

    # First run creates; second run reconciles (no new rows).
    assert first_account_created is True
    assert first_contact_created is True
    assert second_account_created is False
    assert second_contact_created is False
    assert account_count == 1
    assert contact_count == 1
    # The contact is linked to the seeded account.
    assert contact_account_id == first_account_id
    assert first_contact_id is not None
