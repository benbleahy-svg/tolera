"""M1.9 — Kalk context surfaces: the operation-cost context's part/workpiece/
cost-dictionary/custom-attribute/BOM reads, and the pricing-item context.

Spec ``#kalk-contexts``; KALK-REFERENCE §7-§11. The ``part`` object here is a
hand-built KalkObject — the app wiring builds the real one from PartGeometry
(metric, grams; DECISIONS.md 2026-07-07/08 units decisions).
"""

from __future__ import annotations

from typing import Any

from app.services.kalk import EvalResult, check, evaluate
from app.services.kalk.objects import ContextData, KalkObject


def part_object() -> KalkObject:
    return KalkObject(
        "part",
        {
            "size_x": 120.0,  # mm — PartGeometry catalog units
            "size_y": 60.0,
            "size_z": 10.0,
            "volume": 72000.0,  # mm³
            "weight": 194.4,  # g
            "density": 2.7,  # g/cm³
            "material": "Aluminum 6061-T6",
            "qty": 5,
            "bom_qty": 1,
            "part_number": "TL-100",
            "is_root_component": True,
            "obtain_method": "MANUFACTURED",
        },
    )


def run_op(formula: str, **kwargs: Any) -> EvalResult:
    kwargs.setdefault("eval_context", {"part": part_object()})
    return evaluate(formula, context_type="operation_cost", **kwargs)


def ok_op(formula: str, **kwargs: Any) -> EvalResult:
    result = run_op(formula, **kwargs)
    assert not result.errors, result.errors
    return result


def cost(formula: str, **kwargs: Any) -> float:
    result = ok_op(formula, **kwargs)
    assert result.output is not None
    return float(result.output["COST"])


# ---------------------------------------------------------------------------
# part object + geometry reads
# ---------------------------------------------------------------------------


def test_part_attributes_drive_cost() -> None:
    assert cost("COST = max(part.size_x, part.size_y, part.size_z) * part.qty") == 600.0


def test_part_material_split() -> None:
    formula = """
family = part.material.split(' ').pop()
COST = 0
if family == 'Aluminum':
    COST = 1
"""
    assert cost(formula) == 1.0


def test_unknown_part_attribute_is_forbidden() -> None:
    result = run_op("COST = part.secret_field")
    assert result.errors[0].code == "forbidden_attribute"
    assert "part" in result.errors[0].message


def test_check_knows_the_context_names_without_data() -> None:
    assert check("COST = part.size_x * quantity", context_type="operation_cost").ok


def test_is_close_and_is_a_in_b() -> None:
    formula = """
COST = 0
if is_close(0.1 + 0.2, 0.3):
    COST = COST + 1
if is_a_in_b('alum', part.material):
    COST = COST + 10
if is_a_in_b('bend', create_list('bend', 'curl')):
    COST = COST + 100
"""
    assert cost(formula) == 111.0


def test_dynamic_var_reads_part_before_freeze() -> None:
    formula = """
longest = var('Longest Side', 0, 'mm', number, frozen=False)
longest.update(max(part.size_x, part.size_y, part.size_z))
longest.freeze()
COST = longest
"""
    assert cost(formula) == 120.0


# ---------------------------------------------------------------------------
# quantities, workpiece, cost dictionary, custom attributes, children
# ---------------------------------------------------------------------------


def test_quantity_lists_are_index_aligned() -> None:
    data = ContextData(quantities=[1, 5, 20], make_quantities=[1, 5, 20], bom_quantities=[1, 1, 1])
    formula = """
COST = sum(get_quantities()) + sum(get_make_quantities()) * 100 + sum(get_bom_quantities())
"""
    assert cost(formula, context_data=data) == 26 + 2600 + 3


def test_workpiece_flows_in_and_out() -> None:
    data = ContextData(workpiece={"tapped_holes": 8})
    formula = """
set_workpiece_value('needs_anodize', True)
COST = get_workpiece_value('tapped_holes', 0) * 2
"""
    result = ok_op(formula, context_data=data)
    assert result.output is not None
    assert result.output["COST"] == 16.0
    assert result.workpiece == {"tapped_holes": 8, "needs_anodize": True}


def test_cost_dictionary_special_keys_and_default() -> None:
    data = ContextData(cost_values={"--material--": 674.20, "Laser Cutting": 178.16})
    formula = """
COST = get_cost_value('--material--') + get_cost_value('Laser Cutting')
COST = COST + get_cost_value('Never Ran')
"""
    assert cost(formula, context_data=data) == 674.20 + 178.16


def test_custom_attributes_read_write_and_type_stability() -> None:
    data = ContextData(custom_attributes={"tolerance_class": "fine"})
    formula = """
set_custom_attribute('needs_cmm', True)
COST = 0
if get_custom_attribute('tolerance_class', '') == 'fine':
    COST = 1
"""
    result = ok_op(formula, context_data=data)
    assert result.output is not None
    assert result.output["COST"] == 1.0
    assert result.custom_attributes == {"needs_cmm": True}

    stable = run_op(
        "set_custom_attribute('needs_cmm', 'yes')\nCOST = 0",
        context_data=ContextData(custom_attributes={"needs_cmm": True}),
    )
    assert "cannot change type" in stable.errors[0].message


