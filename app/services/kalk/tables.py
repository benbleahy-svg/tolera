"""Kalk custom tables — ``table_var`` / ``table_lookup`` and filtering
(KALK-REFERENCE §5; spec ``#kalk-tables``; DECISIONS.md 2026-07-08 column
types = boolean | numeric | string, caps 200 / 10,000).

Table data never reaches the sandbox by I/O: a :class:`TableProvider` hands
the runtime an immutable, org-scoped snapshot per table name (fetched by the
caller's provider — DB-backed in the app, dict-backed in tests), and all
filtering/ordering runs in-process on that snapshot. This keeps evaluation
deterministic and preserves the M1.8 subprocess-executor option (a future
executor can prefetch snapshots).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.services.kalk.errors import abort as _abort
from app.services.kalk.lists import P3LList

if TYPE_CHECKING:
    from app.services.kalk.runtime import Runtime

COLUMN_TYPES = ("boolean", "numeric", "string")
CONDITIONS = ("=", ">", ">=", "<", "<=", "range", "contains")
TABLE_VAR_MAX_ROWS = 200
TABLE_LOOKUP_MAX_ROWS = 10_000


# ---------------------------------------------------------------------------
# snapshots (provider contract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableColumn:
    name: str
    type: str  # boolean | numeric | string


@dataclass(frozen=True)
class TableSnapshot:
    """An immutable copy of one custom table, rows in ``row_number`` order."""

    name: str
    columns: tuple[TableColumn, ...]
    rows: tuple[tuple[int, dict[str, Any]], ...]  # (row_number, {column: value})

    def column_type(self, name: str) -> str | None:
        for col in self.columns:
            if col.name == name:
                return col.type
        return None


class TableProvider(Protocol):
    def get_table(self, name: str) -> TableSnapshot | None: ...


class MappingTableProvider:
    """Snapshot provider over a plain dict — tests and pre-fetched evaluation."""

    def __init__(self, tables: dict[str, TableSnapshot]) -> None:
        self._tables = tables

    def get_table(self, name: str) -> TableSnapshot | None:
        return self._tables.get(name)


# ---------------------------------------------------------------------------
# filter / order objects (create_filter, filter, exclude, create_order_by, create_range)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Range:
    low: float
    high: float


@dataclass(frozen=True)
class Filter:
    column: str
    condition: str
    value: Any
    exclude: bool


@dataclass(frozen=True)
class FilterSet:
    filters: tuple[Filter, ...]


@dataclass(frozen=True)
class OrderBy:
    columns: tuple[tuple[str, bool], ...]  # (column, descending)


def create_range(runtime: Runtime, low: object, high: object) -> Range:
    runtime.tick()
    low = runtime.unwrap(low)
    high = runtime.unwrap(high)
    if any(isinstance(v, bool) or not isinstance(v, int | float) for v in (low, high)):
        raise _abort("runtime_error", "create_range() takes two numbers")
    assert isinstance(low, int | float) and isinstance(high, int | float)
    return Range(low=float(low), high=float(high))


def _make_filter(
    runtime: Runtime, column: object, condition: object, value: object, *, exclude: bool
) -> Filter:
    runtime.tick()
    fn = "exclude" if exclude else "filter"
    if not isinstance(column, str) or not column:
        raise _abort("runtime_error", f"{fn}() column must be a non-empty string")
    if condition not in CONDITIONS:
        raise _abort(
            "runtime_error",
            f"{fn}() condition must be one of {', '.join(CONDITIONS)}",
        )
    value = runtime.unwrap(value)
    if condition == "range":
        if not isinstance(value, Range):
            raise _abort("runtime_error", "the range condition takes create_range(a, b)")
    elif isinstance(value, Range):
        raise _abort("runtime_error", "create_range() only works with the range condition")
    return Filter(column=column, condition=str(condition), value=value, exclude=exclude)


def filter_(runtime: Runtime, column: object, condition: object, value: object) -> Filter:
    return _make_filter(runtime, column, condition, value, exclude=False)


def exclude(runtime: Runtime, column: object, condition: object, value: object) -> Filter:
    return _make_filter(runtime, column, condition, value, exclude=True)


def create_filter(runtime: Runtime, *specs: object) -> FilterSet:
    runtime.tick()
    filters: list[Filter] = []
    for spec in specs:
        if not isinstance(spec, Filter):
            raise _abort("runtime_error", "create_filter() takes filter(...) / exclude(...) items")
        filters.append(spec)
    return FilterSet(filters=tuple(filters))


def create_order_by(runtime: Runtime, *columns: object) -> OrderBy:
    runtime.tick()
    parsed: list[tuple[str, bool]] = []
    for col in columns:
        if not isinstance(col, str) or not col.lstrip("-"):
            raise _abort("runtime_error", "create_order_by() takes column-name strings")
        descending = col.startswith("-")
        parsed.append((col.lstrip("-"), descending))
    return OrderBy(columns=tuple(parsed))


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------


def _check_condition_type(f: Filter, column_type: str, table: str) -> None:
    ok_by_condition = {
        "=": ("boolean", "numeric", "string"),
        ">": ("numeric", "string"),
        ">=": ("numeric", "string"),
        "<": ("numeric", "string"),
        "<=": ("numeric", "string"),
        "range": ("numeric",),
        "contains": ("string",),
    }
    if column_type not in ok_by_condition[f.condition]:
        raise _abort(
            "runtime_error",
            f"condition {f.condition!r} does not apply to {column_type} "
            f"column {f.column!r} of table {table!r}",
        )
    expected: tuple[type, ...]
    if f.condition == "range":
        return  # value already validated as a Range
    if column_type == "boolean":
        expected = (bool,)
    elif column_type == "numeric":
        expected = (int, float)
    else:
        expected = (str,)
    if not isinstance(f.value, expected) or (
        column_type == "numeric" and isinstance(f.value, bool)
    ):
        raise _abort(
            "runtime_error",
            f"filter value for {column_type} column {f.column!r} has the wrong type",
        )


def _matches(f: Filter, row_value: Any) -> bool:
    if row_value is None:
        return False  # null cells never match any condition
    c = f.condition
    if c == "=":
        result = row_value == f.value and isinstance(row_value, bool) == isinstance(f.value, bool)
    elif c == "range":
        result = f.value.low <= row_value <= f.value.high
    elif c == "contains":
        result = f.value.lower() in row_value.lower()
    elif c == ">":
        result = row_value > f.value
    elif c == ">=":
        result = row_value >= f.value
    elif c == "<":
        result = row_value < f.value
    else:
        result = row_value <= f.value
    return result


def match_rows(
    runtime: Runtime,
    snapshot: TableSnapshot,
    filters: object,
    order_by: object,
) -> list[TableRow]:
    """Apply a FilterSet + OrderBy to a snapshot → TableRows (row_number order base)."""
    if filters is None:
        filter_set = FilterSet(filters=())
    elif isinstance(filters, Filter):
        filter_set = FilterSet(filters=(filters,))
    elif isinstance(filters, FilterSet):
        filter_set = filters
    else:
        raise _abort("runtime_error", "filters must come from create_filter()")

    for f in filter_set.filters:
        column_type = snapshot.column_type(f.column)
        if column_type is None:
            raise _abort(
                "runtime_error",
                f"table {snapshot.name!r} has no column {f.column!r}",
            )
        _check_condition_type(f, column_type, snapshot.name)

    matched: list[TableRow] = []
    for row_number, data in snapshot.rows:
        runtime.tick()
        keep = True
        for f in filter_set.filters:
            hit = _matches(f, data.get(f.column))
            if hit if f.exclude else not hit:
                keep = False
                break
        if keep:
            matched.append(TableRow(table=snapshot.name, row_number=row_number, data=data))

    if order_by is not None:
        if not isinstance(order_by, OrderBy):
            raise _abort("runtime_error", "order_by must come from create_order_by()")
        for column, descending in reversed(order_by.columns):
            if snapshot.column_type(column) is None:
                raise _abort(
                    "runtime_error",
                    f"table {snapshot.name!r} has no column {column!r}",
                )
            # stable per-key passes; null cells always sort last (documented)
            non_null = [r for r in matched if r.data.get(column) is not None]
            nulls = [r for r in matched if r.data.get(column) is None]
            non_null.sort(key=lambda r: r.data[column], reverse=descending)
            matched = non_null + nulls
    return matched


# ---------------------------------------------------------------------------
# rows and table variables
# ---------------------------------------------------------------------------


class TableRow:
    """One custom-table row: dot access to columns + ``row_number`` (§5)."""

    __slots__ = ("data", "row_number", "table")

    def __init__(self, table: str, row_number: int, data: dict[str, Any]) -> None:
        self.table = table
        self.row_number = row_number
        self.data = data

    def kalk_getattr(self, runtime: Runtime, name: str) -> object:
        if name == "row_number":
            return self.row_number
        if name in self.data:
            return self.data[name]

        if name == "to_keys_list":

            def to_keys_list() -> P3LList:
                runtime.tick()
                return P3LList(self.data.keys())

            return to_keys_list
        if name == "to_values_list":

            def to_values_list() -> P3LList:
                runtime.tick()
                return P3LList(self.data.values())

            return to_values_list
        if name == "to_list":

            def to_list() -> P3LList:
                from app.services.kalk.objects import KalkObject

                runtime.tick()
                return P3LList(
                    KalkObject("table cell", {"key": k, "value": v}) for k, v in self.data.items()
                )

            return to_list
        raise _abort(
            "forbidden_attribute",
            f"table {self.table!r} rows have no column {name!r}",
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, TableRow)
            and other.table == self.table
            and other.row_number == self.row_number
        )

    def __hash__(self) -> int:
        return hash((self.table, self.row_number))


def resolve_selected_row(
    runtime: Runtime, name: str, rows: list[TableRow], default: TableRow | None
) -> TableRow | None:
    """Apply a UI row-number override at the freeze/selection point.

    The single place override-selection semantics live — shared by
    ``table_var``'s frozen path and ``TableVariable._freeze``.
    """
    override = runtime.take_row_override(name)
    if override is None:
        return default
    for row in rows:
        if row.row_number == override:
            return row
    raise _abort(
        "runtime_error",
        f"override for {name!r} selects row {override}, which no longer matches",
    )


class TableVariable:
    """``table_var(..., frozen=False)`` — select → freeze → read (§5).

    The selection call is the freeze point: a UI override (a ``row_number``)
    replaces whatever the formula selected, exactly once.
    """

    __slots__ = ("_name", "_rows", "_runtime", "_selected", "_selection_made")

    def __init__(self, runtime: Runtime, name: str, rows: list[TableRow]) -> None:
        self._runtime = runtime
        self._name = name
        self._rows = rows
        self._selected: TableRow | None = None
        self._selection_made = False

    def _freeze(self, selected: TableRow | None) -> None:
        if self._selection_made:
            raise _abort(
                "runtime_error",
                f"table variable {self._name!r} was selected twice (one selection only)",
            )
        self._selection_made = True
        selected = resolve_selected_row(self._runtime, self._name, self._rows, selected)
        self._selected = selected
        self._runtime.record_table_var_value(self._name, selected)

    def kalk_getattr(self, runtime: Runtime, name: str) -> object:
        if name == "rows":
            return P3LList(self._rows)
        if name == "value":
            if not self._selection_made:
                raise _abort(
                    "runtime_error",
                    f"table variable {self._name!r} used before a select_*() call",
                )
            return self._selected

        def select_first() -> None:
            runtime.tick()
            self._freeze(self._rows[0] if self._rows else None)

        def select_last() -> None:
            runtime.tick()
            self._freeze(self._rows[-1] if self._rows else None)

        def select_by_row(row: object) -> None:
            runtime.tick()
            row = runtime.unwrap(row)
            if row is not None and not isinstance(row, TableRow):
                raise _abort("runtime_error", "select_by_row() takes a table row or None")
            if isinstance(row, TableRow) and row not in self._rows:
                raise _abort(
                    "runtime_error",
                    f"select_by_row(): the row is not in {self._name!r}'s matching rows",
                )
            self._freeze(row)

        def select_by_row_number(n: object) -> None:
            runtime.tick()
            n = runtime.unwrap(n)
            if isinstance(n, bool) or not isinstance(n, int):
                raise _abort("runtime_error", "select_by_row_number() takes an integer")
            for candidate in self._rows:
                if candidate.row_number == n:
                    self._freeze(candidate)
                    return
            raise _abort(
                "runtime_error",
                f"select_by_row_number(): no matching row has row_number {n}",
            )

        methods = {
            "select_first": select_first,
            "select_last": select_last,
            "select_by_row": select_by_row,
            "select_by_row_number": select_by_row_number,
        }
        if name in methods:
            return methods[name]
        raise _abort(
            "forbidden_attribute",
            f"attribute {name!r} is not available on a table variable",
        )
