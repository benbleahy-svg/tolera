"""M1.9 — Kalk custom tables: table_var / table_lookup, filters, TableRow,
TableVariable selection-freeze semantics, caps, determinism.

Spec ``#kalk-tables``; KALK-REFERENCE §5; DECISIONS.md 2026-07-08 (column
types boolean|numeric|string, caps 200/10,000, row_number overrides).
"""

from __future__ import annotations

from typing import Any

from app.services.kalk import EvalResult, canonical_bytes, evaluate
from app.services.kalk.tables import (
    MappingTableProvider,
    TableColumn,
    TableSnapshot,
)


def snap(name: str, columns: list[tuple[str, str]], rows: list[dict[str, Any]]) -> TableSnapshot:
    return TableSnapshot(
        name=name,
        columns=tuple(TableColumn(name=n, type=t) for n, t in columns),
        rows=tuple((i + 1, row) for i, row in enumerate(rows)),
    )


MATERIALS = snap(
    "materials",
    [
        ("material", "string"),
        ("thickness", "numeric"),
        ("price", "numeric"),
        ("difficult", "boolean"),
    ],
    [
        {"material": "Aluminum 6061-T6", "thickness": 2.0, "price": 10.0, "difficult": False},
        {"material": "Aluminum 5052", "thickness": 3.0, "price": 12.0, "difficult": False},
        {"material": "Titanium Grade 5", "thickness": 2.0, "price": 80.0, "difficult": True},
        {"material": "Stainless 304", "thickness": None, "price": 30.0, "difficult": False},
    ],
)

PROVIDER = MappingTableProvider({"materials": MATERIALS})


def run(formula: str, **kwargs: Any) -> EvalResult:
    kwargs.setdefault("table_provider", PROVIDER)
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
# table_var — frozen (default)
# ---------------------------------------------------------------------------

TABLE_VAR = """
row = table_var('Material Row', 'stock row', 'materials',
                create_filter(filter('material', 'contains', 'aluminum')),
                create_order_by('price'), 'material')
COST = row.price
"""


def test_table_var_returns_first_match_in_order() -> None:
    assert cost(TABLE_VAR) == 10.0


def test_table_var_row_number_override_selects_other_row() -> None:
    result = ok(TABLE_VAR, overrides={"Material Row": 2})
    assert result.output is not None
    assert result.output["COST"] == 12.0
    assert result.applied_overrides == ["Material Row"]


def test_table_var_override_outside_matches_is_error() -> None:
    result = run(TABLE_VAR, overrides={"Material Row": 3})  # Titanium doesn't match filter
    assert result.errors
    assert "no longer matches" in result.errors[0].message


def test_table_var_zero_matches_returns_none() -> None:
    formula = """
row = table_var('Material Row', '', 'materials',
                create_filter(filter('material', 'contains', 'inconel')), None, 'material')
COST = 0
if not row:
    COST = -1
"""
    assert cost(formula) == -1.0


def test_table_var_declares_ui_options_with_display_column() -> None:
    result = ok(TABLE_VAR)
    decl = result.declared_variables[0]
    assert decl["kind"] == "table_var"
    assert decl["table_name"] == "materials"
    assert decl["options"] == [
        {"row_number": 1, "display": "Aluminum 6061-T6"},
        {"row_number": 2, "display": "Aluminum 5052"},
    ]
    assert decl["value"] == 1


def test_unknown_table_is_clean_error() -> None:
    result = run("row = table_var('R', '', 'nope', None, None, None)\nCOST = 0")
    assert "no custom table named 'nope'" in result.errors[0].message


def test_unknown_filter_column_is_clean_error() -> None:
    result = run(
        "row = table_var('R', '', 'materials',"
        " create_filter(filter('nope', '=', 1)), None, None)\nCOST = 0"
    )
    assert "no column 'nope'" in result.errors[0].message


def test_condition_type_mismatch_is_clean_error() -> None:
    result = run(
        "row = table_var('R', '', 'materials',"
        " create_filter(filter('price', 'contains', 'x')), None, None)\nCOST = 0"
    )
    assert "does not apply" in result.errors[0].message


def test_declaration_inside_if_is_rejected() -> None:
    result = run("if 1 > 0:\n    row = table_var('R', '', 'materials', None, None, None)\nCOST = 0")
    assert result.errors[0].code == "declaration_in_block"


# ---------------------------------------------------------------------------
# table_lookup + filter matrix
# ---------------------------------------------------------------------------


def count_formula(filters: str) -> str:
    return (
        f"rows = table_lookup('materials', {filters}, None)\n"
        "COST = rows.reduce(lambda acc, r: acc + 1, 0)"
    )


def test_table_lookup_returns_all_matches() -> None:
    assert cost(count_formula("None")) == 4.0


def test_filter_equals() -> None:
    assert cost(count_formula("create_filter(filter('thickness', '=', 2.0))")) == 2.0


def test_filter_boolean_equals() -> None:
    assert cost(count_formula("create_filter(filter('difficult', '=', True))")) == 1.0


