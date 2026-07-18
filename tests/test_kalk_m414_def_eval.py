"""Tests for M4.14 — def-level Kalk evaluation against the synthetic context
(pure layer, no DB; the endpoint/API layer is ``test_opdef_variables_m414``).

Covers: declared variables (plain + quantity-specific + drop-down) with
defaults and ``default_visible``; the visibility overlay (the def editor's
eye toggles) including stale-key tolerance; formula errors returned as
positioned error dicts (never raised); the documented synthetic ``part``
answering every catalog attribute a formula may read; ``table_var`` against
an injected provider.
"""

from __future__ import annotations

from typing import Any

from app.services.kalk import MappingTableProvider
from app.services.kalk.synthetic import (
    apply_visibility_overlay,
    evaluate_def_formula,
    synthetic_part_object,
)

FORMULA = """
rate = var('Stundensatz', 60, 'EUR/hr', default_visible=True)
hidden = var('Ruestfaktor', 1.5, '', default_visible=False)
per_qty = var('Minuten pro Teil', 6, '', quantity_specific=True)
COST = rate * per_qty / 60 * quantity
DAYS = 0
"""


def _by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {v["name"]: v for v in report["declared_variables"]}


class TestEvaluateDefFormula:
    def test_declared_variables_with_defaults_and_visibility(self) -> None:
        report = evaluate_def_formula(FORMULA, def_name="Fräsen")
        assert report["errors"] == []
        variables = _by_name(report)
        assert variables["Stundensatz"]["default"] == 60
        assert variables["Stundensatz"]["default_visible"] is True
        assert variables["Ruestfaktor"]["default_visible"] is False
        assert variables["Minuten pro Teil"]["quantity_specific"] is True

    def test_visibility_overlay_wins_over_formula_default(self) -> None:
        report = evaluate_def_formula(
            FORMULA,
            def_name="Fräsen",
            visibility={"Stundensatz": False, "Ruestfaktor": True},
        )
        variables = _by_name(report)
        assert variables["Stundensatz"]["default_visible"] is False
        assert variables["Ruestfaktor"]["default_visible"] is True
        # untouched vars keep the formula's declaration
        assert variables["Minuten pro Teil"]["default_visible"] is True

    def test_stale_visibility_keys_are_ignored(self) -> None:
        report = evaluate_def_formula(FORMULA, def_name="Fräsen", visibility={"weg": False})
        assert report["errors"] == []
        assert "weg" not in _by_name(report)

    def test_runtime_error_reports_never_raises(self) -> None:
        report = evaluate_def_formula("x = var('x', 1)\nCOST = 1 / 0\nDAYS = 0", def_name="Fräsen")
        assert report["errors"], "a runtime error must surface in the report"
        assert report["errors"][0]["code"] == "runtime_error"
        assert report["errors"][0]["line"] is not None
        # declarations made before the error still enumerate
        assert "x" in _by_name(report)

    def test_syntax_error_reports_positioned(self) -> None:
        report = evaluate_def_formula("COST = (", def_name="Fräsen")
        assert report["errors"][0]["code"] == "syntax"
        assert report["errors"][0]["line"] is not None

    def test_part_attributes_are_all_readable(self) -> None:
        # every catalog attribute the quote-side part object carries must
        # resolve on the synthetic part too — a def formula must never hit
        # forbidden_attribute for a name that works on a real quote
        attrs = synthetic_part_object().attrs
        reads = "\n".join(f"v{i} = part.{name}" for i, name in enumerate(attrs))
        report = evaluate_def_formula(f"{reads}\nCOST = 1\nDAYS = 0", def_name="Fräsen")
        assert report["errors"] == []

    def test_geometry_is_metric_and_consistent(self) -> None:
        part = synthetic_part_object().attrs
        assert part["size_x"] * part["size_y"] * part["size_z"] == part["volume"]  # mm³
        assert part["max_dim"] >= part["med_dim"] >= part["min_dim"]
        assert part["quantities"] == [1]

    def test_table_var_uses_injected_provider(self) -> None:
        provider = MappingTableProvider({})
        report = evaluate_def_formula(
            "r = table_var('Satz', '', 'saetze', create_filter('dicke', '>', 1))\n"
            "COST = 1\nDAYS = 0",
            def_name="Laser",
            table_provider=provider,
        )
        # unknown table on an empty provider is an evaluation error in the
        # report, not an exception
        assert report["errors"], "an unknown table must produce an evaluation error"
        assert all(isinstance(e["code"], str) for e in report["errors"])

    def test_manual_nest_is_callable_and_unnested(self) -> None:
        from app.services.kalk.synthetic import unnested_nest_object

        report = evaluate_def_formula(
            "n = manual_nest()\nnested = var('n', 0)\nCOST = n.sheet_cost\nDAYS = 0",
            def_name="Laser",
        )
        assert report["errors"] == []
        assert unnested_nest_object().attrs["nested"] is False

    def test_synthetic_part_matches_quote_side_attribute_set(self) -> None:
        # drift guard: the synthetic part must carry exactly the attributes
        # the quote-side part object exposes (build_part_object) — a formula
        # valid on a real quote must never hit forbidden_attribute here
        from app.kalk_costing import KalkEnv, build_part_object
        from app.models import Component, ObtainMethod, Part
        from app.services.kalk import MappingTableProvider

        env = KalkEnv(
            provider=MappingTableProvider({}),
            part=Part(part_number="X", revision=None),
            geometry=None,
            material=None,
            material_family=None,
            component=Component(
                is_root_component=True,
                is_assembly=False,
                obtain_method=ObtainMethod.manufactured,
            ),
            export_controlled=False,
            quantities=[1],
            make_quantities=[1],
        )
        quote_side = set(build_part_object(env, 1, 1).attrs)
        assert set(synthetic_part_object().attrs) == quote_side


class TestApplyVisibilityOverlay:
    def test_overlay_copies_rather_than_mutates(self) -> None:
        declared = [{"name": "a", "default_visible": True}]
        out = apply_visibility_overlay(declared, {"a": False})
        assert out[0]["default_visible"] is False
        assert declared[0]["default_visible"] is True

    def test_none_visibility_is_a_noop(self) -> None:
        declared = [{"name": "a", "default_visible": True}]
        assert apply_visibility_overlay(declared, None) == declared
