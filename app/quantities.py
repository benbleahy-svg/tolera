"""Quantity breaks + ``ComponentQuantity`` cells (M1.6, spec ``#partview`` Pricing &
Quantities).

A line item (root component) carries N **quantity breaks**; each break is one
``ComponentQuantity`` row — the per-break cell every downstream cost/price renders into
(M1.7 op-costs, M1.10 pricing, M1.11 lead times). This module owns the **structural**
layer only: creating the default break, reshaping the break set ("Change quantities"),
and the index-aligned iterators that back the geometry↔Kalk ``part.*`` quantity contract.

M1.6 rules (DECISIONS.md / M1.6 grill, 2026-06-27):

* Breaks are stored **ascending by quantity** — the stable index the three lists align on.
* Duplicate break values are rejected (the schema's ``UNIQUE (component_id, quantity)``;
  PP's KB allows duplicates, but the higher tier governs).
* A line item always has **>= 1 break**; a new root component is born with ``quantity = 1``.
* ``make_quantity`` (``part.qty``) and ``deliver_quantity`` (``part.bom_qty``) equal
  ``quantity`` for the root — no children, no scrap yet (real tree/scrap math is M4).

The route ("Change quantities") lives in ``app.quotes`` so it can reuse the quote
editability/lock helpers; this module is import-clean (no dependency on ``app.quotes``).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import AppError
from .models import ComponentQuantity

# A generous ceiling so a pathological request can't spawn unbounded cells; real quotes
# use a handful of breaks. Not a spec figure — a guardrail (M1.6 grill default).
MAX_QUANTITY_BREAKS = 50


class QuantityCellOut(BaseModel):
    """One quantity-break cell as rendered in the per-qty grid (M1.6 columns)."""

    quantity: int
    make_quantity: int
    deliver_quantity: int


class ChangeQuantitiesRequest(BaseModel):
    """The "Change quantities" body: the full desired break set. Per-item ``>= 1`` and a
    non-empty, bounded list are enforced here; **uniqueness** is a domain check in
    :func:`set_quantity_breaks` (a clean ``duplicate_quantity`` envelope, not a generic
    validation error). Order is irrelevant — the server canonicalises to ascending."""

    model_config = ConfigDict(extra="forbid")

    quantities: Annotated[
        list[Annotated[int, Field(ge=1)]],
        Field(min_length=1, max_length=MAX_QUANTITY_BREAKS),
    ]


def _cell_out(cell: ComponentQuantity) -> QuantityCellOut:
    """Map a cell to its grid row. ``make``/``deliver`` fall back to ``quantity`` (the
    M1.6 root identity) so the grid never shows a NULL even if a future writer leaves
    them unresolved."""
    return QuantityCellOut(
        quantity=cell.quantity,
        make_quantity=cell.make_quantity if cell.make_quantity is not None else cell.quantity,
        deliver_quantity=(
            cell.deliver_quantity if cell.deliver_quantity is not None else cell.quantity
        ),
    )


async def _load_cells(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> list[ComponentQuantity]:
    """A component's break cells, **ascending by quantity** (the canonical index order).

    Filters on ``org_id`` explicitly as well as relying on RLS: these are reusable
    helpers (the ``part.*`` contract M1.9's Kalk layer wraps) that may run on a non-RLS
    connection (a worker/owner session), so the org guard travels with the query."""
    return list(
        await session.scalars(
            select(ComponentQuantity)
            .where(
                ComponentQuantity.org_id == org_id,
                ComponentQuantity.component_id == component_id,
            )
            .order_by(ComponentQuantity.quantity)
        )
    )


async def create_default_break(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> None:
    """Seed a new root component with its single ``quantity = 1`` break (make = deliver =
    1). Called from the add-line-item flow so every line item has the >= 1 break the grid
    requires."""
    session.add(
        ComponentQuantity(
            org_id=org_id,
            component_id=component_id,
            quantity=1,
            make_quantity=1,
            deliver_quantity=1,
        )
    )
    await session.flush()


async def set_quantity_breaks(
    session: AsyncSession,
    org_id: uuid.UUID,
    component_id: uuid.UUID,
    quantities: Sequence[int],
) -> list[QuantityCellOut]:
    """Reshape a component's break set to exactly ``quantities`` ("Change quantities").

    Reconciles **by value**: breaks whose quantity is unchanged are kept (their future
    cost/price cells survive), new quantities get a fresh cell, dropped quantities are
    deleted (CASCADE will take their downstream cells once those exist). Rejects duplicate
    break values (``UNIQUE`` would 500 the second insert; this is the clean 422). Returns
    the reshaped grid ascending.

    The non-empty / positive / unique invariants are validated **here**, not only at the
    request edge (``ChangeQuantitiesRequest``): this is a reusable helper, so a direct
    caller (M1.9 Kalk, M4 BOM, a worker) gets the same clean 422 rather than wiping all
    breaks or tripping the raw DB CHECK."""
    if not quantities:
        raise AppError(
            "invalid_quantity_breaks",
            "At least one quantity break is required.",
            status_code=422,
        )
    if any(qty < 1 for qty in quantities):
        raise AppError(
            "invalid_quantity_breaks",
            "Quantity breaks must be 1 or greater.",
            status_code=422,
        )
    if len(set(quantities)) != len(quantities):
        raise AppError(
            "duplicate_quantity",
            "Quantity breaks must be unique.",
            status_code=422,
        )
    desired = sorted(quantities)
    existing = {cell.quantity: cell for cell in await _load_cells(session, org_id, component_id)}

    # Drop breaks no longer wanted.
    for qty, cell in existing.items():
        if qty not in desired:
            await session.delete(cell)
    # Keep/add the wanted breaks; M1.6 root identity → make = deliver = quantity.
    for qty in desired:
        kept = existing.get(qty)
        if kept is None:
            session.add(
                ComponentQuantity(
                    org_id=org_id,
                    component_id=component_id,
                    quantity=qty,
                    make_quantity=qty,
                    deliver_quantity=qty,
                )
            )
        else:
            kept.make_quantity = qty
            kept.deliver_quantity = qty
    await session.flush()
    return [_cell_out(cell) for cell in await _load_cells(session, org_id, component_id)]


async def load_grids(
    session: AsyncSession, org_id: uuid.UUID, component_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[QuantityCellOut]]:
    """Batched per-component grids (ascending) for a set of components — one query, so the
    quote detail renders every line item's columns without an N+1. Org-scoped explicitly
    (see :func:`_load_cells`)."""
    grids: dict[uuid.UUID, list[QuantityCellOut]] = defaultdict(list)
    if not component_ids:
        return grids
    rows = await session.scalars(
        select(ComponentQuantity)
        .where(
            ComponentQuantity.org_id == org_id,
            ComponentQuantity.component_id.in_(component_ids),
        )
        .order_by(ComponentQuantity.component_id, ComponentQuantity.quantity)
    )
    for cell in rows:
        grids[cell.component_id].append(_cell_out(cell))
    return grids


# --------------------------------------------------------------------------- #
# The geometry↔Kalk ``part.*`` quantity contract — index-aligned lists.
# (M1.9's Kalk ``part`` object wraps these; M1.6 establishes + tests the alignment.)
# --------------------------------------------------------------------------- #
async def get_quantities(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> list[int]:
    """``part.quantities`` — customer-requested break values, ascending."""
    return [cell.quantity for cell in await _load_cells(session, org_id, component_id)]


async def get_make_quantities(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> list[int]:
    """``part.make_quantities`` — qty to make per break (``part.qty``), index-aligned with
    :func:`get_quantities`. = the requested qty for the root in M1.6."""
    return [
        cell.make_quantity if cell.make_quantity is not None else cell.quantity
        for cell in await _load_cells(session, org_id, component_id)
    ]


async def get_bom_quantities(
    session: AsyncSession, org_id: uuid.UUID, component_id: uuid.UUID
) -> list[int]:
    """``part.bom_quantities`` — qty to deliver per break (``part.bom_qty``), index-aligned
    with :func:`get_quantities`. = the requested qty for the root in M1.6."""
    return [
        cell.deliver_quantity if cell.deliver_quantity is not None else cell.quantity
        for cell in await _load_cells(session, org_id, component_id)
    ]
