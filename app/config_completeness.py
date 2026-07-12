"""Config-completeness guard (M1.14) — spec ``#operation-rates-banner`` +
``#missing-rates-warning``.

The 54-op library seeds with **no rates** (spec: "Rates are not pre-seeded")
and the material catalog with **no costs** (DECISIONS.md 2026-07-07), so the
pilot needs a deterministic, non-AI guard against quoting on a €0/placeholder
rate unnoticed:

* ``GET /api/config-completeness`` — the Configure banner's counts: live
  operation defs whose mode needs a rate but has none, and materials with
  neither ``cost_per_volume`` nor ``cost_per_area``.
* ``POST /api/operation-defs/apply-rate`` — the banner's quick start
  ("apply a single rate to all operations"). It fills every **unrated**
  rate-bearing def in one write; already-configured rates are never
  overwritten (CLAUDE.md §5: recalculation/config sweeps never destroy
  human input — a deliberate reading of the spec's "every operation").

An operation needs a rate when it is neither a material line (no rate
arithmetic), an outside process (Vendor-RFQ-priced), nor Kalk-priced
(``cost_formula`` replaces the mode arithmetic). NULL and 0 both count as
missing — the spec's warning text names "a run rate of €0.00".
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .models import CalculationMode, Material, OpCategory, Operation, OperationDef

config_completeness_router = APIRouter(prefix="/api", tags=["config-completeness"])


def _def_needs_rate() -> ColumnElement[bool]:
    """Live, rate-bearing library defs with no usable run rate."""
    return (
        OperationDef.deleted_at.is_(None)
        & (OperationDef.category != OpCategory.material)
        & (OperationDef.calculation_mode != CalculationMode.outside_process)
        & OperationDef.cost_formula.is_(None)
        & (OperationDef.run_rate.is_(None) | (OperationDef.run_rate == 0))
    )


def operation_missing_rate(op: Operation) -> bool:
    """The quote-row reading of the same rule (#missing-rates-warning)."""
    return (
        op.category is not OpCategory.material
        and op.calculation_mode is not CalculationMode.outside_process
        and op.cost_formula is None
        and (op.run_rate is None or op.run_rate == 0)
    )


async def count_unrated_operation_defs(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(OperationDef).where(_def_needs_rate())
        )
    ) or 0


async def quote_items_missing_rates(session: AsyncSession, quote_id: uuid.UUID) -> int:
    """How many of a quote's line items use an operation with no rate."""
    from .models import QuoteItem

    return (
        await session.scalar(
            select(func.count(func.distinct(QuoteItem.id)))
            .select_from(QuoteItem)
            .join(Operation, Operation.component_id == QuoteItem.root_component_id)
            .where(
                QuoteItem.quote_id == quote_id,
                Operation.category != OpCategory.material,
                Operation.calculation_mode != CalculationMode.outside_process,
                Operation.cost_formula.is_(None),
                or_(Operation.run_rate.is_(None), Operation.run_rate == 0),
            )
        )
    ) or 0


@config_completeness_router.get("/config-completeness")
async def config_completeness(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Any:
    unrated_materials = (
        await session.scalar(
            select(func.count())
            .select_from(Material)
            .where(Material.cost_per_volume.is_(None), Material.cost_per_area.is_(None))
        )
    ) or 0
    return {
        "unrated_operation_defs": await count_unrated_operation_defs(session),
        "unrated_materials": unrated_materials,
    }


class ApplyRatePayload(BaseModel):
    run_rate: Annotated[Decimal, Field(gt=0)]


@config_completeness_router.post("/operation-defs/apply-rate")
async def apply_rate_to_all(
    payload: ApplyRatePayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> Any:
    """The quick-start APPLY TO ALL: one write fills every unrated def."""
    before = await count_unrated_operation_defs(session)
    await session.execute(
        update(OperationDef).where(_def_needs_rate()).values(run_rate=payload.run_rate)
    )
    await session.flush()
    remaining = await count_unrated_operation_defs(session)
    return {"updated": before - remaining, "unrated_operation_defs": remaining}
