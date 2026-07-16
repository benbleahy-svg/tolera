"""M3.7 — Rules AST evaluator (gated on interrogation state).

The deterministic core behind M3.8's review items (spec ``#rules-engine`` /
``#rules-signals``; RULES-ENGINE-SPEC §4 build note, §8 integration map): given
a component's analyzed data, walk the M3.6 rule AST and decide which rules
match. Review-item creation is M3.8 — this block returns matches only.

The nine §5 worked rules at ``fixtures/rules/worked-rules.json`` are the
golden: each is asserted against a matching and a non-matching component.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.rules_eval import _ISO_GPS_SYMBOLS, EvaluationContext, evaluate_rule, evaluate_rules
from app.rules_schema import RuleSchema, parse_rules_json

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "rules" / "worked-rules.json"


@pytest.fixture(scope="module")
def worked_rules() -> list[RuleSchema]:
    return parse_rules_json(FIXTURE.read_text(encoding="utf-8"))


def rule_named(rules: list[RuleSchema], name: str) -> RuleSchema:
    return next(r for r in rules if r.name == name)


# --------------------------------------------------------------------------- #
# builders — findings carry the M3.1 ExtractionFinding shape
# --------------------------------------------------------------------------- #
def dim(
    value: str,
    *,
    type: str = "length",
    units: str | None = "mm",
    tolerance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "category": "dimensions",
        "type": type,
        "value": value,
        "normalized_value": None,
        "units": units,
        "tolerance": tolerance,
        "raw_text": value,
        "gdt": None,
    }


def frame(symbol: str, value: str, *, datum_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "category": "features",
        "type": "control_frame",
        "value": value,
        "normalized_value": None,
        "units": "mm",
        "tolerance": None,
        "raw_text": f"{symbol} {value}",
        "gdt": {"symbol": symbol, "datum_refs": datum_refs or [], "material_condition": None},
    }


def datum(letter: str) -> dict[str, Any]:
    return {
        "category": "features",
        "type": "datum",
        "value": letter,
        "normalized_value": None,
        "units": None,
        "tolerance": None,
        "raw_text": letter,
        "gdt": None,
    }


def ctx(**overrides: Any) -> EvaluationContext:
    """A benign component: has both files, nothing tight, no interrogation."""
    base: dict[str, Any] = {
        "extractions": [],
        "document_texts": [],
        "part_attributes": {"max_dim": 50.0},
        "files": {"has_model": True, "has_print": True},
        "interrogation_result": None,
    }
    base.update(overrides)
    return EvaluationContext(**base)


# --------------------------------------------------------------------------- #
# 1. the nine §5 worked rules — matching vs non-matching components
# --------------------------------------------------------------------------- #
class TestWorkedRules:
    def test_tight_tolerance_fires_on_tight_bilateral(self, worked_rules: list[RuleSchema]) -> None:
        """The §5 threshold is PP's 5 thou re-unit'd to 0.13 mm (§7)."""
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        loose = ctx(
            extractions=[
                dim("25.0", tolerance={"kind": "bilateral", "upper": "0.5", "lower": "0.5"})
            ]
        )
        assert evaluate_rule(rule, loose) is False, "±0.5 mm is looser than the 0.13 mm threshold"

        tight = ctx(
            extractions=[
                dim("25.0", tolerance={"kind": "bilateral", "upper": "0.05", "lower": "0.05"})
            ]
        )
        assert evaluate_rule(rule, tight) is True

    def test_tight_tolerance_boundary_is_inclusive(self, worked_rules: list[RuleSchema]) -> None:
        """lessThanOrEqual — exactly 0.13 mm fires; a hair over does not."""
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        at = ctx(
            extractions=[
                dim("25.0", tolerance={"kind": "bilateral", "upper": "0.13", "lower": "0.13"})
            ]
        )
        assert evaluate_rule(rule, at) is True
        over = ctx(
            extractions=[
                dim("25.0", tolerance={"kind": "bilateral", "upper": "0.14", "lower": "0.14"})
            ]
        )
        assert evaluate_rule(rule, over) is False

    def test_tight_tolerance_silent_on_clean_component(
        self, worked_rules: list[RuleSchema]
    ) -> None:
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        assert evaluate_rule(rule, ctx(extractions=[dim("25.0")])) is False

    def test_tight_tolerance_fires_via_control_frame(self, worked_rules: list[RuleSchema]) -> None:
        """The rule ORs 17 paths — a tight flatness frame alone must fire it."""
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        assert evaluate_rule(rule, ctx(extractions=[frame("flatness", "0.02")])) is True
        assert evaluate_rule(rule, ctx(extractions=[frame("flatness", "0.5")])) is False

    def test_machine_envelope_via_part_max_dim(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Machine envelope exceeded")
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": 400.0})) is True
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": 100.0})) is False

    def test_machine_envelope_via_greatest_dimension(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Machine envelope exceeded")
        assert evaluate_rule(rule, ctx(extractions=[dim("310")])) is True
        assert evaluate_rule(rule, ctx(extractions=[dim("310"), dim("12")])) is True, (
            "greatest_distance_dimension is the max across dimension findings"
        )
        assert evaluate_rule(rule, ctx(extractions=[dim("12")])) is False

    def test_missing_model_or_print(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Missing model or print")
        # has_print false alone fires (second signal, no text requirement)
        assert evaluate_rule(rule, ctx(files={"has_model": True, "has_print": False})) is True
        # has_model false only fires WITH the MODEL text (first signal is an AND)
        no_model = {"has_model": False, "has_print": True}
        assert evaluate_rule(rule, ctx(files=no_model)) is False
        assert evaluate_rule(rule, ctx(files=no_model, document_texts=["SIEHE MODELL"])) is True, (
            "German keyword 'Modell' is in the rule's keyword list (§7)"
        )
        assert evaluate_rule(rule, ctx()) is False

    def test_finish_keyword_adds_operation(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Finish keyword adds finishing operation")
        assert evaluate_rule(rule, ctx(document_texts=["Oberfläche eloxieren"])) is True
        assert evaluate_rule(rule, ctx(document_texts=["Alle Kanten entgraten"])) is True
        assert evaluate_rule(rule, ctx(document_texts=["Keine Nachbearbeitung"])) is False

    def test_oem_spec_regex(self, worked_rules: list[RuleSchema]) -> None:
        """The §5 rule-7 pattern is line-anchored (``^SPX-…$``) — it matches a
        spec code standing on its own line in a notes block."""
        rule = rule_named(worked_rules, "OEM specification referenced")
        notes = "ALLGEMEINTOLERANZ ISO 2768-m\nSPX-1234-A\nOberfläche geschliffen"
        assert evaluate_rule(rule, ctx(document_texts=[notes])) is True
        assert evaluate_rule(rule, ctx(document_texts=["Nach DIN 7168 fertigen"])) is False
        assert evaluate_rule(rule, ctx(document_texts=["Nach SPX-1234-A fertigen"])) is False, (
            "the anchors are the rule author's intent: a bare spec code, not prose"
        )

    def test_accepted_spec_regex_is_unanchored(self, worked_rules: list[RuleSchema]) -> None:
        """Its §5 pattern carries no anchors, so it matches mid-line prose."""
        rule = rule_named(worked_rules, "Accepted spec detected")
        assert evaluate_rule(rule, ctx(document_texts=["Nach DIN 7168 fertigen"])) is True
        assert evaluate_rule(rule, ctx(document_texts=["Keine Norm angegeben"])) is False

    def test_material_werkstoffnummer_regex(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Material spec vendor pick")
        assert evaluate_rule(rule, ctx(document_texts=["Werkstoff: 1.4301"])) is True
        assert evaluate_rule(rule, ctx(document_texts=["Werkstoff: S235JR"])) is False

    def test_sheet_metal_keyword_sets_process(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Sheet metal keyword assigns process")
        assert evaluate_rule(rule, ctx(document_texts=["Halter Blech 2mm"])) is True
        assert evaluate_rule(rule, ctx(document_texts=["Drehteil aus Rundstahl"])) is False

    def test_evaluate_rules_returns_only_matches(self, worked_rules: list[RuleSchema]) -> None:
        matches = evaluate_rules(worked_rules, ctx(part_attributes={"max_dim": 400.0}))
        assert [m.name for m in matches] == ["Machine envelope exceeded"]

    def test_clean_component_matches_nothing(self, worked_rules: list[RuleSchema]) -> None:
        """The non-matching half of the AC: none of the nine fire on a benign part."""
        assert evaluate_rules(worked_rules, ctx(extractions=[dim("25.0")])) == []


# --------------------------------------------------------------------------- #
# 2. AND/OR combination semantics (§4 "the part everyone gets wrong")
# --------------------------------------------------------------------------- #
class TestCombinationSemantics:
    def test_or_rule_fires_on_any_single_signal(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Machine envelope exceeded")
        assert rule.logical_operator == "OR"
        assert len(rule.signals) == 2
        # only the part signal can match; the dimension signal cannot
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": 400.0})) is True

    def test_and_rule_requires_every_signal(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Part complexity level 3")
        assert rule.logical_operator == "AND"
        complex_ctx = _complexity_context()
        assert evaluate_rule(rule, complex_ctx) is True

        # drop the datums below their threshold — the AND must now fail
        thin = _complexity_context(datum_count=4)
        assert evaluate_rule(rule, thin) is False

    def test_group_queries_and_requires_same_item(self) -> None:
        """AND across a group's queries means ONE item satisfies all of them —
        not "each query matched some item"."""
        rule = _rule(
            logical_operator="OR",
            signals=[
                {
                    "logical_operator": "AND",
                    "groups": [
                        {
                            "document_path": "position_control_frames",
                            "logical_operator": "AND",
                            "count_query": None,
                            "queries": [
                                _query(
                                    ["value"], "lessThanOrEqual", 0.1, "distance", "numeric", "mm"
                                ),
                                _query(
                                    ["datum_count"],
                                    "greaterThanOrEqual",
                                    3,
                                    "number",
                                    "numeric",
                                    None,
                                ),
                            ],
                        }
                    ],
                }
            ],
        )
        # one frame tight but datum-poor, another datum-rich but loose: no
        # single frame satisfies both, so the AND group must not match.
        split = ctx(
            extractions=[
                frame("position", "0.05", datum_refs=["A"]),
                frame("position", "0.9", datum_refs=["A", "B", "C"]),
            ]
        )
        assert evaluate_rule(rule, split) is False

        together = ctx(extractions=[frame("position", "0.05", datum_refs=["A", "B", "C"])])
        assert evaluate_rule(rule, together) is True

    def test_group_queries_or_needs_only_one(self) -> None:
        rule = _rule(
            logical_operator="OR",
            signals=[
                {
                    "logical_operator": "AND",
                    "groups": [
                        {
                            "document_path": "position_control_frames",
                            "logical_operator": "OR",
                            "count_query": None,
                            "queries": [
                                _query(
                                    ["value"], "lessThanOrEqual", 0.1, "distance", "numeric", "mm"
                                ),
                                _query(
                                    ["datum_count"],
                                    "greaterThanOrEqual",
                                    3,
                                    "number",
                                    "numeric",
                                    None,
                                ),
                            ],
                        }
                    ],
                }
            ],
        )
        assert (
            evaluate_rule(rule, ctx(extractions=[frame("position", "0.9", datum_refs=["A"])]))
            is False
        )
        assert (
            evaluate_rule(rule, ctx(extractions=[frame("position", "0.05", datum_refs=["A"])]))
            is True
        )


# --------------------------------------------------------------------------- #
# 3. interrogation gating (the block's headline AC)
# --------------------------------------------------------------------------- #
class TestInterrogationGating:
    def test_interrogation_signal_silent_before_interrogation(
        self, worked_rules: list[RuleSchema]
    ) -> None:
        rule = rule_named(worked_rules, "Part complexity level 3")
        pre = _complexity_context(interrogation_result=None)
        assert evaluate_rule(rule, pre) is False, (
            "an interrogation-result signal must not fire before the interrogation ran"
        )

    def test_interrogation_signal_fires_after_interrogation(
        self, worked_rules: list[RuleSchema]
    ) -> None:
        rule = rule_named(worked_rules, "Part complexity level 3")
        assert evaluate_rule(rule, _complexity_context()) is True

    def test_gating_is_per_family(self, worked_rules: list[RuleSchema]) -> None:
        """A sheet-metal interrogation does not un-gate a three_axis_mill signal."""
        rule = rule_named(worked_rules, "Part complexity level 3")
        wrong_family = _complexity_context(interrogation_result={"sheet_metal": {"bends": [1, 2]}})
        assert evaluate_rule(rule, wrong_family) is False

    def test_gated_signal_does_not_block_an_or_rule(self) -> None:
        """Gating makes the signal False, not the rule un-evaluable: a sibling
        OR signal still fires."""
        rule = _rule(
            logical_operator="OR",
            signals=[
                {
                    "logical_operator": "AND",
                    "groups": [
                        {
                            "document_path": "three_axis_mill.machine_direction",
                            "logical_operator": "AND",
                            "count_query": {"operator": "greaterThanOrEqual", "value": 5},
                            "queries": [],
                        }
                    ],
                },
                {
                    "logical_operator": "AND",
                    "groups": [
                        {
                            "document_path": "files",
                            "logical_operator": "AND",
                            "count_query": None,
                            "queries": [
                                _query(["has_print"], "equals", False, "boolean", "boolean", None)
                            ],
                        }
                    ],
                },
            ],
        )
        assert evaluate_rule(rule, ctx(files={"has_model": True, "has_print": False})) is True

    def test_family_ran_but_property_absent(self) -> None:
        """The family ran, so the signal is un-gated — but the property it asks
        for isn't there, so there is nothing to count."""
        rule = _interrogation_rule()
        assert evaluate_rule(rule, ctx(interrogation_result={"three_axis_mill": {}})) is False

    def test_scalar_interrogation_property(self) -> None:
        """M4 may expose a property as a scalar rather than a collection."""
        rule = _single_group_rule(
            "sheet_metal.bend_count",
            [_query(["value"], "greaterThanOrEqual", 3, "number", "numeric", None)],
        )
        bent = ctx(interrogation_result={"sheet_metal": {"bend_count": 4}})
        flat = ctx(interrogation_result={"sheet_metal": {"bend_count": 2}})
        assert evaluate_rule(rule, bent) is True
        assert evaluate_rule(rule, flat) is False
        assert evaluate_rule(rule, ctx()) is False, "still gated when sheet_metal has not run"

    def test_interrogation_ran_but_condition_unmet(self) -> None:
        rule = _interrogation_rule()
        ran = ctx(interrogation_result={"three_axis_mill": {"machine_direction": [1, 2]}})
        assert evaluate_rule(rule, ran) is False
        enough = ctx(
            interrogation_result={"three_axis_mill": {"machine_direction": [1, 2, 3, 4, 5]}}
        )
        assert evaluate_rule(rule, enough) is True


