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
    (Cells of removed breaks/ops are gone already via FK cascade.)

    M1.9: an operation with a ``cost_formula`` snapshot gets its calc from Kalk
    instead of the mode arithmetic. Ops evaluate in **router order per quantity**
    so the workpiece dict and cost dictionary thread op → op; the Kalk batch is
    prefetched async, computed off the event loop, then applied (see
    ``app.kalk_costing``)."""
    from anyio import to_thread

    from . import kalk_costing
    from .models import Component

    operations = (
        await session.scalars(
            select(Operation)
            .where(Operation.component_id == component_id)
            .order_by(Operation.position, Operation.created_at, Operation.id)
        )
    ).all()
    breaks = sorted(
        (
            await session.scalars(
                select(ComponentQuantity).where(ComponentQuantity.component_id == component_id)
            )
        ).all(),
        key=lambda b: b.quantity,
    )
    cells = (
        await session.scalars(select(QuoteCell).where(QuoteCell.component_id == component_id))
    ).all()
    by_key = {(cell.operation_id, cell.quantity): cell for cell in cells}

    env: kalk_costing.KalkEnv | None = None
    if any(op.cost_formula for op in operations):
        component = await session.get(Component, component_id)
        assert component is not None
        env = await kalk_costing.load_kalk_env(session, component, list(breaks))

    def compute() -> tuple[
        dict[tuple[uuid.UUID, int], Decimal | None],
        dict[tuple[uuid.UUID, int], int | None],
        dict[uuid.UUID, kalk_costing.OpTimes],
    ]:
        """Pure batch over prefetched data — runs in a worker thread."""
        calcs: dict[tuple[uuid.UUID, int], Decimal | None] = {}
        cell_days: dict[tuple[uuid.UUID, int], int | None] = {}
        op_times: dict[uuid.UUID, kalk_costing.OpTimes] = {}
        for brk in breaks:
            make_qty = brk.make_quantity if brk.make_quantity is not None else brk.quantity
            deliver_qty = brk.deliver_quantity if brk.deliver_quantity is not None else brk.quantity
            workpiece: dict[str, object] = {}
            # evaluation-scoped working state, seeded fresh per break so
            # recalculation stays idempotent and matches the drawer report
            custom_attributes: dict[str, object] = (
                dict(env.part.custom_attributes) if env is not None else {}
            )
            cost_values: dict[str, float] = {
                "--material--": 0.0,
                "--inside--": 0.0,
                "--outside--": 0.0,
                "--total--": 0.0,
            }
            for op in operations:
                if op.cost_formula and env is not None:
                    cell_eval = kalk_costing.evaluate_cell(
                        env,
                        op,
                        brk.quantity,
                        make_qty,
                        deliver_qty,
                        workpiece,
                        cost_values,
                        custom_attributes,
                    )
                    calc = cell_eval.calc_cost
                    cell_days[(op.id, brk.quantity)] = cell_eval.days
                    workpiece = cell_eval.workpiece
                    custom_attributes.update(cell_eval.custom_attributes)
                    if op.id not in op_times:  # lowest break = the row display pair
                        op_times[op.id] = kalk_costing.OpTimes(
                            runtime_mins=kalk_costing.hours_to_mins(cell_eval.runtime_hours),
                            runtime_overridden=cell_eval.runtime_overridden,
                            setup_mins=kalk_costing.hours_to_mins(cell_eval.setup_hours),
                            setup_overridden=cell_eval.setup_overridden,
                        )
                else:
                    calc = compute_calc_cost(op, make_qty)
                    cell_days[(op.id, brk.quantity)] = None  # mode rows carry no DAYS
                calcs[(op.id, brk.quantity)] = calc
                # the downstream cost dictionary sees this op's EFFECTIVE cost
                existing = by_key.get((op.id, brk.quantity))
                manual = existing.manual_cost if existing is not None else None
                effective = manual if manual is not None else calc
                if effective is not None:
                    amount = float(effective)
                    cost_values[op.name] = cost_values.get(op.name, 0.0) + amount
                    # KALK-REFERENCE §7: the key matches the op name OR its def name
                    def_name = (
                        env.def_names.get(op.operation_def_id)
                        if env is not None and op.operation_def_id is not None
                        else None
                    )
                    if def_name and def_name != op.name:
                        cost_values[def_name] = cost_values.get(def_name, 0.0) + amount
                    if op.category is OpCategory.material:
                        cost_values["--material--"] += amount
                    elif op.is_outside_service:
                        cost_values["--outside--"] += amount
                    else:
                        cost_values["--inside--"] += amount
                    cost_values["--total--"] += amount
        return calcs, cell_days, op_times

    calcs, cell_days, op_times = await to_thread.run_sync(compute)

    for op in operations:
        times = op_times.get(op.id)
        if times is not None:
            # Formula-computed times only: an applied manual override leaves the
            # calc side untouched (never contaminate the calc-vs-manual pair);
            # otherwise assign even None, so stale times from an earlier formula
            # are cleared rather than surviving edits.
            if not times.runtime_overridden:
                op.calc_runtime_mins = times.runtime_mins
            if not times.setup_overridden:
                op.calc_setup_mins = times.setup_mins

    for (op_id, quantity), calc in calcs.items():
        days = cell_days.get((op_id, quantity))
        cell = by_key.get((op_id, quantity))
        if cell is None:
            session.add(
                QuoteCell(
                    org_id=org_id,
                    operation_id=op_id,
                    component_id=component_id,
                    quantity=quantity,
                    calc_cost=calc,
                    days=days,
                )
            )
        else:
            if cell.calc_cost != calc:
                cell.calc_cost = calc
            if cell.days != days:
                cell.days = days
    await session.flush()

    # M1.10: pricing always follows costs — every cost recalc re-runs the
    # roll-up + pricing items + discounts (calc side only; overrides survive).
    from . import pricing

    await pricing.reprice_component(session, org_id, component_id)


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
