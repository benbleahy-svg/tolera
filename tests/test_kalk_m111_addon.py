"""Kalk ``add_on`` context (M1.11) — KALK-REFERENCE §11.4, KB
``add-ons-p3l-cheat-sheet``.

Output ``PRICE`` (finite, >= 0 — a negative add-on would be a hidden
discount, mirroring the discount-positivity rule). Surface = the operation
context **minus** ``no_quote()`` / ``analyze_*()`` / ``set_operation_name()``
**plus** ``set_add_on_name(name)``, ``set_is_required(bool)`` and
``get_price_value(key)`` with the ``--required_add_on--`` /
``--non_required_add_on--`` accumulators (§7 price dictionary).
"""

from __future__ import annotations

from app.services.kalk import ContextData, KalkObject, check, evaluate


def _part(**attrs: object) -> KalkObject:
    base: dict[str, object] = {"part_number": "P-1", "material": "1.4301", "qty": 5}
    base.update(attrs)
    return KalkObject("part", base)


def test_add_on_price_output() -> None:
    result = evaluate("PRICE = 100", context_type="add_on", quantity=5)
    assert result.errors == []
    assert result.output == {"PRICE": 100.0}


def test_add_on_price_must_be_a_finite_non_negative_number() -> None:
    result = evaluate("PRICE = -5", context_type="add_on", quantity=1)
    assert any(e.code == "invalid_output" for e in result.errors)
    result = evaluate("PRICE = 'free'", context_type="add_on", quantity=1)
    assert any(e.code == "invalid_output" for e in result.errors)
    result = evaluate("x = 1", context_type="add_on", quantity=1)
    assert any(e.code == "invalid_output" for e in result.errors)


def test_set_add_on_name_and_set_is_required_are_captured() -> None:
    result = evaluate(
        "set_add_on_name('FAI - ' + str(part.part_number))\n"
        "set_is_required(part.qty > 1)\n"
        "PRICE = 100",
        context_type="add_on",
        eval_context={"part": _part()},
        quantity=5,
    )
    assert result.errors == []
    assert result.add_on_name == "FAI - P-1"
    assert result.add_on_is_required is True


def test_set_is_required_default_is_none() -> None:
    # absent set_is_required, the row's configured default governs (KB)
    result = evaluate("PRICE = 1", context_type="add_on", quantity=1)
    assert result.add_on_is_required is None
    assert result.add_on_name is None


def test_get_price_value_reads_the_price_dictionary() -> None:
    data = ContextData(
        price_values={
            "Tooling": 250.0,
            "--required_add_on--": 350.0,
            "--non_required_add_on--": 25.0,
        }
    )
    result = evaluate(
        "PRICE = get_price_value('Tooling') + get_price_value('--required_add_on--')",
        context_type="add_on",
        quantity=1,
        context_data=data,
    )
    assert result.errors == []
    assert result.output == {"PRICE": 600.0}
    # unknown key sums nothing (P3L parity with get_cost_value)
    result = evaluate("PRICE = get_price_value('missing')", context_type="add_on", quantity=1)
    assert result.output == {"PRICE": 0.0}


def test_minimum_order_pattern() -> None:
    # KB: "enforce things like minimum order item prices"
    data = ContextData(price_values={"--required_add_on--": 120.0})
    result = evaluate(
        "PRICE = max(0, 500 - get_price_value('--required_add_on--'))",
        context_type="add_on",
        quantity=1,
        context_data=data,
    )
    assert result.output == {"PRICE": 380.0}


def test_operation_only_names_are_rejected_in_add_on_context() -> None:
    # KB-exact exclusions: no_quote, analyze_*, set_operation_name
    for formula in (
        "no_quote()\nPRICE = 1",
        "analyze_mill3()\nPRICE = 1",
        "set_operation_name('x')\nPRICE = 1",
    ):
        result = evaluate(formula, context_type="add_on", quantity=1)
        assert result.errors, formula
    # static check flags them too
    assert check("no_quote()\nPRICE = 1", context_type="add_on").errors


def test_operation_functions_are_available() -> None:
    # "all functions specified in the Operation P3L Cheat Sheet" minus the three
    data = ContextData(cost_values={"--total--": 200.0})
    result = evaluate(
        "set_notes('cert included')\nPRICE = 0.1 * get_cost_value('--total--')",
        context_type="add_on",
        quantity=1,
        context_data=data,
    )
    assert result.errors == []
    assert result.output == {"PRICE": 20.0}
    assert result.notes == "cert included"


def test_check_accepts_add_on_context() -> None:
    assert check("PRICE = var('Fee', 100)", context_type="add_on").errors == []