# --------------------------------------------------------------------------- #
# 4. unit / value_type normalization (§7 DACH: mm + deg)
# --------------------------------------------------------------------------- #
class TestNormalization:
    def test_inch_query_threshold_converts_to_mm(self) -> None:
        """A pasted PP rule set may carry inches; the data is mm-native."""
        rule = _envelope_rule(value=12, units="in")  # 12 in = 304.8 mm
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": 305.0})) is True
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": 304.0})) is False

    def test_inch_data_converts_to_mm(self) -> None:
        """A finding may carry inches even though storage is mm-native."""
        rule = _greatest_dim_rule(305)
        assert evaluate_rule(rule, ctx(extractions=[dim("13", units="in")])) is True  # 330.2 mm
        assert evaluate_rule(rule, ctx(extractions=[dim("11", units="in")])) is False  # 279.4 mm

    def test_null_units_default_to_mm(self) -> None:
        """DACH default — a unit-less distance is mm, never inches."""
        assert (
            evaluate_rule(_greatest_dim_rule(305), ctx(extractions=[dim("310", units=None)]))
            is True
        )

    def test_angle_normalizes_in_degrees(self) -> None:
        rule = _rule(
            logical_operator="OR",
            signals=[
                {
                    "logical_operator": "AND",
                    "groups": [
                        {
                            "document_path": "angular_tolerances",
                            "logical_operator": "AND",
                            "count_query": None,
                            "queries": [
                                _query(
                                    ["smallest_delta"],
                                    "lessThanOrEqual",
                                    0.5,
                                    "angle",
                                    "numeric",
                                    "deg",
                                )
                            ],
                        }
                    ],
                }
            ],
        )
        tight = ctx(
            extractions=[
                dim(
                    "45",
                    type="angle",
                    units="deg",
                    tolerance={"kind": "bilateral", "upper": "0.2", "lower": "0.2"},
                )
            ]
        )
        assert evaluate_rule(rule, tight) is True
        loose = ctx(
            extractions=[
                dim(
                    "45",
                    type="angle",
                    units="deg",
                    tolerance={"kind": "bilateral", "upper": "2", "lower": "2"},
                )
            ]
        )
        assert evaluate_rule(rule, loose) is False

    def test_german_decimal_comma_parses(self) -> None:
        """A German print writes 0,05 — not 0.05 (German-first, CLAUDE.md §5)."""
        rule = _tight_length_rule()
        comma = ctx(extractions=[dim("25", tolerance={"kind": "bilateral", "upper": "0,05"})])
        assert evaluate_rule(rule, comma) is True

    def test_german_thousands_separator_parses(self) -> None:
        """1.234,56 is 1234.56 — the last separator is the decimal one."""
        assert evaluate_rule(_greatest_dim_rule(305), ctx(extractions=[dim("1.234,56")])) is True
        assert evaluate_rule(_greatest_dim_rule(305), ctx(extractions=[dim("1,234")])) is False

    def test_smallest_delta_takes_the_tightest_side(self) -> None:
        rule = _tight_length_rule()
        unilateral = ctx(
            extractions=[
                dim("25", tolerance={"kind": "unilateral", "upper": "0.5", "lower": "0.05"})
            ]
        )
        assert evaluate_rule(rule, unilateral) is True, "min(|upper|, |lower|) is the tightest side"

    def test_smallest_delta_for_limit_kind(self) -> None:
        """A limit tolerance carries absolute limits, not deltas — the
        equivalent band is (upper - lower) / 2."""
        rule = _tight_length_rule()
        tight = ctx(
            extractions=[dim("25", tolerance={"kind": "limit", "upper": "25.1", "lower": "25.0"})]
        )
        assert evaluate_rule(rule, tight) is True  # band 0.05
        loose = ctx(
            extractions=[dim("25", tolerance={"kind": "limit", "upper": "25.5", "lower": "24.5"})]
        )
        assert evaluate_rule(rule, loose) is False  # band 0.5


