"""Assembly Components section API (M4.10) — spec ``#assembly``.

The part view's Assembly Components block over a published BOM (M4.9):

* **Listing** — the node tree with per-component data and per-break costs.
  CHILD BOM rows show the **rollup cost to parent** (the node's whole subtree);
  FLAT BOM shows **cost without rollup** (a part's own cost across all its
  occurrences) with the derived Flat Qty. Costs come from the same pricing
  pass the quote uses (``pricing.compute_break`` — one source of truth).
* **Bulk Update Components** (DemoM/15, DemoO/06) — mass-assign process (+
  material): "This action will delete all existing operations." Router
  regenerates per component via auto-routing, then the root reprices.
* **Reorder** (DemoM/04) — single-level drag order persisted as
  ``node.position``; cross-level restructuring is NOT supported (spec).
* **Copy pricing** (DemoM/17) — one source → one target: Material and/or
  Operations (incl. overrides) copied onto the target component.
* **Delete component** / **Add purchased components** (KB
  ``purchased-components``: pick library entries + node qty).
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import (
    Component,
    Material,
    Node,
    ObtainMethod,
    Operation,
    Part,
    PartFile,
    Process,
    PurchasedComponent,
    QuoteItem,
)

assembly_router = APIRouter(prefix="/api", tags=["assembly"])

_TWO_DP = Decimal("0.01")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class AssemblyNodeOut(BaseModel):
    node_id: uuid.UUID
    part_id: uuid.UUID
    component_id: uuid.UUID | None
    part_number: str | None
    revision: str | None
    description: str | None
    filename: str | None
    group: str  # 'subassembly' | 'manufactured' | 'purchased'
    obtain_method: str
    is_assembly: bool
    node_qty: int
    flat_qty: int
    position: int
    process_id: uuid.UUID | None
    material_id: uuid.UUID | None
    piece_price: Decimal | None
    purchased_component_id: uuid.UUID | None
    brand: str | None
    #: per quantity break, 2-dp display values (kaufmännische Rundung)
    self_costs: list[Decimal]
    rollup_costs: list[Decimal]
    children: list[AssemblyNodeOut]


AssemblyNodeOut.model_rebuild()


class AssemblySummaryOut(BaseModel):
    flat_qty_total: int
    totals: list[Decimal]  # per break — Component Summary roll-up


class AssemblyComponentsOut(BaseModel):
    quantities: list[int]
    #: the root part's own node — the parent_node_id for top-level reorders
    root_node_id: uuid.UUID | None
    tree: list[AssemblyNodeOut]  # the root's children, in position order
    summary: AssemblySummaryOut


class BulkUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=200)]
    process_id: uuid.UUID
    material_id: uuid.UUID | None = None


class ReorderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_node_id: uuid.UUID
    ordered_node_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=500)]


class CopyPricingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_component_id: uuid.UUID
    copy_material: bool = True
    copy_operations: bool = True


class AddPurchasedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchased_component_id: uuid.UUID
    node_qty: Annotated[int, Field(ge=1)] = 1


class AddPurchasedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[AddPurchasedItem], Field(min_length=1, max_length=100)]


# --------------------------------------------------------------------------- #
# Shared context
# --------------------------------------------------------------------------- #
async def _load_item(
    session: AsyncSession, quote_item_id: uuid.UUID
) -> tuple[QuoteItem, Component, Part]:
    item = await session.get(QuoteItem, quote_item_id)
    if item is None:
        raise AppError("not_found", "Quote item not found.", status_code=status.HTTP_404_NOT_FOUND)
    root_component = await session.get(Component, item.root_component_id)
    assert root_component is not None  # FK-guaranteed
    root_part = await session.get(Part, root_component.part_id)
    assert root_part is not None
    return item, root_component, root_part


def _display(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #
@assembly_router.get("/quote-items/{quote_item_id}/assembly-components")
async def get_assembly_components(
    quote_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> AssemblyComponentsOut:
    from . import pricing

    item, root_component, root_part = await _load_item(session, quote_item_id)

    nodes = (await session.scalars(select(Node).where(Node.root_part_id == root_part.id))).all()
    by_parent: dict[uuid.UUID | None, list[Node]] = {}
    root_node: Node | None = None
    for node in nodes:
        if node.parent_node_id is None:
            root_node = node
        else:
            by_parent.setdefault(node.parent_node_id, []).append(node)
    for siblings in by_parent.values():
        siblings.sort(key=lambda n: (n.position, n.id.hex))

    env = await pricing.load_pricing_env(session, root_component)
    quantities = [b.quantity for b in env.breaks]

    # per-part per-break unit self cost, derived from the pricing pass's
    # per-child self_cost totals (S = unit x break_make x count)
    unit_self: dict[uuid.UUID, list[Decimal]] = {}
    part_self_total: dict[uuid.UUID, list[Decimal]] = {}
    counts: dict[uuid.UUID, int] = {c.part.id: c.count for c in env.children}
    # Per-child self costs use exactly the compute_break child math (override
    # replaces the whole cost; PURCHASED = piece_price x make; else op costs
    # via _child_op_costs) so this section always agrees with the quote.
    make_by_break = {
        b.quantity: (b.make_quantity if b.make_quantity is not None else b.quantity)
        for b in env.breaks
    }
    for child in env.children:
        totals: list[Decimal] = []
        units: list[Decimal] = []
        for brk in env.breaks:
            child_make = make_by_break[brk.quantity] * child.count
            if child.component.manual_override_cost is not None:
                total = child.component.manual_override_cost * child_make
            elif child.component.obtain_method is ObtainMethod.purchased:
                total = (child.component.piece_price or Decimal(0)) * child_make
            else:
                costs, _unpriced = pricing._child_op_costs(child, brk.quantity, child_make)
                total = sum((c for c in costs.values() if c is not None), start=Decimal(0))
            totals.append(total)
            divisor = Decimal(brk.quantity * child.count) or Decimal(1)
            units.append(total / divisor)
        part_self_total[child.part.id] = totals
        unit_self[child.part.id] = units

    parts = {
        p.id: p
        for p in (await session.scalars(select(Part).where(Part.id.in_(counts.keys())))).all()
    }
    components_by_part = {
        c.part_id: c
        for c in (
            await session.scalars(
                select(Component).where(
                    Component.part_id.in_(counts.keys()),
                    Component.is_root_component.is_(False),
                )
            )
        ).all()
    }
    pc_by_id = {
        pc.id: pc
        for pc in (
            await session.scalars(
                select(PurchasedComponent).where(
                    PurchasedComponent.id.in_(
                        {
                            c.purchased_component_id
                            for c in components_by_part.values()
                            if c.purchased_component_id is not None
                        }
                    )
                )
            )
        ).all()
    }
    filenames: dict[uuid.UUID, str] = {}
    primary_ids = {p.primary_file_id for p in parts.values() if p.primary_file_id is not None}
    if primary_ids:
        rows = (
            (
                await session.execute(
                    select(PartFile.id, PartFile.filename).where(PartFile.id.in_(primary_ids))
                )
            )
            .tuples()
            .all()
        )
        file_names = dict(rows)
        filenames = {
            p.id: file_names[p.primary_file_id]
            for p in parts.values()
            if p.primary_file_id in file_names
        }

    zero = [Decimal(0)] * len(quantities)

    def unit_rollup(node: Node) -> list[Decimal]:
        """Per one instance of this node: own unit self + children's subtrees."""
        own = unit_self.get(node.part_id, zero)
        acc = list(own)
        for child in by_parent.get(node.id, []):
            child_units = unit_rollup(child)
            for i in range(len(acc)):
                acc[i] += child_units[i] * child.qty_relative_to_parent
        return acc

    def build(node: Node, multiplier: int) -> AssemblyNodeOut:
        part = parts.get(node.part_id)
        component = components_by_part.get(node.part_id)
        assert part is not None  # every non-root node's part is in counts
        flat = multiplier * node.qty_relative_to_parent
        is_assembly = bool(component.is_assembly) if component else part.is_assembly
        obtain = (component.obtain_method if component else part.obtain_method).value.upper()
        group = (
            "subassembly"
            if is_assembly
            else ("purchased" if obtain == "PURCHASED" else "manufactured")
        )
        units = unit_rollup(node)
        rollups = [
            _display(units[i] * node.qty_relative_to_parent * Decimal(q))
            for i, q in enumerate(quantities)
        ]
        selfs = [_display(v) for v in part_self_total.get(node.part_id, zero)]
        pc = (
            pc_by_id.get(component.purchased_component_id)
            if component and component.purchased_component_id
            else None
        )
        return AssemblyNodeOut(
            node_id=node.id,
            part_id=node.part_id,
            component_id=component.id if component else None,
            part_number=part.part_number,
            revision=part.revision,
            description=part.description,
            filename=filenames.get(part.id),
            group=group,
            obtain_method=obtain,
            is_assembly=is_assembly,
            node_qty=node.qty_relative_to_parent,
            flat_qty=flat,
            position=node.position,
            process_id=component.process_id if component else None,
            material_id=component.material_id if component else None,
            piece_price=component.piece_price if component else None,
            purchased_component_id=(component.purchased_component_id if component else None),
            brand=pc.brand if pc else None,
            self_costs=selfs,
            rollup_costs=rollups,
            children=[build(child, flat) for child in by_parent.get(node.id, [])],
        )

    top_level = [build(node, 1) for node in by_parent.get(root_node.id, [])] if root_node else []

    flat_total = sum(counts.values())
    totals = [
        _display(sum((part_self_total[pid][i] for pid in part_self_total), start=Decimal(0)))
        for i in range(len(quantities))
    ]
    del item
    return AssemblyComponentsOut(
        quantities=quantities,
        root_node_id=root_node.id if root_node else None,
        tree=top_level,
        summary=AssemblySummaryOut(flat_qty_total=flat_total, totals=totals),
    )


