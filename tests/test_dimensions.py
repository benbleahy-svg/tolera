"""Safe dimension-input evaluator (M1.5).

The dimension fields auto-evaluate math (``2.27 + .359``) and typed units
(``1 meter``) — but the input is **untrusted**, so the evaluator is a restricted
arithmetic parser, never ``eval()`` (DECISIONS.md 2026-06-26 "Safe evaluation of
dimension math/unit inputs"). These tests are the permanent security regression
guard: every escape attempt must be rejected.
"""

from __future__ import annotations

import math

import pytest

from app.dimensions import (
    DimensionError,
    evaluate_area,
    evaluate_length,
    evaluate_mass,
    evaluate_volume,
)


# --------------------------------------------------------------------------- #
# Arithmetic auto-evaluation
# --------------------------------------------------------------------------- #
class TestArithmetic:
    def test_math_expression_evaluates(self) -> None:
        # The spec's worked example: "2.27 + .359" auto-evaluates.
        assert evaluate_length("2.27 + .359") == pytest.approx(2.629)

    def test_subtraction_multiplication_division_and_parens(self) -> None:
        assert evaluate_length("(10 - 4) * 2 / 3") == pytest.approx(4.0)

    def test_unary_minus_then_rejected_as_negative_is_caller_concern(self) -> None:
        # The evaluator itself returns the signed result; the domain (non-negative)
        # rule is enforced by the service, not the parser.
        assert evaluate_length("3 - 5") == pytest.approx(-2.0)

    def test_plain_number_string(self) -> None:
        assert evaluate_length("42") == pytest.approx(42.0)

    def test_leading_decimal(self) -> None:
        assert evaluate_length(".5") == pytest.approx(0.5)

    def test_numeric_input_passthrough(self) -> None:
        assert evaluate_length(10) == pytest.approx(10.0)
        assert evaluate_length(2.5) == pytest.approx(2.5)


# --------------------------------------------------------------------------- #
# Units — stored metric, typed unit converts; toggle drives the default unit
# --------------------------------------------------------------------------- #
class TestUnits:
    def test_typed_unit_meter_to_mm(self) -> None:
        assert evaluate_length("1 meter") == pytest.approx(1000.0)

    def test_typed_unit_inch_to_mm(self) -> None:
        assert evaluate_length("1 in") == pytest.approx(25.4)
        assert evaluate_length("2inch") == pytest.approx(50.8)

    def test_typed_unit_with_math(self) -> None:
        assert evaluate_length("1 + 1 cm") == pytest.approx(20.0)  # 2 cm → 20 mm

    def test_default_unit_mm_when_no_unit(self) -> None:
        assert evaluate_length("5") == pytest.approx(5.0)

    def test_default_unit_inch_toggle(self) -> None:
        # The IN/MM toggle is presentation-only: a bare number under the IN toggle is
        # inches, but storage is always metric (mm).
        assert evaluate_length("2", default_unit="in") == pytest.approx(50.8)

    def test_typed_unit_overrides_default(self) -> None:
        # An explicit unit beats the toggle default.
        assert evaluate_length("10 mm", default_unit="in") == pytest.approx(10.0)


class TestAreaVolumeMass:
    def test_area_applies_squared_factor(self) -> None:
        assert evaluate_area("1 in") == pytest.approx(645.16)  # 25.4**2
        assert evaluate_area("2 * 3") == pytest.approx(6.0)  # mm²

    def test_volume_applies_cubed_factor(self) -> None:
        assert evaluate_volume("1 cm") == pytest.approx(1000.0)  # 10**3
        assert evaluate_volume("10") == pytest.approx(10.0)  # mm³

    def test_mass_units(self) -> None:
        assert evaluate_mass("1 kg") == pytest.approx(1000.0)  # → g
        assert evaluate_mass("2") == pytest.approx(2.0)  # default g
        assert evaluate_mass("1 lb") == pytest.approx(453.592, rel=1e-4)


# --------------------------------------------------------------------------- #
# Security matrix — every escape attempt must be rejected (NEVER eval())
# --------------------------------------------------------------------------- #
class TestSecurity:
    @pytest.mark.parametrize(
        "attack",
        [
            "__import__('os')",
            "__import__('os').system('id')",
            "().__class__.__bases__",
            "(1).__class__",
            "open('/etc/passwd')",
            "eval('1+1')",
            "exec('x=1')",
            "len([1,2,3])",
            "foo",  # bare name
            "foo + 1",
            "x = 1",  # assignment (statement → not an expression)
            "import os",  # statement
            "1; 2",  # multiple statements
            "1 if True else 2",  # conditional expression
            "[1, 2, 3]",  # list
            "{1: 2}",  # dict
            "(1, 2)",  # tuple
            "lambda: 1",
            "1 .__class__",
            "'a' * 3",  # string op
            "f'{1}'",  # f-string
            "2,5",  # German decimal comma → tuple, rejected (not silently misread)
            "1\x002",  # null byte → ast.parse ValueError, must map to DimensionError
            "(" * 200 + "1" + ")" * 200,  # deeply nested / over-long → must not escape as 500
            "",  # empty
            "   ",  # whitespace only
        ],
    )
    def test_rejects_non_arithmetic(self, attack: str) -> None:
        with pytest.raises(DimensionError):
            evaluate_length(attack)

    def test_rejects_power_operator(self) -> None:
        # ** is blocked outright — it enables cheap astronomical results (DoS).
        with pytest.raises(DimensionError):
            evaluate_length("10 ** 100")

    def test_rejects_division_by_zero(self) -> None:
        with pytest.raises(DimensionError):
            evaluate_length("1 / 0")

    def test_rejects_unknown_unit(self) -> None:
        with pytest.raises(DimensionError):
            evaluate_length("5 furlongs")

    def test_rejects_nan_inf_tokens(self) -> None:
        for bad in ("nan", "inf", "1 + inf"):
            with pytest.raises(DimensionError):
                evaluate_length(bad)

    def test_result_is_finite(self) -> None:
        # Sanity: a normal result is a finite float.
        assert math.isfinite(evaluate_length("3 * 3"))