# --------------------------------------------------------------------------- #
# 5. ISO GPS symbology (§7) + the remaining operators
# --------------------------------------------------------------------------- #
#: The 13 ISO 1101 control-frame characteristics, spelled out here rather than
#: read from ``_ISO_GPS_SYMBOLS`` — deriving the expectation from the mapping
#: under test makes a dropped symbol silently untested and a swapped pair
#: (⏥→perpendicularity, ⊥→flatness) still pass, since both sides move together.
_ISO_GPS_ORACLE = {
    "⏤": "straightness",
    "⏥": "flatness",
    "○": "circularity",
    "⌭": "cylindricity",
    "⌒": "profile_of_line",
    "⌓": "profile_of_surface",
    "∥": "parallelism",
    "⊥": "perpendicularity",
    "⌖": "position",
    "◎": "concentricity",
    "⌯": "symmetry",
    "↗": "runout",
    "⌰": "total_runout",
}


class TestIsoGpsAndOperators:
    def test_iso_gps_catalogue_matches_the_13_characteristics(self) -> None:
        """§7: the catalogue itself, against an independent oracle."""
        assert len(_ISO_GPS_ORACLE) == 13
        assert _ISO_GPS_SYMBOLS == _ISO_GPS_ORACLE

    def test_control_frame_matches_by_iso_gps_symbol(self, worked_rules: list[RuleSchema]) -> None:
        """§7: control-frame signals interpret ISO GPS symbology. A print emits
        the symbol (⏥), not the English word."""
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        assert evaluate_rule(rule, ctx(extractions=[frame("⏥", "0.02")])) is True
        assert evaluate_rule(rule, ctx(extractions=[frame("⏥", "0.5")])) is False

    def test_each_iso_gps_symbol_maps_to_its_path(self) -> None:
        """Every symbol resolves to its own characteristic's collection."""
        for symbol, characteristic in _ISO_GPS_ORACLE.items():
            rule = _single_group_rule(
                f"{characteristic}_control_frames",
                [_query(["value"], "lessThanOrEqual", 0.1, "distance", "numeric", "mm")],
            )
            assert evaluate_rule(rule, ctx(extractions=[frame(symbol, "0.02")])) is True, symbol
            # a different characteristic's frame must not leak into this path
            other = "⊥" if symbol != "⊥" else "⏥"
            assert evaluate_rule(rule, ctx(extractions=[frame(other, "0.02")])) is False, symbol

    def test_unknown_symbol_matches_no_characteristic_path(self) -> None:
        rule = _single_group_rule(
            "flatness_control_frames",
            [_query(["value"], "lessThanOrEqual", 0.1, "distance", "numeric", "mm")],
        )
        assert evaluate_rule(rule, ctx(extractions=[frame("∠", "0.02")])) is False, (
            "angularity is not one of the 13 catalogued characteristics"
        )
        # …but it still counts as a control frame in the aggregate path
        aggregate = _single_group_rule(
            "control_frames", [], count_query={"operator": "greaterThanOrEqual", "value": 1}
        )
        assert evaluate_rule(aggregate, ctx(extractions=[frame("∠", "0.02")])) is True

    def test_numeric_equals_survives_unit_conversion(self) -> None:
        """12 in → 304.79999999999995 mm must still equal 304.8 mm."""
        rule = _single_group_rule(
            "part", [_query(["max_dim"], "equals", 12, "distance", "numeric", "in")]
        )
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": 304.8})) is True
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": 304.9})) is False

    def test_string_equals_is_exact(self) -> None:
        rule = _single_group_rule(
            "text", [_query(["raw_text"], "equals", "SPX-1234-A", "string", "string", None)]
        )
        assert evaluate_rule(rule, ctx(document_texts=["SPX-1234-A"])) is True
        assert evaluate_rule(rule, ctx(document_texts=["spx-1234-a"])) is False


