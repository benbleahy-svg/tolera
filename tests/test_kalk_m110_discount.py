"""M1.10 — the Kalk **discount** context (spec ``#costing`` Discounts; the
context table's row: output ``PERCENTAGE`` (positive), adds
``set_discount_name()`` / ``contact`` / ``REQUESTED_QUANTITY`` + the full
variable/list/table/workpiece suite, lacks ``part`` / custom attributes /
``analyze_*()``)."""

from __future__ import annotations

from app.services.kalk.evaluator import check, evaluate
from app.services.kalk.objects import KalkObject


def test_fixed_percentage_evaluates() -> None:
    result = evaluate("PERCENTAGE = 5", context_type="discount")
    assert not result.errors
    assert result.output == {"PERCENTAGE": 5.0}


def test_requested_quantity_and_variables_available() -> None:
    formula = (
        "threshold = var('Threshold', 100, 'break', number)\n"
        "PERCENTAGE = 0\n"
        "if REQUESTED_QUANTITY >= threshold:\n"
        "    PERCENTAGE = 10\n"
    )
    result = evaluate(formula, context_type="discount", quantity=250)
    assert not result.errors
    assert result.output == {"PERCENTAGE": 10.0}
    below = evaluate(formula, context_type="discount", quantity=50)
    assert below.output == {"PERCENTAGE": 0.0}


def test_set_discount_name_and_contact() -> None:
    contact = KalkObject("contact", {"email": "einkauf@fechner.example"})
    formula = (
        "set_discount_name('Treuerabatt')\n"
        "PERCENTAGE = 0\n"
        "if contact and contact.email == 'einkauf@fechner.example':\n"
        "    PERCENTAGE = 5\n"
    )
    result = evaluate(formula, context_type="discount", eval_context={"contact": contact})
    assert not result.errors
    assert result.output == {"PERCENTAGE": 5.0}
    assert result.discount_name == "Treuerabatt"


def test_missing_percentage_is_an_error() -> None:
    result = evaluate("x = 1", context_type="discount")
    assert [e.code for e in result.errors] == ["missing_output"]


def test_negative_percentage_rejected() -> None:
    # the spec fixes discount PERCENTAGE as positive — a sign flip would turn
    # a discount into a hidden surcharge
    result = evaluate("PERCENTAGE = -5", context_type="discount")
    assert [e.code for e in result.errors] == ["invalid_output"]


def test_part_and_analyzers_not_available() -> None:
    # the discount context lacks part / custom attrs / analyzers — CHECK and
    # evaluate must both refuse the names
    for formula in (
        "PERCENTAGE = part.qty",
        "PERCENTAGE = get_custom_attribute('level', 0)",
        "sm = analyze_sheet_metal()\nPERCENTAGE = 0",
    ):
        checked = check(formula, context_type="discount")
        assert not checked.ok, formula
        result = evaluate(formula, context_type="discount")
        assert result.errors, formula


def test_workpiece_suite_available() -> None:
    formula = "set_workpiece_value('k', 3)\nPERCENTAGE = get_workpiece_value('k', 0)\n"
    result = evaluate(formula, context_type="discount")
    assert not result.errors
    assert result.output == {"PERCENTAGE": 3.0}


def test_check_accepts_discount_context() -> None:
    assert check("PERCENTAGE = 5", context_type="discount").ok
