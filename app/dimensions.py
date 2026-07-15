"""Safe evaluation of manual dimension inputs (M1.5).

Dimension fields auto-evaluate arithmetic (``2.27 + .359``) and typed units
(``1 meter``) — but the input is **untrusted**, so this is a *restricted-AST*
evaluator, never ``eval()`` (DECISIONS.md 2026-06-26). The grammar is deliberately
tiny: numeric literals, ``+ - * /``, parentheses, unary ``+``/``-``, and one
optional trailing unit token. Anything else — names, calls, attribute access,
subscripts, comprehensions, ``**``, strings, statements — is rejected with a
:class:`DimensionError` (mapped to a clean 422 at the API edge).

This is **not** Kalk (M1.8): there are no variables, no functions, no ``part``
object — only the math an estimator types into a length/area/volume/mass box.

Storage is always **metric** (mm / mm² / mm³ / g); the IN/MM toggle is
presentation-only and reaches this module as ``default_unit`` — a bare number is
interpreted in that unit, an explicit typed unit overrides it (DACH units
invariant: the toggle never persists imperial; CLAUDE.md §5).
"""

from __future__ import annotations

import ast
import math
import re

# Length units → millimetres. Keys are lower-cased; ``"`` (inch) and ``'`` (foot)
# symbols are accepted too. Area/volume reuse this table with the factor squared/cubed.
LENGTH_UNITS_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimetre": 1.0,
    "millimeters": 1.0,
    "millimetres": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimetre": 10.0,
    "centimeters": 10.0,
    "centimetres": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "metre": 1000.0,
    "meters": 1000.0,
    "metres": 1000.0,
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    '"': 25.4,
    "ft": 304.8,
    "foot": 304.8,
    "feet": 304.8,
    "'": 304.8,
}

# Mass units → grams.
MASS_UNITS_TO_G: dict[str, float] = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    # Parse-only non-metric tokens: a typed pound value CONVERTS to grams at the
    # edge — storage stays metric (DECISIONS.md 2026-06-26 manual-dims model;
    # CLAUDE.md §5 permits the input toggle, never a non-metric storage path).
    "lb": 453.592,  # nosemgrep: semgrep.imperial-units
    "lbs": 453.592,  # nosemgrep: semgrep.imperial-units
    "pound": 453.592,
    "pounds": 453.592,
    "oz": 28.349523125,
    "ounce": 28.349523125,
}

# A trailing unit token: a run of letters, or a single inch/foot quote symbol.
_UNIT_TOKEN_RE = re.compile(r"""([A-Za-z]+|["'])\s*$""")

# Bound the input so a pathological string can't drive parse cost (deep nesting →
# RecursionError) or smuggle control bytes — a real dimension expression is short.
_MAX_EXPR_LEN = 256

# The only operators the arithmetic grammar permits. ``**`` (Pow) is intentionally
# excluded — it turns a short string into an astronomical result (a cheap DoS).
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)


class DimensionError(ValueError):
    """A dimension input could not be safely evaluated (bad math or a rejected token)."""


def _eval_node(node: ast.AST) -> float:
    """Recursively evaluate one restricted-AST node, rejecting anything outside the grammar."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        # Numeric literals only — reject bool (an int subclass), complex, str, bytes, None.
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise DimensionError("Only numeric values are allowed.")
        return float(node.value)
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise DimensionError("Unsupported operator.")
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        try:
            return left / right
        except ZeroDivisionError as exc:
            raise DimensionError("Division by zero.") from exc
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            raise DimensionError("Unsupported unary operator.")
        operand = _eval_node(node.operand)
        return +operand if isinstance(node.op, ast.UAdd) else -operand
    raise DimensionError(f"Unsupported expression element: {type(node).__name__}.")


def _eval_arithmetic(expr: str) -> float:
    """Parse + evaluate a pure-arithmetic expression. Raises :class:`DimensionError`.

    ``ast.parse`` raises ``ValueError`` (not just ``SyntaxError``) on a null byte, so
    both are caught to keep the rejection contract (DimensionError → 422, never a 500)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise DimensionError("Invalid expression.") from exc
    return _eval_node(tree)


def _split_unit(raw: str, units: dict[str, float]) -> tuple[str, str | None]:
    """Split a trailing **known** unit token off ``raw``.

    Only a recognised unit is stripped — an unknown trailing word is left attached so
    it fails arithmetic parsing (and is rejected) rather than being silently dropped."""
    text = raw.strip()
    match = _UNIT_TOKEN_RE.search(text)
    if match:
        token = match.group(1).lower()
        if token in units:
            return text[: match.start()].strip(), token
    return text, None


def _evaluate(
    raw: str | int | float,
    *,
    units: dict[str, float],
    default_unit: str,
    power: int,
) -> float:
    """Evaluate ``raw`` to a metric base value (``base_unit ** power``).

    ``raw`` may be a number (taken in ``default_unit``) or a string carrying an
    arithmetic expression with an optional trailing unit; an explicit unit overrides
    ``default_unit``. ``power`` is 1 for length/mass, 2 for area, 3 for volume."""
    default = default_unit.lower()
    if default not in units:
        raise DimensionError(f"Unknown default unit: {default_unit}.")

    if isinstance(raw, bool):
        raise DimensionError("Only numeric values are allowed.")
    if isinstance(raw, (int, float)):
        if not math.isfinite(raw):
            raise DimensionError("Value is not a finite number.")
        value, unit = float(raw), None
    elif isinstance(raw, str):
        if len(raw) > _MAX_EXPR_LEN:
            raise DimensionError("Expression too long.")
        expr, unit = _split_unit(raw, units)
        if not expr:
            raise DimensionError("No value provided.")
        value = _eval_arithmetic(expr)
    else:
        raise DimensionError("Unsupported input type.")

    factor = units[unit if unit is not None else default] ** power
    result = value * factor
    if not math.isfinite(result):
        raise DimensionError("Result is not a finite number.")
    return result


def evaluate_length(raw: str | int | float, *, default_unit: str = "mm") -> float:
    """Evaluate a linear dimension to **millimetres**."""
    return _evaluate(raw, units=LENGTH_UNITS_TO_MM, default_unit=default_unit, power=1)


def evaluate_area(raw: str | int | float, *, default_unit: str = "mm") -> float:
    """Evaluate an area to **mm²** (the linear ``default_unit`` factor, squared)."""
    return _evaluate(raw, units=LENGTH_UNITS_TO_MM, default_unit=default_unit, power=2)


def evaluate_volume(raw: str | int | float, *, default_unit: str = "mm") -> float:
    """Evaluate a volume to **mm³** (the linear ``default_unit`` factor, cubed)."""
    return _evaluate(raw, units=LENGTH_UNITS_TO_MM, default_unit=default_unit, power=3)


def evaluate_mass(raw: str | int | float, *, default_unit: str = "g") -> float:
    """Evaluate a mass to **grams**."""
    return _evaluate(raw, units=MASS_UNITS_TO_G, default_unit=default_unit, power=1)
