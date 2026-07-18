"""Operation library + component Materials & Operations API (M1.7).

Spec ``#partview`` (Materials · Operations), ``#oplibrary`` (library + picker
behaviours), ``#costing`` (roll-up inputs); decisions DECISIONS.md 2026-07-07.

Surface:

* ``/api/operation-defs`` — the org library: type-ahead list + explicit create
  (library management pages are M1.12; ``config_edit``).
* ``/api/components/{id}/operations`` — attach a row from the library **or**
  inline (an inline name unknown to the library is **auto-saved** to it — the
  library grows from real quoting activity, ``#oplibrary`` Auto-save).
* ``/api/operations/{id}`` — edit (drawer: overrides, rates, notes), duplicate,
  remove (removes from this part only — never from the library), reorder.
* ``/api/operations/{id}/cells/{qty}`` — set/clear the per-qty **manual cost**
  override (the Calculated-vs-Override pair; ``calc_cost`` is engine-owned).
* ``/api/components/{id}/costing`` — the panel read: rows + per-qty cells +
  roll-up inputs.
* ``/api/components/{id}/material`` / ``…/process`` — the header assignments;
  Change Process ships both commits (UPDATE deletes existing operations — router
  regeneration is a no-op until M4; UPDATE AND KEEP EXISTING OPS preserves them).

Every mutation locks the owning quote first and gates on Draft editability (the
M1.4/M1.6 TOCTOU pattern), then recalculates the component's calc cells —
``manual_*`` values are never touched by recalc (CLAUDE.md §5)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .config_completeness import material_missing_cost, operation_missing_rate
from .costing import CostBucket, effective_cost, recalculate_component, rollup_inputs
from .deps import get_session
from .errors import AppError
from .kalk_costing import operation_kalk_report
from .models import (
    CalculationMode,
    Component,
    ComponentQuantity,
    Material,
    OpCategory,
    Operation,
    OperationDef,
    Process,
    Quote,
    QuoteCell,
    QuoteItem,
    QuoteStatus,
    SetupBasis,
    ValueSource,
)
from .services import kalk

operations_router = APIRouter(prefix="/api", tags=["operations"])

#: Type-ahead page bound (the picker narrows by search; ``#oplibrary`` ≤50).
SEARCH_LIMIT = 50


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class OperationDefOut(BaseModel):
    id: uuid.UUID
    name: str
    category: OpCategory
    calculation_mode: CalculationMode
    run_rate: Decimal | None
    labour_rate: Decimal | None
    setup_basis: SetupBasis
    setup_cost: Decimal | None
    setup_time_mins: Decimal | None
    surcharge_pct: Decimal
    is_outside_service: bool
    is_finish: bool
    is_pre_installed: bool
    sort_order: int
    cost_formula: str | None


class OperationDefCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    category: OpCategory = OpCategory.operation
    calculation_mode: CalculationMode = CalculationMode.machine_plus_operator
    run_rate: Annotated[Decimal | None, Field(ge=0)] = None
    labour_rate: Annotated[Decimal | None, Field(ge=0)] = None
    setup_basis: SetupBasis = SetupBasis.flat
    setup_cost: Annotated[Decimal | None, Field(ge=0)] = None
    setup_time_mins: Annotated[Decimal | None, Field(ge=0)] = None
    surcharge_pct: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(0)
    is_outside_service: bool = False
    is_finish: bool = False
    cost_formula: Annotated[str | None, Field(max_length=100_000)] = None


class OperationDefUpdate(BaseModel):
    """Configure-side def edit — the M1.14 per-operation rate table plus the
    M1.9 Kalk editor. Absent fields stay unchanged (``exclude_unset``); an
    explicit ``null`` clears the nullable ones (``cost_formula: null`` falls
    the op back to its mode arithmetic on future attaches). Existing quote
    operations keep their snapshot (E4-d config-freeze)."""

    model_config = ConfigDict(extra="forbid")

    # NOT NULL columns exclude None (explicit null = clean 422, the M1.7
    # OperationUpdate precedent); their defaults are inert placeholders under
    # exclude_unset. Nullable columns accept an explicit null to clear.
    name: Annotated[str, Field(min_length=1, max_length=200)] = "unset"
    calculation_mode: CalculationMode = CalculationMode.machine_plus_operator
    run_rate: Annotated[Decimal | None, Field(ge=0)] = None
    labour_rate: Annotated[Decimal | None, Field(ge=0)] = None
    setup_basis: SetupBasis = SetupBasis.flat
    setup_cost: Annotated[Decimal | None, Field(ge=0)] = None
    setup_time_mins: Annotated[Decimal | None, Field(ge=0)] = None
    surcharge_pct: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(0)
    cost_formula: Annotated[str | None, Field(max_length=100_000)] = None


class QuoteCellOut(BaseModel):
    quantity: int
    calc_cost: Decimal | None
    manual_cost: Decimal | None
    effective_cost: Decimal | None


class OperationOut(BaseModel):
    id: uuid.UUID
    operation_def_id: uuid.UUID | None
    name: str
    category: OpCategory
    position: int
    calculation_mode: CalculationMode
    run_rate: Decimal | None
    labour_rate: Decimal | None
    setup_basis: SetupBasis
    setup_cost: Decimal | None
    calc_setup_mins: Decimal | None
    manual_setup_mins: Decimal | None
    calc_runtime_mins: Decimal | None
    manual_runtime_mins: Decimal | None
    calc_attend_mins: Decimal | None
    manual_attend_mins: Decimal | None
    surcharge_pct: Decimal
    yield_factor: Decimal
    is_outside_service: bool
    is_finish: bool
    is_from_factory: bool
    notes: str | None
    cost_formula: str | None
    variable_overrides: dict[str, Any]
    # M4.13 provenance (spec #ai-quote-assembly): drives the "importiert aus
    # Angebot #N" badge in the variable drawer.
    source: ValueSource
    source_quote_id: uuid.UUID | None
    # M1.14 #missing-rates-warning: this row's rate resolves to nothing — the
    # amber inline highlight (deterministic, computed from the same rule as
    # the Configure banner)
    missing_rate: bool
    cells: list[QuoteCellOut]


class OperationCreate(BaseModel):
    """Attach an operation to a component: from the library (``operation_def_id``)
    or inline by name (auto-saved to the library when the name is new)."""

    model_config = ConfigDict(extra="forbid")

    operation_def_id: uuid.UUID | None = None
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    category: OpCategory = OpCategory.operation
    calculation_mode: CalculationMode = CalculationMode.machine_plus_operator
    run_rate: Annotated[Decimal | None, Field(ge=0)] = None
    labour_rate: Annotated[Decimal | None, Field(ge=0)] = None
    setup_basis: SetupBasis = SetupBasis.flat
    setup_cost: Annotated[Decimal | None, Field(ge=0)] = None
    setup_time_mins: Annotated[Decimal | None, Field(ge=0)] = None
    surcharge_pct: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(0)
    is_outside_service: bool = False
    is_finish: bool = False


class OperationUpdate(BaseModel):
    """The drawer edit: overrides (``manual_*``; ``None`` clears back to
    Calculated), per-quote config, and notes. ``calc_*`` fields are engine-owned.

    Nullability mirrors the columns: the nullable fields accept an explicit
    ``null`` to clear, but ``surcharge_pct``/``yield_factor``/``name`` are NOT
    NULL in the DB, so their types exclude ``None`` — an explicit ``null`` is a
    clean 422, never a 500 (Greptile M1.7 review). The handler applies
    ``exclude_unset``, so their defaults here are inert placeholders: an absent
    field always means "leave unchanged", to reset send the DB default
    (surcharge ``0``, yield ``1``)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)] = "unset"
    calculation_mode: CalculationMode = CalculationMode.machine_plus_operator
    run_rate: Annotated[Decimal | None, Field(ge=0)] = None
    labour_rate: Annotated[Decimal | None, Field(ge=0)] = None
    setup_basis: SetupBasis = SetupBasis.flat
    setup_cost: Annotated[Decimal | None, Field(ge=0)] = None
    manual_setup_mins: Annotated[Decimal | None, Field(ge=0)] = None
    manual_runtime_mins: Annotated[Decimal | None, Field(ge=0)] = None
    manual_attend_mins: Annotated[Decimal | None, Field(ge=0)] = None
    surcharge_pct: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(0)
    yield_factor: Annotated[Decimal, Field(gt=0, le=1)] = Decimal(1)
    is_outside_service: bool = False
    is_finish: bool = False
    notes: Annotated[str | None, Field(max_length=10_000)] = None
    # Kalk (M1.9): edits this quote's snapshot only (never the library def);
    # an explicit null falls the op back to its mode arithmetic.
    cost_formula: Annotated[str | None, Field(max_length=100_000)] = None