# --------------------------------------------------------------------------- #
# 6. robustness — missing/garbage data must not fire or raise
# --------------------------------------------------------------------------- #
class TestRobustness:
    def test_missing_part_attribute_does_not_match(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "Machine envelope exceeded")
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": None})) is False
        assert evaluate_rule(rule, ctx(part_attributes={})) is False
        assert evaluate_rule(rule, ctx(part_attributes=None)) is False

    def test_unparseable_value_does_not_match(self) -> None:
        assert (
            evaluate_rule(_greatest_dim_rule(305), ctx(extractions=[dim("siehe Tabelle")])) is False
        )

    def test_missing_tolerance_does_not_match(self) -> None:
        assert (
            evaluate_rule(_tight_length_rule(), ctx(extractions=[dim("25", tolerance=None)]))
            is False
        )

    def test_empty_context_matches_nothing(self, worked_rules: list[RuleSchema]) -> None:
        empty = EvaluationContext()
        matches = evaluate_rules(worked_rules, empty)
        assert [m.name for m in matches] == ["Missing model or print"], (
            "no files at all means has_model/has_print are both false"
        )

    def test_count_query_counts_matching_items_only(self) -> None:
        rule = _rule(
            logical_operator="OR",
            signals=[
                {
                    "logical_operator": "AND",
                    "groups": [
                        {
                            "document_path": "position_control_frames",
                            "logical_operator": "AND",
                            "count_query": {"operator": "greaterThanOrEqual", "value": 2},
                            "queries": [
                                _query(
                                    ["value"], "lessThanOrEqual", 0.1, "distance", "numeric", "mm"
                                )
                            ],
                        }
                    ],
                }
            ],
        )
        one_tight = ctx(extractions=[frame("position", "0.05"), frame("position", "0.9")])
        assert evaluate_rule(rule, one_tight) is False, "only matching items count"
        two_tight = ctx(extractions=[frame("position", "0.05"), frame("position", "0.08")])
        assert evaluate_rule(rule, two_tight) is True