# --------------------------------------------------------------------------- #
# Bulk Update Components
# --------------------------------------------------------------------------- #
@assembly_router.post("/components/bulk-update")
async def bulk_update_components(
    payload: BulkUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, int]:
    from .nesting import ensure_component_not_nested
    from .operations import _lock_editable_quote
    from .routing import generate_router

    process = await session.get(Process, payload.process_id)
    if process is None or process.deleted_at is not None:
        raise AppError("not_found", "Process not found.", status_code=status.HTTP_404_NOT_FOUND)
    if payload.material_id is not None:
        material = await session.get(Material, payload.material_id)
        if material is None:
            raise AppError(
                "not_found", "Material not found.", status_code=status.HTTP_404_NOT_FOUND
            )

    updated = 0
    roots: set[uuid.UUID] = set()
    for component_id in dict.fromkeys(payload.component_ids):
        component = await session.get(Component, component_id)
        if component is None:
            raise AppError(
                "not_found", "Component not found.", status_code=status.HTTP_404_NOT_FOUND
            )
        await _lock_editable_quote(session, component)
        await ensure_component_not_nested(session, component.id)
        # the modal's warning: "This action will delete all existing operations."
        operations = (
            await session.scalars(select(Operation).where(Operation.component_id == component.id))
        ).all()
        for operation in operations:
            await session.delete(operation)
        component.process_id = payload.process_id
        if payload.material_id is not None:
            component.material_id = payload.material_id
        await session.flush()
        await generate_router(session, component.org_id, component)
        roots.add(component.id)
        updated += 1

    for component_id in roots:
        component = await session.get(Component, component_id)
        if component is not None:
            await _recalculate_root_for(session, component)
    return {"updated": updated}