class VariableOverridesUpdate(BaseModel):
    """Replace an operation's Kalk variable overrides (DECISIONS.md 2026-07-08):
    ``{name: value}`` for plain vars, ``{name: {"<qty>": value}}`` for
    quantity-specific ones. The evaluator validates types/membership per
    variable at recalc; this schema only enforces the shape."""

    model_config = ConfigDict(extra="forbid")

    overrides: dict[
        str,
        bool | int | float | str | dict[str, bool | int | float | str],
    ]


class OperationOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_ids: Annotated[list[uuid.UUID], Field(min_length=1)]


class CellUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_cost: Annotated[Decimal | None, Field(ge=0)] = None


class ComponentMaterialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: uuid.UUID | None  # None = the picker's "clear"


class ComponentProcessUpdate(BaseModel):
    """Change Process. ``keep_operations=False`` is the modal's UPDATE (deletes
    all existing operations; router regeneration is a no-op until M4);
    ``True`` is UPDATE AND KEEP EXISTING OPS."""

    model_config = ConfigDict(extra="forbid")

    process_id: uuid.UUID | None
    keep_operations: bool = False


class ComponentCosting(BaseModel):
    component_id: uuid.UUID
    material_id: uuid.UUID | None
    process_id: uuid.UUID | None
    quantities: list[int]
    operations: list[OperationOut]
    buckets: list[CostBucket]
    # M1.14: any router row on this component resolves to no rate
    has_missing_rates: bool = False


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _get_component_or_404(session: AsyncSession, component_id: uuid.UUID) -> Component:
    component = await session.get(Component, component_id)
    if component is None:
        raise AppError("not_found", "Component not found.", status_code=status.HTTP_404_NOT_FOUND)
    return component


