"""Kalk → costing wiring (M1.9): formula-driven ``calc_cost``.

An operation carrying a ``cost_formula`` snapshot gets its per-break calc from
the Kalk evaluator instead of the M1.7 mode arithmetic (DECISIONS.md
2026-07-07 "Calculated source", 2026-07-08 M1.9 grill decisions):

* **Money boundary:** Kalk outputs a float; it converts via ``repr`` →
  ``Decimal`` quantized to 4 dp ROUND_HALF_UP (``numeric(14,4)``) — the same
  ``_quant`` the mode arithmetic uses; integer minor units appear only at the
  quote-total boundary (M1.10/M1.11).
* **Time boundary:** persisted minutes ↔ formula hours. ``manual_*_mins``
  overrides enter as ``runtime``/``setup_time`` overrides in hours; a
  formula's frozen ``runtime``/``setup_time`` write back to
  ``calc_runtime_mins``/``calc_setup_mins`` in minutes (the lowest break's
  values — the row-level display pair; per-break times stay inside Kalk via
  ``quantity_specific`` vars).
* **Data flow:** ops evaluate in router order per quantity; the workpiece
  dict and the cost dictionary (upstream effective costs, incl. the
  ``--material--``/``--inside--``/``--outside--``/``--total--`` specials)
  thread op → op. ``set_custom_attribute`` persists to
  ``part.custom_attributes``.
* **Row modifiers stay #oplibrary-owned:** ``surcharge_pct`` applies on the
  formula's COST like on the mode arithmetic; material lines additionally
  gross up by ``1 / yield_factor`` (scrap — the M1.7 decision's "once a calc
  source exists"). Assumption noted: a formula author writes net COST.
* Table data is **prefetched** into an in-memory provider (all org custom
  tables, RLS-scoped) so evaluation stays synchronous, deterministic, and
  compatible with a future subprocess executor. Evaluation runs off the event
  loop via ``anyio.to_thread``.

``DAYS`` is validated but not persisted until M1.11 (quote_cell carries no
``days`` — M1.7 decision). Evaluation errors blank the cell (``calc_cost
NULL`` = unpriceable, the M1.14 signal); the drawer surfaces them via
``GET /api/operations/{id}/kalk``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Component,
    ComponentQuantity,
    CustomTable,
    CustomTableRow,
    Material,
    MaterialFamily,
    OpCategory,
    Operation,
    OperationDef,
    Part,
    PartGeometry,
    QuoteItem,
)
from .services.kalk import (
    ContextData,
    EvalResult,
    KalkObject,
    MappingTableProvider,
    TableColumn,
    TableSnapshot,
    evaluate,
)

_CENT4 = Decimal("0.0001")
_MIN4 = Decimal("0.0001")
_MINUTES_PER_HOUR = 60.0


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


async def load_table_provider(session: AsyncSession) -> MappingTableProvider:
    """Snapshot every org custom table (RLS-scoped session ⇒ org-scoped data)."""
    tables = (await session.scalars(select(CustomTable))).all()
    rows = (await session.scalars(select(CustomTableRow).order_by(CustomTableRow.row_number))).all()
    rows_by_table: dict[uuid.UUID, list[tuple[int, dict[str, Any]]]] = {}
    for row in rows:
        rows_by_table.setdefault(row.table_id, []).append((row.row_number, dict(row.data)))
    return MappingTableProvider(
        {
            table.name: TableSnapshot(
                name=table.name,
                columns=tuple(
                    TableColumn(name=col["name"], type=col["type"]) for col in table.columns
                ),
                rows=tuple(rows_by_table.get(table.id, [])),
            )
            for table in tables
        }
    )


@dataclass
class KalkEnv:
    """Everything a component's Kalk evaluations read, prefetched async."""

    provider: MappingTableProvider
    part: Part
    geometry: PartGeometry | None
    material: Material | None
    material_family: MaterialFamily | None
    component: Component
    export_controlled: bool
    quantities: list[int] = field(default_factory=list)  # deliver (bom) quantities
    make_quantities: list[int] = field(default_factory=list)
    def_names: dict[uuid.UUID, str] = field(default_factory=dict)


async def load_kalk_env(
    session: AsyncSession, component: Component, breaks: list[ComponentQuantity]
) -> KalkEnv:
    part = await session.get(Part, component.part_id)
    assert part is not None  # FK-guaranteed
    geometry = await session.scalar(select(PartGeometry).where(PartGeometry.part_id == part.id))
    material = (
        await session.get(Material, component.material_id)
        if component.material_id is not None
        else None
    )
    material_family = (
        await session.get(MaterialFamily, material.family_id) if material is not None else None
    )
    export_controlled = bool(
        await session.scalar(
            select(QuoteItem.export_controlled).where(QuoteItem.root_component_id == component.id)
        )
    )
    def_rows = (await session.execute(select(OperationDef.id, OperationDef.name))).tuples().all()
    ordered = sorted(breaks, key=lambda b: b.quantity)
    return KalkEnv(
        provider=await load_table_provider(session),
        part=part,
        geometry=geometry,
        material=material,
        material_family=material_family,
        component=component,
        export_controlled=export_controlled,
        quantities=[
            b.deliver_quantity if b.deliver_quantity is not None else b.quantity for b in ordered
        ],
        make_quantities=[
            b.make_quantity if b.make_quantity is not None else b.quantity for b in ordered
        ],
        def_names=dict(def_rows),
    )


