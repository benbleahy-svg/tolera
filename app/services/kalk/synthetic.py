"""Def-level Kalk evaluation against a documented synthetic context (M4.14).

The operation-definition editor's Variables table (VARIABLE | WERT |
SICHTBARKEIT) needs a formula's declared variables + defaults *without* a
quote operation. ``evaluate_def_formula`` runs the sandboxed formula once
against a fixed synthetic ``part``/context — the same ``eval_context`` keys
quote-side evaluation injects (``app.kalk_costing.evaluate_cell``), so any
formula that runs on a real quote runs here too. The synthetic values are
placeholders for variable *enumeration*: costs computed against them are
meaningless and deliberately not returned.

The synthetic part (metric-native, mm/g, CLAUDE.md §5): a 100 x 50 x 10 mm
S235JR block, quantity 1, no nesting, no BOM children. Every attribute the
quote-side ``part`` object carries is present so a def formula never hits
``forbidden_attribute`` for a name that works on a real quote.

``apply_visibility_overlay`` lays the def editor's persisted eye toggles
(``operation_def.variable_visibility`` / the operation's attach-time
snapshot) over the formula-declared ``default_visible``; keys that no longer
match a declared variable are ignored (stale residue after a formula edit).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .evaluator import evaluate
from .objects import ContextData, KalkObject
from .tables import TableProvider

#: Zeroed cost dictionary buckets (KALK-REFERENCE §7) — no upstream router.
_EMPTY_COST_VALUES = {"--material--": 0.0, "--inside--": 0.0, "--outside--": 0.0, "--total--": 0.0}


def unnested_nest_object() -> KalkObject:
    """The ``manual_nest()`` fallback for a part that is not nested (M4.3
    shape — shared with ``app.kalk_costing.kalk_nest_object``)."""
    return KalkObject(
        "nest",
        {
            "nested": False,
            "sheet_cost": 0.0,
            "number_of_sheets": 0.0,
            "net_sheet_used": 0.0,
            "parts_per_sheet": 0.0,
            "cost_share_pct": 0.0,
            "allocated_cost": 0.0,
            "sheet_length_mm": 0.0,
            "sheet_width_mm": 0.0,
        },
    )


def synthetic_part_object() -> KalkObject:
    """The documented synthetic ``part`` — attribute set mirrors
    ``app.kalk_costing.build_part_object`` (PartGeometry catalog, mm/g)."""
    return KalkObject(
        "part",
        {
            "size_x": 100.0,  # mm
            "size_y": 50.0,
            "size_z": 10.0,
            "max_dim": 100.0,
            "med_dim": 50.0,
            "min_dim": 10.0,
            "area": 13_000.0,  # mm² — surface area of the block
            "volume": 50_000.0,  # mm³
            "weight": 392.5,  # g — 50 cm³ at 7.85 g/cm³
            "density": 7.85,  # g/cm³ (S235JR)
            "mat_cost_per_volume": 0.0000025,  # €/mm³ (~2 €/kg steel)
            "material": "S235JR",
            "material_family": "Baustahl",
            "qty": 1,
            "bom_qty": 1,
            "innate_quantity": 1,
            "quantities": [1],
            "make_quantities": [1],
            "bom_quantities": [1],
            "part_number": "MUSTER-001",
            "revision": None,
            "is_root_component": True,
            "is_assembly": False,
            "obtain_method": "MAKE",
            "count_manufactured_children": 0,
            "count_purchased_children": 0,
            "purchased_component": None,
        },
    )


def apply_visibility_overlay(
    declared_variables: list[dict[str, Any]],
    visibility: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Overlay persisted eye toggles onto formula-declared ``default_visible``."""
    if not visibility:
        return declared_variables
    return [
        {**declaration, "default_visible": bool(visibility[declaration["name"]])}
        if declaration["name"] in visibility
        else declaration
        for declaration in declared_variables
    ]


def evaluate_def_formula(
    formula: str,
    *,
    def_name: str,
    visibility: Mapping[str, Any] | None = None,
    table_provider: TableProvider | None = None,
) -> dict[str, Any]:
    """The Variables-table report for one operation definition.

    Evaluates ``formula`` in the ``operation_cost`` context at quantity 1
    against the synthetic part. Every failure comes back as a positioned
    error dict in ``errors`` — never an exception (the CHECK-chrome
    acceptance criterion); declarations made before a runtime error still
    enumerate.
    """
    result = evaluate(
        formula,
        context_type="operation_cost",
        eval_context={
            "part": synthetic_part_object(),
            "op_def": KalkObject("op_def", {"name": def_name, "erp_code": None}),
            "line_item": KalkObject("line_item", {"is_export_controlled": False}),
            "quantity": 1,
            "manual_nest": unnested_nest_object,
        },
        quantity=1,
        table_provider=table_provider,
        context_data=ContextData(
            quantities=[1],
            make_quantities=[1],
            bom_quantities=[1],
            cost_values=dict(_EMPTY_COST_VALUES),
        ),
    )
    return {
        "declared_variables": apply_visibility_overlay(result.declared_variables, visibility),
        "variable_groups": result.variable_groups,
        "errors": [
            {"code": e.code, "message": e.message, "line": e.line, "col": e.col}
            for e in result.errors
        ],
    }