# --------------------------------------------------------------------------- #
# 7. the real production shapes (ship-review regressions)
# --------------------------------------------------------------------------- #
class TestProductionShapes:
    def test_part_attributes_accept_decimal(self, worked_rules: list[RuleSchema]) -> None:
        """part_geometry dims are Numeric columns → Decimal, not float. A
        float-only parser would silently kill every `part` rule (ship-review)."""
        rule = rule_named(worked_rules, "Machine envelope exceeded")
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": Decimal("400")})) is True
        assert evaluate_rule(rule, ctx(part_attributes={"max_dim": Decimal("100")})) is False

    def test_normalized_value_never_double_converts(self) -> None:
        """`normalized_value` has no pinned unit semantics, so it must not be
        paired with `units` — M3.2's accept path reads `value` for the same
        reason (ship-review 2026-07-15)."""
        rule = _greatest_dim_rule(305)
        finding = dim("12", units="in")  # 304.8 mm — just under the threshold
        finding["normalized_value"] = "304.8"  # already-converted, unit unknown
        assert evaluate_rule(rule, ctx(extractions=[finding])) is False, (
            "trusting normalized_value here would give 304.8 * 25.4 = 7741.92 mm"
        )

    def test_tight_control_frame_on_an_inch_print_still_fires(
        self, worked_rules: list[RuleSchema]
    ) -> None:
        """The dangerous direction: a missed tight tolerance means the shop
        quotes a job it cannot hold."""
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        finding = frame("⏥", "0.005")  # 0.127 mm — inside the 0.13 mm threshold
        finding["units"] = "in"
        finding["normalized_value"] = "0.127"
        assert evaluate_rule(rule, ctx(extractions=[finding])) is True

    def test_unilateral_zero_side_is_not_maximally_tight(
        self, worked_rules: list[RuleSchema]
    ) -> None:
        """A +5/-0 callout is loose. Reading its zero side as "tightest" would
        fire the tight-tolerance rule on nearly every print (DECISIONS OPEN:)."""
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        loose = ctx(
            extractions=[dim("25", tolerance={"kind": "unilateral", "upper": "5", "lower": "0"})]
        )
        assert evaluate_rule(rule, loose) is False
        # …and the same requirement written as limits agrees
        as_limits = ctx(
            extractions=[dim("25", tolerance={"kind": "limit", "upper": "30", "lower": "25"})]
        )
        assert evaluate_rule(rule, as_limits) is False

    def test_unilateral_tight_side_still_fires(self, worked_rules: list[RuleSchema]) -> None:
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        tight = ctx(
            extractions=[dim("25", tolerance={"kind": "unilateral", "upper": "0.05", "lower": "0"})]
        )
        assert evaluate_rule(rule, tight) is True

    def test_exact_zero_tolerance_still_fires(self, worked_rules: list[RuleSchema]) -> None:
        """Both sides zero is a genuinely exact callout — that IS tight."""
        rule = rule_named(worked_rules, "All tight dimension tolerances")
        exact = ctx(
            extractions=[dim("25", tolerance={"kind": "bilateral", "upper": "0", "lower": "0"})]
        )
        assert evaluate_rule(rule, exact) is True

    def test_trailing_period_does_not_shift_the_decimal(self) -> None:
        """ "0,05." must not read the dot as the decimal separator (→ 5.0)."""
        rule = _tight_length_rule()
        assert (
            evaluate_rule(rule, ctx(extractions=[dim("25", tolerance={"upper": "0,05."})])) is True
        )

    def test_string_equals_with_keyword_list_is_any_of(self) -> None:
        rule = _single_group_rule(
            "text",
            [_query(["raw_text"], "equals", ["SPX-1", "SPX-2"], "string", "string", None)],
        )
        assert evaluate_rule(rule, ctx(document_texts=["SPX-2"])) is True
        assert evaluate_rule(rule, ctx(document_texts=["SPX-3"])) is False

    def test_datum_refs_as_string_does_not_count_characters(self) -> None:
        rule = _single_group_rule(
            "position_control_frames",
            [_query(["datum_count"], "greaterThanOrEqual", 3, "number", "numeric", None)],
        )
        malformed = frame("⌖", "0.1")
        malformed["gdt"]["datum_refs"] = "A|B"  # 3 chars, 2 datums
        assert evaluate_rule(rule, ctx(extractions=[malformed])) is False


