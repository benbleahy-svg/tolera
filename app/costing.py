"""Costing service — mode arithmetic + the Calculated-vs-Override recalc (M1.7).

Spec ``#costing`` (roll-up inputs) + ``#oplibrary`` (calculation modes); grill
decisions DECISIONS.md 2026-07-07. The three rules this module encodes:

* **Calculated source (pre-Kalk):** an operation's ``calc_cost`` per quantity break
  comes from its calculation mode's arithmetic (below). Kalk replaces/augments this
  at M1.9; ``outside_process`` has no internal calc until the Vendor-RFQ path (M6).

  * ``machine_plus_operator`` — ``setup + (Hauptzeit/60 x run_rate
    + Nebenzeit/60 x labour_rate) x Losgröße``
  * ``labour_only`` — ``setup + (Arbeitszeit/60 x run_rate) x Losgröße``
  * setup = flat ``setup_cost``, or (Advanced) ``setup_mins/60 x run_rate``
    (setup rate = ``run_rate`` — DECISIONS.md 2026-07-07 OPEN default)
  * the whole thing x ``(1 + surcharge_pct/100)`` (``#oplibrary`` Operation surcharge)

  Losgröße = the break's **make quantity**; times are minutes; every time input
  resolves ``COALESCE(manual, calc)`` first. A rate that a non-zero term needs but
  is NULL makes the whole calc **NULL** (unpriceable — the M1.14 missing-rates
  guard's signal), never silently 0. Material-category lines have no calc source
  in M1.7 (their calc needs geometry + stock pricing → M1.9/M4).

* **Recalculation never destroys human input:** recalc upserts ``calc_cost`` only;
  ``manual_cost`` is written exclusively by the estimator (CLAUDE.md §5). Cells for
  removed breaks/operations disappear via FK cascade; missing cells are created here.

* **Roll-up inputs (#costing):** per break, the effective cost
  ``COALESCE(manual_cost, calc_cost)`` of each row lands in exactly one bucket —
  material lines → Raw Material, outside-service rows → Outside Processing,
  everything else → Inside Processing. M1.10 turns these inputs into the five-
  category roll-up + pricing; amounts stay ``numeric(14,4)`` here (money decision
  2026-06-27: minor-unit rounding only at the quote-total boundary).
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CalculationMode, ComponentQuantity, OpCategory, Operation, QuoteCell, SetupBasis

_MINUTES_PER_HOUR = Decimal(60)
_CENT4 = Decimal("0.0001")  # numeric(14,4) — the unit-level money precision
_ZERO = Decimal(0)


def _quant(value: Decimal) -> Decimal:
    return value.quantize(_CENT4, rounding=ROUND_HALF_UP)


def _resolved_time(manual: Decimal | None, calc: Decimal | None) -> Decimal:
    """A time input resolves override-over-calculated; absent means zero minutes."""
    if manual is not None:
        return manual
    if calc is not None:
        return calc
    return _ZERO


def compute_calc_cost(op: Operation, make_quantity: int) -> Decimal | None:
    """The mode arithmetic for one operation at one break (Losgröße = make qty).

    Returns ``None`` when there is no internal calc: ``outside_process`` rows,
    material lines (no M1.7 calc source), or a missing rate that a non-zero term
    needs. ``None`` renders as "—" and contributes 0 to the roll-up inputs."""
    if op.category is OpCategory.material:
        return None
    if op.calculation_mode is CalculationMode.outside_process:
        return None

    runtime = _resolved_time(op.manual_runtime_mins, op.calc_runtime_mins)
    attend = _resolved_time(op.manual_attend_mins, op.calc_attend_mins)
    setup_mins = _resolved_time(op.manual_setup_mins, op.calc_setup_mins)

    # Setup: flat € per lot, or time-based at run_rate (the machine is blocked
    # during Rüsten — DECISIONS.md 2026-07-07 OPEN default).
    if op.setup_basis is SetupBasis.flat:
        setup = op.setup_cost if op.setup_cost is not None else _ZERO
    else:
        if setup_mins > 0 and op.run_rate is None:
            return None
        setup = setup_mins / _MINUTES_PER_HOUR * (op.run_rate or _ZERO)

    per_unit = _ZERO
    if runtime > 0:
        if op.run_rate is None:
            return None
        per_unit += runtime / _MINUTES_PER_HOUR * op.run_rate
    if op.calculation_mode is CalculationMode.machine_plus_operator and attend > 0:
        if op.labour_rate is None:
            return None
        per_unit += attend / _MINUTES_PER_HOUR * op.labour_rate

    total = setup + per_unit * Decimal(make_quantity)
    surcharge = Decimal(1) + op.surcharge_pct / Decimal(100)
    return _quant(total * surcharge)


def effective_cost(cell: QuoteCell) -> Decimal | None:
    """The COALESCE(manual, calc) resolution — the one rule everything reads."""
    return cell.manual_cost if cell.manual_cost is not None else cell.calc_cost


async def recalculate_component(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> None:
    """Recompute every ``calc_cost`` for a component and materialise missing cells.

    Idempotent and override-preserving: ``manual_cost`` is never read or written.
    Call after any change that can move a calc — op added/edited, breaks reshaped.
    (Cells of removed breaks/ops are gone already via FK cascade.)"""
    operations = (
        await session.scalars(select(Operation).where(Operation.component_id == component_id))
    ).all()
    breaks = (
        await session.scalars(
            select(ComponentQuantity).where(ComponentQuantity.component_id == component_id)
        )
    ).all()
    cells = (
        await session.scalars(select(QuoteCell).where(QuoteCell.component_id == component_id))
    ).all()
    by_key = {(cell.operation_id, cell.quantity): cell for cell in cells}

    for op in operations:
        for brk in breaks:
            make_qty = brk.make_quantity if brk.make_quantity is not None else brk.quantity
            calc = compute_calc_cost(op, make_qty)
            cell = by_key.get((op.id, brk.quantity))
            if cell is None:
                session.add(
                    QuoteCell(
                        org_id=org_id,
                        operation_id=op.id,
                        component_id=component_id,
                        quantity=brk.quantity,
                        calc_cost=calc,
                    )
                )
            elif cell.calc_cost != calc:
                cell.calc_cost = calc
    await session.flush()


class CostBucket(BaseModel):
    """Roll-up inputs for one quantity break (spec ``#costing`` cost categories —
    the M1.7 subset: purchased components + component overrides arrive at M4/M1.10)."""

    quantity: int
    material_total: Decimal
    inside_total: Decimal
    outside_total: Decimal
    total: Decimal
    # True when some row has neither a calc nor a manual cost — the missing-rates
    # signal (M1.14 banner); those rows contribute 0 above.
    has_unpriced_rows: bool


async def rollup_inputs(session: AsyncSession, component_id: uuid.UUID) -> list[CostBucket]:
    """Per-break totals of effective op cost, bucketed material/inside/outside."""
    operations = (
        await session.scalars(select(Operation).where(Operation.component_id == component_id))
    ).all()
    by_op = {op.id: op for op in operations}
    cells = (
        await session.scalars(select(QuoteCell).where(QuoteCell.component_id == component_id))
    ).all()
    quantities = sorted(
        (
            await session.scalars(
                select(ComponentQuantity.quantity).where(
                    ComponentQuantity.component_id == component_id
                )
            )
        ).all()
    )

    buckets: list[CostBucket] = []
    for qty in quantities:
        material = inside = outside = _ZERO
        unpriced = False
        for cell in cells:
            if cell.quantity != qty:
                continue
            op = by_op.get(cell.operation_id)
            if op is None:  # pragma: no cover — cascade removes cells with their op
                continue
            cost = effective_cost(cell)
            if cost is None:
                unpriced = True
                continue
            if op.category is OpCategory.material:
                material += cost
            elif op.is_outside_service:
                outside += cost
            else:
                inside += cost
        buckets.append(
            CostBucket(
                quantity=qty,
                material_total=_quant(material),
                inside_total=_quant(inside),
                outside_total=_quant(outside),
                total=_quant(material + inside + outside),
                has_unpriced_rows=unpriced,
            )
        )
    return buckets
