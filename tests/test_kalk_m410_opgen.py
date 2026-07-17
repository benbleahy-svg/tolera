"""M4.10 — the process-level ``operation_generation`` Kalk context.

KB ``custom-operation-generation`` is the contract: the formula mutates a
routing (a list of generated operations) instead of outputting COST/DAYS.
``get_allowed_operations()`` iterates the process's allowed op-def names;
``generate_operation(name, custom_name=, operation_properties=)`` appends
(cap 20); the op-level ``get_operation_property(name, default)`` reads the
properties back. The KB-listed operation-UI functions (``var``,
``drop_down_var``, ``variable_group``, ``set_operation_name``,
``get_workpiece_value``, ``set_workpiece_value``, ``get_price_value``) do not
exist in process-level Kalk. Spec ``#kalk-contexts`` "Process generation".
"""

from __future__ import annotations

from typing import Any

from app.services.kalk import EvalResult, check, evaluate
from app.services.kalk.objects import ContextData, KalkObject


def part_object(component_type: str = "MANUFACTURED", *, root: bool = False) -> KalkObject:
    return KalkObject(
        "part",
        {
            "size_x": 120.0,
            "size_y": 60.0,
            "size_z": 10.0,
            "part_number": "TL-100",
            "component_type": component_type,
            "is_root_component": root,
            "obtain_method": component_type if component_type != "ASSEMBLED" else "MANUFACTURED",
        },
    )


ALLOWED = ["Material", "Grinding", "Lathe", "Inspection"]


def run_gen(formula: str, **kwargs: Any) -> EvalResult:
    kwargs.setdefault("eval_context", {"part": part_object()})
    kwargs.setdefault("allowed_operations", ALLOWED)
    allowed = kwargs.pop("allowed_operations")
    return evaluate(
        formula,
        context_type="operation_generation",
        allowed_operations=allowed,
        **kwargs,
    )


def ok_gen(formula: str, **kwargs: Any) -> list[dict[str, Any]]:
    result = run_gen(formula, **kwargs)
    assert not result.errors, result.errors
    assert result.output is not None
    ops: list[dict[str, Any]] = result.output["operations"]
    return ops


# ---------------------------------------------------------------------------
# the KB walk-through examples
# ---------------------------------------------------------------------------


def test_generic_replication_iterates_allowed_operations() -> None:
    # KB example 1 — replicate the generic process with the iterator fn
    ops = ok_gen(
        "for op_name in get_allowed_operations():\n"
        "  if part.component_type == MANUFACTURED:\n"
        "      generate_operation(op_name)\n"
    )
    assert [op["op_def_name"] for op in ops] == ALLOWED


def test_component_type_branching_assembled() -> None:
    # KB example 2 — ASSEMBLED parts get the Assemble op only; root adds Inspection
    formula = (
        "if part.component_type == MANUFACTURED:\n"
        "  generate_operation('Material')\n"
        "elif part.component_type == ASSEMBLED:\n"
        "  generate_operation('Assemble')\n"
        "if part.is_root_component:\n"
        "  generate_operation('Inspection')\n"
    )
    allowed = [*ALLOWED, "Assemble"]
    ops = ok_gen(
        formula,
        eval_context={"part": part_object("ASSEMBLED", root=True)},
        allowed_operations=allowed,
    )
    assert [op["op_def_name"] for op in ops] == ["Assemble", "Inspection"]
    ops = ok_gen(formula, allowed_operations=allowed)
    assert [op["op_def_name"] for op in ops] == ["Material"]


def test_custom_attribute_drives_routing() -> None:
    # KB example 3 — custom attrs work for geometric AND non-geometric parts
    formula = (
        "outer_diameter = get_custom_attribute('outer_diameter', 0)\n"
        "if outer_diameter > 4:\n"
        "  generate_operation('Large Diameter Lathe')\n"
        "else:\n"
        "  generate_operation('Small Diameter Lathe')\n"
    )
    allowed = ["Large Diameter Lathe", "Small Diameter Lathe"]
    ops = ok_gen(
        formula,
        allowed_operations=allowed,
        context_data=ContextData(custom_attributes={"outer_diameter": 6.0}),
    )
    assert [op["op_def_name"] for op in ops] == ["Large Diameter Lathe"]
    ops = ok_gen(formula, allowed_operations=allowed)
    assert [op["op_def_name"] for op in ops] == ["Small Diameter Lathe"]


