"""The quotes filter/sort grammar — the single contract shared by the quotes
``/search`` endpoint and stored saved views (M1.3, spec ``#quoteslist``).

A saved view's ``filters``/``sort`` JSONB has the **exact** shape of the
``POST /api/quotes/search`` request body, so applying a view = replaying its stored
clauses (one grammar, no translation layer — DECISIONS.md 2026-06-25 "M1.3 build
path"). This module is the authority for:

  * the **allow-listed** filter fields + the operators valid for each (an unknown
    field or an op the field doesn't support is a clean 422, never a 500 or a raw SQL
    error);
  * coercing the JSON scalar values to typed comparands (enum / uuid / datetime);
  * applying validated clauses to a SQLAlchemy ``Select`` over :class:`Quote`;
  * the **computed system views** (All Quotes, My Quotes, Drafts, Outstanding,
    Overdue) — derived from status / ``due_date`` / the caller, **never stored**
    (spec: "Outstanding/Overdue are derived, not stored").

v1 scope (DECISIONS.md 2026-06-25): ``priority`` is intentionally **not** a field
(its home — quote vs. line_item — is unresolved; adding it would commit contested
schema). Filters use **absolute** values only; relative presets ("last 90 days") are
surfaced as system views / client sugar, not a stored relative-date type.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import ColumnElement, Select, func, or_
from sqlalchemy.orm import InstrumentedAttribute

from .models import Quote, QuoteStatus


class FilterField(enum.StrEnum):
    """The allow-listed quote columns a filter may target (all on the M1.3 stub)."""

    status = "status"
    account_id = "account_id"
    salesperson_id = "salesperson_id"
    estimator_id = "estimator_id"
    created_at = "created_at"
    due_date = "due_date"


class SortField(enum.StrEnum):
    """The allow-listed columns a sort may target."""

    created_at = "created_at"
    due_date = "due_date"
    status = "status"
    number = "number"


class FilterOp(enum.StrEnum):
    """The supported comparison operators."""

    eq = "eq"
    in_ = "in"
    is_null = "is_null"
    gte = "gte"
    lte = "lte"


class SortDir(enum.StrEnum):
    asc = "asc"
    desc = "desc"


_Kind = Literal["enum", "uuid", "datetime"]

# field → (value kind, operators valid for it). The single allow-list: a clause whose
# (field, op) pair is absent is rejected at parse time with a 422.
_FILTER_SPEC: dict[FilterField, tuple[_Kind, frozenset[FilterOp]]] = {
    FilterField.status: ("enum", frozenset({FilterOp.eq, FilterOp.in_})),
    FilterField.account_id: ("uuid", frozenset({FilterOp.eq, FilterOp.in_, FilterOp.is_null})),
    FilterField.salesperson_id: ("uuid", frozenset({FilterOp.eq, FilterOp.in_, FilterOp.is_null})),
    FilterField.estimator_id: ("uuid", frozenset({FilterOp.eq, FilterOp.in_, FilterOp.is_null})),
    FilterField.created_at: ("datetime", frozenset({FilterOp.gte, FilterOp.lte})),
    FilterField.due_date: ("datetime", frozenset({FilterOp.gte, FilterOp.lte, FilterOp.is_null})),
}

# field → the mapped ORM column (kept beside _FILTER_SPEC; same keys).
_FILTER_COLUMN: dict[FilterField, InstrumentedAttribute[Any]] = {
    FilterField.status: Quote.status,
    FilterField.account_id: Quote.account_id,
    FilterField.salesperson_id: Quote.salesperson_id,
    FilterField.estimator_id: Quote.estimator_id,
    FilterField.created_at: Quote.created_at,
    FilterField.due_date: Quote.due_date,
}

_SORT_COLUMN: dict[SortField, InstrumentedAttribute[Any]] = {
    SortField.created_at: Quote.created_at,
    SortField.due_date: Quote.due_date,
    SortField.status: Quote.status,
    SortField.number: Quote.number,
}


def _coerce_scalar(kind: _Kind, value: Any) -> Any:
    """Coerce one JSON scalar to its typed comparand, or raise ``ValueError``.

    Raising ``ValueError`` (never ``TypeError``) keeps a bad value inside Pydantic's
    validation path → a 422, not a 500."""
    try:
        if kind == "enum":
            return QuoteStatus(value)
        if kind == "uuid":
            if not isinstance(value, str):
                raise ValueError("expected a UUID string")
            return uuid.UUID(value)
        # datetime
        if not isinstance(value, str):
            raise ValueError("expected an ISO-8601 datetime string")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            # Date-only / offset-less values are part of the contract (a date
            # picker sends "2026-06-30"); pin them to UTC explicitly rather than
            # leaving the interpretation to the driver (ISO-8601-UTC convention;
            # stricter rejection is an OPEN item in DECISIONS.md).
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid value for {kind} field: {value!r}") from exc


class FilterClause(BaseModel):
    """One ``{field, op, value}`` predicate. ANDed with its siblings."""

    model_config = ConfigDict(extra="forbid")

    field: FilterField
    op: FilterOp
    value: Any = None

    @model_validator(mode="after")
    def _check(self) -> FilterClause:
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


class SortClause(BaseModel):
    """One ``{field, dir}`` sort key."""

    model_config = ConfigDict(extra="forbid")

    field: SortField
    dir: SortDir = SortDir.asc


def _filter_condition(clause: FilterClause) -> ColumnElement[bool]:
    """Build the SQL boolean for one validated clause."""
    kind, _ = _FILTER_SPEC[clause.field]
    column = _FILTER_COLUMN[clause.field]
    if clause.op == FilterOp.is_null:
        return column.is_(None) if clause.value else column.isnot(None)
    if clause.op == FilterOp.in_:
        return column.in_([_coerce_scalar(kind, v) for v in clause.value])
    operand = _coerce_scalar(kind, clause.value)
    # Assign to a typed local: SQLAlchemy's comparison operators are typed loosely
    # (mypy sees Any), but the result is a boolean SQL expression.
    cond: ColumnElement[bool]
    if clause.op == FilterOp.eq:
        cond = column == operand
    elif clause.op == FilterOp.gte:
        cond = column >= operand
    else:  # FilterOp.lte
        cond = column <= operand
    return cond


def apply_filters(stmt: Select[Any], clauses: list[FilterClause]) -> Select[Any]:
    """AND every clause onto ``stmt``."""
    for clause in clauses:
        stmt = stmt.where(_filter_condition(clause))
    return stmt


def apply_sort(stmt: Select[Any], sorts: list[SortClause]) -> Select[Any]:
    """Apply the sort keys, then a stable ``id`` tiebreaker so pagination is
    deterministic. With no sort keys, default to newest-first."""
    order = []
    for sort in sorts:
        column = _SORT_COLUMN[sort.field]
        order.append(column.desc() if sort.dir == SortDir.desc else column.asc())
    if not order:
        order.append(Quote.created_at.desc())
    order.append(Quote.id.desc())  # deterministic tiebreaker
    return stmt.order_by(*order)


# --------------------------------------------------------------------------- #
# Computed system views — derived, never stored (spec #quoteslist)
# --------------------------------------------------------------------------- #
class SystemView(BaseModel):
    """A built-in, non-stored view. ``label_key`` is an i18n key the frontend
    localizes; ``is_default`` marks the landing view."""

    key: str
    label_key: str
    is_default: bool = False


#: The quotes-scope system views, in sidebar order. ``all-quotes`` is the default.
SYSTEM_QUOTE_VIEWS: tuple[SystemView, ...] = (
    SystemView(key="all-quotes", label_key="quotes.views.all", is_default=True),
    SystemView(key="my-quotes", label_key="quotes.views.mine"),
    SystemView(key="drafts", label_key="quotes.views.drafts"),
    SystemView(key="outstanding", label_key="quotes.views.outstanding"),
    SystemView(key="overdue", label_key="quotes.views.overdue"),
)

_SYSTEM_VIEW_KEYS = frozenset(v.key for v in SYSTEM_QUOTE_VIEWS)

# Statuses that count as "still open" for the Overdue view (a won/lost/expired quote
# is never overdue).
_OPEN_STATUSES = (QuoteStatus.draft, QuoteStatus.sent)


def is_system_view(key: str) -> bool:
    return key in _SYSTEM_VIEW_KEYS


def apply_system_view(stmt: Select[Any], key: str, *, user_id: uuid.UUID) -> Select[Any]:
    """Apply a computed system view's predicate + default sort. Caller must have
    checked :func:`is_system_view` (an unknown key raises)."""
    if key == "all-quotes":
        return stmt.order_by(Quote.created_at.desc(), Quote.id.desc())
    if key == "my-quotes":
        return stmt.where(
            or_(Quote.salesperson_id == user_id, Quote.estimator_id == user_id)
        ).order_by(Quote.created_at.desc(), Quote.id.desc())
    if key == "drafts":
        return stmt.where(Quote.status == QuoteStatus.draft).order_by(
            Quote.created_at.desc(), Quote.id.desc()
        )
    if key == "outstanding":
        return stmt.where(Quote.status == QuoteStatus.sent).order_by(
            Quote.created_at.desc(), Quote.id.desc()
        )
    if key == "overdue":
        # Past due and still open — soonest-overdue first.
        return stmt.where(
            Quote.due_date.isnot(None),
            Quote.due_date < func.now(),
            Quote.status.in_(_OPEN_STATUSES),
        ).order_by(Quote.due_date.asc(), Quote.id.desc())
    raise ValueError(f"unknown system view: {key!r}")
