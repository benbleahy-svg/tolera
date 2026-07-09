"""M1.9 — Kalk lists: create_list/P3LList method surface, multi-sort, iterate.

Spec ``#kalk-lists``; KALK-REFERENCE §4. Everything runs through evaluate()
— the formula-level contract, not the Python one.
"""

from __future__ import annotations

from typing import Any

from app.services.kalk import EvalResult, evaluate


def ok(formula: str, **kwargs: Any) -> EvalResult:
    result = evaluate(formula, context_type="operation_cost", **kwargs)
    assert not result.errors, result.errors
    return result


def err(formula: str, **kwargs: Any) -> EvalResult:
    result = evaluate(formula, context_type="operation_cost", **kwargs)
    assert result.errors
    return result


def cost(formula: str, **kwargs: Any) -> float:
    result = ok(formula, **kwargs)
    assert result.output is not None
    return float(result.output["COST"])


def test_create_list_and_numeric_builtins() -> None:
    assert cost("COST = sum(create_list(1, 2, 3)) + min(create_list(5, 4))") == 10.0


def test_create_list_copies_another_list() -> None:
    formula = """
a = create_list(1, 2)
b = create_list(a)
b.append(3)
COST = sum(a) * 100 + sum(b)
"""
    assert cost(formula) == 306.0


def test_membership_and_iteration() -> None:
    formula = """
total = 0
names = create_list('bend', 'curl')
for n in iterate(names):
    if n in create_list('bend', 'open_hem'):
        total += 1
COST = total
"""
    assert cost(formula) == 1.0


def test_append_extend_chaining_returns_list() -> None:
    assert cost("COST = sum(create_list(1).append(2).extend(create_list(3, 4)))") == 10.0


def test_pop_defaults_to_index_zero() -> None:
    assert cost("COST = create_list(7, 8, 9).pop()") == 7.0


def test_pop_empty_list_is_clean_error() -> None:
    result = err("COST = create_list().pop()")
    assert result.errors[0].code == "runtime_error"


def test_remove_missing_item_is_clean_error() -> None:
    result = err("COST = sum(create_list(1).remove(2))")
    assert "guard with" in result.errors[0].message


def test_remove_present_item() -> None:
    assert cost("COST = sum(create_list(1, 2, 3).remove(2))") == 4.0


def test_sort_with_lambda_key() -> None:
    assert cost("COST = create_list(3, 1, 2).sort(lambda x: x).pop()") == 1.0


def test_sort_with_multi_sort_descending() -> None:
    # sort by -x → descending; first element is the largest
    assert cost("COST = create_list(3, 1, 2).sort(lambda x: create_multi_sort(-x)).pop()") == 3.0


def test_filter_mutates_in_place() -> None:
    formula = """
xs = create_list(1, 2, 3, 4)
xs.filter(lambda x: x > 2)
COST = sum(xs)
"""
    assert cost(formula) == 7.0


def test_map_returns_new_list() -> None:
    formula = """
xs = create_list(1, 2)
ys = xs.map(lambda x: x * 10)
COST = sum(xs) + sum(ys)
"""
    assert cost(formula) == 33.0


def test_reduce_with_and_without_initial() -> None:
    assert cost("COST = create_list(1, 2, 3).reduce(lambda a, b: a + b)") == 6.0
    assert cost("COST = create_list(1, 2, 3).reduce(lambda a, b: a + b, 10)") == 16.0


def test_reduce_empty_without_initial_is_error() -> None:
    err("COST = create_list().reduce(lambda a, b: a + b)")


def test_unique_keeps_first_of_each_key() -> None:
    formula = """
xs = create_list('bend', 'curl', 'bend')
COST = xs.unique(lambda x: x).reduce(lambda acc, x: acc + 1, 0)
"""
    assert cost(formula) == 2.0


def test_join_builds_notes() -> None:
    formula = """
set_notes(create_list('a', 'b').join(', '))
COST = 0
"""
    assert ok(formula).notes == "a, b"


def test_join_non_string_is_error() -> None:
    err("COST = 0\nx = create_list(1).join(',')")


def test_list_concatenation_stays_kalk_list() -> None:
    formula = """
xs = create_list(1) + create_list(2)
xs.append(3)
COST = sum(xs)
"""
    assert cost(formula) == 6.0


def test_lambda_errors_are_sanitized() -> None:
    result = err("COST = sum(create_list('a').map(lambda x: x * x))")
    assert result.errors[0].code == "runtime_error"
    assert "Traceback" not in result.errors[0].message


def test_reference_example_feature_filtering() -> None:
    """The KALK-REFERENCE §4 shape: filter by name + property, multi-sort."""
    formula = """
lengths = create_list(12.0, 8.0, 30.0, 15.0)
long = lengths.filter(lambda x: x > 10).sort(lambda x: create_multi_sort(-x))
COST = long.pop()
"""
    assert cost(formula) == 30.0