def build_part_object(env: KalkEnv, make_qty: int, deliver_qty: int) -> KalkObject:
    """The ``part`` object per the PartGeometry catalog (metric mm/g; the M1.5
    manual subset — interrogation-only attributes stay absent until M4)."""
    geo = env.geometry
    dims = [
        _f(geo.size_x) if geo else None,
        _f(geo.size_y) if geo else None,
        _f(geo.size_z) if geo else None,
    ]
    present = sorted((d for d in dims if d is not None), reverse=True)
    return KalkObject(
        "part",
        {
            "size_x": dims[0],
            "size_y": dims[1],
            "size_z": dims[2],
            "max_dim": _f(geo.max_dim)
            if geo and geo.max_dim is not None
            else (present[0] if present else None),
            "med_dim": _f(geo.med_dim)
            if geo and geo.med_dim is not None
            else (present[1] if len(present) > 1 else None),
            "min_dim": _f(geo.min_dim)
            if geo and geo.min_dim is not None
            else (present[-1] if present else None),
            "area": _f(geo.area) if geo else None,
            "volume": _f(geo.volume) if geo else None,
            "weight": _f(geo.weight) if geo else None,
            "density": _f(env.material.density) if env.material is not None else None,
            "mat_cost_per_volume": (
                _f(env.material.cost_per_volume) if env.material is not None else None
            ),
            "material": env.material.display_name if env.material is not None else None,
            "material_family": (
                env.material_family.name if env.material_family is not None else None
            ),
            "qty": make_qty,
            "bom_qty": deliver_qty,
            "innate_quantity": 1,  # root component (children arrive with M4)
            "quantities": env.quantities.copy(),
            "make_quantities": env.make_quantities.copy(),
            "bom_quantities": env.quantities.copy(),
            "part_number": env.part.part_number,
            "revision": env.part.revision,
            "is_root_component": env.component.is_root_component,
            "is_assembly": env.component.is_assembly,
            "obtain_method": env.component.obtain_method.value.upper(),
            "count_manufactured_children": 0,  # BOM children are M4
            "count_purchased_children": 0,
            "purchased_component": None,
        },
    )


@dataclass
class CellEval:
    calc_cost: Decimal | None
    workpiece: dict[str, Any]
    custom_attributes: dict[str, Any]
    runtime_hours: float | None
    setup_hours: float | None
    errors: list[dict[str, Any]]
    no_quote: bool


def kalk_output_to_calc(op: Operation, cost: float) -> Decimal:
    """Float COST → numeric(14,4) with the #oplibrary row modifiers applied."""
    value = Decimal(repr(cost))
    value *= Decimal(1) + op.surcharge_pct / Decimal(100)
    if op.category is OpCategory.material and op.yield_factor != Decimal(1):
        value /= op.yield_factor  # scrap gross-up: net material / yield
    return value.quantize(_CENT4, rounding=ROUND_HALF_UP)


def _declared_value(result: EvalResult, name: str) -> float | None:
    for declaration in result.declared_variables:
        if declaration["name"] == name:
            value = declaration.get("value")
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
    return None


def evaluate_cell(
    env: KalkEnv,
    op: Operation,
    make_qty: int,
    deliver_qty: int,
    workpiece: dict[str, Any],
    cost_values: dict[str, float],
    custom_attributes: dict[str, Any],
) -> CellEval:
    """One (operation x quantity) evaluation — pure/synchronous (thread-safe)."""
    assert op.cost_formula is not None
    overrides: dict[str, Any] = dict(op.variable_overrides or {})
    # the runtime/setup_time specials override via the M1.7 manual_*_mins pair
    if op.manual_runtime_mins is not None:
        overrides["runtime"] = float(op.manual_runtime_mins) / _MINUTES_PER_HOUR
    if op.manual_setup_mins is not None:
        overrides["setup_time"] = float(op.manual_setup_mins) / _MINUTES_PER_HOUR

    def_name = env.def_names.get(op.operation_def_id) if op.operation_def_id else None
    result = evaluate(
        op.cost_formula,
        context_type="operation_cost",
        eval_context={
            "part": build_part_object(env, make_qty, deliver_qty),
            "op_def": KalkObject("op_def", {"name": def_name or op.name, "erp_code": None}),
            "line_item": KalkObject("line_item", {"is_export_controlled": env.export_controlled}),
        },
        quantity=make_qty,
        overrides=overrides,
        table_provider=env.provider,
        context_data=ContextData(
            quantities=env.quantities.copy(),
            make_quantities=env.make_quantities.copy(),
            bom_quantities=env.quantities.copy(),
            cost_values=dict(cost_values),
            workpiece=dict(workpiece),
            custom_attributes=dict(custom_attributes),
        ),
    )

    errors = [
        {"code": e.code, "message": e.message, "line": e.line, "col": e.col} for e in result.errors
    ]
    calc: Decimal | None = None
    no_quote = False
    if not errors and result.output is not None:
        if result.output.get("no_quote"):
            no_quote = True  # blank the cell deliberately (KALK-REFERENCE §11.1)
        else:
            calc = kalk_output_to_calc(op, result.output["COST"])
    return CellEval(
        calc_cost=calc,
        workpiece=result.workpiece,
        custom_attributes=result.custom_attributes,
        runtime_hours=_declared_value(result, "runtime"),
        setup_hours=_declared_value(result, "setup_time"),
        errors=errors,
        no_quote=no_quote,
    )