def test_get_children_filters_by_obtain_method() -> None:
    child = KalkObject("child", {"obtain_method": "PURCHASED", "is_assembly": False, "count": 2})
    made = KalkObject("child", {"obtain_method": "MANUFACTURED", "is_assembly": False, "count": 1})
    data = ContextData(children=[child, made], descendants=[child, made])
    formula = """
purchased = get_children('PURCHASED')
COST = purchased.reduce(lambda acc, c: acc + c.count, 0)
"""
    assert cost(formula, context_data=data) == 2.0


# ---------------------------------------------------------------------------
# units + analyzer stubs (M4 boundary; DACH metric-native)
# ---------------------------------------------------------------------------


def test_units_mm_is_a_no_op() -> None:
    assert cost("units_mm()\nCOST = part.size_x") == 120.0


def test_units_in_is_rejected() -> None:
    result = run_op("units_in()\nCOST = 0")
    assert "metric-native" in result.errors[0].message


def test_analyzers_are_m4_stubs() -> None:
    result = run_op("sm = analyze_sheet_metal()\nCOST = 0")
    assert "not available until M4" in result.errors[0].message


# ---------------------------------------------------------------------------
# pricing-item context (KALK-REFERENCE §11.3)
# ---------------------------------------------------------------------------


def components_fixture() -> ContextData:
    titanium_op = KalkObject(
        "operation",
        {"cost": 539.36, "name": "Titanium Grade 5", "category": "material"},
    )
    aluminum_op = KalkObject(
        "operation",
        {"cost": 134.84, "name": "Aluminum 6061-T6", "category": "material"},
    )
    root = KalkObject(
        "component",
        {
            "uuid": "c-1",
            "self_cost": 1702.37,
            "part": KalkObject("part", {"material": "Titanium Grade 5"}),
        },
    )
    return ContextData(
        components=[root],
        component_operations={"c-1": [titanium_op, aluminum_op]},
        component_material_operations={"c-1": [titanium_op, aluminum_op]},
    )


def run_pricing(formula: str, **kwargs: Any) -> EvalResult:
    return evaluate(formula, context_type="pricing_item", **kwargs)


def test_pricing_item_percentage_output() -> None:
    result = run_pricing(
        "PERCENTAGE = 60", eval_context={"CALCULATION_TYPE": "MARKUP", "CATEGORY_COST": 674.20}
    )
    assert not result.errors
    assert result.output == {"PERCENTAGE": 60.0, "custom_cost": None}


def test_pricing_item_missing_percentage() -> None:
    result = run_pricing("x = 1")
    assert result.errors[0].code == "missing_output"


def test_pricing_globals_available() -> None:
    formula = """
PERCENTAGE = 0
if CALCULATION_TYPE == MARKUP:
    PERCENTAGE = MATERIAL_COST / TOTAL_COST * 100
"""
    result = run_pricing(
        formula,
        eval_context={"MATERIAL_COST": 674.20, "TOTAL_COST": 1702.37},
    )
    assert not result.errors
    assert result.output is not None
    assert round(result.output["PERCENTAGE"], 2) == 39.6


def test_difficult_material_custom_cost_reslice() -> None:
    """The Demo E Difficult-Material shape: sum only the difficult material
    operations across the BOM and mark up that slice (spec #customcat)."""
    formula = """
set_profit_item_name('Difficult Material Markup')
difficult = 0
for component in get_components():
    ops = get_material_operations(component)
    ops.filter(lambda op: is_a_in_b('titanium', op.name))
    difficult += ops.reduce(lambda acc, op: acc + op.cost, 0)
set_custom_cost(difficult)
PERCENTAGE = 10
"""
    result = run_pricing(formula, context_data=components_fixture())
    assert not result.errors, result.errors
    assert result.output == {"PERCENTAGE": 10.0, "custom_cost": 539.36}
    assert result.profit_item_name == "Difficult Material Markup"


def test_get_components_order_validation() -> None:
    result = run_pricing("x = get_components('sideways')\nPERCENTAGE = 0")
    assert "leaf_to_root" in result.errors[0].message


def test_get_operations_accepts_uuid_string() -> None:
    formula = """
PERCENTAGE = get_operations('c-1').reduce(lambda acc, op: acc + op.cost, 0)
"""
    result = run_pricing(formula, context_data=components_fixture())
    assert not result.errors
    assert result.output is not None
    assert round(result.output["PERCENTAGE"], 2) == 674.20


def test_contact_object_in_pricing_context() -> None:
    contact = KalkObject(
        "contact",
        {"email": "einkauf@fechner.de", "account": KalkObject("account", {"name": "Fechner"})},
    )
    formula = """
PERCENTAGE = 20
if contact and contact.account.name == 'Fechner':
    PERCENTAGE = 15
"""
    result = run_pricing(formula, eval_context={"contact": contact})
    assert not result.errors
    assert result.output is not None
    assert result.output["PERCENTAGE"] == 15.0


def test_pricing_context_has_no_part_or_analyzers() -> None:
    assert not check("PERCENTAGE = part.size_x", context_type="pricing_item").ok
    assert not check("x = analyze_mill3()\nPERCENTAGE = 0", context_type="pricing_item").ok


def test_operation_context_functions_absent_from_pricing() -> None:
    result = run_pricing("no_quote()\nPERCENTAGE = 0")
    assert result.errors[0].code == "unknown_name"


def test_unsupported_contexts_still_rejected() -> None:
    for context in ("add_on", "discount", "operation_generation"):
        result = evaluate("PRICE = 1", context_type=context)
        assert result.errors[0].code == "invalid_context"