def test_filter_range() -> None:
    assert (
        cost(count_formula("create_filter(filter('price', 'range', create_range(10, 30)))")) == 3.0
    )


def test_filter_exclude() -> None:
    assert cost(count_formula("create_filter(exclude('price', '>', 15))")) == 2.0


def test_filters_and_together() -> None:
    filters = "create_filter(filter('material', 'contains', 'aluminum'), filter('price', '>', 11))"
    assert cost(count_formula(filters)) == 1.0


def test_null_cells_never_match() -> None:
    # Stainless has thickness None — no thickness condition can match it
    assert cost(count_formula("create_filter(filter('thickness', '<', 99))")) == 3.0


def test_order_by_descending_and_null_last() -> None:
    formula = """
rows = table_lookup('materials', None, create_order_by('-thickness'))
COST = rows.pop().price
"""
    assert cost(formula) == 12.0  # thickness 3.0 first; Stainless (None) sorts last


def test_range_value_requires_create_range() -> None:
    result = run(count_formula("create_filter(filter('price', 'range', 10))"))
    assert "create_range" in result.errors[0].message


# ---------------------------------------------------------------------------
# TableRow surface
# ---------------------------------------------------------------------------


def test_row_number_and_unknown_column() -> None:
    formula = """
row = table_var('R', '', 'materials', None, None, 'material')
COST = row.row_number
"""
    assert cost(formula) == 1.0
    bad = run("row = table_var('R', '', 'materials', None, None, None)\nCOST = row.nope")
    assert bad.errors[0].code == "forbidden_attribute"


def test_row_to_keys_list_join() -> None:
    formula = """
row = table_var('R', '', 'materials', None, None, None)
set_notes(row.to_keys_list().join(','))
COST = 0
"""
    assert ok(formula).notes == "material,thickness,price,difficult"


def test_row_to_list_key_value_objects() -> None:
    formula = """
row = table_var('R', '', 'materials', None, None, None)
prices = row.to_list().filter(lambda kv: kv.key == 'price').map(lambda kv: kv.value)
COST = sum(prices)
"""
    assert cost(formula) == 10.0


# ---------------------------------------------------------------------------
# TableVariable (frozen=False) — selection is the freeze/override point
# ---------------------------------------------------------------------------

DYNAMIC = """
tv = table_var('Material Row', '', 'materials',
               create_filter(filter('material', 'contains', 'aluminum')),
               create_order_by('price'), 'material', False)
{body}
"""


def test_select_first_and_value() -> None:
    assert cost(DYNAMIC.format(body="tv.select_first()\nCOST = tv.value.price")) == 10.0


def test_select_last() -> None:
    assert cost(DYNAMIC.format(body="tv.select_last()\nCOST = tv.value.price")) == 12.0


def test_select_by_row_number() -> None:
    assert cost(DYNAMIC.format(body="tv.select_by_row_number(2)\nCOST = tv.value.price")) == 12.0


def test_rows_property_is_filterable() -> None:
    body = "tv.select_first()\nCOST = tv.rows.reduce(lambda acc, r: acc + 1, 0)"
    assert cost(DYNAMIC.format(body=body)) == 2.0


def test_value_before_selection_is_error() -> None:
    result = run(DYNAMIC.format(body="COST = tv.value.price"))
    assert "before a select_" in result.errors[0].message


def test_double_selection_is_error() -> None:
    result = run(DYNAMIC.format(body="tv.select_first()\ntv.select_last()\nCOST = 0"))
    assert "selected twice" in result.errors[0].message


def test_override_applies_at_selection_point() -> None:
    result = ok(
        DYNAMIC.format(body="tv.select_first()\nCOST = tv.value.price"),
        overrides={"Material Row": 2},
    )
    assert result.output is not None
    assert result.output["COST"] == 12.0


def test_quantity_specific_table_override() -> None:
    formula = TABLE_VAR.replace("'material')", "'material', True, True)")
    with_qty = ok(formula, quantity=5, overrides={"Material Row": {"5": 2}})
    assert with_qty.output is not None
    assert with_qty.output["COST"] == 12.0
    other_qty = ok(formula, quantity=1, overrides={"Material Row": {"5": 2}})
    assert other_qty.output is not None
    assert other_qty.output["COST"] == 10.0


# ---------------------------------------------------------------------------
# caps + determinism
# ---------------------------------------------------------------------------


def test_table_var_caps_options_at_200() -> None:
    big = snap(
        "big",
        [("n", "numeric")],
        [{"n": float(i)} for i in range(250)],
    )
    result = evaluate(
        "row = table_var('R', '', 'big', None, None, None)\nCOST = row.n",
        context_type="operation_cost",
        table_provider=MappingTableProvider({"big": big}),
    )
    assert not result.errors
    assert len(result.declared_variables[0]["options"]) == 200


def test_table_formula_is_canonically_deterministic() -> None:
    outputs = {canonical_bytes(ok(TABLE_VAR, overrides={"Material Row": 2})) for _ in range(200)}
    assert len(outputs) == 1
