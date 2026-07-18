"""The orders filter/sort grammar — the read contract for ``POST /api/orders/search``
(M5.6, spec ``#orderslist``).

Mirrors the quotes grammar (:mod:`app.quote_filters`, M1.3): an **allow-listed** set
of filter fields with the operators each supports (an unknown field or an op a field
doesn't support is a clean 422), JSON-scalar coercion to typed comparands, and the
computed **system views** (All Orders / Buyer Portal / Facilitated / Awaiting Shipment)
— derived, never stored. The generic operator/direction enums are shared with the
quotes engine; only the order-specific fields, columns and value-coercion live here.

The Orders toolbar (spec ``#orderslist``) is: a free-text search (order # / quote # /
PO / account — handled by the endpoint, not a filter clause), a **Date Placed** range
(``created_at`` gte/lte), an **Account** filter (``account_id``) and — since the grid
carries a **Source** column — a source filter (``source``). There is deliberately **no
status field**: orders have no lifecycle in v1 (status is ERP-owned); the only shipment
state is nullable ``shipped_at``, surfaced via the Awaiting-Shipment system view.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import InstrumentedAttribute

from .models import Order, OrderLine, OrderSource
from .quote_filters import FilterOp, SortDir, SystemView

#: A filterable/sortable target: a mapped ``Order`` column (all order filters are flat
#: columns — no derived expressions, unlike the quotes priority rollup).
_Col = InstrumentedAttribute[Any] | ColumnElement[Any]

#: Derived per-order **parts count** = number of its :class:`OrderLine` rows (spec
#: ``#orderslist`` "Parts" column). Correlated scalar subquery so it rides the same
#: machinery as a flat column; ``correlate(Order)`` pins it to the outer order row.
ORDER_PARTS_COUNT: ColumnElement[Any] = (
    select(func.count(OrderLine.id))
    .where(OrderLine.order_id == Order.id)
    .correlate(Order)
    .scalar_subquery()
)

#: Derived **Expected Ship Date** = earliest ``ships_on`` across the order's lines
#: (spec ``#orderslist``; there is no order-level Ships-On). NULL when no line has a
#: ships_on (e.g. a facilitated order still being built).
ORDER_EARLIEST_SHIP: ColumnElement[Any] = (
    select(func.min(OrderLine.ships_on))
    .where(OrderLine.order_id == Order.id)
    .correlate(Order)
    .scalar_subquery()
)


class OrderFilterField(enum.StrEnum):
    """The allow-listed order columns a filter may target."""

    account_id = "account_id"
    source = "source"
    created_at = "created_at"  # "Date Placed"


class OrderSortField(enum.StrEnum):
    """The allow-listed columns a sort may target."""

    created_at = "created_at"
    number = "number"
    net_minor = "net_minor"  # Order Total (net)


_Kind = Literal["enum", "uuid", "datetime"]

# field → (value kind, operators valid for it). A clause whose (field, op) pair is
# absent is rejected at parse time with a 422.
_FILTER_SPEC: dict[OrderFilterField, tuple[_Kind, frozenset[FilterOp]]] = {
    OrderFilterField.account_id: (
        "uuid",
        frozenset({FilterOp.eq, FilterOp.in_, FilterOp.is_null}),
    ),
    OrderFilterField.source: ("enum", frozenset({FilterOp.eq, FilterOp.in_})),
    OrderFilterField.created_at: ("datetime", frozenset({FilterOp.gte, FilterOp.lte})),
}

_FILTER_COLUMN: dict[OrderFilterField, _Col] = {
    OrderFilterField.account_id: Order.account_id,
    OrderFilterField.source: Order.source,
    OrderFilterField.created_at: Order.created_at,
}

_SORT_COLUMN: dict[OrderSortField, _Col] = {
    OrderSortField.created_at: Order.created_at,
    OrderSortField.number: Order.number,
    OrderSortField.net_minor: Order.net_minor,
}


def _coerce_scalar(kind: _Kind, value: Any) -> Any:
    """Coerce one JSON scalar to its typed comparand, or raise ``ValueError``.

    Raising ``ValueError`` (never ``TypeError``) keeps a bad value inside Pydantic's
    validation path → a 422, not a 500."""
    try:
        if kind == "enum":
            return OrderSource(value)
        if kind == "uuid":
            if not isinstance(value, str):
                raise ValueError("expected a UUID string")
            return uuid.UUID(value)
        # datetime — the "Date Placed" (created_at) column is timestamptz stored in
        # UTC. The frontend sends a naive local-day boundary (e.g. "2026-07-01T00:00:00");
        # attach UTC explicitly so the comparison is unambiguous at the Python layer
        # (never left to the driver's naive-datetime interpretation). Offset-aware
        # inputs are respected as given.
        if not isinstance(value, str):
            raise ValueError("expected an ISO-8601 datetime string")
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid value for {kind} field: {value!r}") from exc


class OrderFilterClause(BaseModel):
    """One ``{field, op, value}`` predicate. ANDed with its siblings."""

    model_config = ConfigDict(extra="forbid")

    field: OrderFilterField
    op: FilterOp
    value: Any = None

    @model_validator(mode="after")
    def _check(self) -> OrderFilterClause:
        kind, allowed = _FILTER_SPEC[self.field]
        if self.op not in allowed:
            raise ValueError(
                f"operator {self.op.value!r} is not valid for field {self.field.value!r}"
            )
        if self.op == FilterOp.is_null:
            if not isinstance(self.value, bool):
                raise ValueError("is_null requires a boolean value")
        elif self.op == FilterOp.in_:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("in requires a non-empty list value")
            for item in self.value:
                _coerce_scalar(kind, item)
        else:  # eq / gte / lte — a single scalar
            if self.value is None or isinstance(self.value, list | dict | bool):
                raise ValueError(f"{self.op.value} requires a scalar value")
            _coerce_scalar(kind, self.value)
        return self


class OrderSortClause(BaseModel):
    """One ``{field, dir}`` sort key."""

    model_config = ConfigDict(extra="forbid")

    field: OrderSortField
    dir: SortDir = SortDir.asc


def _filter_condition(clause: OrderFilterClause) -> ColumnElement[bool]:
    """Build the SQL boolean for one validated clause."""
    kind, _ = _FILTER_SPEC[clause.field]
    column = _FILTER_COLUMN[clause.field]
    if clause.op == FilterOp.is_null:
        return column.is_(None) if clause.value else column.isnot(None)
    if clause.op == FilterOp.in_:
        return column.in_([_coerce_scalar(kind, v) for v in clause.value])
    operand = _coerce_scalar(kind, clause.value)
    cond: ColumnElement[bool]
    if clause.op == FilterOp.eq:
        cond = column == operand
    elif clause.op == FilterOp.gte:
        cond = column >= operand
    else:  # FilterOp.lte
        cond = column <= operand
    return cond


def apply_filters(stmt: Select[Any], clauses: list[OrderFilterClause]) -> Select[Any]:
    """AND every clause onto ``stmt``."""
    for clause in clauses:
        stmt = stmt.where(_filter_condition(clause))
    return stmt


def apply_sort(stmt: Select[Any], sorts: list[OrderSortClause]) -> Select[Any]:
    """Apply the sort keys, then a stable ``id`` tiebreaker so pagination is
    deterministic. With no sort keys, default to newest-first (Date Placed desc)."""
    order = []
    for sort in sorts:
        column = _SORT_COLUMN[sort.field]
        expr = column.desc() if sort.dir == SortDir.desc else column.asc()
        order.append(expr)
    if not order:
        order.append(Order.created_at.desc())
    order.append(Order.id.desc())  # deterministic tiebreaker
    return stmt.order_by(*order)


# --------------------------------------------------------------------------- #
# Computed system views — derived, never stored (spec #orderslist)
# --------------------------------------------------------------------------- #
#: The orders-scope system views, in sidebar order. ``all-orders`` is the default.
SYSTEM_ORDER_VIEWS: tuple[SystemView, ...] = (
    SystemView(key="all-orders", label_key="orders.views.all", is_default=True),
    SystemView(key="buyer-portal", label_key="orders.views.buyer_portal"),
    SystemView(key="facilitated", label_key="orders.views.facilitated"),
    SystemView(key="awaiting-shipment", label_key="orders.views.awaiting_shipment"),
)

_SYSTEM_VIEW_KEYS = frozenset(v.key for v in SYSTEM_ORDER_VIEWS)


def is_system_view(key: str) -> bool:
    return key in _SYSTEM_VIEW_KEYS


def apply_system_view(stmt: Select[Any], key: str) -> Select[Any]:
    """Apply a computed system view's predicate + default sort. Caller must have
    checked :func:`is_system_view` (an unknown key raises). All views sort by Date
    Placed desc — orders have no other natural ordering."""
    newest = (Order.created_at.desc(), Order.id.desc())
    if key == "all-orders":
        return stmt.order_by(*newest)
    if key == "buyer-portal":
        return stmt.where(Order.source == OrderSource.buyer_portal).order_by(*newest)
    if key == "facilitated":
        return stmt.where(Order.source == OrderSource.facilitated).order_by(*newest)
    if key == "awaiting-shipment":
        # No shipment recorded yet (spec: the only shipment state is nullable
        # shipped_at). Earliest expected ship first, so the most urgent surface.
        return stmt.where(Order.shipped_at.is_(None)).order_by(
            ORDER_EARLIEST_SHIP.asc().nulls_last(), *newest
        )
    raise ValueError(f"unknown system view: {key!r}")
