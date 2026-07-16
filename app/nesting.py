"""M4.3 — the multi-component sheet-metal Nesting module (spec ``#nesting``).

Overview (components grouped by material/thickness across line items) →
create-nest flow (per-break stock, Cost Method = Per Sheet) → the ``Nest``
object per quantity break, computed by the estimation-grade area packing in
:mod:`app.nesting_math`. The allocated material cost reaches the material
drawer through Kalk ``manual_nest()`` (see :mod:`app.kalk_costing`).

Rules folded in from KB ``multi-component-sheet-metal-nesting``:

- compatibility = same material + same interrogated thickness (toggleable) +
  a material-category op; **across quote items every component needs a single
  make quantity** (online checkout cannot enforce a partial order — checkout
  itself is M5, the constraint is enforced here already);
- same-item components with multiple make quantities generate **one nest per
  break**, associated via ``config.set_id`` — deleting one deletes the set;
- while nested, make-quantity changes and deleting the nestable (material) op
  are locked ("Operations and quantities will be locked…" — the dialog
  warning); overview rows show ``Nested?``.

v1 scope notes: rows are the quote items' **root** components (assembly
children join with the M4.9 BOM tree); linear-metal nesting is the 1D analog,
stubbed as an empty tab (spec: "stub if time-constrained").
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .costing import recalculate_component
from .deps import get_session
from .errors import AppError
from .models import (
    Component,
    ComponentQuantity,
    InterrogationRun,
    Material,
    Nest,
    OpCategory,
    Operation,
    Part,
    Process,
    ProcessFamily,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from .nesting_math import NestComponent, NestSettings, NestStock, compute_nest

nesting_router = APIRouter(prefix="/api", tags=["nesting"])

_THICKNESS_TOL_MM = 0.01


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class StockIn(BaseModel):
    """Quantity-break-specific stock (the prepare dialog's per-break row)."""

    model_config = ConfigDict(extra="forbid")

    quantity: Annotated[int, Field(gt=0)]
    length_mm: Annotated[float, Field(gt=0)]
    width_mm: Annotated[float, Field(gt=0)]
    erp_code: Annotated[str, Field(max_length=200)] = ""
    #: Manual sheet cost always wins over an ERP lookup (KB); no lookup until M6.8.
    sheet_cost: str


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_buffer_mm: Annotated[float, Field(ge=0)] = 3.0
    clearance_mm: Annotated[float, Field(ge=0)] = 3.0
    kerf_mm: Annotated[float, Field(ge=0)] = 0.25
    drop_threshold_pct: Annotated[float, Field(ge=0, le=100)] = 25.0
    distribution_method: str = "area_of_parts"
    grain_direction: str | None = None
    allow_mixed_thickness: bool = False


class ComponentSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: uuid.UUID
    cost_distribution_pct: Annotated[Decimal | None, Field(ge=0, le=100)] = None
    grain_direction: str | None = None


class NestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_ids: Annotated[list[uuid.UUID], Field(min_length=1)]
    stock: Annotated[list[StockIn], Field(min_length=1)]
    settings: SettingsIn = SettingsIn()
    component_settings: list[ComponentSettingIn] = []


class NestOut(BaseModel):
    id: uuid.UUID
    label: str | None
    kind: str | None
    set_id: str | None
    quantity: int | None
    config: dict[str, Any] | None
    result: dict[str, Any] | None


class OverviewRow(BaseModel):
    component_id: uuid.UUID
    part_id: uuid.UUID
    part_number: str | None
    part_name: str | None
    item_id: uuid.UUID
    position: int
    material_id: uuid.UUID | None
    material_name: str | None
    thickness_mm: float | None
    flat_x_mm: float | None
    flat_y_mm: float | None
    flat_area_mm2: float | None
    contour_length_mm: float | None
    quantities: list[int]
    make_quantities: list[int]
    eligible: bool
    nest_id: uuid.UUID | None
    nest_label: str | None


class NestingOverview(BaseModel):
    sheet_metal: list[OverviewRow]
    linear_metal: list[OverviewRow]  # 1D analog — stub (spec #nesting)
    nests: list[NestOut]


class NestList(BaseModel):
    nests: list[NestOut]


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _nest_out(nest: Nest) -> NestOut:
    config = nest.config or {}
    return NestOut(
        id=nest.id,
        label=nest.label,
        kind=nest.kind,
        set_id=config.get("set_id"),
        quantity=config.get("quantity"),
        config=nest.config,
        result=nest.result,
    )


async def _quote_or_404(session: AsyncSession, quote_id: uuid.UUID, *, lock: bool = False) -> Quote:
    stmt = select(Quote).where(Quote.id == quote_id)
    if lock:
        # the change-quantities TOCTOU pattern: serialise concurrent nest edits
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    quote = await session.scalar(stmt)
    if quote is None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    return quote


def _is_editable(quote: Quote) -> bool:
    if quote.deleted_at is not None:
        return False
    if quote.status is QuoteStatus.draft:
        return True
    return quote.status is QuoteStatus.on_hold and quote.status_before_hold is QuoteStatus.draft


async def _quote_nests(session: AsyncSession, quote_id: uuid.UUID) -> list[Nest]:
    return list(
        (
            await session.scalars(
                select(Nest).where(Nest.quote_id == quote_id).order_by(Nest.created_at, Nest.id)
            )
        ).all()
    )


def _nested_component_ids(nests: list[Nest]) -> dict[str, Nest]:
    """component id (str) → the nest that contains it."""
    membership: dict[str, Nest] = {}
    for nest in nests:
        for cid in (nest.config or {}).get("component_ids", []):
            membership.setdefault(cid, nest)
    return membership


async def ensure_component_not_nested(session: AsyncSession, component_id: uuid.UUID) -> None:
    """The locking rule: make-quantity changes and nestable-op deletion are
    rejected while the component is in a nest (spec dialog warning; KB FAQ)."""
    nest = await session.scalar(
        select(Nest).where(Nest.config.contains({"component_ids": [str(component_id)]})).limit(1)
    )
    if nest is not None:
        raise AppError(
            "nest_locked",
            "Operations and quantities are locked while this component is in a nest. "
            "Delete the nest first.",
            status_code=status.HTTP_409_CONFLICT,
        )


async def _sheet_metal_rows(
    session: AsyncSession, quote: Quote
) -> tuple[list[OverviewRow], dict[uuid.UUID, dict[str, Any]]]:
    """Overview rows + the raw per-component context the create flow validates on."""
    items = (
        await session.scalars(
            select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.position)
        )
    ).all()
    nests = await _quote_nests(session, quote.id)
    membership = _nested_component_ids(nests)

    rows: list[OverviewRow] = []
    context: dict[uuid.UUID, dict[str, Any]] = {}
    for item in items:
        component = await session.get(Component, item.root_component_id)
        if component is None or component.process_id is None:
            continue
        process = await session.get(Process, component.process_id)
        if process is None or process.family is not ProcessFamily.SHEET_METAL:
            continue
        part = await session.get(Part, component.part_id)
        material = (
            await session.get(Material, component.material_id)
            if component.material_id is not None
            else None
        )
        run = await session.scalar(
            select(InterrogationRun)
            .where(
                InterrogationRun.part_id == component.part_id,
                InterrogationRun.family == "SHEET_METAL",
                InterrogationRun.status == "succeeded",
            )
            .order_by(InterrogationRun.created_at.desc())
            .limit(1)
        )
        scalars: dict[str, Any] = (run.result or {}).get("family_scalars", {}) if run else {}
        breaks = sorted(
            (
                await session.scalars(
                    select(ComponentQuantity).where(ComponentQuantity.component_id == component.id)
                )
            ).all(),
            key=lambda b: b.quantity,
        )
        material_op = await session.scalar(
            select(Operation)
            .where(
                Operation.component_id == component.id,
                Operation.category == OpCategory.material,
            )
            .limit(1)
        )
        thickness = scalars.get("thickness")
        flat_x, flat_y = scalars.get("size_x"), scalars.get("size_y")
        flat_area = scalars.get("flat_area")
        eligible = (
            material is not None
            and material_op is not None
            and thickness is not None
            and flat_x is not None
            and flat_y is not None
            and flat_area is not None
        )
        nest = membership.get(str(component.id))
        rows.append(
            OverviewRow(
                component_id=component.id,
                part_id=component.part_id,
                part_number=part.part_number if part else None,
                part_name=part.name if part else None,
                item_id=item.id,
                position=item.position,
                material_id=component.material_id,
                material_name=material.display_name if material else None,
                thickness_mm=thickness,
                flat_x_mm=flat_x,
                flat_y_mm=flat_y,
                flat_area_mm2=flat_area,
                contour_length_mm=scalars.get("total_cut_length"),
                quantities=[b.quantity for b in breaks],
                make_quantities=[
                    b.make_quantity if b.make_quantity is not None else b.quantity for b in breaks
                ],
                eligible=eligible,
                nest_id=nest.id if nest else None,
                nest_label=nest.label if nest else None,
            )
        )
        context[component.id] = {
            "row": rows[-1],
            "item_id": item.id,
            "breaks": {
                b.quantity: (b.make_quantity if b.make_quantity is not None else b.quantity)
                for b in breaks
            },
        }
    return rows, context


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@nesting_router.get("/quotes/{quote_id}/nesting")
async def nesting_overview(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> NestingOverview:
    quote = await _quote_or_404(session, quote_id)
    rows, _context = await _sheet_metal_rows(session, quote)
    nests = await _quote_nests(session, quote.id)
    return NestingOverview(sheet_metal=rows, linear_metal=[], nests=[_nest_out(n) for n in nests])


@nesting_router.post("/quotes/{quote_id}/nests", status_code=status.HTTP_201_CREATED)
async def create_nest(
    quote_id: uuid.UUID,
    payload: NestCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> NestList:
    quote = await _quote_or_404(session, quote_id, lock=True)
    if not _is_editable(quote):
        raise AppError(
            "quote_locked",
            "Nests can only be created while the quote is a draft.",
            status_code=status.HTTP_409_CONFLICT,
        )
    _rows, context = await _sheet_metal_rows(session, quote)
    settings = payload.settings

    # -- membership + eligibility -----------------------------------------
    unique_ids = list(dict.fromkeys(payload.component_ids))
    selected: list[dict[str, Any]] = []
    for cid in unique_ids:
        ctx = context.get(cid)
        if ctx is None:
            raise AppError(
                "validation_error",
                "Every nested component must be a sheet-metal component of this quote.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if not ctx["row"].eligible:
            raise AppError(
                "validation_error",
                f"Component {cid} is not nest-eligible (it needs a material, a material "
                "operation, and a completed sheet-metal interrogation).",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if ctx["row"].nest_id is not None:
            raise AppError(
                "already_nested",
                f"Component {cid} is already in a nest.",
                status_code=status.HTTP_409_CONFLICT,
            )
        selected.append(ctx)

    # -- compatibility (KB): material, thickness, break structure ---------
    material_ids = {ctx["row"].material_id for ctx in selected}
    if len(material_ids) > 1:
        raise AppError(
            "validation_error",
            "Nested components must share the same material.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    thicknesses = [ctx["row"].thickness_mm for ctx in selected]
    if not settings.allow_mixed_thickness and (
        max(thicknesses) - min(thicknesses) > _THICKNESS_TOL_MM
    ):
        raise AppError(
            "validation_error",
            "Nested components must share the same thickness "
            "(enable the non-identical-thickness toggle to override).",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    break_sets = {tuple(sorted(ctx["breaks"])) for ctx in selected}
    if len(break_sets) > 1:
        raise AppError(
            "validation_error",
            "Nested components must share the same quantity breaks.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    (break_set,) = break_sets
    items = {ctx["item_id"] for ctx in selected}
    if len(items) > 1 and len(break_set) != 1:
        raise AppError(
            "validation_error",
            "Components across quote items need a single make quantity each — the "
            "optimized pricing is only valid if all nested parts are ordered together.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    stock_by_qty = {s.quantity: s for s in payload.stock}
    if set(stock_by_qty) != set(break_set) or len(payload.stock) != len(stock_by_qty):
        raise AppError(
            "validation_error",
            "Provide exactly one stock entry per quantity break.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    comp_settings = {cs.component_id: cs for cs in payload.component_settings}
    # explicit cost-distribution is all-or-none over EXACTLY the selected set:
    # a partial/duplicated/foreign-id set would silently zero components
    # (fresh-eyes review + CodeRabbit)
    explicit_pct_ids = [
        cs.component_id for cs in payload.component_settings if cs.cost_distribution_pct is not None
    ]
    if explicit_pct_ids and (
        len(explicit_pct_ids) != len(set(explicit_pct_ids))
        or set(explicit_pct_ids) != set(unique_ids)
    ):
        raise AppError(
            "validation_error",
            "Set a cost-distribution percentage for every nested component or none.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if settings.distribution_method != "area_of_parts":
        # only the spec's default method exists (manual % rides component
        # settings) — reject rather than silently ignore a requested method
        raise AppError(
            "validation_error",
            "Unsupported price distribution method (v1 supports 'area_of_parts').",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    set_id = str(uuid.uuid4())
    # next free label number — a plain count would reuse numbers after a delete
    existing = max(
        (
            int(n.label.rsplit("#", 1)[1])
            for n in await _quote_nests(session, quote.id)
            if n.label and n.label.rsplit("#", 1)[-1].isdigit()
        ),
        default=0,
    )
    created: list[Nest] = []
    for offset, quantity in enumerate(sorted(break_set)):
        stock_in = stock_by_qty[quantity]
        try:
            sheet_cost = Decimal(stock_in.sheet_cost)
        except InvalidOperation:
            raise AppError(
                "validation_error",
                "sheet_cost must be a decimal amount.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from None
        math_components = [
            NestComponent(
                key=str(ctx["row"].component_id),
                flat_x_mm=ctx["row"].flat_x_mm,
                flat_y_mm=ctx["row"].flat_y_mm,
                flat_area_mm2=ctx["row"].flat_area_mm2,
                contour_length_mm=ctx["row"].contour_length_mm or 0.0,
                make_qty=ctx["breaks"][quantity],
                cost_distribution_pct=(
                    cs.cost_distribution_pct
                    if (cs := comp_settings.get(ctx["row"].component_id)) is not None
                    else None
                ),
            )
            for ctx in selected
        ]
        try:
            result = compute_nest(
                math_components,
                NestStock(
                    length_mm=stock_in.length_mm,
                    width_mm=stock_in.width_mm,
                    sheet_cost=sheet_cost,
                ),
                NestSettings(
                    edge_buffer_mm=settings.edge_buffer_mm,
                    clearance_mm=settings.clearance_mm,
                    kerf_mm=settings.kerf_mm,
                    drop_threshold_pct=settings.drop_threshold_pct,
                ),
            )
        except ValueError as exc:
            raise AppError(
                "validation_error", str(exc), status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            ) from exc
        nest = Nest(
            org_id=principal.active_org_id,
            quote_id=quote.id,
            label=f"Nest #{existing + offset + 1}",
            kind="sheet",
            config={
                "set_id": set_id,
                "quantity": quantity,
                "material_id": str(next(iter(material_ids))),
                "thickness_mm": min(thicknesses),
                "component_ids": [str(c.key) for c in math_components],
                "stock": {
                    "length_mm": stock_in.length_mm,
                    "width_mm": stock_in.width_mm,
                    "erp_code": stock_in.erp_code,
                    "sheet_cost": str(sheet_cost),
                    "currency": quote.currency,
                },
                "settings": settings.model_dump(),
                "components": [
                    {
                        "component_id": c.key,
                        "flat_x_mm": c.flat_x_mm,
                        "flat_y_mm": c.flat_y_mm,
                        "flat_area_mm2": c.flat_area_mm2,
                        "contour_length_mm": c.contour_length_mm,
                        "make_qty": c.make_qty,
                        "cost_distribution_pct": (
                            str(c.cost_distribution_pct)
                            if c.cost_distribution_pct is not None
                            else None
                        ),
                    }
                    for c in math_components
                ],
            },
            result={
                "net_sheet_used": result.net_sheet_used,
                "charged_sheets": result.charged_sheets,
                "gross_sheets": result.gross_sheets,
                "material_cost": str(result.material_cost),
                "currency": quote.currency,
                "used_area_mm2": result.used_area_mm2,
                "scrap_area_mm2": result.scrap_area_mm2,
                "drop_area_mm2": result.drop_area_mm2,
                "total_contour_length_mm": result.total_contour_length_mm,
                "components": [
                    {
                        "component_id": c.key,
                        "parts_per_sheet": c.parts_per_sheet,
                        "used_area_mm2": c.used_area_mm2,
                        "cost_share_pct": str(c.cost_share_pct),
                        "allocated_cost": str(c.allocated_cost),
                    }
                    for c in result.components
                ],
            },
        )
        session.add(nest)
        created.append(nest)
    await session.flush()
    # nest results feed manual_nest() → the material op's calc cells move
    for ctx in selected:
        await recalculate_component(session, quote.org_id, ctx["row"].component_id)
    return NestList(nests=[_nest_out(n) for n in created])


@nesting_router.delete("/quotes/{quote_id}/nests/{nest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_nest(
    quote_id: uuid.UUID,
    nest_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> None:
    """Deletes the whole associated per-break set (KB: deleting one nest of a
    multi-make-quantity set deletes the others)."""
    quote = await _quote_or_404(session, quote_id, lock=True)
    if not _is_editable(quote):
        # deleting a nest recalculates costs — a sent quote's figures must not
        # drift (the same draft gate every costing mutation carries)
        raise AppError(
            "quote_locked",
            "Nests can only be deleted while the quote is a draft.",
            status_code=status.HTTP_409_CONFLICT,
        )
    nests = await _quote_nests(session, quote.id)
    target = next((n for n in nests if n.id == nest_id), None)
    if target is None:
        raise AppError("not_found", "Nest not found.", status_code=status.HTTP_404_NOT_FOUND)
    set_id = (target.config or {}).get("set_id")
    doomed = [
        n
        for n in nests
        if n.id == nest_id or (set_id is not None and (n.config or {}).get("set_id") == set_id)
    ]
    affected: set[str] = set()
    for nest in doomed:
        affected.update((nest.config or {}).get("component_ids", []))
        await session.delete(nest)
    await session.flush()
    for cid in affected:
        await recalculate_component(session, quote.org_id, uuid.UUID(cid))
