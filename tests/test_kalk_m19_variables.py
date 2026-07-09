"""M1.9 — Kalk variable system beyond var(): drop_down_var, variable_group,
quantity_specific overrides.

Spec ``#kalk-vars``; KALK-REFERENCE §3; DECISIONS.md 2026-07-08 (override
shapes: plain value, ``{qty: value}`` for quantity-specific).
"""

from __future__ import annotations

from typing import Any

from app.services.kalk import EvalResult, check, evaluate
from app.services.kalk.tables import MappingTableProvider, TableColumn, TableSnapshot


def run(formula: str, **kwargs: Any) -> EvalResult:
    return evaluate(formula, context_type="operation_cost", **kwargs)


def ok(formula: str, **kwargs: Any) -> EvalResult:
    result = run(formula, **kwargs)
    assert not result.errors, result.errors
    return result


def cost(formula: str, **kwargs: Any) -> float:
    result = ok(formula, **kwargs)
    assert result.output is not None
    return float(result.output["COST"])


# ---------------------------------------------------------------------------
# drop_down_var — frozen (default)
# ---------------------------------------------------------------------------

DROPDOWN = """
finish = drop_down_var('Finish', 'Anodize', create_list('Anodize', 'Powder Coat'),
                       'surface finish', string)
COST = 0
if finish == 'Powder Coat':
    COST = 25
"""


def test_dropdown_default_value() -> None:
    assert cost(DROPDOWN) == 0.0


def test_dropdown_override_applies() -> None:
    result = ok(DROPDOWN, overrides={"Finish": "Powder Coat"})
    assert result.output is not None
    assert result.output["COST"] == 25.0
    assert result.applied_overrides == ["Finish"]


def test_dropdown_override_outside_options_is_error() -> None:
    result = run(DROPDOWN, overrides={"Finish": "Chrome"})
    assert "not one of the options" in result.errors[0].message


def test_dropdown_declaration_carries_options() -> None:
    decl = ok(DROPDOWN).declared_variables[0]
    assert decl["kind"] == "drop_down"
    assert decl["options"] == ["Anodize", "Powder Coat"]
    assert decl["value"] == "Anodize"


def test_dropdown_default_must_be_an_option() -> None:
    result = run("x = drop_down_var('X', 'c', create_list('a', 'b'), '', string)\nCOST = 0")
    assert "default value is not one of the options" in result.errors[0].message


def test_dropdown_option_type_enforced() -> None:
    result = run("x = drop_down_var('X', 1, create_list(1, 'b'), '', number)\nCOST = 0")
    assert "is not a number" in result.errors[0].message


def test_dropdown_numeric_values_compute() -> None:
    formula = """
level = drop_down_var('Level', 2, create_list(1, 2, 3), 'complexity', number)
COST = level * 10
"""
    assert cost(formula) == 20.0
    assert cost(formula, overrides={"Level": 3}) == 30.0


# ---------------------------------------------------------------------------
# drop_down_var — frozen=False (dynamic options; selection = freeze point)
# ---------------------------------------------------------------------------

DYNAMIC = """
dd = drop_down_var('Pick', 'a', create_list('a'), '', string, False)
{body}
"""


def test_dynamic_dropdown_update_then_select() -> None:
    body = (
        "dd.update_options(create_list('x', 'y'))\ndd.select_option('y')\nCOST = 0\nset_notes(dd)"
    )
    result = ok(DYNAMIC.format(body=body))
    assert result.notes == "y"


def test_dynamic_dropdown_select_default() -> None:
    body = "dd.select_default()\nset_notes(dd)\nCOST = 0"
    assert ok(DYNAMIC.format(body=body)).notes == "a"


def test_dynamic_dropdown_read_before_select_is_error() -> None:
    result = run(DYNAMIC.format(body="set_notes(dd)\nCOST = 0"))
    assert "before a select_" in result.errors[0].message


def test_dynamic_dropdown_double_select_is_error() -> None:
    result = run(DYNAMIC.format(body="dd.select_default()\ndd.select_default()\nCOST = 0"))
    assert "selected twice" in result.errors[0].message


def test_dynamic_dropdown_select_outside_current_options_is_error() -> None:
    body = "dd.update_options(create_list('x'))\ndd.select_option('a')\nCOST = 0"
    result = run(DYNAMIC.format(body=body))
    assert "not one of the options" in result.errors[0].message


def test_dynamic_dropdown_override_wins_at_selection() -> None:
    body = (
        "dd.update_options(create_list('x', 'y'))\ndd.select_option('x')\nset_notes(dd)\nCOST = 0"
    )
    result = ok(DYNAMIC.format(body=body), overrides={"Pick": "y"})
    assert result.notes == "y"