# --------------------------------------------------------------------------- #
# helpers — AST builders
# --------------------------------------------------------------------------- #
def _query(
    field_name: list[str],
    operator: str,
    value: Any,
    value_type: str,
    filter_type: str,
    units: str | None,
) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "operator": operator,
        "value": value,
        "value_type": value_type,
        "filter_type": filter_type,
        "units": units,
    }


def _rule(**parts: Any) -> RuleSchema:
    base: dict[str, Any] = {
        "uuid": "00000000-0000-4000-8000-0000000000bb",
        "name": "Testregel",
        "description": "",
        "resolutions": [{"type": "RESOLVE", "parameters": [], "custom_label": "Geprüft"}],
        "default_assignee_id": None,
    }
    base.update(parts)
    return RuleSchema.model_validate(base)


def _single_group_rule(
    document_path: str, queries: list[dict[str, Any]], count_query: Any = None
) -> RuleSchema:
    return _rule(
        logical_operator="OR",
        signals=[
            {
                "logical_operator": "AND",
                "groups": [
                    {
                        "document_path": document_path,
                        "logical_operator": "AND",
                        "count_query": count_query,
                        "queries": queries,
                    }
                ],
            }
        ],
    )


def _envelope_rule(value: Any, units: str | None) -> RuleSchema:
    return _single_group_rule(
        "part", [_query(["max_dim"], "greaterThanOrEqual", value, "distance", "numeric", units)]
    )


