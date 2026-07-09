"""Kalk lists — ``P3LList`` and its guarded method surface (KALK-REFERENCE §4).

``P3LList`` itself is a dumb ``list`` subclass so membership (``in``),
iteration (via the ``_k_iter`` hook), and the numeric builtins work unchanged;
it carries no runtime handle. All formula-visible methods are dispatched
through :func:`list_attr` from ``Runtime.getattr_`` so every call ticks the
op budget, guards sizes, and sanitizes lambda failures.

Mutating methods return ``self`` for chaining; ``copy``/``map``/``unique``
return new lists (KALK-REFERENCE §4).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from app.services.kalk.errors import KalkAbort, KalkError

if TYPE_CHECKING:
    from app.services.kalk.runtime import Runtime


class P3LList(list):  # type: ignore[type-arg]  # deliberate untyped-list subclass
    """The Kalk list type (``create_list()``)."""

    __slots__ = ()


class MultiSort(tuple):  # type: ignore[type-arg]
    """Opaque multi-key sort value (``create_multi_sort()``) — compares as a tuple."""

    __slots__ = ()


def _abort(code: str, message: str) -> KalkAbort:
    return KalkAbort(KalkError(code=code, message=message))


def create_list(runtime: Runtime, *args: object) -> P3LList:
    runtime.tick()
    if len(args) == 1 and isinstance(args[0], list | tuple):
        return P3LList(args[0])
    return P3LList(runtime.unwrap(a) for a in args)


def create_multi_sort(runtime: Runtime, *args: object) -> MultiSort:
    runtime.tick()
    return MultiSort(runtime.unwrap(a) for a in args)


def iterate(runtime: Runtime, value: object) -> P3LList:
    """Loop helper — ``for x in iterate(lst)`` (KALK-REFERENCE §4)."""
    runtime.tick()
    value = runtime.unwrap(value)
    if not isinstance(value, list | tuple):
        raise _abort("runtime_error", "iterate() takes a list")
    return P3LList(value)


def _call_lambda(runtime: Runtime, fn: object, *args: object) -> object:
    """Run a formula-supplied lambda under the same guards as formula code."""
    runtime.tick()
    if not callable(fn):
        raise _abort("runtime_error", "expected a lambda")
    try:
        return fn(*args)
    except KalkAbort:
        raise
    except Exception as exc:  # sanitized — never a traceback
        from app.services.kalk.runtime import _sanitize_exception

        raise _abort("runtime_error", _sanitize_exception(exc)) from None


def _guard_len(runtime: Runtime, obj: P3LList) -> None:
    if len(obj) > runtime.limits.max_collection_len:
        raise _abort("resource_limit", "collection grew too large")


def _sort_key(runtime: Runtime, fn: object) -> Callable[[object], object]:
    def key(item: object) -> object:
        return runtime.unwrap(_call_lambda(runtime, fn, item))

    return key


def list_attr(runtime: Runtime, obj: P3LList, name: str) -> object:
    """Resolve a method access on a ``P3LList`` (called from ``Runtime.getattr_``)."""

    def append(item: object) -> P3LList:
        runtime.tick()
        obj.append(runtime.unwrap(item))
        _guard_len(runtime, obj)
        return obj

    def extend(other: object) -> P3LList:
        runtime.tick()
        other_u = runtime.unwrap(other)
        if not isinstance(other_u, list | tuple):
            raise _abort("runtime_error", "extend() takes a list")
        obj.extend(other_u)
        _guard_len(runtime, obj)
        return obj

    def reverse() -> P3LList:
        runtime.tick()
        obj.reverse()
        return obj

    def copy() -> P3LList:
        runtime.tick()
        return P3LList(obj)

    def clear() -> P3LList:
        runtime.tick()
        obj.clear()
        return obj

    def remove(item: object) -> P3LList:
        runtime.tick()
        item_u = runtime.unwrap(item)
        if item_u not in obj:
            raise _abort("runtime_error", "remove(): item not in list (guard with `in`)")
        obj.remove(item_u)
        return obj

    def pop(index: object = 0) -> object:
        runtime.tick()
        index = runtime.unwrap(index)
        if not isinstance(index, int) or isinstance(index, bool):
            raise _abort("runtime_error", "pop() index must be an integer")
        if not obj:
            raise _abort("runtime_error", "pop() from an empty list")
        try:
            return obj.pop(index)
        except IndexError:
            raise _abort("runtime_error", "pop() index out of range") from None

    def sort(fn: object) -> P3LList:
        try:
            obj.sort(key=_sort_key(runtime, fn))  # type: ignore[arg-type]  # stable — determinism contract
        except KalkAbort:
            raise
        except TypeError:
            raise _abort("runtime_error", "sort() keys are not comparable") from None
        return obj

    def filter_(fn: object) -> P3LList:
        kept = [item for item in obj if _call_lambda(runtime, fn, item)]
        obj[:] = kept
        return obj

    def map_(fn: object) -> P3LList:
        return P3LList(runtime.unwrap(_call_lambda(runtime, fn, item)) for item in obj)

    def reduce(fn: object, initial: object = None) -> object:
        items = list(obj)
        if initial is None:
            if not items:
                raise _abort("runtime_error", "reduce() of an empty list with no initial value")
            acc, rest = items[0], items[1:]
        else:
            acc, rest = runtime.unwrap(initial), items
        for item in rest:
            acc = runtime.unwrap(_call_lambda(runtime, fn, acc, item))
        return acc

    def unique(fn: object) -> P3LList:
        seen: list[object] = []  # list, not set — values may be unhashable; N is capped
        result = P3LList()
        for item in obj:
            key = runtime.unwrap(_call_lambda(runtime, fn, item))
            if key not in seen:
                seen.append(key)
                result.append(item)
        return result

    def join(delimiter: object = "\n") -> str:
        runtime.tick()
        delim = runtime.unwrap(delimiter)
        if not isinstance(delim, str):
            raise _abort("runtime_error", "join() delimiter must be a string")
        parts: list[str] = []
        for item in obj:
            item_u = runtime.unwrap(item)
            if not isinstance(item_u, str):
                raise _abort("runtime_error", "join() takes a list of strings")
            parts.append(item_u)
        result = delim.join(parts)
        if len(result) > runtime.limits.max_str_len:
            raise _abort("resource_limit", "string grew too long")
        return result

    methods: dict[str, object] = {
        "append": append,
        "extend": extend,
        "reverse": reverse,
        "copy": copy,
        "clear": clear,
        "remove": remove,
        "pop": pop,
        "sort": sort,
        "filter": filter_,
        "map": map_,
        "reduce": reduce,
        "unique": unique,
        "join": join,
    }
    if name not in methods:
        raise _abort("forbidden_attribute", f"attribute {name!r} is not available on a list")
    return methods[name]
