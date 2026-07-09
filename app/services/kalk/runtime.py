"""Kalk runtime — guarded builtins, hooks, and the variable registry.

One ``Runtime`` instance exists per evaluation (thread-safe by construction:
all counters live on the instance, injected into the formula's globals as
bound methods). Every guard raises ``KalkAbort`` with a typed error; nothing
here may raise anything else for in-formula misuse.
"""

from __future__ import annotations

import functools
import math
import re
import statistics
import string as string_module
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

from app.services.kalk import lists, tables
from app.services.kalk.errors import KalkAbort, KalkError
from app.services.kalk.limits import Limits
from app.services.kalk.lists import P3LList
from app.services.kalk.objects import ContextData, KalkObject
from app.services.kalk.tables import TableProvider, TableRow, TableVariable
from app.services.kalk.variables import DropDownVar, VariableGroup

_MISSING = object()


class ValueType:
    """Sentinel for var() value types — exposed as ``number``/``currency``/``string``."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


NUMBER = ValueType("number")
CURRENCY = ValueType("currency")
STRING = ValueType("string")


def _abort(code: str, message: str) -> KalkAbort:
    return KalkAbort(KalkError(code=code, message=message))


def _type_ok(value_type: ValueType, value: object) -> bool:
    if value_type is STRING:
        return isinstance(value, str)
    # number / currency: int or float, bools excluded
    return isinstance(value, int | float) and not isinstance(value, bool)


class DynamicVar:
    """A ``var(..., frozen=False)`` value: update → freeze → use.

    UI overrides apply *at the freeze point* (KALK-REFERENCE §3) — an override
    discards every ``update()``. Reading the value before ``freeze()`` is an
    error; ``freeze()`` is idempotent; ``update()`` after freeze is an error.
    """

    def __init__(self, runtime: Runtime, name: str, declaration: dict[str, Any]) -> None:
        self._runtime = runtime
        self._name = name
        self._declaration = declaration
        self._value_type: ValueType = runtime._value_types[declaration["value_type"]]
        self._pending: object = declaration["default"]
        self._frozen = False

    def update(self, value: object) -> None:
        if self._frozen:
            raise _abort("runtime_error", f"variable {self._name!r} was updated after freeze()")
        value = self._runtime.unwrap(value)
        if not _type_ok(self._value_type, value):
            raise _abort(
                "runtime_error",
                f"variable {self._name!r} update is not a {self._value_type.name}",
            )
        self._pending = value

    def freeze(self) -> None:
        if self._frozen:
            return
        self._frozen = True
        value = self._runtime.apply_override(
            self._name,
            self._value_type,
            self._pending,
            quantity_specific=self._declaration["quantity_specific"],
        )
        self._pending = value
        self._declaration["value"] = value

    @property
    def kalk_value(self) -> object:
        if not self._frozen:
            raise _abort(
                "runtime_error",
                f"variable {self._name!r} used before freeze() was called",
            )
        return self._pending


class Runtime:
    def __init__(
        self,
        limits: Limits,
        overrides: Mapping[str, object] | None,
        quantity: int = 1,
        table_provider: TableProvider | None = None,
        context_data: ContextData | None = None,
    ) -> None:
        self.limits = limits
        self.overrides: dict[str, object] = dict(overrides or {})
        self.quantity = quantity
        self.table_provider = table_provider
        self.context_data = context_data or ContextData()
        self._deadline = time.monotonic() + limits.deadline_seconds
        self._ops = 0
        self._value_types = {"number": NUMBER, "currency": CURRENCY, "string": STRING}
        # contract outputs
        self.declared_variables: list[dict[str, Any]] = []
        self.variable_groups: list[dict[str, Any]] = []
        self.applied_overrides: list[str] = []
        self.operation_name: str | None = None
        self.notes: str | None = None
        self.no_quote_called = False
        # operation-context state (KALK-REFERENCE §7-§8)
        self.workpiece: dict[str, Any] = dict(self.context_data.workpiece)
        self.custom_attributes: dict[str, Any] = dict(self.context_data.custom_attributes)
        self.custom_attributes_out: dict[str, Any] = {}
        # pricing-item-context state (KALK-REFERENCE §11.3)
        self.profit_item_name: str | None = None
        self.custom_cost: float | None = None

    # -- caps ---------------------------------------------------------------

    def tick(self, cost: int = 1) -> None:
        self._ops += cost
        if self._ops > self.limits.op_budget:
            raise _abort("resource_limit", "formula exceeded its operation budget")
        if time.monotonic() > self._deadline:
            raise _abort("timeout", "formula exceeded its time limit")

    def _check_number(self, value: object) -> object:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value.bit_length() > self.limits.max_int_bits:
            raise _abort("resource_limit", "number grew too large")
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                raise _abort("resource_limit", "computation produced a non-finite number")
            if abs(value) > self.limits.max_numeric_magnitude:
                raise _abort("resource_limit", "number grew too large")
        if isinstance(value, str) and len(value) > self.limits.max_str_len:
            raise _abort("resource_limit", "string grew too long")
        if isinstance(value, list | tuple) and len(value) > self.limits.max_collection_len:
            raise _abort("resource_limit", "collection grew too large")
        return value

    # -- hooks (injected as _k_binop / _k_getattr / _k_iter) ------------------

    def binop(self, op: str, left: object, right: object) -> object:
        self.tick()
        left = self.unwrap(left)
        right = self.unwrap(right)
        if op == "**":
            return self._pow(left, right)
        if op == "*":
            self._guard_repetition(left, right)
        if (
            op == "+"
            and isinstance(left, str)
            and isinstance(right, str)
            and len(left) + len(right) > self.limits.max_str_len
        ):
            raise _abort("resource_limit", "string grew too long")
        if (
            op == "+"
            and isinstance(left, list | tuple)
            and isinstance(right, list | tuple)
            and len(left) + len(right) > self.limits.max_collection_len
        ):
            raise _abort("resource_limit", "collection grew too large")
        try:
            if op == "+":
                result = left + right  # type: ignore[operator]
            elif op == "-":
                result = left - right  # type: ignore[operator]
            elif op == "*":
                result = left * right  # type: ignore[operator]
            else:
                result = left / right  # type: ignore[operator]
        except KalkAbort:
            raise
        except Exception as exc:
            raise _abort("runtime_error", _sanitize_exception(exc)) from None
        if isinstance(result, list) and not isinstance(result, P3LList):
            # list + list / list * n on P3LLists must stay P3LLists
            result = P3LList(result)
        return self._check_number(result)

    def _pow(self, base: object, exponent: object) -> object:
        if not isinstance(base, int | float) or not isinstance(exponent, int | float):
            raise _abort("runtime_error", "** requires numbers")
        if abs(exponent) > self.limits.max_pow_exponent:
            raise _abort("resource_limit", "** exponent is too large")
        if (
            isinstance(base, int)
            and not isinstance(base, bool)
            and abs(base) > 1
            and exponent > 0
            and base.bit_length() * exponent > self.limits.max_pow_result_bits
        ):
            raise _abort("resource_limit", "** result would be too large")
        try:
            result = base**exponent
        except Exception as exc:
            raise _abort("runtime_error", _sanitize_exception(exc)) from None
        if isinstance(result, complex):
            raise _abort("runtime_error", "** produced a complex number")
        return self._check_number(result)

    def _guard_repetition(self, left: object, right: object) -> None:
        for seq, count in ((left, right), (right, left)):
            if not isinstance(count, int):
                continue
            if isinstance(seq, str):
                if len(seq) * max(count, 0) > self.limits.max_str_len:
                    raise _abort("resource_limit", "string grew too long")
            elif isinstance(seq, list | tuple) and (
                len(seq) * max(count, 0) > self.limits.max_collection_len
            ):
                raise _abort("resource_limit", "collection grew too large")

    def getattr_(self, obj: object, name: str) -> object:
        self.tick()
        # defence in depth — the validator already rejects these statically
        if name.startswith("_"):
            raise _abort("forbidden_attribute", f"attribute {name!r} is not accessible")
        if isinstance(obj, DynamicVar):
            if name in ("update", "freeze"):
                return getattr(obj, name)
        elif isinstance(obj, KalkObject | TableRow | TableVariable | DropDownVar | VariableGroup):
            return obj.kalk_getattr(self, name)
        elif isinstance(obj, P3LList):
            return lists.list_attr(self, obj, name)
        elif isinstance(obj, str):
            if name == "split":
                return self._guarded_split(obj)
            if name == "format":
                return self._guarded_format(obj)
        raise _abort(
            "forbidden_attribute",
            f"attribute {name!r} is not available on {type(obj).__name__}",
        )

    def iter_(self, iterable: object) -> Iterator[object]:
        iterable = self.unwrap(iterable)
        if not isinstance(iterable, list | tuple | str):
            raise _abort("runtime_error", "for loops iterate lists, tuples, or strings")
        for count, item in enumerate(iterable, start=1):
            if count > self.limits.max_loop_iterations:
                raise _abort("resource_limit", "loop exceeded its iteration limit")
            self.tick()
            yield item

    # -- guarded string methods ----------------------------------------------

    def _guarded_split(self, value: str) -> Callable[..., P3LList]:
        def split(sep: object = None, maxsplit: object = -1) -> P3LList:
            self.tick()
            sep_u = self.unwrap(sep)
            if sep_u is not None and not isinstance(sep_u, str):
                raise _abort("runtime_error", "split() separator must be a string")
            if not isinstance(maxsplit, int):
                raise _abort("runtime_error", "split() maxsplit must be an integer")
            return P3LList(value.split(sep_u, maxsplit))

        return split

    def _guarded_format(self, template: str) -> Callable[..., str]:
        def format_(*args: object, **kwargs: object) -> str:
            self.tick()
            if len(template) > self.limits.max_format_string_len:
                raise _abort("resource_limit", "format string is too long")
            for _, field_name, spec, _ in string_module.Formatter().parse(template):
                if field_name and ("." in field_name or "[" in field_name):
                    # str.format field names can walk object graphs
                    # ({0.__func__.__globals__}) — a sandbox escape that never
                    # touches the AST. Allow only plain names / positional refs.
                    raise _abort(
                        "forbidden_attribute",
                        "attribute or index access is not allowed in format fields",
                    )
                if spec and "{" in spec:
                    # nested replacement fields take the width/precision from
                    # an argument, sidestepping the literal-digit scan below
                    raise _abort("resource_limit", "dynamic format widths are not allowed")
                for digits in re.findall(r"\d+", spec or ""):
                    if int(digits) > self.limits.max_format_spec_number:
                        raise _abort("resource_limit", "format specification is too large")
            clean_args = tuple(self.unwrap(a) for a in args)
            clean_kwargs = {k: self.unwrap(v) for k, v in kwargs.items()}
            try:
                result = template.format(*clean_args, **clean_kwargs)
            except KalkAbort:
                raise
            except Exception as exc:
                raise _abort("runtime_error", _sanitize_exception(exc)) from None
            if len(result) > self.limits.max_str_len:
                raise _abort("resource_limit", "string grew too long")
            return result

        return format_

    # -- variables ------------------------------------------------------------

    def _raw_override(self, name: str, quantity_specific: bool) -> object:
        """Resolve the stored override for a variable, honouring per-quantity shape.

        Quantity-specific overrides are persisted as ``{name: {"<qty>": value}}``
        keyed by the **break quantity** (DECISIONS.md 2026-07-08); a plain
        scalar on a quantity-specific variable applies at every break (the
        ``runtime``/``setup_time`` manual pair takes this path). Returns
        ``_MISSING`` when no override applies to the current quantity.
        """
        if name not in self.overrides:
            return _MISSING
        raw = self.overrides[name]
        if quantity_specific:
            if not isinstance(raw, Mapping):
                return raw  # scalar override → same value for every break
            return raw.get(str(self.quantity), _MISSING)
        if isinstance(raw, Mapping):
            raise _abort(
                "runtime_error",
                f"variable {name!r} is not quantity-specific but has a per-quantity override",
            )
        return raw

    def apply_override(
        self,
        name: str,
        value_type: ValueType,
        current: object,
        quantity_specific: bool = False,
    ) -> object:
        value = self._raw_override(name, quantity_specific)
        if value is _MISSING:
            return current
        if not _type_ok(value_type, value):
            raise _abort(
                "runtime_error",
                f"override for {name!r} is not a {value_type.name}",
            )
        self.applied_overrides.append(name)
        return value

    def take_row_override(self, name: str) -> int | None:
        """The row_number override for a table variable (applies at selection)."""
        declaration = self._declaration_by_name(name)
        value = self._raw_override(name, bool(declaration and declaration["quantity_specific"]))
        if value is _MISSING:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise _abort(
                "runtime_error",
                f"override for table variable {name!r} must be a row number",
            )
        self.applied_overrides.append(name)
        return value

    def record_table_var_value(self, name: str, row: TableRow | None) -> None:
        declaration = self._declaration_by_name(name)
        if declaration is not None:
            declaration["value"] = row.row_number if row is not None else None

    def resolve_dropdown_override(
        self, name: str, declaration: dict[str, Any], value: object
    ) -> object:
        override = self._raw_override(name, declaration["quantity_specific"])
        if override is _MISSING:
            return value
        if not _type_ok(self._value_types[declaration["value_type"]], override):
            raise _abort(
                "runtime_error",
                f"override for {name!r} is not a {declaration['value_type']}",
            )
        self.applied_overrides.append(name)
        return override

    def check_dropdown_options(
        self, name: str, value_type: ValueType, options: object
    ) -> list[Any]:
        options = self.unwrap(options)
        if not isinstance(options, list | tuple):
            raise _abort("runtime_error", f"drop-down {name!r} options must be a list")
        checked: list[Any] = []
        for raw in options:
            option = self.unwrap(raw)
            if not _type_ok(value_type, option):
                raise _abort(
                    "runtime_error",
                    f"drop-down {name!r} option {option!r} is not a {value_type.name}",
                )
            checked.append(option)
        return checked

    def _declaration_by_name(self, name: str) -> dict[str, Any] | None:
        for declaration in self.declared_variables:
            if declaration["name"] == name:
                return declaration
        return None

    def _register_name(self, fn: str, name: object) -> str:
        if not isinstance(name, str) or not name:
            raise _abort("runtime_error", f"{fn}() name must be a non-empty string")
        if self._declaration_by_name(name) is not None:
            raise _abort("runtime_error", f"variable {name!r} is declared twice")
        return name

    def var(
        self,
        name: object,
        default: object,
        description: object = "",
        value_type: object = NUMBER,
        default_visible: object = True,
        frozen: object = True,
        quantity_specific: object = False,
    ) -> object:
        self.tick()
        if not isinstance(name, str) or not name:
            raise _abort("runtime_error", "var() name must be a non-empty string")
        if not isinstance(value_type, ValueType):
            raise _abort("runtime_error", "var() value_type must be number, currency, or string")
        if any(d["name"] == name for d in self.declared_variables):
            raise _abort("runtime_error", f"variable {name!r} is declared twice")
        default = self.unwrap(default)
        if not _type_ok(value_type, default):
            raise _abort("runtime_error", f"var() default for {name!r} is not a {value_type.name}")
        declaration: dict[str, Any] = {
            "name": name,
            "value_type": value_type.name,
            "default": default,
            "description": description if isinstance(description, str) else "",
            "default_visible": bool(default_visible),
            "frozen": bool(frozen),
            "quantity_specific": bool(quantity_specific),
            "value": None,
        }
        self.declared_variables.append(declaration)
        if not frozen:
            return DynamicVar(self, name, declaration)
        value = self.apply_override(
            name, value_type, default, quantity_specific=bool(quantity_specific)
        )
        declaration["value"] = value
        return value

    def _m4_stub(self, fn_name: str) -> Callable[..., object]:
        def stub(*_args: object, **_kwargs: object) -> object:
            raise _abort(
                "runtime_error",
                f"{fn_name}() is not available until M4 (GeometryService interrogation)",
            )

        return stub

    # -- declaration functions: tables, drop-downs, groups (KALK-REFERENCE §3, §5)

    def _get_snapshot(self, fn: str, table_name: object) -> tables.TableSnapshot:
        if not isinstance(table_name, str) or not table_name:
            raise _abort("runtime_error", f"{fn}() table_name must be a non-empty string")
        snapshot = self.table_provider.get_table(table_name) if self.table_provider else None
        if snapshot is None:
            raise _abort("runtime_error", f"no custom table named {table_name!r}")
        return snapshot

    def table_var(
        self,
        name: object,
        description: object = "",
        table_name: object = None,
        filters: object = None,
        order_by: object = None,
        display_column_name: object = None,
        frozen: object = True,
        quantity_specific: object = False,
    ) -> object:
        self.tick()
        name = self._register_name("table_var", name)
        snapshot = self._get_snapshot("table_var", table_name)
        if (
            display_column_name is not None
            and snapshot.column_type(str(display_column_name)) is None
        ):
            raise _abort(
                "runtime_error",
                f"table {snapshot.name!r} has no column {display_column_name!r}",
            )
        rows = tables.match_rows(self, snapshot, filters, order_by)
        rows = rows[: tables.TABLE_VAR_MAX_ROWS]

        def display(row: TableRow) -> str:
            if display_column_name is not None:
                return str(row.data.get(str(display_column_name)))
            return f"Zeile {row.row_number}"

        declaration: dict[str, Any] = {
            "name": name,
            "kind": "table_var",
            "value_type": "table_row",
            "default": None,
            "description": description if isinstance(description, str) else "",
            "default_visible": True,
            "frozen": bool(frozen),
            "quantity_specific": bool(quantity_specific),
            "table_name": snapshot.name,
            "display_column_name": (
                str(display_column_name) if display_column_name is not None else None
            ),
            "options": [{"row_number": r.row_number, "display": display(r)} for r in rows],
            "value": None,
        }
        self.declared_variables.append(declaration)
        if not frozen:
            return TableVariable(self, name, rows)
        selected = rows[0] if rows else None
        override = self.take_row_override(name)
        if override is not None:
            for row in rows:
                if row.row_number == override:
                    selected = row
                    break
            else:
                raise _abort(
                    "runtime_error",
                    f"override for {name!r} selects row {override}, which no longer matches",
                )
        declaration["value"] = selected.row_number if selected is not None else None
        return selected

    def table_lookup(
        self,
        table_name: object = None,
        filters: object = None,
        order_by: object = None,
        quantity_specific: object = False,  # accepted for P3L parity; no UI variable
    ) -> P3LList:
        self.tick()
        snapshot = self._get_snapshot("table_lookup", table_name)
        rows = tables.match_rows(self, snapshot, filters, order_by)
        return P3LList(rows[: tables.TABLE_LOOKUP_MAX_ROWS])

    def drop_down_var(
        self,
        name: object,
        default_value: object = None,
        default_options: object = None,
        description: object = "",
        value_type: object = NUMBER,
        frozen: object = True,
        quantity_specific: object = False,
    ) -> object:
        self.tick()
        name = self._register_name("drop_down_var", name)
        if not isinstance(value_type, ValueType):
            raise _abort(
                "runtime_error",
                "drop_down_var() value_type must be number, currency, or string",
            )
        options = self.check_dropdown_options(name, value_type, default_options)
        if not options:
            raise _abort("runtime_error", f"drop-down {name!r} needs at least one option")
        default_value = self.unwrap(default_value)
        if default_value not in options:
            raise _abort(
                "runtime_error",
                f"drop-down {name!r} default value is not one of the options",
            )
        declaration: dict[str, Any] = {
            "name": name,
            "kind": "drop_down",
            "value_type": value_type.name,
            "default": default_value,
            "description": description if isinstance(description, str) else "",
            "default_visible": True,
            "frozen": bool(frozen),
            "quantity_specific": bool(quantity_specific),
            "options": list(options),
            "value": None,
        }
        self.declared_variables.append(declaration)
        if not frozen:
            return DropDownVar(self, name, value_type, options, declaration)
        value = self.resolve_dropdown_override(name, declaration, default_value)
        if value not in options:
            raise _abort(
                "runtime_error",
                f"override for drop-down {name!r} is not one of the options",
            )
        declaration["value"] = value
        return value

    def variable_group(self, name: object, default_collapsed: object = False) -> VariableGroup:
        self.tick()
        if not isinstance(name, str) or not name:
            raise _abort("runtime_error", "variable_group() name must be a non-empty string")
        if any(g["name"] == name for g in self.variable_groups):
            raise _abort("runtime_error", f"variable group {name!r} is declared twice")
        group: dict[str, Any] = {
            "name": name,
            "default_collapsed": bool(default_collapsed),
            "members": [],
        }
        self.variable_groups.append(group)
        return VariableGroup(self, group)

    def add_to_group(self, group: dict[str, Any], var_name: str) -> None:
        if var_name in ("runtime", "setup_time"):
            # KALK-REFERENCE §3: the primary specials never join a group
            raise _abort(
                "runtime_error",
                "runtime and setup_time cannot be added to a variable group",
            )
        if self._declaration_by_name(var_name) is None:
            raise _abort(
                "runtime_error",
                f"add_by_name(): no variable named {var_name!r} is declared",
            )
        for existing in self.variable_groups:
            if var_name in existing["members"]:
                raise _abort(
                    "runtime_error",
                    f"variable {var_name!r} is already in group {existing['name']!r}",
                )
        group["members"].append(var_name)

    # -- operation-cost context functions --------------------------------------

    def set_operation_name(self, name: object) -> None:
        self.tick()
        if not isinstance(name, str):
            raise _abort("runtime_error", "set_operation_name() takes a string")
        self.operation_name = name

    def set_notes(self, notes: object) -> None:
        self.tick()
        notes = self.unwrap(notes)
        if not isinstance(notes, str):
            raise _abort("runtime_error", "set_notes() takes a string")
        self.notes = notes

    def no_quote(self) -> None:
        self.tick()
        self.no_quote_called = True

    def set_notes_from_list(self, notes: object) -> None:
        self.tick()
        notes = self.unwrap(notes)
        if not isinstance(notes, list | tuple):
            raise _abort("runtime_error", "set_notes_from_list() takes a list of strings")
        parts: list[str] = []
        for raw in notes:
            item = self.unwrap(raw)
            if not isinstance(item, str):
                raise _abort("runtime_error", "set_notes_from_list() takes a list of strings")
            parts.append(item)
        joined = "\n".join(parts)
        if len(joined) > self.limits.max_str_len:
            raise _abort("resource_limit", "string grew too long")
        self.notes = joined

    def is_close(self, n1: object, n2: object, tol: object = 0.001) -> bool:
        self.tick()
        values: list[int | float] = []
        for raw in (n1, n2, tol):
            v = self.unwrap(raw)
            if isinstance(v, bool) or not isinstance(v, int | float):
                raise _abort("runtime_error", "is_close() takes numbers")
            values.append(v)
        return abs(values[0] - values[1]) <= values[2]

    def is_a_in_b(self, a: object, b: object) -> bool:
        self.tick()
        a = self.unwrap(a)
        b = self.unwrap(b)
        if isinstance(a, str) and isinstance(b, str):
            return a.lower() in b.lower()  # case-insensitive, the common material test
        if isinstance(b, list | tuple):
            return a in b
        raise _abort("runtime_error", "is_a_in_b() takes strings or a value and a list")

    def get_quantities(self) -> P3LList:
        self.tick()
        return P3LList(self.context_data.quantities)

    def get_make_quantities(self) -> P3LList:
        self.tick()
        return P3LList(self.context_data.make_quantities)

    def get_bom_quantities(self) -> P3LList:
        self.tick()
        return P3LList(self.context_data.bom_quantities)

    def set_workpiece_value(self, key: object, value: object) -> None:
        self.tick()
        if not isinstance(key, str) or not key:
            raise _abort("runtime_error", "set_workpiece_value() key must be a non-empty string")
        value = self.unwrap(value)
        if value is not None and not isinstance(value, bool | int | float | str):
            raise _abort(
                "runtime_error",
                "set_workpiece_value() takes a number, string, boolean, or None",
            )
        self.workpiece[key] = value

    def get_workpiece_value(self, key: object, default: object = None) -> object:
        self.tick()
        if not isinstance(key, str):
            raise _abort("runtime_error", "get_workpiece_value() key must be a string")
        return self.workpiece.get(key, self.unwrap(default))

    def get_cost_value(self, key: object) -> float:
        """Summed cost of cells matching ``key`` for the current quantity (§7).

        Special keys: ``--material--``, ``--outside--``, ``--inside--``,
        ``--total--``. An unknown name sums nothing → 0.0 (P3L parity).
        """
        self.tick()
        if not isinstance(key, str):
            raise _abort("runtime_error", "get_cost_value() key must be a string")
        return float(self.context_data.cost_values.get(key, 0.0))

    def set_custom_attribute(self, key: object, value: object) -> None:
        self.tick()
        if not isinstance(key, str) or not key:
            raise _abort("runtime_error", "set_custom_attribute() key must be a non-empty string")
        value = self.unwrap(value)
        if not isinstance(value, bool | int | float | str):
            raise _abort(
                "runtime_error",
                "set_custom_attribute() takes a number, string, or boolean",
            )
        existing = self.custom_attributes.get(key)
        if existing is not None and (
            isinstance(existing, bool) != isinstance(value, bool)
            or isinstance(existing, str) != isinstance(value, str)
        ):
            # KALK-REFERENCE §8: custom attributes are type-stable
            raise _abort(
                "runtime_error",
                f"custom attribute {key!r} cannot change type",
            )
        self.custom_attributes[key] = value
        self.custom_attributes_out[key] = value

    def get_custom_attribute(self, key: object, default: object = None) -> object:
        self.tick()
        if not isinstance(key, str):
            raise _abort("runtime_error", "get_custom_attribute() key must be a string")
        return self.custom_attributes.get(key, self.unwrap(default))

    def get_children(
        self,
        obtain_method: object = None,
        is_assembly: object = None,
        recursive: object = False,
    ) -> P3LList:
        self.tick()
        source = self.context_data.descendants if recursive else self.context_data.children
        result = P3LList()
        for child in source:
            if obtain_method is not None and child.attrs.get("obtain_method") != obtain_method:
                continue
            if is_assembly is not None and child.attrs.get("is_assembly") != bool(is_assembly):
                continue
            result.append(child)
        return result

    def units_mm(self) -> None:
        self.tick()  # metric is the only mode (DACH delta) — an explicit no-op

    def units_in(self) -> None:
        self.tick()
        raise _abort(
            "runtime_error",
            "units_in() is not supported — Tolera formulas are metric-native (DACH)",
        )

    # -- pricing-item context functions (KALK-REFERENCE §11.3) -------------------

    def set_profit_item_name(self, name: object) -> None:
        self.tick()
        if not isinstance(name, str):
            raise _abort("runtime_error", "set_profit_item_name() takes a string")
        self.profit_item_name = name

    def set_custom_cost(self, cost: object) -> None:
        self.tick()
        cost = self.unwrap(cost)
        if isinstance(cost, bool) or not isinstance(cost, int | float):
            raise _abort("runtime_error", "set_custom_cost() takes a number")
        if not math.isfinite(cost):
            raise _abort("runtime_error", "set_custom_cost() takes a finite number")
        self.custom_cost = float(cost)

    def get_components(self, order: object = "leaf_to_root") -> P3LList:
        self.tick()
        if order not in ("leaf_to_root", "root_to_leaf"):
            raise _abort(
                "runtime_error",
                "get_components() order must be 'leaf_to_root' or 'root_to_leaf'",
            )
        components = self.context_data.components
        if order == "root_to_leaf":
            components = list(reversed(components))
        return P3LList(components)

    def _component_uuid(self, fn: str, component: object) -> str:
        component = self.unwrap(component)
        if isinstance(component, str):
            return component
        if isinstance(component, KalkObject):
            uuid = component.attrs.get("uuid")
            if isinstance(uuid, str):
                return uuid
        raise _abort("runtime_error", f"{fn}() takes a component or a component uuid")

    def get_component_children(self, component: object) -> P3LList:
        self.tick()
        uuid = self._component_uuid("get_children", component)
        return P3LList(self.context_data.component_children.get(uuid, []))

    def get_operations(self, component: object) -> P3LList:
        self.tick()
        uuid = self._component_uuid("get_operations", component)
        return P3LList(self.context_data.component_operations.get(uuid, []))

    def get_material_operations(self, component: object) -> P3LList:
        self.tick()
        uuid = self._component_uuid("get_material_operations", component)
        return P3LList(self.context_data.component_material_operations.get(uuid, []))

    # -- helpers ----------------------------------------------------------------

    def unwrap(self, value: object) -> object:
        if isinstance(value, DynamicVar | DropDownVar):
            return value.kalk_value
        return value

    def _numeric_args(self, fn_name: str, args: tuple[object, ...]) -> list[int | float]:
        if len(args) == 1 and isinstance(args[0], list | tuple):
            values: Iterable[object] = args[0]
        else:
            values = args
        result: list[int | float] = []
        for raw in values:
            v = self.unwrap(raw)
            if isinstance(v, bool) or not isinstance(v, int | float):
                raise _abort("runtime_error", f"{fn_name}() takes numbers")
            result.append(v)
        if not result:
            raise _abort("runtime_error", f"{fn_name}() needs at least one value")
        return result

    # -- guarded builtins ---------------------------------------------------------

    def b_min(self, *args: object) -> object:
        self.tick()
        return min(self._numeric_args("min", args))

    def b_max(self, *args: object) -> object:
        self.tick()
        return max(self._numeric_args("max", args))

    def b_mean(self, *args: object) -> object:
        self.tick()
        # fmean: always a float regardless of Python version/input mix
        return self._check_number(statistics.fmean(self._numeric_args("mean", args)))

    def b_median(self, *args: object) -> object:
        self.tick()
        return self._check_number(statistics.median(self._numeric_args("median", args)))

    def b_sum(self, iterable: object, start: object = 0) -> object:
        self.tick()
        values = self._numeric_args("sum", (iterable,))
        start_u = self.unwrap(start)
        if isinstance(start_u, bool) or not isinstance(start_u, int | float):
            raise _abort("runtime_error", "sum() start must be a number")
        total: int | float = start_u
        for v in values:
            total = total + v
        return self._check_number(total)

    def b_round(self, number: object, ndigits: object = None) -> object:
        self.tick()
        number = self.unwrap(number)
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _abort("runtime_error", "round() takes a number")
        if ndigits is None:
            return self._check_number(round(number))
        if isinstance(ndigits, bool) or not isinstance(ndigits, int):
            raise _abort("runtime_error", "round() ndigits must be an integer")
        return self._check_number(round(number, ndigits))

    def b_abs(self, number: object) -> object:
        self.tick()
        number = self.unwrap(number)
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _abort("runtime_error", "abs() takes a number")
        return self._check_number(abs(number))

    def b_floor(self, number: object) -> object:
        self.tick()
        number = self.unwrap(number)
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _abort("runtime_error", "floor() takes a number")
        return self._check_number(math.floor(number))

    def b_ceil(self, number: object) -> object:
        self.tick()
        number = self.unwrap(number)
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _abort("runtime_error", "ceil() takes a number")
        return self._check_number(math.ceil(number))

    def b_str(self, value: object = "") -> str:
        self.tick()
        result = str(self.unwrap(value))
        if len(result) > self.limits.max_str_len:
            raise _abort("resource_limit", "string grew too long")
        return result

    def b_split(self, value: object, sep: object = None) -> P3LList:
        self.tick()
        value = self.unwrap(value)
        if not isinstance(value, str):
            raise _abort("runtime_error", "split() takes a string")
        return self._guarded_split(value)(sep)

    # -- namespace -------------------------------------------------------------

    def build_globals(
        self, eval_context: Mapping[str, object], context_type: str = "operation_cost"
    ) -> dict[str, object]:
        namespace: dict[str, object] = {
            "__builtins__": {},
            # hooks injected by the transformer
            "_k_binop": self.binop,
            "_k_getattr": self.getattr_,
            "_k_iter": self.iter_,
            # shared subset builtins (KALK-REFERENCE §2)
            "min": self.b_min,
            "max": self.b_max,
            "mean": self.b_mean,
            "median": self.b_median,
            "round": self.b_round,
            "abs": self.b_abs,
            "sum": self.b_sum,
            "floor": self.b_floor,
            "ceil": self.b_ceil,
            "str": self.b_str,
            "split": self.b_split,
            # variable system (KALK-REFERENCE §3, §5)
            "var": self.var,
            "table_var": self.table_var,
            "table_lookup": self.table_lookup,
            "variable_group": self.variable_group,
            "drop_down_var": self.drop_down_var,
            "number": NUMBER,
            "currency": CURRENCY,
            "string": STRING,
            # lists + table filtering (KALK-REFERENCE §4, §5)
            "create_list": functools.partial(lists.create_list, self),
            "create_multi_sort": functools.partial(lists.create_multi_sort, self),
            "iterate": functools.partial(lists.iterate, self),
            "create_filter": functools.partial(tables.create_filter, self),
            "filter": functools.partial(tables.filter_, self),
            "exclude": functools.partial(tables.exclude, self),
            "create_order_by": functools.partial(tables.create_order_by, self),
            "create_range": functools.partial(tables.create_range, self),
        }
        if context_type == "operation_cost":
            namespace.update(
                {
                    "no_quote": self.no_quote,
                    "set_operation_name": self.set_operation_name,
                    "set_notes": self.set_notes,
                    "set_notes_from_list": self.set_notes_from_list,
                    "is_close": self.is_close,
                    "is_a_in_b": self.is_a_in_b,
                    "quantity": self.quantity,
                    "get_quantities": self.get_quantities,
                    "get_make_quantities": self.get_make_quantities,
                    "get_bom_quantities": self.get_bom_quantities,
                    "set_workpiece_value": self.set_workpiece_value,
                    "get_workpiece_value": self.get_workpiece_value,
                    "get_cost_value": self.get_cost_value,
                    "set_custom_attribute": self.set_custom_attribute,
                    "get_custom_attribute": self.get_custom_attribute,
                    "get_children": self.get_children,
                    "units_mm": self.units_mm,
                    "units_in": self.units_in,
                    # domain objects — the wiring supplies real ones via eval_context
                    "part": None,
                    "quote": None,
                    "op_def": None,
                    "line_item": None,
                }
            )
            # geometry analyzers arrive with M4 (GeometryService)
            for analyzer in ANALYZER_NAMES:
                namespace[analyzer] = self._m4_stub(analyzer)
        elif context_type == "pricing_item":
            namespace.update(
                {
                    # calculation-type constants + globals; the wiring overrides
                    # via eval_context (defaults keep CHECK-only runs evaluable)
                    "MARKUP": "MARKUP",
                    "MARGIN": "MARGIN",
                    "MATERIAL_COST": 0.0,
                    "INSIDE_COST": 0.0,
                    "OUTSIDE_COST": 0.0,
                    "PURCHASED_COMPONENT_COST": 0.0,
                    "TOTAL_COST": 0.0,
                    "CALCULATION_TYPE": "MARKUP",
                    "COST_CATEGORY": "general",
                    "CATEGORY_COST": 0.0,
                    "REQUESTED_QUANTITY": self.quantity,
                    "contact": None,
                    "set_profit_item_name": self.set_profit_item_name,
                    "set_custom_cost": self.set_custom_cost,
                    "get_components": self.get_components,
                    "get_children": self.get_component_children,
                    "get_operations": self.get_operations,
                    "get_material_operations": self.get_material_operations,
                    # generic comparison helpers — shared with the op context
                    "is_close": self.is_close,
                    "is_a_in_b": self.is_a_in_b,
                }
            )
        namespace.update(eval_context)
        return namespace


ANALYZER_NAMES = (
    "analyze_mill3",
    "analyze_lathe",
    "analyze_sheet_metal",
    "analyze_tube_laser",
    "analyze_wire_edm",
    "analyze_casting",
    "analyze_additive",
    "manual_nest",
    "get_features",
)

BUILTIN_NAMES = frozenset(
    {
        "min",
        "max",
        "mean",
        "median",
        "round",
        "abs",
        "sum",
        "floor",
        "ceil",
        "str",
        "split",
        "var",
        "table_var",
        "table_lookup",
        "variable_group",
        "drop_down_var",
        "number",
        "currency",
        "string",
        "create_list",
        "create_multi_sort",
        "iterate",
        "create_filter",
        "filter",
        "exclude",
        "create_order_by",
        "create_range",
    }
)

OPERATION_COST_NAMES = frozenset(
    {
        "no_quote",
        "set_operation_name",
        "set_notes",
        "set_notes_from_list",
        "is_close",
        "is_a_in_b",
        "quantity",
        "get_quantities",
        "get_make_quantities",
        "get_bom_quantities",
        "set_workpiece_value",
        "get_workpiece_value",
        "get_cost_value",
        "set_custom_attribute",
        "get_custom_attribute",
        "get_children",
        "units_mm",
        "units_in",
        "part",
        "quote",
        "op_def",
        "line_item",
        *ANALYZER_NAMES,
    }
)

PRICING_ITEM_NAMES = frozenset(
    {
        "MARKUP",
        "MARGIN",
        "MATERIAL_COST",
        "INSIDE_COST",
        "OUTSIDE_COST",
        "PURCHASED_COMPONENT_COST",
        "TOTAL_COST",
        "CALCULATION_TYPE",
        "COST_CATEGORY",
        "CATEGORY_COST",
        "REQUESTED_QUANTITY",
        "contact",
        "set_profit_item_name",
        "set_custom_cost",
        "get_components",
        "get_children",
        "get_operations",
        "get_material_operations",
        "is_close",
        "is_a_in_b",
    }
)


def _sanitize_exception(exc: Exception) -> str:
    """A one-line, traceback-free description of an in-formula failure."""
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return f"{type(exc).__name__}: {text}"
