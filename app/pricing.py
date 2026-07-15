"""Pricing engine — cost roll-up + pricing items + discounts (M1.10).

Spec ``#costing`` / ``#kalk-rollup`` / ``#newscope`` §1; grill decisions
DECISIONS.md 2026-07-09. The rules this module encodes:

* **Roll-up (operation → component → root):** per root quantity break, every
  euro of effective cost lands in exactly one of the five standard categories.
  Root operations read their persisted cells (``COALESCE(manual, calc)``);
  **child components** roll up on the fly with ``make_qty(child) = break qty x
  Π qty_relative_to_parent`` along the node path — no child cell rows until M4.
  A child's ``manual_override_cost`` replaces its whole cost (→ Component
  Overrides); a PURCHASED child contributes ``piece_price x make_qty``
  (→ Purchased Components).
* **Pricing items are independent and additive** (verified against Demo E):
  every amount is computed **off cost**, never off a running subtotal —
  markup ``C x pct``, margin ``C x pct/(1-pct)`` (DECISIONS.md 2026-06-14),
  target-margin back-solves ``amount = pct/(1-pct) x TOTAL_COST - Σ others``
  against Total excl. Discounts, holding the other items fixed; a negative
  solution is **unreachable** (contribution 0 + flag). A custom item's
  category cost is its formula's ``set_custom_cost()`` output — informational
  (a re-slice, never added to Total Estimated Cost).
* **Money boundary:** amounts stay ``numeric(14,4)``; the unit price rounds
  HALF-UP to 2 dp (kaufmännische Rundung), discounts apply to the **rounded**
  unit (``x (1 - Σ pct/100)`` — percentages sum, they don't compound), and
  ``unit_price x quantity = total_price`` holds exactly.
* **Calc-vs-override:** the engine writes only ``calc_*`` (+ the roll-up
  columns); ``manual_pct`` / ``manual_profit`` / ``manual_unit_price`` are the
  estimator's and always win via COALESCE. Recalculation never destroys them.
* **E4-d freeze:** org defs (``pricing_item_def`` / ``discount_def``) are
  snapshot-on-attach; editing a def never reprices an existing draft.
  ``Refresh Pricing`` re-snapshots ``is_from_factory`` rows (and op formula
  snapshots) deliberately, preserving every manual override.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import (
    AddOn,
    AddOnCell,
    AddOnDef,
    CalcType,
    Component,
    ComponentQuantity,
    CostCategory,
    Discount,
    DiscountCell,
    DiscountDef,
    ExpediteOption,
    Material,
    MaterialFamily,
    Node,
    OpCategory,
    Operation,
    OperationDef,
    Organization,
    Part,
    PricingItem,
    PricingItemCell,
    PricingItemDef,
    Process,
    Quote,
    QuoteItem,
)
from .services.kalk import ContextData, KalkObject, MappingTableProvider, evaluate
from .services.kalk import check as kalk_check

_CENT4 = Decimal("0.0001")
_CENT2 = Decimal("0.01")
_PCT4 = Decimal("0.0001")
_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
_MINUTES_PER_HOUR = Decimal(60)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(_CENT4, rounding=ROUND_HALF_UP)


def round_price(value: Decimal) -> Decimal:
    """The 2-dp HALF-UP unit-price boundary (DECISIONS.md 2026-07-09)."""
    return value.quantize(_CENT2, rounding=ROUND_HALF_UP)


def markup_amount(cost: Decimal, pct: Decimal) -> Decimal:
    """Markup: amount = C x pct — off cost, never off a running price."""
    return _q4(cost * pct / _HUNDRED)


def margin_amount(cost: Decimal, pct: Decimal) -> Decimal | None:
    """Margin: amount = C x pct/(1-pct), so the slice nets ``pct`` margin.
    ``pct >= 100`` has no finite price — unpriceable (None), never a crash."""
    if pct >= _HUNDRED:
        return None
    return _q4(cost * pct / (_HUNDRED - pct))


def target_margin_amount(
    total_cost: Decimal, pct: Decimal, other_amounts: Decimal
) -> tuple[Decimal, bool]:
    """Back-solve the amount so profit/total (excl. discounts) = ``pct``,
    holding the other items fixed → ``(amount, unreachable)``."""
    if pct >= _HUNDRED:
        return (_q4(_ZERO), True)
    raw = total_cost * pct / (_HUNDRED - pct) - other_amounts
    if raw < 0:
        return (_q4(_ZERO), True)
    return (_q4(raw), False)


# --------------------------------------------------------------------------- #
# Environment loading (async — everything the sync compute pass reads)
# --------------------------------------------------------------------------- #
@dataclass
class ChildInfo:
    """One BOM child: its component + occurrence count per root unit."""

    component: Component
    part: Part
    count: int
    material_name: str | None
    material_family: str | None
    operations: list[Operation] = field(default_factory=list)
    kalk_env: Any = None  # KalkEnv when a child op carries a formula


@dataclass
class PricingEnv:
    component: Component
    part: Part
    material_name: str | None
    material_family: str | None
    breaks: list[ComponentQuantity]
    operations: list[Operation]
    cells: dict[tuple[uuid.UUID, int], Any]
    children: list[ChildInfo]
    items: list[PricingItem]
    item_cells: dict[tuple[uuid.UUID, int], PricingItemCell]
    discounts: list[Discount]
    discount_cells: dict[tuple[uuid.UUID, int], DiscountCell]
    add_ons: list[AddOn]
    add_on_cells: dict[tuple[uuid.UUID, int], AddOnCell]
    add_on_def_names: dict[uuid.UUID, str]
    expedites: list[ExpediteOption]
    def_names: dict[uuid.UUID, str]
    provider: MappingTableProvider
    contact: KalkObject | None
    # lead-time base (M1.11): process default + material adder; ``has_lead_base``
    # distinguishes "no source at all" (calc stays NULL) from a genuine 0
    base_lead_days: int = 0
    has_lead_base: bool = False
    # DACH Costing Mode (M1.12) — exposes the Zuschlagskalkulation Kalk helpers
    dach_costing_mode: bool = False


async def _material_names(
    session: AsyncSession, material_id: uuid.UUID | None
) -> tuple[str | None, str | None]:
    if material_id is None:
        return (None, None)
    material = await session.get(Material, material_id)
    if material is None:  # pragma: no cover — FK-guaranteed
        return (None, None)
    family = await session.get(MaterialFamily, material.family_id)
    return (material.display_name, family.name if family else None)


async def _load_children(
    session: AsyncSession, root: Component, breaks: list[ComponentQuantity]
) -> list[ChildInfo]:
    """Walk the node tree under the root part; count occurrences per root unit.

    Components are resolved by ``part_id`` — parts are created fresh per line
    item (M1.5), so the mapping is unique in practice; the real component↔node
    linkage is the M4 BOM Builder's. A part appearing several times counts once
    per occurrence x its path quantity product."""
    from . import kalk_costing

    nodes = (await session.scalars(select(Node).where(Node.root_part_id == root.part_id))).all()
    by_parent: dict[uuid.UUID | None, list[Node]] = {}
    root_node: Node | None = None
    for node in nodes:
        if node.parent_node_id is None:
            root_node = node
        else:
            by_parent.setdefault(node.parent_node_id, []).append(node)
    if root_node is None:
        return []

    counts: dict[uuid.UUID, int] = {}  # part_id → occurrences per one root
    stack: list[tuple[Node, int]] = [(root_node, 1)]
    while stack:
        node, multiplier = stack.pop()
        for child in by_parent.get(node.id, ()):
            child_count = multiplier * child.qty_relative_to_parent
            counts[child.part_id] = counts.get(child.part_id, 0) + child_count
            stack.append((child, child_count))
    if not counts:
        return []

    components = (
        await session.scalars(
            select(Component).where(Component.part_id.in_(counts)).order_by(Component.created_at)
        )
    ).all()
    by_part = {component.part_id: component for component in components}

    children: list[ChildInfo] = []
    for part_id, count in counts.items():
        component = by_part.get(part_id)
        if component is None:
            continue  # a node without a quoting layer contributes nothing yet
        part = await session.get(Part, part_id)
        assert part is not None  # FK-guaranteed
        material_name, family_name = await _material_names(session, component.material_id)
        operations = (
            await session.scalars(
                select(Operation)
                .where(Operation.component_id == component.id)
                .order_by(Operation.position, Operation.created_at, Operation.id)
            )
        ).all()
        info = ChildInfo(
            component=component,
            part=part,
            count=count,
            material_name=material_name,
            material_family=family_name,
            operations=list(operations),
        )
        if any(op.cost_formula for op in operations):
            # synthetic per-break rows: the child's make qty per root break
            synthetic = [
                ComponentQuantity(
                    org_id=root.org_id,
                    component_id=component.id,
                    quantity=brk.quantity,
                    make_quantity=(
                        brk.make_quantity if brk.make_quantity is not None else brk.quantity
                    )
                    * count,
                    deliver_quantity=(
                        brk.deliver_quantity if brk.deliver_quantity is not None else brk.quantity
                    )
                    * count,
                )
                for brk in breaks
            ]
            info.kalk_env = await kalk_costing.load_kalk_env(session, component, synthetic)
        children.append(info)
    return children


async def load_pricing_env(session: AsyncSession, component: Component) -> PricingEnv:
    from .kalk_costing import load_table_provider
    from .models import Contact, QuoteCell

    part = await session.get(Part, component.part_id)
    assert part is not None
    material_name, family_name = await _material_names(session, component.material_id)
    breaks = sorted(
        (
            await session.scalars(
                select(ComponentQuantity).where(ComponentQuantity.component_id == component.id)
            )
        ).all(),
        key=lambda b: b.quantity,
    )
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
    items = (
        await session.scalars(
            select(PricingItem)
            .where(PricingItem.component_id == component.id)
            .order_by(PricingItem.position, PricingItem.created_at, PricingItem.id)
        )
    ).all()
    item_cells = (
        await session.scalars(
            select(PricingItemCell).where(PricingItemCell.component_id == component.id)
        )
    ).all()
    discounts = (
        await session.scalars(
            select(Discount)
            .where(Discount.component_id == component.id)
            .order_by(Discount.position, Discount.created_at, Discount.id)
        )
    ).all()
    discount_cells = (
        await session.scalars(select(DiscountCell).where(DiscountCell.component_id == component.id))
    ).all()
    add_ons = (
        await session.scalars(
            select(AddOn)
            .where(AddOn.component_id == component.id)
            .order_by(AddOn.position, AddOn.created_at, AddOn.id)
        )
    ).all()
    add_on_cells = (
        await session.scalars(select(AddOnCell).where(AddOnCell.component_id == component.id))
    ).all()
    expedites = (
        await session.scalars(
            select(ExpediteOption)
            .where(ExpediteOption.component_id == component.id)
            .order_by(ExpediteOption.position, ExpediteOption.days_faster)
        )
    ).all()
    def_rows = (await session.execute(select(OperationDef.id, OperationDef.name))).tuples().all()

    base_lead_days = 0
    has_lead_base = False
    if component.process_id is not None:
        process = await session.get(Process, component.process_id)
        if process is not None:
            base_lead_days += process.default_lead_time_days
            has_lead_base = True
    if component.material_id is not None:
        material = await session.get(Material, component.material_id)
        if material is not None:
            base_lead_days += material.added_lead_time_days
            has_lead_base = True

    contact_obj: KalkObject | None = None
    quote_row = await session.scalar(
        select(Quote)
        .join(QuoteItem, QuoteItem.quote_id == Quote.id)
        .where(QuoteItem.root_component_id == component.id)
    )
    if quote_row is not None and quote_row.contact_id is not None:
        contact = await session.get(Contact, quote_row.contact_id)
        if contact is not None:
            full_name = " ".join(p for p in (contact.first_name, contact.last_name) if p)
            contact_obj = KalkObject(
                "contact",
                {
                    "email": contact.email,
                    "first_name": contact.first_name,
                    "last_name": contact.last_name,
                    "full_name": full_name or None,
                    "uuid": str(contact.id),
                },
            )

    return PricingEnv(
        component=component,
        part=part,
        material_name=material_name,
        material_family=family_name,
        breaks=list(breaks),
        operations=list(operations),
        cells={(cell.operation_id, cell.quantity): cell for cell in cells},
        children=await _load_children(session, component, list(breaks)),
        items=list(items),
        item_cells={(c.pricing_item_id, c.quantity): c for c in item_cells},
        discounts=list(discounts),
        discount_cells={(c.discount_id, c.quantity): c for c in discount_cells},
        add_ons=list(add_ons),
        add_on_cells={(c.add_on_id, c.quantity): c for c in add_on_cells},
        add_on_def_names=dict(
            (await session.execute(select(AddOnDef.id, AddOnDef.name))).tuples().all()
        ),
        expedites=list(expedites),
        def_names=dict(def_rows),
        provider=await load_table_provider(session),
        contact=contact_obj,
        base_lead_days=base_lead_days,
        has_lead_base=has_lead_base,
        dach_costing_mode=await session.scalar(
            select(Organization.dach_costing_mode).where(Organization.id == component.org_id)
        )
        or False,
    )


# --------------------------------------------------------------------------- #
# The compute pass (sync — runs off the event loop)
# --------------------------------------------------------------------------- #
@dataclass
class ItemResult:
    calc_pct: Decimal | None
    calc_profit: Decimal | None  # the computed $ amount (None = unpriceable)
    effective_amount: Decimal  # what the totals actually used
    calc_custom_cost: Decimal | None
    unreachable: bool


@dataclass
class AddOnEval:
    """One add-on at one break: calc-vs-override + resolved required-ness."""

    calc_price: Decimal | None
    effective_price: Decimal
    calc_is_required: bool | None
    is_required: bool
    calc_name: str | None = None  # the formula's set_add_on_name() output


@dataclass
class BreakResult:
    quantity: int
    material: Decimal = _ZERO
    inside: Decimal = _ZERO
    outside: Decimal = _ZERO
    purchased: Decimal = _ZERO
    override: Decimal = _ZERO
    total_cost: Decimal = _ZERO
    has_unpriced: bool = False
    items: dict[uuid.UUID, ItemResult] = field(default_factory=dict)
    discount_pcts: dict[uuid.UUID, Decimal] = field(default_factory=dict)
    unit_cost: Decimal = _ZERO
    total_excl_discounts: Decimal = _ZERO
    calc_unit_price: Decimal = _ZERO
    unit_price: Decimal = _ZERO
    total_price: Decimal = _ZERO
    total_discount: Decimal = _ZERO
    total_discount_pct: Decimal = _ZERO
    total_profit: Decimal = _ZERO
    profit_margin_pct: Decimal | None = None
    # M1.11 — add-ons (after discounts, never in the unit price) + lead time
    add_ons: dict[uuid.UUID, AddOnEval] = field(default_factory=dict)
    required_add_on_total: Decimal = _ZERO
    calc_lead_time_days: int | None = None
    lead_time_days: int | None = None


def _hours(mins: Decimal | None) -> float | None:
    return float(mins / _MINUTES_PER_HOUR) if mins is not None else None


def _resolved_mins(manual: Decimal | None, calc: Decimal | None) -> Decimal | None:
    return manual if manual is not None else calc


def _operation_object(
    env: PricingEnv, op: Operation, cost: Decimal | None, break_qty: int
) -> KalkObject:
    def_name = env.def_names.get(op.operation_def_id) if op.operation_def_id else None

    def get_variable(name: object, default: object = None) -> object:
        overrides = op.variable_overrides or {}
        value = overrides.get(name if isinstance(name, str) else "")
        if isinstance(value, dict):  # quantity-specific: keyed by break value
            value = value.get(str(break_qty))
        return value if value is not None else default

    return KalkObject(
        "operation",
        {
            "cost": float(cost) if cost is not None else 0.0,
            "lead_time": 0,  # DAYS wiring lands with M1.11
            "runtime": _hours(_resolved_mins(op.manual_runtime_mins, op.calc_runtime_mins)),
            "setup_time": _hours(_resolved_mins(op.manual_setup_mins, op.calc_setup_mins)),
            "name": op.name,
            "category": op.category.value,
            "is_outside_service": op.is_outside_service,
            "is_finish": op.is_finish,
            "op_def": KalkObject("op_def", {"name": def_name or op.name, "erp_code": None}),
        },
        methods={"get_variable": get_variable},
    )


def _part_object(
    part: Part,
    component: Component,
    material_name: str | None,
    material_family: str | None,
    make_qty: int,
    deliver_qty: int,
    innate_quantity: int,
) -> KalkObject:
    return KalkObject(
        "part",
        {
            "part_number": part.part_number,
            "revision": part.revision,
            "material": material_name,
            "material_family": material_family,
            "qty": make_qty,
            "bom_qty": deliver_qty,
            "innate_quantity": innate_quantity,
            "is_root_component": component.is_root_component,
            "is_assembly": component.is_assembly,
            "obtain_method": component.obtain_method.value.upper(),
        },
    )


def _child_op_costs(
    child: ChildInfo, break_qty: int, child_make: int
) -> tuple[dict[uuid.UUID, Decimal | None], bool]:
    """Per-op effective costs for a manufactured child at one break — computed
    on the fly (no child cells until M4), threading workpiece + cost dict in
    router order like the root recalc does."""
    from . import kalk_costing
    from .costing import compute_calc_cost

    costs: dict[uuid.UUID, Decimal | None] = {}
    unpriced = False
    workpiece: dict[str, Any] = {}
    custom_attributes: dict[str, Any] = (
        dict(child.kalk_env.part.custom_attributes) if child.kalk_env is not None else {}
    )
    cost_values: dict[str, float] = {
        "--material--": 0.0,
        "--inside--": 0.0,
        "--outside--": 0.0,
        "--total--": 0.0,
    }
    for op in child.operations:
        if op.cost_formula and child.kalk_env is not None:
            cell_eval = kalk_costing.evaluate_cell(
                child.kalk_env,
                op,
                break_qty,
                child_make,
                child_make,
                workpiece,
                cost_values,
                custom_attributes,
            )
            cost = cell_eval.calc_cost
            workpiece = cell_eval.workpiece
            custom_attributes.update(cell_eval.custom_attributes)
        else:
            cost = compute_calc_cost(op, child_make)
        costs[op.id] = cost
        if cost is None:
            unpriced = True
            continue
        amount = float(cost)
        cost_values[op.name] = cost_values.get(op.name, 0.0) + amount
        if op.category is OpCategory.material:
            cost_values["--material--"] += amount
        elif op.is_outside_service:
            cost_values["--outside--"] += amount
        else:
            cost_values["--inside--"] += amount
        cost_values["--total--"] += amount
    return costs, unpriced


def compute_break(env: PricingEnv, brk: ComponentQuantity) -> BreakResult:
    """The whole pricing pass for one quantity break (pure, thread-safe)."""
    result = BreakResult(quantity=brk.quantity)
    make_qty = brk.make_quantity if brk.make_quantity is not None else brk.quantity
    deliver_qty = brk.deliver_quantity if brk.deliver_quantity is not None else brk.quantity

    components: list[KalkObject] = []
    component_operations: dict[str, list[KalkObject]] = {}
    component_material_operations: dict[str, list[KalkObject]] = {}
    component_children: dict[str, list[KalkObject]] = {}

    # ---- children (leaf side of leaf_to_root) --------------------------------
    child_objects: list[KalkObject] = []
    for child in env.children:
        child_make = make_qty * child.count
        self_cost = _ZERO
        op_objects: list[KalkObject] = []
        material_ops: list[KalkObject] = []
        if child.component.manual_override_cost is not None:
            # the estimator's override replaces the child's whole cost
            self_cost = _q4(child.component.manual_override_cost * child_make)
            result.override += self_cost
        elif child.component.obtain_method.value.upper() == "PURCHASED":
            if child.component.piece_price is not None:
                self_cost = _q4(child.component.piece_price * child_make)
                result.purchased += self_cost
            else:
                result.has_unpriced = True  # a purchased child without a price
        else:
            costs, unpriced = _child_op_costs(child, brk.quantity, child_make)
            result.has_unpriced = result.has_unpriced or unpriced
            for op in child.operations:
                cost = costs.get(op.id)
                obj = _operation_object(env, op, cost, brk.quantity)
                op_objects.append(obj)
                if op.category is OpCategory.material:
                    material_ops.append(obj)
                if cost is None:
                    continue
                self_cost += cost
                if op.category is OpCategory.material:
                    result.material += cost
                elif op.is_outside_service:
                    result.outside += cost
                else:
                    result.inside += cost

        part_obj = _part_object(
            child.part,
            child.component,
            child.material_name,
            child.material_family,
            child_make,
            child_make,
            child.count,
        )
        child_obj = KalkObject(
            "component",
            {
                "uuid": str(child.component.id),
                "part_uuid": str(child.component.part_id),
                "self_cost": float(self_cost),
                "lead_time": 0,
                "process": None,
                "part": part_obj,
            },
        )
        components.append(child_obj)
        child_objects.append(child_obj)
        key = str(child.component.id)
        component_operations[key] = op_objects
        component_material_operations[key] = material_ops
        component_children[key] = []

    # ---- root operations (persisted cells; COALESCE(manual, calc)) -----------
    root_self = _ZERO
    root_ops: list[KalkObject] = []
    root_material_ops: list[KalkObject] = []
    for op in env.operations:
        cell = env.cells.get((op.id, brk.quantity))
        root_cost: Decimal | None = None
        if cell is not None:
            root_cost = cell.manual_cost if cell.manual_cost is not None else cell.calc_cost
        obj = _operation_object(env, op, root_cost, brk.quantity)
        root_ops.append(obj)
        if op.category is OpCategory.material:
            root_material_ops.append(obj)
        if root_cost is None:
            result.has_unpriced = True
            continue
        root_self += root_cost
        if op.category is OpCategory.material:
            result.material += root_cost
        elif op.is_outside_service:
            result.outside += root_cost
        else:
            result.inside += root_cost

    root_key = str(env.component.id)
    root_part_obj = _part_object(
        env.part,
        env.component,
        env.material_name,
        env.material_family,
        make_qty,
        deliver_qty,
        1,
    )
    root_obj = KalkObject(
        "component",
        {
            "uuid": root_key,
            "part_uuid": str(env.component.part_id),
            "self_cost": float(root_self),
            "lead_time": 0,
            "process": None,
            "part": root_part_obj,
        },
    )
    components.append(root_obj)
    component_operations[root_key] = root_ops
    component_material_operations[root_key] = root_material_ops
    component_children[root_key] = child_objects

    for bucket in ("material", "inside", "outside", "purchased", "override"):
        setattr(result, bucket, _q4(getattr(result, bucket)))
    result.total_cost = _q4(
        result.material + result.inside + result.outside + result.purchased + result.override
    )
    result.unit_cost = _q4(result.total_cost / brk.quantity)

    context_data = ContextData(
        components=components,
        component_operations=component_operations,
        component_material_operations=component_material_operations,
        component_children=component_children,
    )
    category_cost = {
        CostCategory.general: result.total_cost,
        CostCategory.material: result.material,
        CostCategory.inside: result.inside,
        CostCategory.outside: result.outside,
        CostCategory.purchased_component: result.purchased,
    }

    # ---- pricing items: independent, additive, off cost -----------------------
    def evaluate_item(item: PricingItem, prior_items_total: Decimal) -> ItemResult:
        cell = env.item_cells.get((item.id, brk.quantity))
        calc_pct: Decimal | None = None
        custom_cost: Decimal | None = None
        if item.formula:
            eval_context: dict[str, Any] = {
                "MATERIAL_COST": float(result.material),
                "INSIDE_COST": float(result.inside),
                "OUTSIDE_COST": float(result.outside),
                "PURCHASED_COMPONENT_COST": float(result.purchased),
                "TOTAL_COST": float(result.total_cost),
                "CALCULATION_TYPE": ("MARGIN" if item.calc_type is CalcType.margin else "MARKUP"),
                "COST_CATEGORY": item.custom_category_name or item.category.value,
                "CATEGORY_COST": float(_ZERO if item.is_custom else category_cost[item.category]),
                "REQUESTED_QUANTITY": brk.quantity,
                "contact": env.contact,
            }
            if env.dach_costing_mode:
                # Zuschlagskalkulation helpers (spec #dach-costing, M1.12):
                # Herstellkosten = Material + Inside cost categories;
                # Selbstkosten = everything before this item in the stack
                # (all cost categories + prior items' amounts — the seed
                # positions Gewinn last, so it sees MGK/VwGK/VtGK).
                herstellkosten = float(_q4(result.material + result.inside))
                selbstkosten = float(_q4(result.total_cost + prior_items_total))
                eval_context["get_herstellkosten"] = lambda: herstellkosten
                eval_context["get_selbstkosten"] = lambda: selbstkosten
            eval_result = evaluate(
                item.formula,
                context_type="pricing_item",
                eval_context=eval_context,
                quantity=brk.quantity,
                table_provider=env.provider,
                context_data=context_data,
            )
            if not eval_result.errors and eval_result.output is not None:
                calc_pct = _q4(Decimal(repr(eval_result.output["PERCENTAGE"])))
                raw_custom = eval_result.output.get("custom_cost")
                if raw_custom is not None:
                    custom_cost = _q4(Decimal(repr(raw_custom)))
        elif item.default_pct is not None:
            calc_pct = _q4(item.default_pct)

        pct = cell.manual_pct if cell is not None and cell.manual_pct is not None else calc_pct
        base = custom_cost if item.is_custom else category_cost[item.category]
        amount: Decimal | None = None
        if pct is not None and base is not None and item.calc_type is not CalcType.target_margin:
            if item.calc_type is CalcType.margin:
                amount = margin_amount(base, pct)
            else:
                amount = markup_amount(base, pct)
        manual_amount = cell.manual_profit if cell is not None else None
        effective = manual_amount if manual_amount is not None else (amount or _ZERO)
        return ItemResult(
            calc_pct=calc_pct,
            calc_profit=amount,
            effective_amount=_q4(effective),
            calc_custom_cost=custom_cost,
            unreachable=False,
        )

    target_items = [i for i in env.items if i.calc_type is CalcType.target_margin]
    other_sum = _ZERO
    for item in env.items:
        if item.calc_type is CalcType.target_margin:
            continue
        item_result = evaluate_item(item, other_sum)
        result.items[item.id] = item_result
        other_sum += item_result.effective_amount

    for item in target_items:  # validated single; loop stays defensive
        cell = env.item_cells.get((item.id, brk.quantity))
        calc_pct = _q4(item.default_pct) if item.default_pct is not None else None
        pct = cell.manual_pct if cell is not None and cell.manual_pct is not None else calc_pct
        manual_amount = cell.manual_profit if cell is not None else None
        if manual_amount is not None:
            item_result = ItemResult(calc_pct, manual_amount, _q4(manual_amount), None, False)
        elif pct is None:
            item_result = ItemResult(None, None, _q4(_ZERO), None, False)
        else:
            amount, unreachable = target_margin_amount(result.total_cost, pct, other_sum)
            item_result = ItemResult(calc_pct, amount, amount, None, unreachable)
        result.items[item.id] = item_result
        other_sum += item_result.effective_amount

    result.total_excl_discounts = _q4(result.total_cost + other_sum)
    result.calc_unit_price = round_price(result.total_excl_discounts / brk.quantity)

    # ---- discounts: Σ pct off the ROUNDED unit --------------------------------
    discount_sum = _ZERO
    for discount in env.discounts:
        cell = env.discount_cells.get((discount.id, brk.quantity))
        calc_pct = None
        if discount.formula:
            eval_result = evaluate(
                discount.formula,
                context_type="discount",
                eval_context={"contact": env.contact},
                quantity=brk.quantity,
                table_provider=env.provider,
            )
            if not eval_result.errors and eval_result.output is not None:
                calc_pct = _q4(Decimal(repr(eval_result.output["PERCENTAGE"])))
        elif discount.default_pct is not None:
            calc_pct = _q4(discount.default_pct)
        pct = cell.manual_pct if cell is not None and cell.manual_pct is not None else calc_pct
        result.discount_pcts[discount.id] = calc_pct if calc_pct is not None else _ZERO
        discount_sum += pct if pct is not None else _ZERO

    pre_discount_unit = (
        brk.manual_unit_price if brk.manual_unit_price is not None else result.calc_unit_price
    )
    result.total_discount_pct = discount_sum.quantize(_PCT4, rounding=ROUND_HALF_UP)
    result.unit_price = round_price(pre_discount_unit * (_HUNDRED - discount_sum) / _HUNDRED)
    result.total_price = result.unit_price * brk.quantity
    result.total_discount = _q4((pre_discount_unit - result.unit_price) * brk.quantity)
    result.total_profit = _q4(result.total_price - result.total_cost)
    if result.total_price != 0:
        result.profit_margin_pct = (result.total_profit / result.total_price * _HUNDRED).quantize(
            _PCT4, rounding=ROUND_HALF_UP
        )

    # ---- lead time: base (process default + material adder) + Σ op DAYS ------
    # (spec #addons Lead Times; PRICING-ENGINE-SPEC §3.2 "lead-time
    # contribution = DAYS"). No source at all keeps calc NULL — PP blocks
    # finalize on a missing base lead time, it never invents 0.
    op_days_total = 0
    has_op_days = False
    for op in env.operations:
        op_cell = env.cells.get((op.id, brk.quantity))
        if op_cell is not None and op_cell.days is not None:
            op_days_total += op_cell.days
            has_op_days = True
    if env.has_lead_base or has_op_days:
        result.calc_lead_time_days = env.base_lead_days + op_days_total
    result.lead_time_days = (
        brk.manual_lead_time_days
        if brk.manual_lead_time_days is not None
        else result.calc_lead_time_days
    )

    # ---- add-ons: AFTER discounts; one-time fees, never in the unit price ----
    # (PRICING-ENGINE-SPEC §3.5; KB add-ons-p3l-cheat-sheet). Position order
    # matters: get_price_value() sees only the cells above the active add-on.
    if env.add_ons:
        addon_cost_values = {
            "--material--": float(result.material),
            "--inside--": float(result.inside),
            "--outside--": float(result.outside),
            "--total--": float(result.total_cost),
        }
        for op in env.operations:
            op_cell = env.cells.get((op.id, brk.quantity))
            if op_cell is None:
                continue
            op_cost = op_cell.manual_cost if op_cell.manual_cost is not None else op_cell.calc_cost
            if op_cost is not None:
                addon_cost_values[op.name] = addon_cost_values.get(op.name, 0.0) + float(op_cost)
        price_values: dict[str, float] = {
            "--required_add_on--": 0.0,
            "--non_required_add_on--": 0.0,
        }
        break_quantities = [b.quantity for b in env.breaks]
        break_make_quantities = [
            b.make_quantity if b.make_quantity is not None else b.quantity for b in env.breaks
        ]
        for add_on in env.add_ons:
            add_on_cell = env.add_on_cells.get((add_on.id, brk.quantity))
            calc_price: Decimal | None = None
            calc_required: bool | None = None
            calc_name: str | None = None
            if add_on.formula:
                eval_result = evaluate(
                    add_on.formula,
                    context_type="add_on",
                    eval_context={"part": root_part_obj, "quantity": make_qty},
                    quantity=brk.quantity,
                    table_provider=env.provider,
                    context_data=ContextData(
                        quantities=list(break_quantities),
                        make_quantities=list(break_make_quantities),
                        bom_quantities=list(break_quantities),
                        cost_values=dict(addon_cost_values),
                        price_values=dict(price_values),
                    ),
                )
                if not eval_result.errors and eval_result.output is not None:
                    calc_price = _q4(Decimal(repr(eval_result.output["PRICE"])))
                    calc_required = eval_result.add_on_is_required
                    calc_name = eval_result.add_on_name
            elif add_on.default_price is not None:
                calc_price = _q4(add_on.default_price)
            manual_price = add_on_cell.manual_price if add_on_cell is not None else None
            effective = _q4(manual_price if manual_price is not None else (calc_price or _ZERO))
            if add_on.manual_is_required is not None:
                required = add_on.manual_is_required
            elif calc_required is not None:
                required = calc_required
            else:
                required = add_on.default_is_required
            result.add_ons[add_on.id] = AddOnEval(
                calc_price, effective, calc_required, required, calc_name
            )
            # the price dictionary matches by add-on name OR its definition
            # name (KALK-REFERENCE §7); a dynamic rename counts under both
            def_name = (
                env.add_on_def_names.get(add_on.source_def_id)
                if add_on.source_def_id is not None
                else None
            )
            keys = {calc_name or add_on.name, add_on.name}
            if def_name is not None:
                keys.add(def_name)
            for key in keys:
                price_values[key] = price_values.get(key, 0.0) + float(effective)
            bucket = "--required_add_on--" if required else "--non_required_add_on--"
            price_values[bucket] += float(effective)
            if required:
                result.required_add_on_total += effective
        result.required_add_on_total = _q4(result.required_add_on_total)
    return result


# --------------------------------------------------------------------------- #
# Reprice — compute + persist (calc side only; overrides never touched)
# --------------------------------------------------------------------------- #
async def reprice_component(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> None:
    from anyio import to_thread

    component = await session.get(Component, component_id)
    if component is None:  # pragma: no cover — callers hold a live row
        return
    env = await load_pricing_env(session, component)

    def compute() -> list[BreakResult]:
        return [compute_break(env, brk) for brk in env.breaks]

    results = await to_thread.run_sync(compute)

    for brk, computed in zip(env.breaks, results, strict=True):
        brk.material_cost = computed.material
        brk.inside_cost = computed.inside
        brk.outside_cost = computed.outside
        brk.purchased_component_cost = computed.purchased
        brk.child_override_cost = computed.override
        brk.unit_cost = computed.unit_cost
        brk.calc_unit_price = computed.calc_unit_price
        brk.unit_price = computed.unit_price
        brk.total_price = computed.total_price
        brk.total_discount = computed.total_discount
        brk.total_discount_pct = computed.total_discount_pct
        brk.total_profit = computed.total_profit
        brk.profit_margin_pct = computed.profit_margin_pct
        brk.calc_lead_time_days = computed.calc_lead_time_days
        brk.lead_time_days = computed.lead_time_days

        for add_on in env.add_ons:
            add_on_eval = computed.add_ons.get(add_on.id)
            if add_on_eval is None:  # pragma: no cover
                continue
            add_on_cell = env.add_on_cells.get((add_on.id, brk.quantity))
            if add_on_cell is None:
                add_on_cell = AddOnCell(
                    org_id=org_id,
                    add_on_id=add_on.id,
                    component_id=component_id,
                    quantity=brk.quantity,
                )
                session.add(add_on_cell)
                env.add_on_cells[(add_on.id, brk.quantity)] = add_on_cell
            add_on_cell.calc_price = add_on_eval.calc_price

        for item in env.items:
            item_result = computed.items.get(item.id)
            if item_result is None:  # pragma: no cover
                continue
            cell = env.item_cells.get((item.id, brk.quantity))
            if cell is None:
                cell = PricingItemCell(
                    org_id=org_id,
                    pricing_item_id=item.id,
                    component_id=component_id,
                    quantity=brk.quantity,
                )
                session.add(cell)
                env.item_cells[(item.id, brk.quantity)] = cell
            cell.calc_pct = item_result.calc_pct
            cell.calc_profit = item_result.calc_profit
            cell.calc_custom_cost = item_result.calc_custom_cost
            cell.unreachable = item_result.unreachable

        for discount in env.discounts:
            pct = computed.discount_pcts.get(discount.id)
            discount_cell = env.discount_cells.get((discount.id, brk.quantity))
            if discount_cell is None:
                discount_cell = DiscountCell(
                    org_id=org_id,
                    discount_id=discount.id,
                    component_id=component_id,
                    quantity=brk.quantity,
                )
                session.add(discount_cell)
                env.discount_cells[(discount.id, brk.quantity)] = discount_cell
            discount_cell.calc_pct = pct

    # the row-level calc side of the Required pair follows the lowest break
    # (the display-pair precedent from the M1.9 op-times write-back)
    if results:
        for add_on in env.add_ons:
            add_on_eval = results[0].add_ons.get(add_on.id)
            if add_on_eval is not None:
                add_on.calc_is_required = add_on_eval.calc_is_required
                add_on.calc_name = add_on_eval.calc_name

    await session.flush()


async def attach_default_pricing(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> None:
    """Snapshot the org's pricing-item/discount defs onto a new quote item
    (E4-d: attach-time copy; later def edits never touch this line)."""
    defs = (
        await session.scalars(
            select(PricingItemDef)
            .where(PricingItemDef.deleted_at.is_(None))
            .order_by(PricingItemDef.position, PricingItemDef.created_at)
        )
    ).all()
    for position, item_def in enumerate(defs):
        session.add(_snapshot_item(item_def, org_id, component_id, position))
    discount_defs = (
        await session.scalars(
            select(DiscountDef)
            .where(DiscountDef.deleted_at.is_(None))
            .order_by(DiscountDef.position, DiscountDef.created_at)
        )
    ).all()
    for position, discount_def in enumerate(discount_defs):
        session.add(_snapshot_discount(discount_def, org_id, component_id, position))
    await session.flush()


def _snapshot_item(
    item_def: PricingItemDef, org_id: uuid.UUID, component_id: uuid.UUID, position: int
) -> PricingItem:
    return PricingItem(
        org_id=org_id,
        component_id=component_id,
        source_def_id=item_def.id,
        name=item_def.name,
        calc_type=item_def.calc_type,
        category=item_def.category,
        is_custom=item_def.is_custom,
        custom_category_name=item_def.custom_category_name,
        color=item_def.color,
        formula=item_def.formula,
        default_pct=item_def.default_pct,
        position=position,
        is_from_factory=True,
    )


def _snapshot_discount(
    discount_def: DiscountDef, org_id: uuid.UUID, component_id: uuid.UUID, position: int
) -> Discount:
    return Discount(
        org_id=org_id,
        component_id=component_id,
        source_def_id=discount_def.id,
        name=discount_def.name,
        formula=discount_def.formula,
        default_pct=discount_def.default_pct,
        position=position,
        is_from_factory=True,
    )


# --------------------------------------------------------------------------- #
# API — schemas
# --------------------------------------------------------------------------- #
pricing_router = APIRouter(prefix="/api", tags=["pricing"])

_PCT_FIELD = Field(ge=0, le=10000)


class PricingItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Attach a Configure-library def (snapshot-on-attach, same copy semantics
    # as quote creation); when set, every other field comes from the def.
    source_def_id: uuid.UUID | None = None
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    calc_type: CalcType = CalcType.markup
    category: CostCategory = CostCategory.general
    is_custom: bool = False
    custom_category_name: Annotated[str | None, Field(max_length=200)] = None
    color: Annotated[str | None, Field(max_length=32)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_pct: Annotated[Decimal | None, _PCT_FIELD] = None


class PricingItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)] = "unset"
    calc_type: CalcType = CalcType.markup
    category: CostCategory = CostCategory.general
    is_custom: bool = False
    custom_category_name: Annotated[str | None, Field(max_length=200)] = None
    color: Annotated[str | None, Field(max_length=32)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_pct: Annotated[Decimal | None, _PCT_FIELD] = None


class PricingItemCellUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_pct: Annotated[Decimal | None, _PCT_FIELD] = None
    manual_profit: Annotated[Decimal | None, Field(ge=0)] = None


class DiscountPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_def_id: uuid.UUID | None = None
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_pct: Annotated[Decimal | None, Field(ge=0, le=100)] = None


class DiscountCellUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_pct: Annotated[Decimal | None, Field(ge=0, le=100)] = None


class UnitPriceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_unit_price: Annotated[Decimal | None, Field(ge=0)] = None


class PricingItemOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pricing_item_ids: Annotated[list[uuid.UUID], Field(min_length=1)]


class PricingItemDefPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    calc_type: CalcType = CalcType.markup
    category: CostCategory = CostCategory.general
    is_custom: bool = False
    custom_category_name: Annotated[str | None, Field(max_length=200)] = None
    color: Annotated[str | None, Field(max_length=32)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_pct: Annotated[Decimal | None, _PCT_FIELD] = None
    position: int = 0


class PricingItemDefUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)] = "unset"
    calc_type: CalcType = CalcType.markup
    category: CostCategory = CostCategory.general
    is_custom: bool = False
    custom_category_name: Annotated[str | None, Field(max_length=200)] = None
    color: Annotated[str | None, Field(max_length=32)] = None
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_pct: Annotated[Decimal | None, _PCT_FIELD] = None
    position: int = 0


class DiscountDefPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    formula: Annotated[str | None, Field(max_length=100_000)] = None
    default_pct: Annotated[Decimal | None, Field(ge=0, le=100)] = None
    position: int = 0


class PricingItemOut(BaseModel):
    id: uuid.UUID
    source_def_id: uuid.UUID | None
    name: str
    calc_type: CalcType
    category: CostCategory
    is_custom: bool
    custom_category_name: str | None
    color: str | None
    formula: str | None
    default_pct: Decimal | None
    position: int
    is_from_factory: bool


# --------------------------------------------------------------------------- #
# API — helpers
# --------------------------------------------------------------------------- #
async def _get_component_or_404(session: AsyncSession, component_id: uuid.UUID) -> Component:
    component = await session.get(Component, component_id)
    if component is None:
        raise AppError("not_found", "Component not found.", status_code=status.HTTP_404_NOT_FOUND)
    return component


def _validate_pricing_formula(formula: str | None, context_type: str) -> None:
    if formula is None:
        return
    checked = kalk_check(formula, context_type=context_type)
    if not checked.ok:
        first = checked.errors[0]
        raise AppError(
            "invalid_formula",
            f"Formula error: {first.message}"
            + (f" (line {first.line})" if first.line is not None else ""),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


def _validate_item_shape(
    payload: PricingItemPayload | PricingItemUpdate | PricingItemDefPayload | PricingItemDefUpdate,
) -> None:
    if payload.is_custom and not payload.custom_category_name:
        raise AppError(
            "custom_requires_name",
            "A custom pricing item needs its cost-category name.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if payload.is_custom and not payload.formula:
        raise AppError(
            "custom_requires_formula",
            "A custom pricing item computes its category cost via a Kalk formula.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    _validate_pricing_formula(payload.formula, "pricing_item")


async def _reject_duplicate_target_margin(
    session: AsyncSession, component_id: uuid.UUID, exclude: uuid.UUID | None = None
) -> None:
    query = select(PricingItem.id).where(
        PricingItem.component_id == component_id,
        PricingItem.calc_type == CalcType.target_margin,
    )
    if exclude is not None:
        query = query.where(PricingItem.id != exclude)
    if (await session.scalar(query)) is not None:
        raise AppError(
            "duplicate_target_margin",
            "Only one target-margin item can exist per line item — "
            "two back-solves against each other are ill-defined.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


async def _lock_editable(session: AsyncSession, component: Component) -> Quote:
    from .operations import _lock_editable_quote

    return await _lock_editable_quote(session, component)


def _item_out(item: PricingItem) -> dict[str, Any]:
    return PricingItemOut.model_validate(item, from_attributes=True).model_dump(mode="json")


async def _pricing_summary(session: AsyncSession, component: Component) -> dict[str, Any]:
    env = await load_pricing_env(session, component)
    quantities = [brk.quantity for brk in env.breaks]

    costing = []
    for brk in env.breaks:
        custom_rows = []
        for item in env.items:
            if not item.is_custom:
                continue
            cell = env.item_cells.get((item.id, brk.quantity))
            custom_rows.append(
                {
                    "pricing_item_id": str(item.id),
                    "name": item.custom_category_name,
                    "color": item.color,
                    "cost": cell.calc_custom_cost if cell is not None else None,
                }
            )
        costing.append(
            {
                "quantity": brk.quantity,
                "material": brk.material_cost,
                "inside": brk.inside_cost,
                "outside": brk.outside_cost,
                "purchased_component": brk.purchased_component_cost,
                "child_override": brk.child_override_cost,
                "total": (
                    _q4(
                        (brk.material_cost or _ZERO)
                        + (brk.inside_cost or _ZERO)
                        + (brk.outside_cost or _ZERO)
                        + (brk.purchased_component_cost or _ZERO)
                        + (brk.child_override_cost or _ZERO)
                    )
                    if brk.material_cost is not None
                    else None
                ),
                "unit_cost": brk.unit_cost,
                "custom_rows": custom_rows,
            }
        )

    items_out = []
    for item in env.items:
        cells = []
        for brk in env.breaks:
            cell = env.item_cells.get((item.id, brk.quantity))
            if cell is None:
                continue
            pct = cell.manual_pct if cell.manual_pct is not None else cell.calc_pct
            amount = cell.manual_profit if cell.manual_profit is not None else cell.calc_profit
            cells.append(
                {
                    "quantity": brk.quantity,
                    "calc_pct": cell.calc_pct,
                    "manual_pct": cell.manual_pct,
                    "pct": pct,
                    "calc_profit": cell.calc_profit,
                    "manual_profit": cell.manual_profit,
                    "amount": amount,
                    "calc_custom_cost": cell.calc_custom_cost,
                    "unreachable": cell.unreachable,
                }
            )
        items_out.append({**_item_out(item), "cells": cells})

    discounts_out = []
    for discount in env.discounts:
        cells = []
        for brk in env.breaks:
            discount_cell = env.discount_cells.get((discount.id, brk.quantity))
            if discount_cell is None:
                continue
            cells.append(
                {
                    "quantity": brk.quantity,
                    "calc_pct": discount_cell.calc_pct,
                    "manual_pct": discount_cell.manual_pct,
                    "pct": (
                        discount_cell.manual_pct
                        if discount_cell.manual_pct is not None
                        else discount_cell.calc_pct
                    ),
                }
            )
        discounts_out.append(
            {
                "id": str(discount.id),
                "source_def_id": (str(discount.source_def_id) if discount.source_def_id else None),
                "name": discount.name,
                "formula": discount.formula,
                "default_pct": discount.default_pct,
                "position": discount.position,
                "is_from_factory": discount.is_from_factory,
                "cells": cells,
            }
        )

    add_ons_out = []
    for add_on in env.add_ons:
        add_on_cells = []
        for brk in env.breaks:
            addon_cell = env.add_on_cells.get((add_on.id, brk.quantity))
            if addon_cell is None:
                continue
            add_on_cells.append(
                {
                    "quantity": brk.quantity,
                    "calc_price": addon_cell.calc_price,
                    "manual_price": addon_cell.manual_price,
                    "price": (
                        addon_cell.manual_price
                        if addon_cell.manual_price is not None
                        else addon_cell.calc_price
                    ),
                }
            )
        add_ons_out.append(
            {
                "id": str(add_on.id),
                "source_def_id": str(add_on.source_def_id) if add_on.source_def_id else None,
                "name": add_on.name,
                "calc_name": add_on.calc_name,
                "display_name": add_on.display_name,
                "formula": add_on.formula,
                "default_price": add_on.default_price,
                "default_is_required": add_on.default_is_required,
                "calc_is_required": add_on.calc_is_required,
                "manual_is_required": add_on.manual_is_required,
                "is_required": add_on.is_required,
                "position": add_on.position,
                "is_from_factory": add_on.is_from_factory,
                "cells": add_on_cells,
            }
        )

    def required_add_ons_total(brk: ComponentQuantity) -> Decimal:
        total = _ZERO
        for add_on in env.add_ons:
            if not add_on.is_required:
                continue
            cell = env.add_on_cells.get((add_on.id, brk.quantity))
            if cell is None:
                continue
            price = cell.manual_price if cell.manual_price is not None else cell.calc_price
            if price is not None:
                total += price
        return _q4(total)

    # per-break lead times + the buyer-facing expedite rows (lead - days_faster,
    # unit x (1 + markup%); KB dynamic-lead-times-guide)
    lead_times_out = []
    for brk in env.breaks:
        expedite_rows = []
        for option in env.expedites:
            expedite_unit = (
                round_price(brk.unit_price * (_HUNDRED + option.markup_pct) / _HUNDRED)
                if brk.unit_price is not None
                else None
            )
            expedite_rows.append(
                {
                    "id": str(option.id),
                    "days_faster": option.days_faster,
                    "markup_pct": option.markup_pct,
                    "lead_time_days": (
                        max(brk.lead_time_days - option.days_faster, 0)
                        if brk.lead_time_days is not None
                        else None
                    ),
                    "unit_price": expedite_unit,
                    "total_price": (
                        expedite_unit * brk.quantity if expedite_unit is not None else None
                    ),
                }
            )
        lead_times_out.append(
            {
                "quantity": brk.quantity,
                "calc_lead_time_days": brk.calc_lead_time_days,
                "manual_lead_time_days": brk.manual_lead_time_days,
                "lead_time_days": brk.lead_time_days,
                "expedites": expedite_rows,
            }
        )

    def total_excl_discounts(brk: ComponentQuantity) -> Decimal | None:
        """The authoritative Total (excl. Discounts) — spec #costing step 8:
        Total Estimated Cost + Σ item amounts, at the exact 4-dp precision,
        NOT rounded_unit x qty (which can drift by cents at some breaks).
        A manual unit-price override redefines the pre-discount total as
        manual x qty by construction."""
        if brk.manual_unit_price is not None:
            return _q4(brk.manual_unit_price * brk.quantity)
        if brk.material_cost is None:  # never repriced — no roll-up state yet
            return None
        cost_total = (
            brk.material_cost
            + (brk.inside_cost or _ZERO)
            + (brk.outside_cost or _ZERO)
            + (brk.purchased_component_cost or _ZERO)
            + (brk.child_override_cost or _ZERO)
        )
        amounts = _ZERO
        for item in env.items:
            cell = env.item_cells.get((item.id, brk.quantity))
            if cell is None:
                continue
            amount = cell.manual_profit if cell.manual_profit is not None else cell.calc_profit
            amounts += amount if amount is not None else _ZERO
        return _q4(cost_total + amounts)

    def total_markup(brk: ComponentQuantity) -> tuple[Decimal | None, Decimal | None]:
        """Total Markup (spec #costing output rows, DemoE 09): the pre-discount
        price delta over Total Estimated Cost, as amount + %. Display-only —
        derived from the same 4-dp figures the other output rows use."""
        pre_discount = total_excl_discounts(brk)
        if pre_discount is None or brk.material_cost is None:
            return None, None
        cost_total = (
            brk.material_cost
            + (brk.inside_cost or _ZERO)
            + (brk.outside_cost or _ZERO)
            + (brk.purchased_component_cost or _ZERO)
            + (brk.child_override_cost or _ZERO)
        )
        amount = _q4(pre_discount - cost_total)
        pct = _q4(amount / cost_total * _HUNDRED) if cost_total != _ZERO else None
        return amount, pct

    totals = []
    for brk in env.breaks:
        required_total = required_add_ons_total(brk)
        markup_amount_total, markup_pct_total = total_markup(brk)
        totals.append(
            {
                "quantity": brk.quantity,
                "unit_cost": brk.unit_cost,
                "total_excl_discounts": total_excl_discounts(brk),
                "total_markup": markup_amount_total,
                "total_markup_pct": markup_pct_total,
                "calc_unit_price": brk.calc_unit_price,
                "manual_unit_price": brk.manual_unit_price,
                "unit_price": brk.unit_price,
                "total_price": brk.total_price,
                "total_discount": brk.total_discount,
                "total_discount_pct": brk.total_discount_pct,
                "total_profit": brk.total_profit,
                "profit_margin_pct": brk.profit_margin_pct,
                # spec #addons roll-up rows — required add-ons only; the
                # optional ones are the buyer's checkout choice (M5)
                "total_required_add_ons": required_total,
                "total_with_required_add_ons": (
                    _q4(brk.total_price + required_total) if brk.total_price is not None else None
                ),
            }
        )

    return {
        "component_id": str(component.id),
        "quantities": quantities,
        "costing": costing,
        "pricing_items": items_out,
        "discounts": discounts_out,
        "add_ons": add_ons_out,
        "lead_times": lead_times_out,
        "totals": totals,
    }


# --------------------------------------------------------------------------- #
# API — line-item pricing endpoints
# --------------------------------------------------------------------------- #
@pricing_router.get("/components/{component_id}/pricing")
async def get_component_pricing(
    component_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    return await _pricing_summary(session, component)


@pricing_router.post(
    "/components/{component_id}/pricing-items", status_code=status.HTTP_201_CREATED
)
async def add_pricing_item(
    component_id: uuid.UUID,
    payload: PricingItemPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable(session, component)
    max_position = max(
        (
            i.position
            for i in (
                await session.scalars(
                    select(PricingItem).where(PricingItem.component_id == component_id)
                )
            ).all()
        ),
        default=-1,
    )
    if payload.source_def_id is not None:
        # add-from-library: the same snapshot-on-attach copy as quote creation,
        # but estimator-chosen — Refresh Pricing must not re-snapshot it, so
        # is_from_factory stays False.
        item_def = await session.get(PricingItemDef, payload.source_def_id)
        if item_def is None or item_def.deleted_at is not None:
            raise AppError(
                "not_found",
                "Pricing item definition not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if item_def.calc_type is CalcType.target_margin:
            await _reject_duplicate_target_margin(session, component_id)
        item = _snapshot_item(item_def, principal.active_org_id, component_id, max_position + 1)
        item.is_from_factory = False
    else:
        if payload.name is None:
            raise AppError(
                "name_required",
                "A pricing item needs a name (or a source_def_id).",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        _validate_item_shape(payload)
        if payload.calc_type is CalcType.target_margin:
            await _reject_duplicate_target_margin(session, component_id)
        item = PricingItem(
            org_id=principal.active_org_id,
            component_id=component_id,
            position=max_position + 1,
            **payload.model_dump(exclude={"source_def_id"}),
        )
    session.add(item)
    await session.flush()
    await reprice_component(session, principal.active_org_id, component_id)
    return _item_out(item)


@pricing_router.patch("/pricing-items/{pricing_item_id}")
async def update_pricing_item(
    pricing_item_id: uuid.UUID,
    payload: PricingItemUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    item = await session.get(PricingItem, pricing_item_id)
    if item is None:
        raise AppError(
            "not_found", "Pricing item not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    component = await _get_component_or_404(session, item.component_id)
    await _lock_editable(session, component)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    _validate_item_shape(
        PricingItemUpdate(
            name=item.name,
            calc_type=item.calc_type,
            category=item.category,
            is_custom=item.is_custom,
            custom_category_name=item.custom_category_name,
            color=item.color,
            formula=item.formula,
            default_pct=item.default_pct,
        )
    )
    if item.calc_type is CalcType.target_margin:
        await _reject_duplicate_target_margin(session, item.component_id, exclude=item.id)
    await session.flush()
    await reprice_component(session, principal.active_org_id, item.component_id)
    return _item_out(item)


@pricing_router.delete("/pricing-items/{pricing_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_pricing_item(
    pricing_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> None:
    item = await session.get(PricingItem, pricing_item_id)
    if item is None:
        raise AppError(
            "not_found", "Pricing item not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    component = await _get_component_or_404(session, item.component_id)
    await _lock_editable(session, component)
    component_id = item.component_id
    await session.delete(item)
    await session.flush()
    await reprice_component(session, principal.active_org_id, component_id)


@pricing_router.put("/components/{component_id}/pricing-items/order")
async def reorder_pricing_items(
    component_id: uuid.UUID,
    payload: PricingItemOrder,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable(session, component)
    items = (
        await session.scalars(select(PricingItem).where(PricingItem.component_id == component_id))
    ).all()
    by_id = {item.id: item for item in items}
    if set(payload.pricing_item_ids) != set(by_id):
        raise AppError(
            "invalid_order",
            "The order must list every pricing item of this line exactly once.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    for position, item_id in enumerate(payload.pricing_item_ids):
        by_id[item_id].position = position
    await session.flush()
    return {"pricing_item_ids": [str(i) for i in payload.pricing_item_ids]}


@pricing_router.patch("/pricing-items/{pricing_item_id}/cells/{quantity}")
async def set_pricing_item_cell_override(
    pricing_item_id: uuid.UUID,
    quantity: int,
    payload: PricingItemCellUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    item = await session.get(PricingItem, pricing_item_id)
    if item is None:
        raise AppError(
            "not_found", "Pricing item not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    component = await _get_component_or_404(session, item.component_id)
    await _lock_editable(session, component)
    cell = await session.scalar(
        select(PricingItemCell).where(
            PricingItemCell.pricing_item_id == pricing_item_id,
            PricingItemCell.quantity == quantity,
        )
    )
    if cell is None:
        raise AppError(
            "not_found",
            "No such quantity break on this pricing item.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    updates = payload.model_dump(exclude_unset=True)
    if "manual_pct" in updates:
        cell.manual_pct = updates["manual_pct"]
    if "manual_profit" in updates:
        cell.manual_profit = updates["manual_profit"]
    await session.flush()
    await reprice_component(session, principal.active_org_id, item.component_id)
    return {
        "quantity": quantity,
        "calc_pct": cell.calc_pct,
        "manual_pct": cell.manual_pct,
        "calc_profit": cell.calc_profit,
        "manual_profit": cell.manual_profit,
        "unreachable": cell.unreachable,
    }


@pricing_router.post("/components/{component_id}/discounts", status_code=status.HTTP_201_CREATED)
async def add_discount(
    component_id: uuid.UUID,
    payload: DiscountPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable(session, component)
    max_position = max(
        (
            d.position
            for d in (
                await session.scalars(select(Discount).where(Discount.component_id == component_id))
            ).all()
        ),
        default=-1,
    )
    if payload.source_def_id is not None:
        discount_def = await session.get(DiscountDef, payload.source_def_id)
        if discount_def is None or discount_def.deleted_at is not None:
            raise AppError(
                "not_found",
                "Discount definition not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        discount = _snapshot_discount(
            discount_def, principal.active_org_id, component_id, max_position + 1
        )
        discount.is_from_factory = False
    else:
        if payload.name is None:
            raise AppError(
                "name_required",
                "A discount needs a name (or a source_def_id).",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        _validate_pricing_formula(payload.formula, "discount")
        discount = Discount(
            org_id=principal.active_org_id,
            component_id=component_id,
            position=max_position + 1,
            **payload.model_dump(exclude={"source_def_id"}),
        )
    session.add(discount)
    await session.flush()
    await reprice_component(session, principal.active_org_id, component_id)
    return {"id": str(discount.id), "name": discount.name}


@pricing_router.patch("/discounts/{discount_id}")
async def update_discount(
    discount_id: uuid.UUID,
    payload: DiscountPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    discount = await session.get(Discount, discount_id)
    if discount is None:
        raise AppError("not_found", "Discount not found.", status_code=status.HTTP_404_NOT_FOUND)
    component = await _get_component_or_404(session, discount.component_id)
    await _lock_editable(session, component)
    _validate_pricing_formula(payload.formula, "discount")
    updates = payload.model_dump(exclude_unset=True, exclude={"source_def_id"})
    if "name" in updates and updates["name"] is None:
        raise AppError(
            "name_required",
            "A discount name cannot be cleared.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    for key, value in updates.items():
        setattr(discount, key, value)
    await session.flush()
    await reprice_component(session, principal.active_org_id, discount.component_id)
    return {"id": str(discount.id), "name": discount.name}


@pricing_router.delete("/discounts/{discount_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_discount(
    discount_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> None:
    discount = await session.get(Discount, discount_id)
    if discount is None:
        raise AppError("not_found", "Discount not found.", status_code=status.HTTP_404_NOT_FOUND)
    component = await _get_component_or_404(session, discount.component_id)
    await _lock_editable(session, component)
    component_id = discount.component_id
    await session.delete(discount)
    await session.flush()
    await reprice_component(session, principal.active_org_id, component_id)


@pricing_router.patch("/discounts/{discount_id}/cells/{quantity}")
async def set_discount_cell_override(
    discount_id: uuid.UUID,
    quantity: int,
    payload: DiscountCellUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    discount = await session.get(Discount, discount_id)
    if discount is None:
        raise AppError("not_found", "Discount not found.", status_code=status.HTTP_404_NOT_FOUND)
    component = await _get_component_or_404(session, discount.component_id)
    await _lock_editable(session, component)
    cell = await session.scalar(
        select(DiscountCell).where(
            DiscountCell.discount_id == discount_id, DiscountCell.quantity == quantity
        )
    )
    if cell is None:
        raise AppError(
            "not_found",
            "No such quantity break on this discount.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    updates = payload.model_dump(exclude_unset=True)
    if "manual_pct" in updates:
        cell.manual_pct = updates["manual_pct"]
    await session.flush()
    await reprice_component(session, principal.active_org_id, discount.component_id)
    return {"quantity": quantity, "calc_pct": cell.calc_pct, "manual_pct": cell.manual_pct}


@pricing_router.patch("/components/{component_id}/price/{quantity}")
async def set_unit_price_override(
    component_id: uuid.UUID,
    quantity: int,
    payload: UnitPriceUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    component = await _get_component_or_404(session, component_id)
    await _lock_editable(session, component)
    brk = await session.scalar(
        select(ComponentQuantity).where(
            ComponentQuantity.component_id == component_id,
            ComponentQuantity.quantity == quantity,
        )
    )
    if brk is None:
        raise AppError(
            "not_found", "No such quantity break.", status_code=status.HTTP_404_NOT_FOUND
        )
    updates = payload.model_dump(exclude_unset=True)
    if "manual_unit_price" in updates:
        brk.manual_unit_price = updates["manual_unit_price"]
    await session.flush()
    await reprice_component(session, principal.active_org_id, component_id)
    return {
        "quantity": quantity,
        "calc_unit_price": brk.calc_unit_price,
        "manual_unit_price": brk.manual_unit_price,
        "unit_price": brk.unit_price,
    }


# --------------------------------------------------------------------------- #
# API — org config (Configure → Pricing / Discounts; E4-d defs)
# --------------------------------------------------------------------------- #
def _def_out(item_def: PricingItemDef) -> dict[str, Any]:
    return {
        "id": str(item_def.id),
        "name": item_def.name,
        "calc_type": item_def.calc_type.value,
        "category": item_def.category.value,
        "is_custom": item_def.is_custom,
        "custom_category_name": item_def.custom_category_name,
        "color": item_def.color,
        "formula": item_def.formula,
        "default_pct": item_def.default_pct,
        "position": item_def.position,
    }


@pricing_router.get("/pricing-item-defs")
async def list_pricing_item_defs(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Any:
    defs = (
        await session.scalars(
            select(PricingItemDef)
            .where(PricingItemDef.deleted_at.is_(None))
            .order_by(PricingItemDef.position, PricingItemDef.name)
        )
    ).all()
    return [_def_out(d) for d in defs]


@pricing_router.post("/pricing-item-defs", status_code=status.HTTP_201_CREATED)
async def create_pricing_item_def(
    payload: PricingItemDefPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> Any:
    _validate_item_shape(payload)
    item_def = PricingItemDef(org_id=principal.active_org_id, **payload.model_dump())
    session.add(item_def)
    await session.flush()
    return _def_out(item_def)


@pricing_router.patch("/pricing-item-defs/{def_id}")
async def update_pricing_item_def(
    def_id: uuid.UUID,
    payload: PricingItemDefUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> Any:
    item_def = await session.get(PricingItemDef, def_id)
    if item_def is None or item_def.deleted_at is not None:
        raise AppError(
            "not_found", "Pricing item not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item_def, key, value)
    _validate_item_shape(
        PricingItemDefUpdate(
            name=item_def.name,
            calc_type=item_def.calc_type,
            category=item_def.category,
            is_custom=item_def.is_custom,
            custom_category_name=item_def.custom_category_name,
            color=item_def.color,
            formula=item_def.formula,
            default_pct=item_def.default_pct,
        )
    )
    await session.flush()
    return _def_out(item_def)


@pricing_router.delete("/pricing-item-defs/{def_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pricing_item_def(
    def_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> None:
    from datetime import UTC, datetime

    item_def = await session.get(PricingItemDef, def_id)
    if item_def is None or item_def.deleted_at is not None:
        raise AppError(
            "not_found", "Pricing item not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    item_def.deleted_at = datetime.now(UTC)  # soft delete: existing snapshots keep working
    await session.flush()


@pricing_router.get("/discount-defs")
async def list_discount_defs(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Any:
    defs = (
        await session.scalars(
            select(DiscountDef)
            .where(DiscountDef.deleted_at.is_(None))
            .order_by(DiscountDef.position, DiscountDef.name)
        )
    ).all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "formula": d.formula,
            "default_pct": d.default_pct,
            "position": d.position,
        }
        for d in defs
    ]


@pricing_router.post("/discount-defs", status_code=status.HTTP_201_CREATED)
async def create_discount_def(
    payload: DiscountDefPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> Any:
    _validate_pricing_formula(payload.formula, "discount")
    discount_def = DiscountDef(org_id=principal.active_org_id, **payload.model_dump())
    session.add(discount_def)
    await session.flush()
    return {"id": str(discount_def.id), "name": discount_def.name}


@pricing_router.delete("/discount-defs/{def_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discount_def(
    def_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> None:
    from datetime import UTC, datetime

    discount_def = await session.get(DiscountDef, def_id)
    if discount_def is None or discount_def.deleted_at is not None:
        raise AppError("not_found", "Discount not found.", status_code=status.HTTP_404_NOT_FOUND)
    discount_def.deleted_at = datetime.now(UTC)
    await session.flush()


# --------------------------------------------------------------------------- #
# API — Refresh Pricing (E4-d opt-in re-run; single quote)
# --------------------------------------------------------------------------- #
@pricing_router.post("/quotes/{quote_id}/refresh-pricing")
async def refresh_pricing(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> Any:
    from .costing import recalculate_component

    quote = await session.get(Quote, quote_id)
    if quote is None or quote.deleted_at is not None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)

    items = (await session.scalars(select(QuoteItem).where(QuoteItem.quote_id == quote_id))).all()
    defs = {
        d.id: d
        for d in (
            await session.scalars(select(PricingItemDef).where(PricingItemDef.deleted_at.is_(None)))
        ).all()
    }
    discount_defs = {
        d.id: d
        for d in (
            await session.scalars(select(DiscountDef).where(DiscountDef.deleted_at.is_(None)))
        ).all()
    }
    op_def_formulas = {
        row[0]: row[1]
        for row in (await session.execute(select(OperationDef.id, OperationDef.cost_formula))).all()
    }

    refreshed = 0
    for quote_item in items:
        component_id = quote_item.root_component_id
        existing = (
            await session.scalars(
                select(PricingItem).where(PricingItem.component_id == component_id)
            )
        ).all()
        attached_def_ids = set()
        for item in existing:
            if not item.is_from_factory or item.source_def_id is None:
                continue
            attached_def_ids.add(item.source_def_id)
            item_def = defs.get(item.source_def_id)
            if item_def is None:
                continue  # def deleted — the snapshot stays as-is (manual cleanup)
            item.name = item_def.name
            item.calc_type = item_def.calc_type
            item.category = item_def.category
            item.is_custom = item_def.is_custom
            item.custom_category_name = item_def.custom_category_name
            item.color = item_def.color
            item.formula = item_def.formula
            item.default_pct = item_def.default_pct
        # defs added since the line was created attach now ("added" cleanup case)
        position = max((i.position for i in existing), default=-1) + 1
        for def_id, item_def in defs.items():
            if def_id not in attached_def_ids:
                session.add(
                    _snapshot_item(item_def, principal.active_org_id, component_id, position)
                )
                position += 1

        existing_discounts = (
            await session.scalars(select(Discount).where(Discount.component_id == component_id))
        ).all()
        attached_discount_defs = set()
        for discount in existing_discounts:
            if not discount.is_from_factory or discount.source_def_id is None:
                continue
            attached_discount_defs.add(discount.source_def_id)
            discount_def = discount_defs.get(discount.source_def_id)
            if discount_def is None:
                continue
            discount.name = discount_def.name
            discount.formula = discount_def.formula
            discount.default_pct = discount_def.default_pct
        position = max((d.position for d in existing_discounts), default=-1) + 1
        for def_id, discount_def in discount_defs.items():
            if def_id not in attached_discount_defs:
                session.add(
                    _snapshot_discount(
                        discount_def, principal.active_org_id, component_id, position
                    )
                )
                position += 1

        # op formula snapshots re-copy too (DECISIONS.md 2026-07-08)
        operations = (
            await session.scalars(select(Operation).where(Operation.component_id == component_id))
        ).all()
        for op in operations:
            if op.operation_def_id is not None and op.operation_def_id in op_def_formulas:
                op.cost_formula = op_def_formulas[op.operation_def_id]

        await session.flush()
        # full re-run: costs first (preserving manual_*), then pricing
        await recalculate_component(session, principal.active_org_id, component_id)
        refreshed += 1

    return {"refreshed_items": refreshed}