def _quote_is_editable(quote: Quote) -> bool:
    # Same rules as app.quotes._is_editable (kept private there): Draft, or
    # On-Hold entered from Draft; never trashed.
    if quote.deleted_at is not None:
        return False
    if quote.status is QuoteStatus.draft:
        return True
    return quote.status is QuoteStatus.on_hold and quote.status_before_hold is QuoteStatus.draft


async def _lock_editable_quote(session: AsyncSession, component: Component) -> Quote:
    """Lock the quote owning this component and gate on Draft editability.

    M1-era operations live on root components (children arrive with M4's BOM
    Builder — this helper then walks to the root). Locking FOR UPDATE first makes
    the editability check race-free against a concurrent transition/trash
    (the M1.4 pattern)."""
    quote_id = await session.scalar(
        select(QuoteItem.quote_id).where(QuoteItem.root_component_id == component.id)
    )
    if quote_id is None:
        raise AppError(
            "not_found",
            "Component is not attached to a quote line item.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    quote = await session.scalar(
        select(Quote)
        .where(Quote.id == quote_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if quote is None:  # pragma: no cover — FK guarantees the row exists
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    if not _quote_is_editable(quote):
        raise AppError(
            "quote_locked",
            "Materials and operations can only be changed while the quote is a draft.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return quote


def _validate_formula(formula: str) -> None:
    """Saving an invalid Kalk formula is a clean 422 with positioned errors
    (acceptance: the editor rejects invalid Kalk with a clear error)."""
    result = kalk.check(formula, context_type="operation_cost")
    if not result.ok:
        raise AppError(
            "invalid_formula",
            "The Kalk formula is invalid.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=[
                {"code": e.code, "message": e.message, "line": e.line, "col": e.col}
                for e in result.errors
            ],
        )


def _def_out(op_def: OperationDef) -> OperationDefOut:
    return OperationDefOut(
        id=op_def.id,
        name=op_def.name,
        category=op_def.category,
        calculation_mode=op_def.calculation_mode,
        run_rate=op_def.run_rate,
        labour_rate=op_def.labour_rate,
        setup_basis=op_def.setup_basis,
        setup_cost=op_def.setup_cost,
        setup_time_mins=op_def.setup_time_mins,
        surcharge_pct=op_def.surcharge_pct,
        is_outside_service=op_def.is_outside_service,
        is_finish=op_def.is_finish,
        is_pre_installed=op_def.is_pre_installed,
        sort_order=op_def.sort_order,
        cost_formula=op_def.cost_formula,
    )


def _operation_out(op: Operation, cells: list[QuoteCell]) -> OperationOut:
    cell_out = [
        QuoteCellOut(
            quantity=cell.quantity,
            calc_cost=cell.calc_cost,
            manual_cost=cell.manual_cost,
            effective_cost=effective_cost(cell),
        )
        for cell in sorted(cells, key=lambda c: c.quantity)
    ]
    return OperationOut(
        id=op.id,
        operation_def_id=op.operation_def_id,
        name=op.name,
        category=op.category,
        position=op.position,
        calculation_mode=op.calculation_mode,
        run_rate=op.run_rate,
        labour_rate=op.labour_rate,
        setup_basis=op.setup_basis,
        setup_cost=op.setup_cost,
        calc_setup_mins=op.calc_setup_mins,
        manual_setup_mins=op.manual_setup_mins,
        calc_runtime_mins=op.calc_runtime_mins,
        manual_runtime_mins=op.manual_runtime_mins,
        calc_attend_mins=op.calc_attend_mins,
        manual_attend_mins=op.manual_attend_mins,
        surcharge_pct=op.surcharge_pct,
        yield_factor=op.yield_factor,
        is_outside_service=op.is_outside_service,
        is_finish=op.is_finish,
        is_from_factory=op.is_from_factory,
        notes=op.notes,
        cost_formula=op.cost_formula,
        variable_overrides=op.variable_overrides,
        source=op.source,
        source_quote_id=op.source_quote_id,
        missing_rate=operation_missing_rate(op),
        cells=cell_out,
    )


async def _component_costing(session: AsyncSession, component: Component) -> ComponentCosting:
    operations = (
        await session.scalars(
            select(Operation)
            .where(Operation.component_id == component.id)
            .order_by(Operation.position, Operation.created_at, Operation.id)
        )
    ).all()
    cells = (
        await session.scalars(select(QuoteCell).where(QuoteCell.component_id == component.id))
    ).all()
    cells_by_op: dict[uuid.UUID, list[QuoteCell]] = {}
    for cell in cells:
        cells_by_op.setdefault(cell.operation_id, []).append(cell)
    quantities = sorted(
        (
            await session.scalars(
                select(ComponentQuantity.quantity).where(
                    ComponentQuantity.component_id == component.id
                )
            )
        ).all()
    )
    rows = [_operation_out(op, cells_by_op.get(op.id, [])) for op in operations]
    material = (
        await session.get(Material, component.material_id)
        if component.material_id is not None
        else None
    )
    return ComponentCosting(
        component_id=component.id,
        material_id=component.material_id,
        process_id=component.process_id,
        quantities=list(quantities),
        operations=rows,
        buckets=await rollup_inputs(session, component.id),
        has_missing_rates=(
            any(row.missing_rate for row in rows) or material_missing_cost(material)
        ),
    )


async def attach_operation_from_def(
    session: AsyncSession,
    org_id: uuid.UUID,
    component: Component,
    op_def: OperationDef,
    *,
    added_manually: bool = True,
) -> Operation:
    """Append ``op_def`` to the bottom of ``component``'s router.

    Config is **copied** from the def at attach time: a later library edit never
    silently reprices an existing quote (config-freeze posture, E4-d) —
    including the Kalk formula snapshot (DECISIONS.md 2026-07-08).

    Shared by the estimator's manual add (``add_operation``) and M3.8's
    ADD_OPERATION resolution (``app.review_items``), which is the same act — §3
    says the resolution "appends the specified operation(s) to the bottom of the
    router" — so both must freeze config identically. The caller owns the
    editability lock and the follow-up ``recalculate_component``.

    ``added_manually`` (M3.10) records provenance: the default ``True`` is the
    estimator's direct add (the pattern the rule-suggestion detector learns
    from); the rule resolution passes ``False`` so an auto-added op is never
    mistaken for tribal knowledge (spec ``#ai-rule-suggest``).
    """
    operation = Operation(
        org_id=org_id,
        component_id=component.id,
        operation_def_id=op_def.id,
        name=op_def.name,
        category=op_def.category,
        added_manually=added_manually,
        position=await _next_position(session, component.id),
        calculation_mode=op_def.calculation_mode,
        run_rate=op_def.run_rate,
        labour_rate=op_def.labour_rate,
        setup_basis=op_def.setup_basis,
        setup_cost=op_def.setup_cost,
        cost_formula=op_def.cost_formula,
        calc_setup_mins=op_def.setup_time_mins,
        # Outside-process defs are outside services by construction.
        is_outside_service=(
            op_def.is_outside_service or op_def.calculation_mode == CalculationMode.outside_process
        ),
        is_finish=op_def.is_finish,
        surcharge_pct=op_def.surcharge_pct,
    )
    session.add(operation)
    await session.flush()
    return operation


async def _next_position(session: AsyncSession, component_id: uuid.UUID) -> int:
    max_position = await session.scalar(
        select(func.max(Operation.position)).where(Operation.component_id == component_id)
    )
    return (max_position or 0) + 1


async def _get_operation_or_404(session: AsyncSession, operation_id: uuid.UUID) -> Operation:
    operation = await session.get(Operation, operation_id)
    if operation is None:
        raise AppError("not_found", "Operation not found.", status_code=status.HTTP_404_NOT_FOUND)
    return operation


# --------------------------------------------------------------------------- #
# Operation library (org-wide defs)
# --------------------------------------------------------------------------- #
@operations_router.get("/operation-defs")
async def list_operation_defs(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    q: Annotated[str | None, Query(max_length=100)] = None,
    is_finish: Annotated[bool | None, Query()] = None,
) -> list[OperationDefOut]:
    """The picker's type-ahead: live defs, case-insensitive substring on name.
    ``is_finish=true`` narrows to finish operations — the source for the estimating
    band's REQUESTED FINISHES multi-select (M5.0 #partview)."""
    stmt = select(OperationDef).where(OperationDef.deleted_at.is_(None))
    if q:
        stmt = stmt.where(OperationDef.name.ilike(f"%{q}%"))
    if is_finish is not None:
        stmt = stmt.where(OperationDef.is_finish.is_(is_finish))
    defs = (
        await session.scalars(
            stmt.order_by(OperationDef.sort_order, OperationDef.name).limit(SEARCH_LIMIT)
        )
    ).all()
    return [_def_out(op_def) for op_def in defs]


@operations_router.post("/operation-defs", status_code=status.HTTP_201_CREATED)
async def create_operation_def(
    payload: OperationDefCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> OperationDefOut:
    duplicate = await session.scalar(
        select(OperationDef.id).where(
            OperationDef.name == payload.name, OperationDef.deleted_at.is_(None)
        )
    )
    if duplicate is not None:
        raise AppError(
            "duplicate_operation",
            "An operation with this name already exists in the library.",
            status_code=status.HTTP_409_CONFLICT,
        )
    if payload.cost_formula is not None:
        _validate_formula(payload.cost_formula)
    op_def = OperationDef(org_id=principal.active_org_id, **payload.model_dump())
    session.add(op_def)
    await session.flush()
    return _def_out(op_def)


@operations_router.patch("/operation-defs/{def_id}")
async def update_operation_def(
    def_id: uuid.UUID,
    payload: OperationDefUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> OperationDefOut:
    """The Configure-side def edit (rates table + Kalk editor). Existing quote
    operations keep their snapshot (E4-d config-freeze) — only future attaches
    see the change."""
    op_def = await session.get(OperationDef, def_id)
    if op_def is None or op_def.deleted_at is not None:
        raise AppError(
            "not_found",
            "Operation definition not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("cost_formula") is not None:
        _validate_formula(updates["cost_formula"])
    for key, value in updates.items():
        setattr(op_def, key, value)
    await session.flush()
    return _def_out(op_def)


# --------------------------------------------------------------------------- #
# Component operations (router rows + material lines)
# --------------------------------------------------------------------------- #
@operations_router.get("/components/{component_id}/costing")
async def get_component_costing(
    component_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> ComponentCosting:
    component = await _get_component_or_404(session, component_id)
    return await _component_costing(session, component)


@operations_router.post(
    "/components/{component_id}/operations", status_code=status.HTTP_201_CREATED
)
async def add_operation(
    component_id: uuid.UUID,
    payload: OperationCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable_quote(session, component)

    op_def: OperationDef | None = None
    if payload.operation_def_id is not None:
        op_def = await session.get(OperationDef, payload.operation_def_id)
        if op_def is None or op_def.deleted_at is not None:
            raise AppError(
                "not_found",
                "Operation definition not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
    elif payload.name is None:
        raise AppError(
            "validation_error",
            "Provide an operation_def_id or a name.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    else:
        # Inline add. If the name is unknown to the library, auto-save it there
        # (the library grows from real quoting activity — #oplibrary Auto-save).
        op_def = await session.scalar(
            select(OperationDef).where(
                OperationDef.name == payload.name, OperationDef.deleted_at.is_(None)
            )
        )
        if op_def is None:
            op_def = OperationDef(
                org_id=principal.active_org_id,
                name=payload.name,
                category=payload.category,
                calculation_mode=payload.calculation_mode,
                run_rate=payload.run_rate,
                labour_rate=payload.labour_rate,
                setup_basis=payload.setup_basis,
                setup_cost=payload.setup_cost,
                setup_time_mins=payload.setup_time_mins,
                surcharge_pct=payload.surcharge_pct,
                is_outside_service=payload.is_outside_service,
                is_finish=payload.is_finish,
            )
            session.add(op_def)
            await session.flush()

    await attach_operation_from_def(session, principal.active_org_id, component, op_def)
    await recalculate_component(session, principal.active_org_id, component.id)
    return await _component_costing(session, component)


@operations_router.patch("/operations/{operation_id}")
async def update_operation(
    operation_id: uuid.UUID,
    payload: OperationUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    operation = await _get_operation_or_404(session, operation_id)
    component = await _get_component_or_404(session, operation.component_id)
    await _lock_editable_quote(session, component)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("cost_formula") is not None:
        _validate_formula(updates["cost_formula"])
    for field, value in updates.items():
        setattr(operation, field, value)
    await session.flush()
    await recalculate_component(session, principal.active_org_id, component.id)
    return await _component_costing(session, component)


@operations_router.post("/operations/{operation_id}/duplicate")
async def duplicate_operation(
    operation_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    """Copy a row (same mode/rates/times — e.g. Schleifen Maschine A / B). Cell
    overrides are NOT copied; the copy recalculates fresh."""
    operation = await _get_operation_or_404(session, operation_id)
    component = await _get_component_or_404(session, operation.component_id)
    await _lock_editable_quote(session, component)
    copy = Operation(
        org_id=principal.active_org_id,
        component_id=component.id,
        operation_def_id=operation.operation_def_id,
        name=operation.name,
        category=operation.category,
        position=await _next_position(session, component.id),
        calculation_mode=operation.calculation_mode,
        run_rate=operation.run_rate,
        labour_rate=operation.labour_rate,
        setup_basis=operation.setup_basis,
        setup_cost=operation.setup_cost,
        calc_setup_mins=operation.calc_setup_mins,
        manual_setup_mins=operation.manual_setup_mins,
        calc_runtime_mins=operation.calc_runtime_mins,
        manual_runtime_mins=operation.manual_runtime_mins,
        calc_attend_mins=operation.calc_attend_mins,
        manual_attend_mins=operation.manual_attend_mins,
        surcharge_pct=operation.surcharge_pct,
        yield_factor=operation.yield_factor,
        is_outside_service=operation.is_outside_service,
        is_finish=operation.is_finish,
        notes=operation.notes,
        cost_formula=operation.cost_formula,
        variable_overrides=dict(operation.variable_overrides),
    )
    session.add(copy)
    await session.flush()
    await recalculate_component(session, principal.active_org_id, component.id)
    return await _component_costing(session, component)


@operations_router.delete("/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_operation(
    operation_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> None:
    """Remove from this part only — never deletes the library def (#oplibrary)."""
    operation = await _get_operation_or_404(session, operation_id)
    component = await _get_component_or_404(session, operation.component_id)
    await _lock_editable_quote(session, component)
    if operation.category is OpCategory.material:
        # M4.3: the nestable (material) op is locked while nested (KB FAQ)
        from .nesting import ensure_component_not_nested

        await ensure_component_not_nested(session, component.id)
    await session.delete(operation)  # cells cascade
    await session.flush()


@operations_router.put("/components/{component_id}/operations/order")
async def reorder_operations(
    component_id: uuid.UUID,
    payload: OperationOrder,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    """Drag-reorder: the payload is the full desired order (set equality enforced)."""
    component = await _get_component_or_404(session, component_id)
    await _lock_editable_quote(session, component)
    operations = (
        await session.scalars(select(Operation).where(Operation.component_id == component.id))
    ).all()
    by_id = {op.id: op for op in operations}
    if set(payload.operation_ids) != set(by_id) or len(payload.operation_ids) != len(by_id):
        raise AppError(
            "invalid_order",
            "The order must list each of the component's operations exactly once.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    for position, op_id in enumerate(payload.operation_ids, start=1):
        by_id[op_id].position = position
    await session.flush()
    return await _component_costing(session, component)


@operations_router.patch("/operations/{operation_id}/cells/{quantity}")
async def set_cell_override(
    operation_id: uuid.UUID,
    quantity: int,
    payload: CellUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    """Set (or clear, with ``manual_cost: null``) one cell's cost override. The
    calc value underneath is retained — clearing falls back to Calculated."""
    operation = await _get_operation_or_404(session, operation_id)
    component = await _get_component_or_404(session, operation.component_id)
    await _lock_editable_quote(session, component)
    brk = await session.scalar(
        select(ComponentQuantity).where(
            ComponentQuantity.component_id == component.id,
            ComponentQuantity.quantity == quantity,
        )
    )
    if brk is None:
        raise AppError(
            "not_found",
            "No such quantity break on this line item.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    cell = await session.scalar(
        select(QuoteCell).where(
            QuoteCell.operation_id == operation.id, QuoteCell.quantity == quantity
        )
    )
    if cell is None:  # recalc not yet materialised for this break — create it now
        cell = QuoteCell(
            org_id=principal.active_org_id,
            operation_id=operation.id,
            component_id=component.id,
            quantity=quantity,
        )
        session.add(cell)
    cell.manual_cost = payload.manual_cost
    await session.flush()
    await recalculate_component(session, principal.active_org_id, component.id)
    return await _component_costing(session, component)


# --------------------------------------------------------------------------- #
# Kalk (M1.9): editor CHECK, variable overrides, the drawer's evaluation report
# --------------------------------------------------------------------------- #
class KalkCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula: Annotated[str, Field(max_length=100_000)]
    context_type: str = "operation_cost"


class KalkErrorOut(BaseModel):
    code: str
    message: str
    line: int | None
    col: int | None


class KalkCheckResult(BaseModel):
    ok: bool
    errors: list[KalkErrorOut]


@operations_router.post("/kalk/check")
async def kalk_check(
    payload: KalkCheckRequest,
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> KalkCheckResult:
    """The editor CHECK button — static validation only, never executes."""
    result = kalk.check(payload.formula, context_type=payload.context_type)
    return KalkCheckResult(
        ok=result.ok,
        errors=[
            KalkErrorOut(code=e.code, message=e.message, line=e.line, col=e.col)
            for e in result.errors
        ],
    )


@operations_router.put("/operations/{operation_id}/variables")
async def set_variable_overrides(
    operation_id: uuid.UUID,
    payload: VariableOverridesUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    """Replace the operation's Kalk variable overrides and recalculate. The
    special ``runtime``/``setup_time`` names are rejected here — they override
    via the M1.7 ``manual_*_mins`` pair (DECISIONS.md 2026-07-08)."""
    operation = await _get_operation_or_404(session, operation_id)
    component = await _get_component_or_404(session, operation.component_id)
    await _lock_editable_quote(session, component)
    if "runtime" in payload.overrides or "setup_time" in payload.overrides:
        raise AppError(
            "validation_error",
            "runtime and setup_time override via the operation's manual time fields.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    operation.variable_overrides = payload.overrides
    await session.flush()
    await recalculate_component(session, principal.active_org_id, component.id)
    return await _component_costing(session, component)


@operations_router.get("/operations/{operation_id}/kalk")
async def get_operation_kalk_report(
    operation_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[dict[str, Any]]:
    """The drawer's per-break evaluation report: declared variables (with
    current values/options), groups, applied overrides, output, and errors.
    An operation without a formula reports an empty list."""
    operation = await _get_operation_or_404(session, operation_id)
    if operation.cost_formula is None:
        return []
    component = await _get_component_or_404(session, operation.component_id)
    operations = (
        await session.scalars(
            select(Operation)
            .where(Operation.component_id == component.id)
            .order_by(Operation.position, Operation.created_at, Operation.id)
        )
    ).all()
    breaks = (
        await session.scalars(
            select(ComponentQuantity).where(ComponentQuantity.component_id == component.id)
        )
    ).all()
    cells = (
        await session.scalars(select(QuoteCell).where(QuoteCell.component_id == component.id))
    ).all()
    return await operation_kalk_report(
        session, component, operation, list(operations), list(breaks), list(cells)
    )


# --------------------------------------------------------------------------- #
# Component header assignments (material picker / Change Process)
# --------------------------------------------------------------------------- #
@operations_router.patch("/components/{component_id}/material")
async def set_component_material(
    component_id: uuid.UUID,
    payload: ComponentMaterialUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable_quote(session, component)
    # M4.3: same-material is a nest's compatibility premise — reassigning the
    # material of a nested component would silently invalidate the shared
    # costing (fresh-eyes review; KB locking rule).
    from .nesting import ensure_component_not_nested

    await ensure_component_not_nested(session, component.id)
    if payload.material_id is not None:
        material = await session.get(Material, payload.material_id)
        if material is None:
            raise AppError(
                "not_found", "Material not found.", status_code=status.HTTP_404_NOT_FOUND
            )
    component.material_id = payload.material_id
    await session.flush()
    # M4.8: the material picks the most-specific interrogation profile
    # (Aluminium vs Stainless thresholds), so a material change must
    # re-interrogate exactly like a process change — the fingerprint dedupe
    # inside skips when the resolved inputs are unchanged.
    from .interrogation import maybe_enqueue_for_process

    await maybe_enqueue_for_process(session, component)
    return await _component_costing(session, component)


@operations_router.patch("/components/{component_id}/process")
async def set_component_process(
    component_id: uuid.UUID,
    payload: ComponentProcessUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentCosting:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable_quote(session, component)
    # M4.3: a process change deletes ops (UPDATE) or moves the component off
    # the sheet-metal family either way — both orphan a nest, so it is locked
    # like quantities and the nestable op (fresh-eyes review; KB locking rule).
    from .nesting import ensure_component_not_nested

    await ensure_component_not_nested(session, component.id)
    if payload.process_id is not None:
        process = await session.get(Process, payload.process_id)
        if process is None or process.deleted_at is not None:
            raise AppError("not_found", "Process not found.", status_code=status.HTTP_404_NOT_FOUND)
    if not payload.keep_operations:
        # The modal's UPDATE: "This action will delete all existing operations."
        # Router regeneration from the new process is a no-op until M4.
        operations = (
            await session.scalars(select(Operation).where(Operation.component_id == component.id))
        ).all()
        for operation in operations:
            await session.delete(operation)
    component.process_id = payload.process_id
    await session.flush()
    # M4.2 (spec #sheetmetal): a recognizer-family process queues a family
    # interrogation of the part's PRIMARY CAD — the viewer's results block.
    from .interrogation import maybe_enqueue_for_process

    await maybe_enqueue_for_process(session, component)
    return await _component_costing(session, component)