async def _recalculate_root_for(session: AsyncSession, component: Component) -> None:
    from .costing import recalculate_component

    if component.is_root_component:
        await recalculate_component(session, component.org_id, component.id)
        return
    root_part_id = await session.scalar(
        select(Node.root_part_id).where(Node.part_id == component.part_id).limit(1)
    )
    if root_part_id is None:
        return
    root_id = await session.scalar(
        select(Component.id)
        .where(Component.part_id == root_part_id, Component.is_root_component)
        .limit(1)
    )
    if root_id is not None:
        await recalculate_component(session, component.org_id, root_id)


# --------------------------------------------------------------------------- #
# Reorder (single level — spec: cross-level drag not supported)
# --------------------------------------------------------------------------- #
@assembly_router.post("/quote-items/{quote_item_id}/assembly-components/reorder")
async def reorder_components(
    quote_item_id: uuid.UUID,
    payload: ReorderIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, int]:
    _item, _root_component, root_part = await _load_item(session, quote_item_id)
    siblings = (
        await session.scalars(
            select(Node).where(
                Node.root_part_id == root_part.id,
                Node.parent_node_id == payload.parent_node_id,
            )
        )
    ).all()
    by_id = {n.id: n for n in siblings}
    if set(payload.ordered_node_ids) != set(by_id):
        raise AppError(
            "invalid_order",
            "The order must list exactly the children of one level.",
            status_code=422,
        )
    for position, node_id in enumerate(payload.ordered_node_ids):
        by_id[node_id].position = position
    await session.flush()
    return {"reordered": len(payload.ordered_node_ids)}


