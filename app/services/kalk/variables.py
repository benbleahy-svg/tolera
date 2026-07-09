"""Kalk variable objects beyond plain ``var()`` — drop-downs and groups
(KALK-REFERENCE §3; spec ``#kalk-vars``).

``DropDownVar`` mirrors the dynamic-variable lifecycle: mutate options →
select (the freeze point, where a UI override applies) → read. A
``VariableGroup`` is pure UI metadata — it collects declared variables into
ordered collapsible sections; declaration order = UI order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.kalk.errors import abort as _abort

if TYPE_CHECKING:
    from app.services.kalk.runtime import Runtime, ValueType


class DropDownVar:
    """``drop_down_var(..., frozen=False)`` — options mutate until a select call."""

    __slots__ = ("_declaration", "_name", "_options", "_runtime", "_selected", "_value_type")

    def __init__(
        self,
        runtime: Runtime,
        name: str,
        value_type: ValueType,
        options: list[Any],
        declaration: dict[str, Any],
    ) -> None:
        self._runtime = runtime
        self._name = name
        self._value_type = value_type
        self._options = options
        self._declaration = declaration
        self._selected: Any = _UNSELECTED

    def _freeze(self, value: Any) -> None:
        if self._selected is not _UNSELECTED:
            raise _abort(
                "runtime_error",
                f"drop-down {self._name!r} was selected twice (one selection only)",
            )
        value = self._runtime.resolve_dropdown_override(self._name, self._declaration, value)
        if value not in self._options:
            raise _abort(
                "runtime_error",
                f"drop-down {self._name!r}: the selected value is not one of the options",
            )
        self._selected = value
        self._declaration["options"] = list(self._options)
        self._declaration["value"] = value

    @property
    def kalk_value(self) -> object:
        if self._selected is _UNSELECTED:
            raise _abort(
                "runtime_error",
                f"drop-down {self._name!r} used before a select_*() call",
            )
        return self._selected

    def kalk_getattr(self, runtime: Runtime, name: str) -> object:
        def clear_options() -> None:
            runtime.tick()
            self._options.clear()

        def update_options(options: object) -> None:
            runtime.tick()
            self._options[:] = runtime.check_dropdown_options(self._name, self._value_type, options)

        def select_option(value: object) -> None:
            runtime.tick()
            self._freeze(runtime.unwrap(value))

        def select_default() -> None:
            runtime.tick()
            self._freeze(self._declaration["default"])

        methods = {
            "clear_options": clear_options,
            "update_options": update_options,
            "select_option": select_option,
            "select_default": select_default,
        }
        if name in methods:
            return methods[name]
        raise _abort(
            "forbidden_attribute",
            f"attribute {name!r} is not available on a drop-down variable",
        )


_UNSELECTED = object()


class VariableGroup:
    """``variable_group()`` — ordered, collapsible UI sections (§3)."""

    __slots__ = ("_group", "_runtime")

    def __init__(self, runtime: Runtime, group: dict[str, Any]) -> None:
        self._runtime = runtime
        self._group = group

    def kalk_getattr(self, runtime: Runtime, name: str) -> object:
        if name != "add_by_name":
            raise _abort(
                "forbidden_attribute",
                f"attribute {name!r} is not available on a variable group",
            )

        def add_by_name(*names: object) -> None:
            runtime.tick()
            for raw in names:
                var_name = runtime.unwrap(raw)
                if not isinstance(var_name, str):
                    raise _abort("runtime_error", "add_by_name() takes variable-name strings")
                runtime.add_to_group(self._group, var_name)

        return add_by_name
