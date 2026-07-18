"""Purchased-component library + Smart Match + convert-to-purchased (M4.10).

Spec ``#assembly`` (Convert to Purchased Component / Smart Match / Persistent
geometry memory) + DOMAIN-MODEL §5; KB ``purchased-components``.

Match tiers (DemoL/03): **OEM Part Number Match** (the part's part number or
primary-file stem equals a library entry's OEM/internal part number), **OEM
Geometric Match** (the library entry's linked OEM-catalog product carries the
same geometry signature), **Historical Geometric Match (N)** (the org's
geometry memory points this signature at the entry, N = how often it matched
before). "Unlinked OEM Products" are catalog rows with the same signature no
library entry references yet.

Convert freezes ``piece_price`` onto the component (E4-d config-freeze —
later library edits never reprice an existing quote; the FK is provenance)
and upserts the geometry memory, so the same signature **auto-tags** as
purchased in all future quotes (the interrogation-success hook calls
:func:`apply_purchased_memory_by_hash`) — deterministic geometry matching,
not Lens, hence no AI-Governor gate.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import (
    Component,
    Node,
    OemProduct,
    Part,
    PartFile,
    PcGeometryMemory,
    PurchasedComponent,
    QuoteItem,
)

purchased_components_router = APIRouter(prefix="/api", tags=["purchased-components"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class PurchasedComponentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oem_part_number: Annotated[str, Field(min_length=1, max_length=200)]
    internal_part_number: Annotated[str | None, Field(max_length=200)] = None
    piece_price: Annotated[Decimal | None, Field(ge=0)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    brand: Annotated[str | None, Field(max_length=200)] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class PurchasedComponentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oem_part_number: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    internal_part_number: Annotated[str | None, Field(max_length=200)] = None
    piece_price: Annotated[Decimal | None, Field(ge=0)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    brand: Annotated[str | None, Field(max_length=200)] = None
    custom_fields: dict[str, Any] | None = None


class PurchasedComponentOut(BaseModel):
    id: uuid.UUID
    oem_part_number: str
    internal_part_number: str | None
    piece_price: Decimal | None
    currency: str
    description: str | None
    brand: str | None
    custom_fields: dict[str, Any]
    oem_product_id: uuid.UUID | None


class OemProductOut(BaseModel):
    id: uuid.UUID
    brand: str
    oem_part_number: str
    specs: dict[str, Any]


class MatchCard(BaseModel):
    """One Previously-Used card with its three ✓/✗ indicators (DemoL/03)."""

    purchased_component: PurchasedComponentOut
    oem_part_number_match: bool
    oem_geometric_match: bool
    historical_geometric_matches: int


class ComponentSummaryOut(BaseModel):
    id: uuid.UUID
    part_number: str | None
    revision: str | None
    filename: str | None
    obtain_method: str
    piece_price: Decimal | None
    purchased_component_id: uuid.UUID | None


class PurchaseMatchesOut(BaseModel):
    component: ComponentSummaryOut
    smart: list[MatchCard]
    unlinked_oem: list[OemProductOut]
    all: list[PurchasedComponentOut]


class ConvertPayload(BaseModel):
    """Pick a library entry OR create one inline (the Create-New fallback)."""

    model_config = ConfigDict(extra="forbid")

    purchased_component_id: uuid.UUID | None = None
    create: PurchasedComponentCreate | None = None


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def _pc_out(pc: PurchasedComponent) -> PurchasedComponentOut:
    return PurchasedComponentOut(
        id=pc.id,
        oem_part_number=pc.oem_part_number,
        internal_part_number=pc.internal_part_number,
        piece_price=pc.piece_price,
        currency=pc.currency,
        description=pc.description,
        brand=pc.brand,
        custom_fields=pc.custom_fields,
        oem_product_id=pc.oem_product_id,
    )


# --------------------------------------------------------------------------- #
# Library CRUD
# --------------------------------------------------------------------------- #
@purchased_components_router.get("/purchased-components")
async def list_purchased_components(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    q: str | None = None,
) -> list[PurchasedComponentOut]:
    query = (
        select(PurchasedComponent)
        .where(PurchasedComponent.deleted_at.is_(None))
        .order_by(PurchasedComponent.oem_part_number)
    )
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(
            PurchasedComponent.oem_part_number.ilike(needle)
            | PurchasedComponent.internal_part_number.ilike(needle)
            | PurchasedComponent.description.ilike(needle)
        )
    rows = (await session.scalars(query)).all()
    return [_pc_out(pc) for pc in rows]


async def _org_currency(session: AsyncSession, org_id: uuid.UUID) -> str:
    from .models import Organization

    org = await session.get(Organization, org_id)
    return org.currency if org is not None else "EUR"


@purchased_components_router.post("/purchased-components", status_code=status.HTTP_201_CREATED)
async def create_purchased_component(
    payload: PurchasedComponentCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PurchasedComponentOut:
    # piece prices carry the org's currency (EUR/CHF) — a CHF shop's library
    # must never be silently EUR-labelled (fresh-eyes review)
    pc = PurchasedComponent(
        org_id=principal.active_org_id,
        currency=await _org_currency(session, principal.active_org_id),
        **payload.model_dump(),
    )
    session.add(pc)
    await session.flush()
    return _pc_out(pc)


@purchased_components_router.patch("/purchased-components/{pc_id}")
async def update_purchased_component(
    pc_id: uuid.UUID,
    payload: PurchasedComponentUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> PurchasedComponentOut:
    pc = await session.get(PurchasedComponent, pc_id)
    if pc is None or pc.deleted_at is not None:
        raise AppError(
            "not_found", "Purchased component not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(pc, key, value)
    await session.flush()
    return _pc_out(pc)


# --------------------------------------------------------------------------- #
# Smart Match
# --------------------------------------------------------------------------- #
async def _get_component_or_404(session: AsyncSession, component_id: uuid.UUID) -> Component:
    component = await session.get(Component, component_id)
    if component is None:
        raise AppError("not_found", "Component not found.", status_code=status.HTTP_404_NOT_FOUND)
    return component


def _stem(filename: str | None) -> str | None:
    if not filename:
        return None
    return filename.rsplit(".", 1)[0]


async def _component_filename(session: AsyncSession, part: Part) -> str | None:
    if part.primary_file_id is None:
        return None
    filename = await session.scalar(
        select(PartFile.filename).where(PartFile.id == part.primary_file_id)
    )
    return filename


def _names_for_matching(part: Part, filename: str | None) -> set[str]:
    names = {
        name.strip().casefold()
        for name in (part.part_number, filename, _stem(filename))
        if name and name.strip()
    }
    return names


@purchased_components_router.get("/components/{component_id}/purchase-matches")
async def get_purchase_matches(
    component_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> PurchaseMatchesOut:
    component = await _get_component_or_404(session, component_id)
    part = await session.get(Part, component.part_id)
    assert part is not None  # FK-guaranteed
    filename = await _component_filename(session, part)
    names = _names_for_matching(part, filename)

    library = (
        await session.scalars(
            select(PurchasedComponent)
            .where(PurchasedComponent.deleted_at.is_(None))
            .order_by(PurchasedComponent.oem_part_number)
        )
    ).all()

    memory: PcGeometryMemory | None = None
    oem_products_by_id: dict[uuid.UUID, OemProduct] = {}
    geometric_oem_ids: set[uuid.UUID] = set()
    if part.geom_hash:
        memory = await session.scalar(
            select(PcGeometryMemory).where(PcGeometryMemory.geom_hash == part.geom_hash)
        )
        geo_products = (
            await session.scalars(select(OemProduct).where(OemProduct.geom_hash == part.geom_hash))
        ).all()
        oem_products_by_id = {p.id: p for p in geo_products}
        geometric_oem_ids = set(oem_products_by_id)

    cards: list[MatchCard] = []
    linked_oem_ids: set[uuid.UUID] = set()
    for pc in library:
        if pc.oem_product_id is not None:
            linked_oem_ids.add(pc.oem_product_id)
        pn_match = bool(
            names
            and (
                pc.oem_part_number.casefold() in names
                or (pc.internal_part_number or "").casefold() in names
            )
        )
        geo_match = pc.oem_product_id in geometric_oem_ids
        historical = memory.match_count if memory and memory.purchased_component_id == pc.id else 0
        if pn_match or geo_match or historical:
            cards.append(
                MatchCard(
                    purchased_component=_pc_out(pc),
                    oem_part_number_match=pn_match,
                    oem_geometric_match=geo_match,
                    historical_geometric_matches=historical,
                )
            )
    cards.sort(
        key=lambda c: (
            c.oem_part_number_match,
            c.oem_geometric_match,
            c.historical_geometric_matches,
        ),
        reverse=True,
    )

    unlinked = [
        OemProductOut(id=p.id, brand=p.brand, oem_part_number=p.oem_part_number, specs=p.specs)
        for p in oem_products_by_id.values()
        if p.id not in linked_oem_ids
    ]

    return PurchaseMatchesOut(
        component=ComponentSummaryOut(
            id=component.id,
            part_number=part.part_number,
            revision=part.revision,
            filename=filename,
            obtain_method=component.obtain_method.value.upper(),
            piece_price=component.piece_price,
            purchased_component_id=component.purchased_component_id,
        ),
        smart=cards,
        unlinked_oem=unlinked,
        all=[_pc_out(pc) for pc in library],
    )


# --------------------------------------------------------------------------- #
# Convert + memory
# --------------------------------------------------------------------------- #
async def link_component_to_pc(
    session: AsyncSession,
    component: Component,
    part: Part,
    pc: PurchasedComponent,
    *,
    record_memory: bool,
) -> None:
    """The convert mutation: PURCHASED + provenance FK + frozen piece price.

    Existing operations are deliberately kept (the estimator prunes them) —
    the purchased contribution is ``piece_price x make_qty`` regardless
    (DECISIONS.md 2026-07-09 (4))."""
    from .models import ObtainMethod

    component.obtain_method = ObtainMethod.purchased
    component.purchased_component_id = pc.id
    component.piece_price = pc.piece_price
    part.obtain_method = ObtainMethod.purchased
    if record_memory and part.geom_hash:
        await _upsert_memory(session, component.org_id, part.geom_hash, pc.id)


async def _upsert_memory(
    session: AsyncSession, org_id: uuid.UUID, geom_hash: str, pc_id: uuid.UUID
) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    # atomic upsert (CodeRabbit): concurrent converts must neither duplicate
    # the (org, signature) row nor lose an increment. Latest conversion wins
    # the link; every (re-)conversion counts as one historical match.
    statement = pg_insert(PcGeometryMemory).values(
        org_id=org_id, geom_hash=geom_hash, purchased_component_id=pc_id, match_count=1
    )
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_pc_geometry_memory_org_hash",
            set_={
                "purchased_component_id": pc_id,
                "match_count": PcGeometryMemory.match_count + 1,
            },
        )
    )
    await session.flush()


async def _reprice_root_for(session: AsyncSession, component: Component) -> None:
    """A child's cost source changed — recompute the root's roll-up."""
    from .costing import recalculate_component

    root_component_id = await session.scalar(
        select(QuoteItem.root_component_id).where(QuoteItem.root_component_id == component.id)
    )
    if root_component_id is None:
        root_part_id = await session.scalar(
            select(Node.root_part_id).where(Node.part_id == component.part_id).limit(1)
        )
        if root_part_id is not None:
            root_component_id = await session.scalar(
                select(Component.id)
                .where(Component.part_id == root_part_id, Component.is_root_component)
                .limit(1)
            )
    if root_component_id is not None:
        root = await session.get(Component, root_component_id)
        if root is not None:
            await recalculate_component(session, root.org_id, root.id)


@purchased_components_router.post("/components/{component_id}/convert-to-purchased")
async def convert_to_purchased(
    component_id: uuid.UUID,
    payload: ConvertPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> ComponentSummaryOut:
    component = await _get_component_or_404(session, component_id)
    if component.is_assembly:
        # KB: converting a subassembly deletes its children — deliberately out
        # of the v1 slice; only manufactured leaves convert here
        raise AppError(
            "not_convertible",
            "Nur Fertigungsteile können in Kaufteile umgewandelt werden.",
            status_code=422,
        )
    # a convert changes quote costing — same Draft editability gate + race
    # lock as every operation edit (CodeRabbit)
    from .operations import _lock_editable_quote

    await _lock_editable_quote(session, component)
    if (payload.purchased_component_id is None) == (payload.create is None):
        raise AppError(
            "invalid_payload",
            "Pass exactly one of purchased_component_id or create.",
            status_code=422,
        )

    if payload.create is not None:
        pc = PurchasedComponent(
            org_id=principal.active_org_id,
            currency=await _org_currency(session, principal.active_org_id),
            **payload.create.model_dump(),
        )
        session.add(pc)
        await session.flush()
    else:
        found = await session.get(PurchasedComponent, payload.purchased_component_id)
        if found is None or found.deleted_at is not None:
            raise AppError(
                "not_found",
                "Purchased component not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        pc = found

    # tier-1 money: the frozen piece price flows into the quote's costing —
    # its currency must match the org's (EUR/CHF are never mixed silently)
    if pc.currency != await _org_currency(session, principal.active_org_id):
        raise AppError(
            "currency_mismatch",
            "Die Währung des Kaufteils passt nicht zur Angebotswährung.",
            status_code=422,
        )

    part = await session.get(Part, component.part_id)
    assert part is not None  # FK-guaranteed
    await link_component_to_pc(session, component, part, pc, record_memory=True)
    await session.flush()
    await _reprice_root_for(session, component)
    filename = await _component_filename(session, part)
    return ComponentSummaryOut(
        id=component.id,
        part_number=part.part_number,
        revision=part.revision,
        filename=filename,
        obtain_method=component.obtain_method.value.upper(),
        piece_price=component.piece_price,
        purchased_component_id=component.purchased_component_id,
    )


# --------------------------------------------------------------------------- #
# Auto-tag hooks (spec #assembly "Persistent geometry memory")
# --------------------------------------------------------------------------- #
async def apply_purchased_memory_by_hash(
    session: AsyncSession, *, org_id: uuid.UUID, part_id: uuid.UUID, geom_hash: str
) -> bool:
    """Interrogation-success hook: a freshly signed part whose signature is in
    the org's memory auto-tags as purchased — the estimator never re-converts
    the same fastener. Root components stay untouched (a quote line item is
    never silently flipped); deterministic geometry matching, not Lens."""
    memory = await session.scalar(
        select(PcGeometryMemory).where(
            PcGeometryMemory.org_id == org_id, PcGeometryMemory.geom_hash == geom_hash
        )
    )
    if memory is None:
        return False
    pc = await session.get(PurchasedComponent, memory.purchased_component_id)
    if pc is None or pc.deleted_at is not None:
        return False
    # money guard (CodeRabbit): the frozen price must match the org currency —
    # a stale-currency library entry never silently mixes EUR/CHF
    if pc.currency != await _org_currency(session, org_id):
        return False
    part = await session.get(Part, part_id)
    if part is None:
        return False
    from .models import ObtainMethod

    components = (
        await session.scalars(
            select(Component).where(
                Component.part_id == part_id,
                Component.is_root_component.is_(False),
                Component.obtain_method == ObtainMethod.manufactured,
                Component.is_assembly.is_(False),
                Component.purchased_component_id.is_(None),
            )
        )
    ).all()
    if not components:
        return False
    # only quotes still in Draft may be mutated by the background job
    # (CodeRabbit): a quote finalized while interrogation ran keeps its
    # costing untouched — the estimator converts manually if wanted
    from .operations import _quote_is_editable

    tagged: list[Component] = []
    for component in components:
        quote = await _owning_quote(session, component)
        if quote is not None and not _quote_is_editable(quote):
            continue
        await link_component_to_pc(session, component, part, pc, record_memory=False)
        tagged.append(component)
    if not tagged:
        return False
    memory.match_count += len(tagged)
    await session.flush()
    for component in tagged:
        await _reprice_root_for(session, component)
    return True


async def _owning_quote(session: AsyncSession, component: Component) -> Any:
    """The Quote owning this component's tree (None when unattached)."""
    from .models import Quote

    root_component_id = await session.scalar(
        select(QuoteItem.root_component_id).where(QuoteItem.root_component_id == component.id)
    )
    if root_component_id is None:
        root_part_id = await session.scalar(
            select(Node.root_part_id).where(Node.part_id == component.part_id).limit(1)
        )
        if root_part_id is None:
            return None
        root_component_id = await session.scalar(
            select(Component.id)
            .where(Component.part_id == root_part_id, Component.is_root_component)
            .limit(1)
        )
    if root_component_id is None:
        return None
    return await session.scalar(
        select(Quote)
        .join(QuoteItem, QuoteItem.quote_id == Quote.id)
        .where(QuoteItem.root_component_id == root_component_id)
        .limit(1)
    )


async def auto_link_purchased_by_name(
    session: AsyncSession, *, names: set[str]
) -> PurchasedComponent | None:
    """KB ``purchased-components``: a child whose filename/part number exactly
    matches a library entry auto-converts. Case-insensitive exact match on
    OEM or internal part number; None when ambiguous or absent. Org scoping
    rides the session's RLS (the router-session pattern)."""
    if not names:
        return None
    folded = {n.casefold() for n in names if n}
    if not folded:
        return None
    rows = (
        await session.scalars(
            select(PurchasedComponent).where(
                PurchasedComponent.deleted_at.is_(None),
                func.lower(PurchasedComponent.oem_part_number).in_(folded)
                | func.lower(func.coalesce(PurchasedComponent.internal_part_number, "")).in_(
                    folded
                ),
            )
        )
    ).all()
    return rows[0] if len(rows) == 1 else None