def _greatest_dim_rule(value: Any) -> RuleSchema:
    return _single_group_rule(
        "greatest_distance_dimension",
        [_query(["value"], "greaterThanOrEqual", value, "distance", "numeric", "mm")],
    )


def _tight_length_rule() -> RuleSchema:
    return _single_group_rule(
        "length_tolerances",
        [_query(["smallest_delta"], "lessThanOrEqual", 0.13, "distance", "numeric", "mm")],
    )


def _interrogation_rule() -> RuleSchema:
    return _single_group_rule(
        "three_axis_mill.machine_direction",
        [],
        count_query={"operator": "greaterThanOrEqual", "value": 5},
    )


def _complexity_context(*, datum_count: int = 5, **overrides: Any) -> EvaluationContext:
    """Data satisfying every signal of the §5 rule-4 composite."""
    extractions: list[dict[str, Any]] = [
        frame("position", "0.05", datum_refs=["A", "B", "C"]) for _ in range(7)
    ]
    extractions += [datum(letter) for letter in "ABCDEFG"[:datum_count]]
    extractions.append(dim("10"))
    base: dict[str, Any] = {
        "extractions": extractions,
        "document_texts": [],
        "part_attributes": {"max_dim": 50.0},
        "files": {"has_model": True, "has_print": True},
        "interrogation_result": {"three_axis_mill": {"machine_direction": [1, 2, 3, 4, 5]}},
    }
    base.update(overrides)
    return EvaluationContext(**base)


def test_fixture_is_the_nine_worked_rules(worked_rules: list[RuleSchema]) -> None:
    """Guard the golden: the evaluator's contract is the §5 set."""
    assert len(worked_rules) == 9
    assert json.loads(FIXTURE.read_text(encoding="utf-8"))[0]["signals"], "fixture carries AST"
