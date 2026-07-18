"""Kalk object surface — attribute-allowlisted data objects + per-context data.

``KalkObject`` is the one shape every sandbox-exposed domain object takes
(``part``, ``quote``, ``contact``, ``op_def``, ``line_item``, pricing-item
components/operations, BOM children, …): a type name, a dict of plain-data
attributes, and a dict of bound methods. Attribute access is dispatched from
``Runtime.getattr_`` — anything not in the two dicts is a typed error, so a
domain object can never leak private state into a formula.

``ContextData`` carries the structured per-evaluation inputs that context
functions read (quantity lists, workpiece, cost dictionary, custom
attributes, BOM/component graphs). It is built by the app-layer wiring —
this module stays import-light (KALK-REFERENCE §11; the M1.8 seam rules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.services.kalk.errors import abort as _abort

if TYPE_CHECKING:
    from app.services.kalk.runtime import Runtime


class KalkObject:
    """A sandbox-safe domain object: explicit attributes, explicit methods."""

    __slots__ = ("attrs", "methods", "type_name")

    def __init__(
        self,
        type_name: str,
        attrs: dict[str, Any] | None = None,
        methods: dict[str, Any] | None = None,
    ) -> None:
        self.type_name = type_name
        self.attrs = attrs or {}
        self.methods = methods or {}

    def kalk_getattr(self, runtime: Runtime, name: str) -> object:
        if name in self.attrs:
            return self.attrs[name]
        if name in self.methods:
            return self.methods[name]
        raise _abort(
            "forbidden_attribute",
            f"attribute {name!r} is not available on {self.type_name}",
        )

    def __repr__(self) -> str:  # error messages only — formulas can't call repr
        return f"<{self.type_name}>"


@dataclass
class ContextData:
    """Structured inputs the context functions read (all optional)."""

    # operation-cost context (KALK-REFERENCE §7-§9)
    quantities: list[int] = field(default_factory=list)
    make_quantities: list[int] = field(default_factory=list)
    bom_quantities: list[int] = field(default_factory=list)
    cost_values: dict[str, float] = field(default_factory=dict)
    workpiece: dict[str, Any] = field(default_factory=dict)
    custom_attributes: dict[str, Any] = field(default_factory=dict)
    children: list[KalkObject] = field(default_factory=list)
    descendants: list[KalkObject] = field(default_factory=list)  # recursive flat BOM
    # operation-cost context (M4.10) — the generate_operation() payload this
    # operation was created with (KB custom-operation-generation)
    operation_properties: dict[str, Any] = field(default_factory=dict)
    # add-on context (KALK-REFERENCE §11.4 / §7 price dictionary; M1.11) —
    # effective prices of the add-on cells above the active one, plus the
    # --required_add_on-- / --non_required_add_on-- accumulators
    price_values: dict[str, float] = field(default_factory=dict)
    # pricing-item context (KALK-REFERENCE §11.3) — components in leaf-to-root order
    components: list[KalkObject] = field(default_factory=list)
    component_children: dict[str, list[KalkObject]] = field(default_factory=dict)
    component_operations: dict[str, list[KalkObject]] = field(default_factory=dict)
    component_material_operations: dict[str, list[KalkObject]] = field(default_factory=dict)