def test_custom_name_and_operation_properties() -> None:
    # KB example 4 — Transit ops with per-instance names + property payloads
    ops = ok_gen(
        "props = {'time': 15}\n"
        "generate_operation('Transit', custom_name='Admin to Programming',"
        " operation_properties=props)\n"
        "generate_operation('Lathe')\n",
        allowed_operations=["Transit", "Lathe"],
    )
    assert ops[0] == {
        "op_def_name": "Transit",
        "custom_name": "Admin to Programming",
        "operation_properties": {"time": 15},
    }
    assert ops[1]["op_def_name"] == "Lathe"
    assert ops[1]["custom_name"] is None
    assert ops[1]["operation_properties"] is None


# ---------------------------------------------------------------------------
# guard rails
# ---------------------------------------------------------------------------


def test_generation_cap_20() -> None:
    result = run_gen(
        "for c in 'abcdefghijklmnopqrstuvwxy':\n  generate_operation('Material')\n",
    )
    assert any("20" in e.message for e in result.errors), result.errors


def test_unknown_op_def_name_rejected() -> None:
    result = run_gen("generate_operation('No Such Op')\n")
    assert any("No Such Op" in e.message for e in result.errors), result.errors


def test_generate_operation_name_must_be_string() -> None:
    result = run_gen("generate_operation(42)\n")
    assert result.errors, "non-string op name must be a runtime error"


def test_empty_generation_is_valid() -> None:
    # a purchased part may legitimately generate no operations
    ops = ok_gen(
        "if part.component_type == MANUFACTURED:\n  pass\n",
    )
    assert ops == []


def test_banned_operation_ui_functions_fail_check() -> None:
    # KB: no var/drop_down_var/variable_group/set_operation_name/
    # get_workpiece_value/set_workpiece_value/get_price_value in process P3L
    banned = [
        "x = var('Rate', 25, '', number)",
        "x = drop_down_var('Choice', 'a', create_list('a'), '')",
        "variable_group('G')",
        "set_operation_name('X')",
        "x = get_workpiece_value('stock')",
        "set_workpiece_value('stock', 1)",
        "x = get_price_value('FAI')",
    ]
    for formula in banned:
        result = check(formula, context_type="operation_generation")
        assert not result.ok, f"{formula!r} must not validate in process-level Kalk"


def test_output_has_no_cost_or_days() -> None:
    result = run_gen("generate_operation('Material')\n")
    assert not result.errors
    assert result.output is not None
    assert "COST" not in result.output
    assert "DAYS" not in result.output


def test_check_supports_operation_generation_context() -> None:
    result = check(
        "for op_name in get_allowed_operations():\n  generate_operation(op_name)\n",
        context_type="operation_generation",
    )
    assert result.ok, result.errors


# ---------------------------------------------------------------------------
# get_operation_property — the op-cost side of the KB contract
# ---------------------------------------------------------------------------


def test_get_operation_property_reads_generated_payload() -> None:
    # KB Transit example: move_time from the property, divided down to hours
    result = evaluate(
        "move_time = get_operation_property('time', 0) / 60\n"
        "rate = 25\n"
        "COST = move_time * rate\n"
        "DAYS = 0\n",
        context_type="operation_cost",
        eval_context={"part": part_object()},
        context_data=ContextData(operation_properties={"time": 15}),
    )
    assert not result.errors, result.errors
    assert result.output is not None
    assert result.output["COST"] == 6.25


def test_get_operation_property_default_when_absent() -> None:
    result = evaluate(
        "COST = get_operation_property('time', 99)\nDAYS = 0\n",
        context_type="operation_cost",
        eval_context={"part": part_object()},
    )
    assert not result.errors, result.errors
    assert result.output is not None
    assert result.output["COST"] == 99.0
