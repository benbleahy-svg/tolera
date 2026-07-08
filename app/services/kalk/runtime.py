"""Kalk runtime — guarded builtins, hooks, and the variable registry.

One ``Runtime`` instance exists per evaluation (thread-safe by construction:
all counters live on the instance, injected into the formula's globals as
bound methods). Every guard raises ``KalkAbort`` with a typed error; nothing
here may raise anything else for in-formula misuse.
"""

from __future__ import annotations

import re
import statistics
import string as string_module
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

from app.services.kalk.errors import KalkAbort, KalkError
from app.services.kalk.limits import Limits


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
            raise _abort(
                "runtime_error", f"variable {self._name!r} was updated after freeze()"
            )
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
        value = self._runtime.apply_override(self._name, self._value_type, self._pending)
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
    def __init__(self, limits: Limits, overrides: Mapping[str, object] | None) -> None:
        self.limits = limits
        self.overrides: dict[str, object] = dict(overrides or {})
        self._deadline = time.monotonic() + limits.deadline_seconds
        self._ops = 0
        self._value_types = {"number": NUMBER, "currency": CURRENCY, "string": STRING}
        # contract outputs
        self.declared_variables: list[dict[str, Any]] = []
        self.applied_overrides: list[str] = []
        self.operation_name: str | None = None
        self.notes: str | None = None
        self.no_quote_called = False

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

    def _guarded_split(self, value: str) -> Callable[..., list[str]]:
        def split(sep: object = None, maxsplit: object = -1) -> list[str]:
            self.tick()
            sep_u = self.unwrap(sep)
            if sep_u is not None and not isinstance(sep_u, str):
                raise _abort("runtime_error", "split() separator must be a string")
            if not isinstance(maxsplit, int):
                raise _abort("runtime_error", "split() maxsplit must be an integer")
            return value.split(sep_u, maxsplit)

        return split

    def _guarded_format(self, template: str) -> Callable[..., str]:
        def format_(*args: object, **kwargs: object) -> str:
            self.tick()
            if len(template) > self.limits.max_format_string_len:
                raise _abort("resource_limit", "format string is too long")
            for _, _, spec, _ in string_module.Formatter().parse(template):
                for digits in re.findall(r"\d+", spec or ""):
                    if int(digits) > self.limits.max_format_spec_number:
                        raise _abort(
                            "resource_limit", "format specification is too large"
                        )
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

    def apply_override(
        self, name: str, value_type: ValueType, current: object
    ) -> object:
        if name not in self.overrides:
            return current
        value = self.overrides[name]
        if not _type_ok(value_type, value):
            raise _abort(
                "runtime_error",
                f"override for {name!r} is not a {value_type.name}",
            )
        self.applied_overrides.append(name)
        return value

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
            raise _abort(
                "runtime_error", "var() value_type must be number, currency, or string"
            )
        if any(d["name"] == name for d in self.declared_variables):
            raise _abort("runtime_error", f"variable {name!r} is declared twice")
        default = self.unwrap(default)
        if not _type_ok(value_type, default):
            raise _abort(
                "runtime_error", f"var() default for {name!r} is not a {value_type.name}"
            )
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
        value = self.apply_override(name, value_type, default)
        declaration["value"] = value
        return value

    def _m19_stub(self, fn_name: str) -> Callable[..., object]:
        def stub(*_args: object, **_kwargs: object) -> object:
            raise _abort(
                "runtime_error", f"{fn_name}() is not available until M1.9"
            )

        return stub

    # -- operation-cost context functions --------------------------------------

    def set_operation_name(self, name: object) -> None:
        self.tick()
        if not isinstance(name, str):
            raise _abort("runtime_error", "set_operation_name() takes a string")
        self.operation_name = name

    def set_notes(self, notes: object) -> None:
        self.tick()
        if not isinstance(notes, str):
            raise _abort("runtime_error", "set_notes() takes a string")
        self.notes = notes

    def no_quote(self) -> None:
        self.tick()
        self.no_quote_called = True

    # -- helpers ----------------------------------------------------------------

    def unwrap(self, value: object) -> object:
        if isinstance(value, DynamicVar):
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
        return statistics.mean(self._numeric_args("mean", args))

    def b_median(self, *args: object) -> object:
        self.tick()
        return statistics.median(self._numeric_args("median", args))

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
            return round(number)
        if isinstance(ndigits, bool) or not isinstance(ndigits, int):
            raise _abort("runtime_error", "round() ndigits must be an integer")
        return round(number, ndigits)

    def b_abs(self, number: object) -> object:
        self.tick()
        number = self.unwrap(number)
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _abort("runtime_error", "abs() takes a number")
        return abs(number)

    def b_floor(self, number: object) -> int:
        self.tick()
        number = self.unwrap(number)
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _abort("runtime_error", "floor() takes a number")
        import math

        return math.floor(number)

    def b_ceil(self, number: object) -> int:
        self.tick()
        number = self.unwrap(number)
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _abort("runtime_error", "ceil() takes a number")
        import math

        return math.ceil(number)

    def b_str(self, value: object = "") -> str:
        self.tick()
        result = str(self.unwrap(value))
        if len(result) > self.limits.max_str_len:
            raise _abort("resource_limit", "string grew too long")
        return result

    def b_split(self, value: object, sep: object = None) -> list[str]:
        self.tick()
        value = self.unwrap(value)
        if not isinstance(value, str):
            raise _abort("runtime_error", "split() takes a string")
        return self._guarded_split(value)(sep)

    # -- namespace -------------------------------------------------------------

    def build_globals(
        self, eval_context: Mapping[str, object], quantity: int
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
            # variable system (M1.8: var; the rest are M1.9 stubs)
            "var": self.var,
            "table_var": self._m19_stub("table_var"),
            "table_lookup": self._m19_stub("table_lookup"),
            "variable_group": self._m19_stub("variable_group"),
            "drop_down_var": self._m19_stub("drop_down_var"),
            "number": NUMBER,
            "currency": CURRENCY,
            "string": STRING,
            # operation-cost context
            "no_quote": self.no_quote,
            "set_operation_name": self.set_operation_name,
            "set_notes": self.set_notes,
            "quantity": quantity,
        }
        namespace.update(eval_context)
        return namespace


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
    }
)

OPERATION_COST_NAMES = frozenset(
    {"no_quote", "set_operation_name", "set_notes", "quantity"}
)


def _sanitize_exception(exc: Exception) -> str:
    """A one-line, traceback-free description of an in-formula failure."""
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return f"{type(exc).__name__}: {text}"