def test_dropdown_options_from_custom_table() -> None:
    table = TableSnapshot(
        name="finishes",
        columns=(TableColumn(name="finish", type="string"),),
        rows=((1, {"finish": "Anodize"}), (2, {"finish": "Powder Coat"})),
    )
    formula = """
dd = drop_down_var('Finish', 'none', create_list('none'), '', string, False)
names = table_lookup('finishes', None, None).map(lambda r: r.finish)
dd.update_options(names.append('none'))
dd.select_option('Powder Coat')
set_notes(dd)
COST = 0
"""
    result = evaluate(
        formula,
        context_type="operation_cost",
        table_provider=MappingTableProvider({"finishes": table}),
    )
    assert not result.errors, result.errors
    assert result.notes == "Powder Coat"


# ---------------------------------------------------------------------------
# variable_group
# ---------------------------------------------------------------------------

GROUPED = """
labor_rate = var('Labor Rate', 50, '$/hr', currency)
machine_rate = var('Machine Rate', 40, '$/hr', currency)
rates = variable_group('Rates', True)
rates.add_by_name('Labor Rate', 'Machine Rate')
COST = labor_rate + machine_rate
"""


def test_variable_group_membership_and_order() -> None:
    result = ok(GROUPED)
    assert result.variable_groups == [
        {"name": "Rates", "default_collapsed": True, "members": ["Labor Rate", "Machine Rate"]}
    ]


def test_group_rejects_undeclared_variable() -> None:
    result = run("g = variable_group('G')\ng.add_by_name('Nope')\nCOST = 0")
    assert "no variable named 'Nope'" in result.errors[0].message


def test_group_rejects_runtime_and_setup_time() -> None:
    formula = """
runtime = var('runtime', 0, 'hours', number)
g = variable_group('G')
g.add_by_name('runtime')
COST = 0
"""
    result = run(formula)
    assert "cannot be added to a variable group" in result.errors[0].message


def test_variable_can_join_only_one_group() -> None:
    formula = """
x = var('X', 1, '', number)
a = variable_group('A')
b = variable_group('B')
a.add_by_name('X')
b.add_by_name('X')
COST = 0
"""
    result = run(formula)
    assert "already in group 'A'" in result.errors[0].message


def test_group_declared_in_block_rejected() -> None:
    result = check("if 1 > 0:\n    g = variable_group('G')\nCOST = 0")
    assert not result.ok
    assert result.errors[0].code == "declaration_in_block"


# ---------------------------------------------------------------------------
# quantity_specific vars
# ---------------------------------------------------------------------------

QTY_VAR = """
per_part = var('Per Part', 4.0, 'per-qty input', number, True, True, True)
COST = per_part * quantity
"""


def test_quantity_specific_override_applies_to_matching_quantity() -> None:
    overrides = {"Per Part": {"5": 3.0}}
    assert cost(QTY_VAR, quantity=5, overrides=overrides) == 15.0
    assert cost(QTY_VAR, quantity=20, overrides=overrides) == 80.0  # default 4.0


def test_plain_var_rejects_per_quantity_override() -> None:
    formula = "x = var('X', 1.0, '', number)\nCOST = x"
    result = run(formula, overrides={"X": {"5": 2.0}})
    assert "not quantity-specific" in result.errors[0].message


def test_scalar_override_on_quantity_specific_var_applies_to_all_breaks() -> None:
    # the runtime/setup_time manual pair takes this path (kalk_costing wiring)
    overrides = {"Per Part": 3.0}
    assert cost(QTY_VAR, quantity=5, overrides=overrides) == 15.0
    assert cost(QTY_VAR, quantity=20, overrides=overrides) == 60.0


def test_override_key_is_the_quantity_param_not_the_formula_global() -> None:
    """The wiring keys overrides by the UI-visible break quantity (evaluate's
    ``quantity``) while the formula's ``quantity`` global carries the make
    quantity via eval_context — a break with scrap must still honour the
    estimator's per-break override (M1.9 review finding)."""
    formula = """
x = var('X', 1.0, '', number, True, True, True)
COST = x * quantity
"""
    result = ok(
        formula,
        quantity=10,  # break quantity — what the drawer shows and keys by
        eval_context={"quantity": 12},  # make quantity (scrap allowance)
        overrides={"X": {"10": 2.0}},
    )
    assert result.output is not None
    assert result.output["COST"] == 24.0  # override applied x make qty
    assert result.applied_overrides == ["X"]


def test_quantity_specific_dynamic_var_freeze_point() -> None:
    formula = """
x = var('X', 0.0, '', number, True, False, True)
x.update(7.0)
x.freeze()
COST = x
"""
    assert cost(formula, quantity=5, overrides={"X": {"5": 2.0}}) == 2.0
    assert cost(formula, quantity=1, overrides={"X": {"5": 2.0}}) == 7.0
