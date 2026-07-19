"""Per-org **Dashboard work-queue settings** accessor (spec ``#newscope`` §2; M6.1)
— the single read/write seam over :class:`~app.models.OrgDashboardSettings`.

Mirrors :mod:`app.quote_settings` / :mod:`app.ai_settings`: a direct DB read (no
cache), and an **absent row is treated as all-defaults**, so an org provisioned
before the default-row insert scores its queue exactly like one provisioned
after. The weights are handed on as :class:`~app.urgency.UrgencyWeights` so the
scoring module never sees an ORM row — the math stays pure and unit-testable.
"""

from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import OrgDashboardSettings
from .urgency import DEFAULT_URGENCY_WEIGHTS, UrgencyWeights


@dataclasses.dataclass(frozen=True, slots=True)
class DashboardSettings:
    """A resolved snapshot of an org's work-queue configuration."""

    weights: UrgencyWeights = DEFAULT_URGENCY_WEIGHTS
    #: The vendor-RFQ queue source (entities land in M6.2) — off by default.
    vendor_rfq_queue_enabled: bool = False


async def load_dashboard_settings(session: AsyncSession, org_id: uuid.UUID) -> DashboardSettings:
    """The org's queue settings, or all-defaults when no row exists."""
    row = (
        await session.scalars(
            select(OrgDashboardSettings).where(OrgDashboardSettings.org_id == org_id)
        )
    ).one_or_none()
    if row is None:
        return DashboardSettings()
    return DashboardSettings(
        weights=UrgencyWeights(
            due=row.weight_due,
            value=row.weight_value,
            unresolved=row.weight_unresolved,
            flags=row.weight_flags,
        ),
        vendor_rfq_queue_enabled=row.vendor_rfq_queue_enabled,
    )


async def get_or_create_row(session: AsyncSession, org_id: uuid.UUID) -> OrgDashboardSettings:
    """The org's row, inserting an all-default one if absent.

    ``ON CONFLICT DO NOTHING`` so two concurrent first saves cannot race on the
    primary key; RLS's ``WITH CHECK`` still pins ``org_id`` to the caller."""
    await session.execute(
        pg_insert(OrgDashboardSettings)
        .values(org_id=org_id)
        .on_conflict_do_nothing(index_elements=[OrgDashboardSettings.org_id])
    )
    return (
        await session.scalars(
            select(OrgDashboardSettings).where(OrgDashboardSettings.org_id == org_id)
        )
    ).one()
