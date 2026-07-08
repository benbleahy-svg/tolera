"""M1.8 — Kalk evaluator contract: check/evaluate, toy operation-cost context,
variable freeze semantics, declaration-placement constraint.

Spec: #kalk-exec evaluator contract; KALK-REFERENCE §2 (subset), §3 (variables,
frozen=True/False, declarations-not-in-loops).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.kalk import EvalResult, check, evaluate

TOY_FORMULA = """
COST = setup_time * rate + runtime * make_quantity * rate
DAYS = 3
"""

TOY_CONTEXT = {
    "setup_time": 1.0,
    "runtime": 0.25,
    "rate": 60.0,
    "make_quantity": 10,
}


def ok_eval(formula: str, **kwargs: Any) -> EvalResult:
    kwargs.setdefault("context_type", "operation_cost")
    result = evaluate(formula, **kwargs)
    assert not result.errors, result.errors
    return result


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


def test_check_accepts_valid_formula() -> None:
    result = check(TOY_FORMULA, extra_names=TOY_CONTEXT.keys())
    assert result.ok
    assert result.errors == []


def test_check_reports_syntax_error_with_position() -> None:
    result = check("COST = = 1")
    assert not result.ok
    err = result.errors[0]
    assert err.code == "syntax"
    assert err.line == 1
    assert "Traceback" not in err.message


def test_check_unknown_name_positions() -> None:
    result = check("x = 1\nCOST = x + missing_rate")
    assert not result.ok
    err = next(e for e in result.errors if e.code == "unknown_name")
    assert err.line == 2
    assert "missing_rate" in err.message


# ---------------------------------------------------------------------------
# evaluate() — toy operation-cost context
# ---------------------------------------------------------------------------


def test_toy_operation_cost_formula() -> None:
    result = ok_eval(TOY_FORMULA, eval_context=TOY_CONTEXT, quantity=10)
    assert result.output == {"COST": 210.0, "DAYS": 3, "no_quote": False}


def test_quantity_available_as_global() -> None:
    result = ok_eval("COST = quantity * 2.0", quantity=7)
    assert result.output is not None
    assert result.output["COST"] == 14.0


def test_days_defaults_to_zero() -> None:
    result = ok_eval("COST = 5")
    assert result.output is not None
    assert result.output["DAYS"] == 0


def test_missing_cost_is_error() -> None:
    result = evaluate("x = 1", context_type="operation_cost")
    assert {e.code for e in result.errors} == {"missing_output"}
    assert result.output is None


@pytest.mark.parametrize(
    "formula",
    ["COST = 'abc'", "COST = True", "COST = None", "DAYS = 2.5\nCOST = 1"],
)
def test_invalid_output_types_rejected(formula: str) -> None:
    result = evaluate(formula, context_type="operation_cost")
    assert "invalid_output" in {e.code for e in result.errors}


def test_integral_float_days_coerced() -> None:
    result = ok_eval("COST = 1\nDAYS = 2.0")
    assert result.output is not None
    assert result.output["DAYS"] == 2
    assert isinstance(result.output["DAYS"], int)


def test_no_quote() -> None:
    result = ok_eval("no_quote()")
    assert result.output is not None
    assert result.output["no_quote"] is True
    assert result.output["COST"] is None


def test_operation_name_and_notes() -> None:
    result = ok_eval("set_operation_name('Fräsen 3-Achs')\nset_notes('checked')\nCOST = 1")
    assert result.operation_name == "Fräsen 3-Achs"
    assert result.notes == "checked"


def test_unsupported_context_rejected() -> None:
    result = evaluate("PRICE = 1", context_type="add_on")
    assert "invalid_context" in {e.code for e in result.errors}


def test_runtime_error_sanitized() -> None:
    result = evaluate("COST = 1 / 0", context_type="operation_cost")
    err = next(e for e in result.errors if e.code == "runtime_error")
    assert "Traceback" not in err.message
    assert err.line == 1


def test_bankers_rounding_p3l_parity() -> None:
    result = ok_eval("COST = round(2.5)\nDAYS = 0")
    assert result.output is not None
    assert result.output["COST"] == 2.0


def test_builtins_available() -> None:
    result = ok_eval(
        "a = min(3, 1, 2)\n"
        "b = max((4, 9))\n"
        "c = mean(2, 4)\n"
        "d = median((1, 2, 3))\n"
        "e = abs(0 - 5)\n"
        "f = sum((1.5, 2.5))\n"
        "g = floor(2.9)\n"
        "h = ceil(2.1)\n"
        "i = str(42)\n"
        "j = split('Alu 6061', ' ')\n"
        "COST = a + b + c + d + e + f + g + h"
    )
    assert result.output is not None
    assert result.output["COST"] == 1 + 9 + 3 + 2 + 5 + 4.0 + 2 + 3


def test_string_format_and_split_and_membership() -> None:
    result = ok_eval(
        "parts = material.split(' ')\n"
        "label = '{}|{}'.format(quantity, material)\n"
        "COST = 1.0\n"
        "if 'Titan' in material:\n"
        "    COST = 2.0\n"
        "set_notes(label)",
        eval_context={"material": "Titan Grade 5"},
        quantity=3,
    )
    assert result.output is not None
    assert result.output["COST"] == 2.0
    assert result.notes == "3|Titan Grade 5"


# ---------------------------------------------------------------------------
# Variables — frozen=True/False semantics (KALK-REFERENCE §3)
# ---------------------------------------------------------------------------


def test_var_default_and_declaration_recorded() -> None:
    result = ok_eval("rate = var('Rate', 55.0, 'EUR/h', number)\nCOST = rate")
    assert result.output is not None
    assert result.output["COST"] == 55.0
    assert result.applied_overrides == []
    [decl] = result.declared_variables
    assert decl["name"] == "Rate"
    assert decl["value_type"] == "number"
    assert decl["frozen"] is True
    assert decl["value"] == 55.0


def test_frozen_var_override_applied_at_declaration() -> None:
    result = ok_eval(
        "rate = var('Rate', 55.0, 'EUR/h', number)\nCOST = rate",
        overrides={"Rate": 80.0},
    )
    assert result.output is not None
    assert result.output["COST"] == 80.0
    assert result.applied_overrides == ["Rate"]


def test_var_type_enforced() -> None:
    result = evaluate(
        "rate = var('Rate', 'not-a-number', '', number)\nCOST = 1",
        context_type="operation_cost",
    )
    assert result.errors
    result = evaluate(
        "rate = var('Rate', 10.0, '', number)\nCOST = rate",
        context_type="operation_cost",
        overrides={"Rate": "abc"},
    )
    assert result.errors


def test_dynamic_var_update_then_freeze() -> None:
    result = ok_eval(
        "size = var('Size', 0, '', number, frozen=False)\n"
        "size.update(max(dims))\n"
        "size.update(max(dims) + 1.0)\n"
        "size.freeze()\n"
        "COST = size * 2",
        eval_context={"dims": [10.0, 30.0, 20.0]},
    )
    assert result.output is not None
    assert result.output["COST"] == 62.0


def test_dynamic_var_override_wins_at_freeze_point() -> None:
    """UI overrides apply at the freeze point — every update is discarded."""
    result = ok_eval(
        "size = var('Size', 0, '', number, frozen=False)\n"
        "size.update(999.0)\n"
        "size.freeze()\n"
        "COST = size",
        overrides={"Size": 42.0},
    )
    assert result.output is not None
    assert result.output["COST"] == 42.0
    assert result.applied_overrides == ["Size"]


def test_dynamic_var_use_before_freeze_is_error() -> None:
    result = evaluate(
        "size = var('Size', 0, '', number, frozen=False)\nCOST = size * 2",
        context_type="operation_cost",
    )
    assert result.errors


def test_dynamic_var_update_after_freeze_is_error() -> None:
    result = evaluate(
        "size = var('Size', 0, '', number, frozen=False)\n"
        "size.freeze()\n"
        "size.update(1.0)\n"
        "COST = 1",
        context_type="operation_cost",
    )
    assert result.errors


def test_cost_may_be_frozen_dynamic_var() -> None:
    result = ok_eval(
        "c = var('C', 0, '', number, frozen=False)\nc.update(12.5)\nc.freeze()\nCOST = c"
    )
    assert result.output is not None
    assert result.output["COST"] == 12.5


# ---------------------------------------------------------------------------
# Declarations-not-in-blocks (all five declaration names, structural)
# ---------------------------------------------------------------------------

DECLARATION_IN_BLOCK = [
    "if quantity > 1:\n    x = var('X', 1, '', number)\nCOST = 1",
    "if quantity > 1:\n    pass\nelse:\n    x = var('X', 1, '', number)\nCOST = 1",
    "for i in (1, 2):\n    x = var('X', 1, '', number)\nCOST = 1",
    "for i in (1, 2):\n    t = table_var('T', '', 'tbl', f, o, 'col')\nCOST = 1",
    "if quantity > 1:\n    t = table_lookup('tbl', f, o)\nCOST = 1",
    "if quantity > 1:\n    g = variable_group('G')\nCOST = 1",
    "for i in (1, 2):\n    d = drop_down_var('D', 1, opts, '', number)\nCOST = 1",
]


@pytest.mark.parametrize("formula", DECLARATION_IN_BLOCK)
def test_declaration_in_block_rejected(formula: str) -> None:
    result = check(formula, extra_names=("f", "o", "opts"))
    assert not result.ok
    assert "declaration_in_block" in {e.code for e in result.errors}


def test_declaration_at_top_level_inside_lambda_arg_ok() -> None:
    # lambdas are admitted grammar (inert until M1.9 P3LList); a declaration
    # *call* inside one must still be rejected.
    result = check("x = var('X', 1, '', number)\nCOST = x")
    assert result.ok
    result = check("f = lambda: var('X', 1, '', number)\nCOST = 1")
    assert not result.ok
    assert "declaration_in_block" in {e.code for e in result.errors}