def hours_to_mins(hours: float | None) -> Decimal | None:
    if hours is None:
        return None
    return (Decimal(repr(hours)) * Decimal(60)).quantize(_MIN4, rounding=ROUND_HALF_UP)


async def operation_kalk_report(
    session: AsyncSession,
    component: Component,
    operation: Operation,
    operations: list[Operation],
    breaks: list[ComponentQuantity],
    cells: list[Any],
) -> list[dict[str, Any]]:
    """The drawer's per-break evaluation report for ONE operation's formula.

    Threads the same router-order state recalc uses — cost dictionary from the
    persisted cells' effective costs, workpiece from re-evaluating upstream
    formula ops — then returns the target op's full evaluation (declared
    variables, groups, applied overrides, output, errors) per quantity break.
    """
    assert operation.cost_formula is not None
    env = await load_kalk_env(session, component, breaks)
    effective_by_key: dict[tuple[uuid.UUID, int], Decimal | None] = {
        (c.operation_id, c.quantity): (c.manual_cost if c.manual_cost is not None else c.calc_cost)
        for c in cells
    }

    reports: list[dict[str, Any]] = []
    for brk in sorted(breaks, key=lambda b: b.quantity):
        make_qty = brk.make_quantity if brk.make_quantity is not None else brk.quantity
        deliver_qty = brk.deliver_quantity if brk.deliver_quantity is not None else brk.quantity
        workpiece: dict[str, Any] = {}
        cost_values: dict[str, float] = {
            "--material--": 0.0,
            "--inside--": 0.0,
            "--outside--": 0.0,
            "--total--": 0.0,
        }
        custom_attributes = dict(env.part.custom_attributes)
        for op in operations:
            if op.id == operation.id:
                break
            if op.cost_formula:  # rebuild the workpiece state this op would see
                upstream = evaluate_cell(
                    env, op, make_qty, deliver_qty, workpiece, cost_values, custom_attributes
                )
                workpiece = upstream.workpiece
                custom_attributes.update(upstream.custom_attributes)
            effective = effective_by_key.get((op.id, brk.quantity))
            if effective is not None:
                amount = float(effective)
                cost_values[op.name] = cost_values.get(op.name, 0.0) + amount
                def_name = (
                    env.def_names.get(op.operation_def_id)
                    if op.operation_def_id is not None
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

        overrides: dict[str, Any] = dict(operation.variable_overrides or {})
        if operation.manual_runtime_mins is not None:
            overrides["runtime"] = float(operation.manual_runtime_mins) / _MINUTES_PER_HOUR
        if operation.manual_setup_mins is not None:
            overrides["setup_time"] = float(operation.manual_setup_mins) / _MINUTES_PER_HOUR
        def_name = (
            env.def_names.get(operation.operation_def_id) if operation.operation_def_id else None
        )
        result = evaluate(
            operation.cost_formula,
            context_type="operation_cost",
            eval_context={
                "part": build_part_object(env, make_qty, deliver_qty),
                "op_def": KalkObject(
                    "op_def", {"name": def_name or operation.name, "erp_code": None}
                ),
                "line_item": KalkObject(
                    "line_item", {"is_export_controlled": env.export_controlled}
                ),
            },
            quantity=make_qty,
            overrides=overrides,
            table_provider=env.provider,
            context_data=ContextData(
                quantities=env.quantities.copy(),
                make_quantities=env.make_quantities.copy(),
                bom_quantities=env.quantities.copy(),
                cost_values=cost_values,
                workpiece=workpiece,
                custom_attributes=custom_attributes,
            ),
        )
        reports.append(
            {
                "quantity": brk.quantity,
                "output": result.output,
                "declared_variables": result.declared_variables,
                "variable_groups": result.variable_groups,
                "applied_overrides": result.applied_overrides,
                "notes": result.notes,
                "operation_name": result.operation_name,
                "errors": [
                    {"code": e.code, "message": e.message, "line": e.line, "col": e.col}
                    for e in result.errors
                ],
            }
        )
    return reports