# --------------------------------------------------------------------------- #
# Copy pricing (one source → one target; spec limitation)
# --------------------------------------------------------------------------- #
@assembly_router.post("/components/{component_id}/copy-pricing")
async def copy_pricing(
    component_id: uuid.UUID,
    payload: CopyPricingIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, int]:
    from .operations import _lock_editable_quote

    source = await session.get(Component, component_id)
    target = await session.get(Component, payload.target_component_id)
    if source is None or target is None:
        raise AppError("not_found", "Component not found.", status_code=status.HTTP_404_NOT_FOUND)
    if source.id == target.id:
        raise AppError("invalid_target", "Source and target are the same.", status_code=422)
    await _lock_editable_quote(session, target)

    copied = 0
    operations = (
        await session.scalars(
            select(Operation)
            .where(Operation.component_id == source.id)
            .order_by(Operation.position, Operation.created_at, Operation.id)
        )
    ).all()
    if payload.copy_material:
        target.material_id = source.material_id
    for op in operations:
        is_material = op.category.value == "material"
        if is_material and not payload.copy_material:
            continue
        if not is_material and not payload.copy_operations:
            continue
        clone = Operation(
            org_id=target.org_id,
            component_id=target.id,
            operation_def_id=op.operation_def_id,
            name=op.name,
            category=op.category,
            position=op.position,
            calculation_mode=op.calculation_mode,
            run_rate=op.run_rate,
            labour_rate=op.labour_rate,
            setup_basis=op.setup_basis,
            setup_cost=op.setup_cost,
            cost_formula=op.cost_formula,
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
            notes=op.notes,
            variable_overrides=dict(op.variable_overrides or {}),
            origin=op.origin,
            operation_properties=(
                dict(op.operation_properties) if op.operation_properties else None
            ),
            added_manually=False,
        )
        session.add(clone)
        copied += 1
    await session.flush()
    await _recalculate_root_for(session, target)
    return {"copied_operations": copied}


# --------------------------------------------------------------------------- #
# Delete component (⋮ menu)
# --------------------------------------------------------------------------- #
@assembly_router.delete("/components/{component_id}")
async def delete_component(
    component_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, bool]:
    from .operations import _lock_editable_quote

    component = await session.get(Component, component_id)
    if component is None:
        raise AppError("not_found", "Component not found.", status_code=status.HTTP_404_NOT_FOUND)
    if component.is_root_component:
        raise AppError(
            "not_deletable",
            "Die Stücklisten-Position selbst kann hier nicht gelöscht werden.",
            status_code=422,
        )
    await _lock_editable_quote(session, component)
    # remove every occurrence (and its subtree) of this part from the tree
    levels: list[list[uuid.UUID]] = [
        [
            n.id
            for n in (
                await session.scalars(select(Node).where(Node.part_id == component.part_id))
            ).all()
            if n.parent_node_id is not None
        ]
    ]
    while levels[-1]:
        children = (
            await session.scalars(select(Node).where(Node.parent_node_id.in_(levels[-1])))
        ).all()
        levels.append([c.id for c in children])
    # bottom-up: children first (fk_node_parent_org forbids orphaning)
    for level in reversed(levels):
        if level:
            await session.execute(sa_delete(Node).where(Node.id.in_(level)))
    await session.flush()
    root = component
    await session.delete(component)
    await session.flush()
    await _recalculate_root_for(session, root)
    return {"deleted": True}


# --------------------------------------------------------------------------- #
# ADD PURCHASED COMPONENTS (library picker; KB purchased-components)
# --------------------------------------------------------------------------- #
@assembly_router.post("/quote-items/{quote_item_id}/purchased-components")
async def add_purchased_components(
    quote_item_id: uuid.UUID,
    payload: AddPurchasedIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, int]:
    from .operations import _lock_editable_quote

    _item, root_component, root_part = await _load_item(session, quote_item_id)
    await _lock_editable_quote(session, root_component)
    root_node = await session.scalar(
        select(Node).where(Node.part_id == root_part.id, Node.parent_node_id.is_(None))
    )
    if root_node is None:
        root_node = Node(
            org_id=root_part.org_id,
            part_id=root_part.id,
            root_part_id=root_part.id,
            qty_relative_to_parent=1,
        )
        session.add(root_node)
        await session.flush()
    max_position = max(
        (
            n.position
            for n in (
                await session.scalars(select(Node).where(Node.parent_node_id == root_node.id))
            ).all()
        ),
        default=-1,
    )
    created = 0
    for entry in payload.items:
        pc = await session.get(PurchasedComponent, entry.purchased_component_id)
        if pc is None or pc.deleted_at is not None:
            raise AppError(
                "not_found",
                "Purchased component not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        part = Part(
            org_id=principal.active_org_id,
            part_number=pc.oem_part_number,
            description=pc.description,
            obtain_method=ObtainMethod.purchased,
        )
        session.add(part)
        await session.flush()
        component = Component(
            org_id=principal.active_org_id,
            part_id=part.id,
            is_root_component=False,
            obtain_method=ObtainMethod.purchased,
            piece_price=pc.piece_price,
            purchased_component_id=pc.id,
        )
        session.add(component)
        max_position += 1
        session.add(
            Node(
                org_id=principal.active_org_id,
                part_id=part.id,
                parent_node_id=root_node.id,
                root_part_id=root_part.id,
                qty_relative_to_parent=entry.node_qty,
                position=max_position,
            )
        )
        created += 1
    await session.flush()
    root_component.is_assembly = True
    root_part.is_assembly = True
    await _recalculate_root_for(session, root_component)
    return {"added": created}
