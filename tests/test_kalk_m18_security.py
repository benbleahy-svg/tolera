"""M1.8 — Kalk sandbox security escape matrix.

Permanent regression guard (build-plan M1.8: "security test matrix … become
permanent regression guards"). Every case is an attempted sandbox escape or a
resource-exhaustion attack; each must be rejected cleanly — a typed
``KalkError``, never an unhandled exception, never a traceback leaked into an
error message, never a side effect.

Isolation boundary decision: DECISIONS.md [2026-07-08] — in-process
restricted-AST evaluator (v1) behind an executor seam.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.services.kalk import KalkError, Limits, check, evaluate


def eval_errors(formula: str, **kwargs: Any) -> list[KalkError]:
    result = evaluate(formula, context_type="operation_cost", **kwargs)
    assert result.errors, f"expected errors for: {formula!r}"
    return result.errors


def error_codes(formula: str, **kwargs: Any) -> set[str]:
    return {e.code for e in eval_errors(formula, **kwargs)}


# ---------------------------------------------------------------------------
# Static rejection — forbidden syntax (caught by check(), before execution)
# ---------------------------------------------------------------------------

FORBIDDEN_SYNTAX = [
    # imports
    "import os\nCOST = 1",
    "from os import path\nCOST = 1",
    # function/class definition
    "def f():\n    return 1\nCOST = f()",
    "class A:\n    pass\nCOST = 1",
    # while loops (unbounded iteration class removed from the grammar)
    "while True:\n    COST = 1",
    # comprehensions (all four)
    "COST = sum([x for x in quantities])",
    "COST = sum({x for x in quantities})",
    "d = {x: 1 for x in quantities}\nCOST = 1",
    "g = (x for x in quantities)\nCOST = 1",
    # container literals outside list/tuple
    "s = {1, 2}\nCOST = 1",
    "d = {'a': 1}\nCOST = 1",
    # statements outside the subset
    "try:\n    COST = 1\nexcept Exception:\n    COST = 2",
    "raise ValueError('x')",
    "assert 1 == 1\nCOST = 1",
    "with q:\n    COST = 1",
    "global x\nCOST = 1",
    "del x\nCOST = 1",
    # subscripts (banned in v1 — P3LList methods arrive in M1.9)
    "COST = quantities[0]",
    # f-strings ('{}'.format is the documented path)
    "COST = 1\nname = f'{COST}'",
    # walrus / ternary
    "COST = (x := 1)",
    "COST = 1 if quantity > 5 else 2",
    # operators outside the documented set (* / + - ** only)
    "COST = 7 % 3",
    "COST = 7 // 3",
    "COST = 1 & 2",
    "COST = 1 | 2",
    "COST = 1 ^ 2",
    "COST = 1 << 2",
    "COST = ~1",
    # attribute assignment
    "quantity.x = 1\nCOST = 1",
    # starred
    "COST = min(*quantities)",
    # bytes literal
    "b = b'x'\nCOST = 1",
]


@pytest.mark.parametrize("formula", FORBIDDEN_SYNTAX)
def test_forbidden_syntax_rejected_at_check(formula: str) -> None:
    result = check(formula, extra_names=("quantities", "q", "x"))
    assert not result.ok
    assert result.errors


@pytest.mark.parametrize("formula", FORBIDDEN_SYNTAX)
def test_forbidden_syntax_rejected_at_evaluate(formula: str) -> None:
    codes = error_codes(
        formula,
        eval_context={"quantities": [1, 2], "q": 1, "x": 1},
    )
    assert codes  # rejected before execution
    assert "missing_output" not in codes or len(codes) > 1


# ---------------------------------------------------------------------------
# Static rejection — dunder / underscore reach and unknown names
# ---------------------------------------------------------------------------

UNDERSCORE_REACH = [
    "COST = __import__('os').getpid()",
    "__builtins__['open']('/etc/passwd')",
    "COST = ().__class__.__mro__",
    "COST = (1).__class__",
    "COST = 'x'.__class__.__bases__",
    "f = lambda: __import__('os')\nCOST = 1",
    "COST = quantity.__dict__",
]


@pytest.mark.parametrize("formula", UNDERSCORE_REACH)
def test_underscore_reach_blocked(formula: str) -> None:
    result = check(formula)
    assert not result.ok
    codes = {e.code for e in result.errors}
    assert codes & {"forbidden_name", "forbidden_attribute", "forbidden_node"}


DANGEROUS_UNKNOWN_NAMES = [
    "COST = exec('1')",
    "COST = eval('1')",
    "COST = open('/tmp/kalk-escape', 'w')",
    "COST = compile('1', '<s>', 'eval')",
    "COST = getattr(quantity, 'to_bytes')",
    "COST = setattr(quantity, 'x', 1)",
    "COST = globals()",
    "COST = locals()",
    "COST = vars()",
    "COST = input()",
    "COST = breakpoint()",
    "COST = type(1)",
    "COST = object()",
    "COST = memoryview(b'')",
    "COST = mystery_name",
]


@pytest.mark.parametrize("formula", DANGEROUS_UNKNOWN_NAMES)
def test_dangerous_names_unknown_at_check(formula: str) -> None:
    """None of these names exist in the Kalk namespace — check() flags them
    statically so the editor CHECK button catches them before execution."""
    result = check(formula)
    assert not result.ok
    codes = {e.code for e in result.errors}
    assert "unknown_name" in codes or codes & {"forbidden_name", "forbidden_node"}


def test_open_has_no_side_effect(tmp_path: Path) -> None:
    target = tmp_path / "escape.txt"
    result = evaluate(
        f"COST = open('{target}', 'w')",
        context_type="operation_cost",
    )
    assert result.errors
    assert not target.exists()


# ---------------------------------------------------------------------------
# Resource exhaustion — default caps must catch the canonical bombs
# ---------------------------------------------------------------------------


def test_pow_tower_blocked() -> None:
    # 10 ** 10 ** 10: inner pow is fine, outer exponent (1e10) exceeds the cap.
    # Un-interruptible C-level bigint pow is exactly why the operand guard exists.
    assert "resource_limit" in error_codes("COST = 10 ** 10 ** 10")


def test_large_int_pow_blocked() -> None:
    assert "resource_limit" in error_codes("COST = 2 ** 5000")


def test_bigint_growth_blocked() -> None:
    # doubling loop: 2**512 stays under the exponent cap but repeated
    # squaring must hit the numeric-magnitude cap, not hang.
    formula = "x = 2 ** 100\nfor i in (1, 2, 3, 4, 5):\n    x = x * x\nCOST = 1"
    assert "resource_limit" in error_codes(formula)


def test_string_repetition_bomb_blocked() -> None:
    assert "resource_limit" in error_codes("s = 'a' * 999999\nCOST = 1")


def test_list_repetition_bomb_blocked() -> None:
    assert "resource_limit" in error_codes("l = (0,) * 99999999\nCOST = 1")


def test_string_concat_bomb_blocked() -> None:
    formula = (
        "s = 'aaaaaaaaaaaaaaaa'\n"
        "for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):\n"
        "    s = s + s\n"
        "COST = 1"
    )
    assert "resource_limit" in error_codes(formula)


def test_format_padding_bomb_blocked() -> None:
    assert "resource_limit" in error_codes("s = '{:>999999999}'.format('x')\nCOST = 1")


def test_iteration_budget_enforced() -> None:
    formula = "x = 0\nfor i in (0,) * 2000:\n    x = x + 1\nCOST = x"
    codes = error_codes(formula, limits=Limits(op_budget=1000))
    assert "resource_limit" in codes


def test_per_loop_iteration_cap_enforced() -> None:
    formula = "x = 0\nfor i in (0,) * 200:\n    x = x + 1\nCOST = x"
    codes = error_codes(formula, limits=Limits(max_loop_iterations=100))
    assert "resource_limit" in codes


def test_wall_clock_deadline_enforced() -> None:
    formula = "x = 0\nfor i in (0,) * 50000:\n    x = x + i + i + i + i\nCOST = x"
    codes = error_codes(formula, limits=Limits(deadline_seconds=0.0001))
    assert "timeout" in codes or "resource_limit" in codes


def test_nonfinite_literal_rejected() -> None:
    result = check("COST = 9e999")
    assert not result.ok


def test_float_overflow_rejected_at_runtime() -> None:
    assert "resource_limit" in error_codes("COST = 1e308 * 1e308")


def test_huge_source_rejected() -> None:
    formula = "# " + "a" * 200_000 + "\nCOST = 1"
    result = check(formula)
    assert not result.ok
    assert {e.code for e in result.errors} & {"source_too_large"}


def test_deep_nesting_rejected_cleanly() -> None:
    formula = "COST = " + "(" * 300 + "1" + ")" * 300
    result = check(formula)  # must not crash the process
    assert not result.ok


def test_many_nodes_rejected() -> None:
    formula = "COST = " + " + ".join(["1"] * 60_000)
    result = check(formula)
    assert not result.ok


def test_lambda_self_recursion_bounded() -> None:
    # unbounded recursion is only reachable via lambda self-application;
    # the interpreter recursion limit bounds it and the error stays clean.
    formula = "f = lambda g: g(g)\nCOST = f(f)"
    result = evaluate(formula, context_type="operation_cost")
    assert result.errors
    assert all("Traceback" not in e.message for e in result.errors)


# ---------------------------------------------------------------------------
# Error hygiene — no tracebacks, ever
# ---------------------------------------------------------------------------

ALL_ATTACKS = (
    FORBIDDEN_SYNTAX
    + UNDERSCORE_REACH
    + DANGEROUS_UNKNOWN_NAMES
    + [
        "COST = 10 ** 10 ** 10",
        "COST = 1 / 0",
        "s = 'a' * 999999\nCOST = 1",
        "f = lambda g: g(g)\nCOST = f(f)",
    ]
)


@pytest.mark.parametrize("formula", ALL_ATTACKS)
def test_no_traceback_in_errors(formula: str) -> None:
    result = evaluate(
        formula,
        context_type="operation_cost",
        eval_context={"quantities": [1, 2], "q": 1, "x": 1},
    )
    assert result.errors
    for err in result.errors:
        assert "Traceback" not in err.message
        assert 'File "' not in err.message
