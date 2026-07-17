"""M4.7 — DFM warning engine: per-family threshold evaluation (pure).

The evaluator consumes what the M4.2/M4.4-M4.6 recognizers actually emit
(``family_scalars`` + ``features`` + ``dimensions``) against the resolved
``InterrogationInputs`` and produces ``feedback: Warning[]`` — each warning
carrying the threshold that fired (INTERROGATION-ENGINE-SPEC §2: the value
must be auditable). Thresholds and toggle defaults are the DFM-WARNINGS.md
catalogue, metric-native (CLAUDE.md §5: mm/deg; inch defaults x25.4).

These tests are synthetic-data pure tests; the STEP-fixture integration path
is covered in ``test_interrogation_m47.py``-style flows via ``analyze()``.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.geometry.contract import (
    FAMILY_LATHE,
    FAMILY_MILLING,
    FAMILY_SHEET_METAL,
    FAMILY_TUBE_LASER,
    Dimensions,
)
from app.geometry.dfm import (
    CATALOGUE,
    dfm_default_inputs,
    evaluate_feedback,
)


def _dims(x: float = 100.0, y: float = 50.0, z: float = 10.0) -> Dimensions:
    return Dimensions(
        size_x=x,
        size_y=y,
        size_z=z,
        max_dim=x,
        med_dim=y,
        min_dim=z,
        area=1000.0,
        volume=1000.0,
        weight=None,
        bbox_source="aabb",
    )


def _bend(radius: float, angle: float = 90.0, length: float = 50.0) -> dict[str, Any]:
    return {
        "name": "bend",
        "properties": {"radius": radius, "angle": angle, "length": length, "k_factor": 0.4},
        "geometry_refs": [],
    }


def _hole(
    depth: float, diameter: float, bottom_type: str = "thru", circular_pocket: bool = False
) -> dict[str, Any]:
    return {
        "name": "circular_pocket" if circular_pocket else "hole",
        "properties": {
            "area": 100.0,
            "volume": 100.0,
            "depth": depth,
            "bottom_type": bottom_type,
            "min_radius": diameter / 2,
            "diameter": diameter,
        },
        "geometry_refs": [],
    }


def _warning(feedback: list[dict[str, Any]], wtype: str) -> dict[str, Any] | None:
    hits = [w for w in feedback if w["type"] == wtype]
    assert len(hits) <= 1, f"duplicate warning rows for {wtype}"
    return hits[0] if hits else None


# --------------------------------------------------------------------------- #
# Catalogue shape
# --------------------------------------------------------------------------- #
def test_catalogue_covers_core_four_families() -> None:
    assert set(CATALOGUE) == {
        FAMILY_SHEET_METAL,
        FAMILY_MILLING,
        FAMILY_LATHE,
        FAMILY_TUBE_LASER,
    }


def test_always_on_warnings_cannot_carry_a_toggle() -> None:
    """Sheet-metal Additional Operations Required + milling Uncut Faces are
    always-on (DFM-WARNINGS §Implementation 3): no ``should_detect_*`` key."""
    sm = {d.type: d for d in CATALOGUE[FAMILY_SHEET_METAL]}
    mill = {d.type: d for d in CATALOGUE[FAMILY_MILLING]}
    assert sm["additional_operations_required"].toggle is None
    assert mill["uncut_faces"].toggle is None


def test_v2_warnings_are_marked_not_dropped() -> None:
    """A feature v1 OCCT can't recognize keeps its catalogue row, flagged
    v2/Spatial (build-plan M4.7 Decisions — a missing feature is a missing
    review signal, never silently dropped)."""
    sm = {d.type: d for d in CATALOGUE[FAMILY_SHEET_METAL]}
    # Cutout positions are not recognized in v1 — proximity warnings are v2.
    assert sm["close_cutouts"].v1_supported is False
    # Bend radius rides the recognized bend features — v1.
    assert sm["small_bend_radius"].v1_supported is True


def test_default_inputs_are_metric() -> None:
    """Inch catalogue defaults are stored converted (x25.4): milling small
    hole 1/16 in = 1.5875 mm; press length 240 in = 6096 mm (CLAUDE.md §5)."""
    mill = dfm_default_inputs(FAMILY_MILLING)
    assert mill["small_hole_diameter"] == pytest.approx(1.5875)
    assert mill["deep_hole_ratio_threshold"] == 8.0
    sm = dfm_default_inputs(FAMILY_SHEET_METAL)
    assert sm["press_length"] == pytest.approx(6096.0)
    assert sm["min_bend_radius"] == 0.75  # xt — unit-agnostic
    assert sm["should_detect_small_bend_radius"] is True
    # documented-off defaults stay off
    assert sm["should_detect_tight_corners"] is False


# --------------------------------------------------------------------------- #
# Sheet metal
# --------------------------------------------------------------------------- #
def test_small_bend_radius_fires_with_threshold_attached() -> None:
    scalars = {"thickness": 2.0, "bend_count": 1}
    feedback = evaluate_feedback(
        FAMILY_SHEET_METAL,
        _dims(),
        scalars,
        [_bend(radius=1.0)],
        dfm_default_inputs(FAMILY_SHEET_METAL),
    )
    w = _warning(feedback, "small_bend_radius")
    assert w is not None
    assert w["count"] == 1
    assert w["threshold_used"] == {"min_bend_radius": 0.75}
    assert w["can_disable"] is True
    assert len(w["instances"]) == 1


def test_ok_bend_radius_emits_nothing() -> None:
    scalars = {"thickness": 2.0, "bend_count": 1}
    feedback = evaluate_feedback(
        FAMILY_SHEET_METAL,
        _dims(),
        scalars,
        [_bend(radius=3.0)],
        dfm_default_inputs(FAMILY_SHEET_METAL),
    )
    assert _warning(feedback, "small_bend_radius") is None
    assert _warning(feedback, "large_bend_radius") is None


def test_toggle_off_suppresses_the_warning() -> None:
    scalars = {"thickness": 2.0, "bend_count": 1}
    inputs = {**dfm_default_inputs(FAMILY_SHEET_METAL), "should_detect_small_bend_radius": False}
    feedback = evaluate_feedback(FAMILY_SHEET_METAL, _dims(), scalars, [_bend(radius=1.0)], inputs)
    assert _warning(feedback, "small_bend_radius") is None


def test_abnormal_bend_angle() -> None:
    scalars = {"thickness": 2.0, "bend_count": 2}
    feats = [_bend(radius=3.0, angle=45.0), _bend(radius=3.0, angle=90.0)]
    feedback = evaluate_feedback(
        FAMILY_SHEET_METAL, _dims(), scalars, feats, dfm_default_inputs(FAMILY_SHEET_METAL)
    )
    w = _warning(feedback, "abnormal_bend_angle")
    assert w is not None and w["count"] == 1


def test_exceeds_press_length_has_no_toggle() -> None:
    scalars = {"thickness": 2.0, "bend_count": 1}
    feats = [_bend(radius=3.0, length=7000.0)]
    feedback = evaluate_feedback(
        FAMILY_SHEET_METAL, _dims(), scalars, feats, dfm_default_inputs(FAMILY_SHEET_METAL)
    )
    w = _warning(feedback, "exceeds_press_length")
    assert w is not None
    assert w["can_disable"] is False
    assert w["threshold_used"] == {"press_length": pytest.approx(6096.0)}


def test_dimensions_exceed_limits_checks_unfolded_too() -> None:
    scalars = {"thickness": 2.0, "bend_count": 1, "size_x": 4000.0, "size_y": 100.0}
    feedback = evaluate_feedback(
        FAMILY_SHEET_METAL, _dims(), scalars, [_bend(3.0)], dfm_default_inputs(FAMILY_SHEET_METAL)
    )
    assert _warning(feedback, "dimensions_exceed_limits") is not None


def test_unrecognized_body_yields_no_warnings() -> None:
    """Empty scalars (recognizer returned nothing) → no thickness → no xt
    evaluation; never a fabricated warning."""
    feedback = evaluate_feedback(
        FAMILY_SHEET_METAL, _dims(), {}, [], dfm_default_inputs(FAMILY_SHEET_METAL)
    )
    assert feedback == []


# --------------------------------------------------------------------------- #
# Milling
# --------------------------------------------------------------------------- #
def test_deep_hole_and_small_hole() -> None:
    scalars = {"setup_count": 1, "setups": [], "uncovered_area": 0.0}
    feats = [_hole(depth=40.0, diameter=3.0), _hole(depth=5.0, diameter=1.0)]
    feedback = evaluate_feedback(
        FAMILY_MILLING, _dims(), scalars, feats, dfm_default_inputs(FAMILY_MILLING)
    )
    deep = _warning(feedback, "deep_hole")
    assert deep is not None and deep["count"] == 1
    assert deep["threshold_used"] == {"deep_hole_ratio_threshold": 8.0}
    small = _warning(feedback, "small_hole_diameter")
    assert small is not None and small["count"] == 1


def test_blind_hole_types() -> None:
    scalars = {"setup_count": 1, "setups": [], "uncovered_area": 0.0}
    feats = [_hole(10.0, 6.0, bottom_type="tipped"), _hole(10.0, 6.0, bottom_type="flat")]
    feedback = evaluate_feedback(
        FAMILY_MILLING, _dims(), scalars, feats, dfm_default_inputs(FAMILY_MILLING)
    )
    assert _warning(feedback, "tipped_hole") is not None
    assert _warning(feedback, "flat_bottom_hole") is not None


def test_deep_circular_pocket_uses_tool_diameter() -> None:
    scalars = {"setup_count": 1, "setups": [], "uncovered_area": 0.0}
    # depth 50 ÷ tool-dia 12.7 = 3.94 > 3.0
    feats = [_hole(depth=50.0, diameter=60.0, circular_pocket=True)]
    feedback = evaluate_feedback(
        FAMILY_MILLING, _dims(), scalars, feats, dfm_default_inputs(FAMILY_MILLING)
    )
    w = _warning(feedback, "deep_circular_pocket")
    assert w is not None
    assert w["threshold_used"] == {
        "deep_cut_radiused_ratio_threshold": 3.0,
        "max_tool_diameter": pytest.approx(12.7),
    }


def test_uncut_faces_is_always_on() -> None:
    scalars = {"setup_count": 1, "setups": [], "uncovered_area": 123.0}
    feedback = evaluate_feedback(
        FAMILY_MILLING, _dims(), scalars, [], dfm_default_inputs(FAMILY_MILLING)
    )
    w = _warning(feedback, "uncut_faces")
    assert w is not None
    assert w["can_disable"] is False


def test_work_envelope() -> None:
    scalars = {"setup_count": 1, "setups": [], "uncovered_area": 0.0}
    feedback = evaluate_feedback(
        FAMILY_MILLING, _dims(x=2000.0), scalars, [], dfm_default_inputs(FAMILY_MILLING)
    )
    w = _warning(feedback, "work_envelope_size")
    assert w is not None
    assert w["threshold_used"]["max_part_length"] == pytest.approx(1625.6)


# --------------------------------------------------------------------------- #
# Lathe
# --------------------------------------------------------------------------- #
def _lathe_scalars(**over: Any) -> dict[str, Any]:
    return {
        "setup_count": 1,
        "stock_radius": 15.0,
        "stock_length": 80.0,
        "min_external_radius": 6.0,
        **over,
    }


def test_slender_part() -> None:
    scalars = _lathe_scalars(stock_length=200.0, min_external_radius=6.0)
    # 200 / 12 = 16.7 > 8.0
    feedback = evaluate_feedback(
        FAMILY_LATHE, _dims(), scalars, [], dfm_default_inputs(FAMILY_LATHE)
    )
    w = _warning(feedback, "slender_part")
    assert w is not None
    assert w["threshold_used"] == {"slender_part_ratio": 8.0}


def test_lathe_envelope_and_live_tooling_callouts() -> None:
    scalars = _lathe_scalars(stock_length=1000.0)
    feats = [
        {"name": "off_axis_hole", "properties": {}, "geometry_refs": []},
        {"name": "asymmetric_cavity", "properties": {"face_count": 3}, "geometry_refs": []},
    ]
    feedback = evaluate_feedback(
        FAMILY_LATHE, _dims(), scalars, feats, dfm_default_inputs(FAMILY_LATHE)
    )
    assert _warning(feedback, "work_envelope_size") is not None
    assert _warning(feedback, "off_axis_hole") is not None
    assert _warning(feedback, "asymmetric_cavity") is not None


def test_lathe_small_internal_radius() -> None:
    feats = [
        {
            "name": "internal_cut",
            "properties": {"radius": 0.8, "diameter": 1.6, "depth": 5.0, "thru": False},
            "geometry_refs": [],
        }
    ]
    feedback = evaluate_feedback(
        FAMILY_LATHE, _dims(), _lathe_scalars(), feats, dfm_default_inputs(FAMILY_LATHE)
    )
    w = _warning(feedback, "small_internal_radius")
    assert w is not None
    assert w["threshold_used"] == {"small_internal_radius_threshold": 1.0}


# --------------------------------------------------------------------------- #
# Tube laser
# --------------------------------------------------------------------------- #
def test_tube_angled_cut_fires_but_not_on_round_by_default() -> None:
    feats = [
        {
            "name": "angled_cut",
            "properties": {"angle": 30.0, "cut_length": 100.0, "machining_required": False},
            "geometry_refs": [],
        }
    ]
    rect = {"stock_type": "rectangular", "thickness": 2.0}
    feedback = evaluate_feedback(
        FAMILY_TUBE_LASER, _dims(), rect, feats, dfm_default_inputs(FAMILY_TUBE_LASER)
    )
    w = _warning(feedback, "angled_cut")
    assert w is not None
    assert w["threshold_used"] == {"max_angled_cut_threshold": 45.0}

    # should_detect_angled_cuts_on_round_tubes defaults False (DFM-WARNINGS §Tube)
    round_ = {"stock_type": "round", "thickness": 2.0}
    feedback = evaluate_feedback(
        FAMILY_TUBE_LASER, _dims(), round_, feats, dfm_default_inputs(FAMILY_TUBE_LASER)
    )
    assert _warning(feedback, "angled_cut") is None


# --------------------------------------------------------------------------- #
# General behavior
# --------------------------------------------------------------------------- #
def test_unknown_family_returns_empty() -> None:
    assert evaluate_feedback("WIRE_EDM", _dims(), {}, [], {}) == []


def test_v2_warnings_are_never_evaluated() -> None:
    """No v2/Spatial warning type may appear in feedback even with wildly
    violating data — the feature behind it is not recognized in v1."""
    scalars = {"thickness": 2.0, "bend_count": 1}
    feedback = evaluate_feedback(
        FAMILY_SHEET_METAL, _dims(), scalars, [_bend(1.0)], dfm_default_inputs(FAMILY_SHEET_METAL)
    )
    v2_types = {d.type for d in CATALOGUE[FAMILY_SHEET_METAL] if not d.v1_supported}
    assert not v2_types & {w["type"] for w in feedback}


# --------------------------------------------------------------------------- #
# STEP-fixture integration (through analyze(); goldens pin the fired set)
# --------------------------------------------------------------------------- #
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from app.geometry import get_engine  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
GOLDENS = json.loads((FIXTURES / "goldens.json").read_text(encoding="utf-8"))
_FAMILY_OF = {
    "sheet_metal": FAMILY_SHEET_METAL,
    "milling": FAMILY_MILLING,
    "lathe": FAMILY_LATHE,
    "tube_laser": FAMILY_TUBE_LASER,
}
FAMILY_FIXTURES = sorted(name for name, g in GOLDENS.items() if g.get("family") in _FAMILY_OF)


@pytest.mark.parametrize("name", FAMILY_FIXTURES)
def test_fixture_feedback_matches_golden(name: str) -> None:
    """Every family fixture's fired warning set is pinned: a fixture with a
    known violation raises exactly its catalogued warning(s) (M4.7
    acceptance), and clean fixtures raise none — drift either way fails."""
    golden = GOLDENS[name]
    result = get_engine().analyze(
        (FIXTURES / name).read_bytes(), family=_FAMILY_OF[golden["family"]]
    )
    fired = {w["type"]: w["count"] for w in result.feedback}
    assert fired == golden.get("feedback", {})


def test_small_bend_radius_fixture_carries_threshold() -> None:
    result = get_engine().analyze(
        (FIXTURES / "bracket-tightbend-t2-r1.step").read_bytes(), family=FAMILY_SHEET_METAL
    )
    (w,) = [w for w in result.feedback if w["type"] == "small_bend_radius"]
    assert w["threshold_used"] == {"min_bend_radius": 0.75}
    assert w["instances"][0]["radius"] == pytest.approx(1.0, rel=1e-3)


def test_deep_hole_fixture_carries_threshold_and_respects_toggle() -> None:
    blob = (FIXTURES / "block-deephole-40x40x30.step").read_bytes()
    result = get_engine().analyze(blob, family=FAMILY_MILLING)
    (w,) = [w for w in result.feedback if w["type"] == "deep_hole"]
    assert w["threshold_used"] == {"deep_hole_ratio_threshold": 8.0}
    assert w["instances"][0]["ratio"] == pytest.approx(10.0, rel=1e-3)

    # the org toggle suppresses it end-to-end through analyze(inputs=...)
    result = get_engine().analyze(
        blob, family=FAMILY_MILLING, inputs={"should_detect_deep_hole": False}
    )
    assert not [w for w in result.feedback if w["type"] == "deep_hole"]


@pytest.mark.parametrize("name", FAMILY_FIXTURES)
def test_analyze_accepts_the_full_seeded_profile(name: str) -> None:
    """The worker passes the org profile (strategy + DFM thresholds + toggles)
    verbatim into analyze() — every recognizer must tolerate the DFM keys it
    doesn't consume itself (fresh-eyes 🔴: tube-laser rejected them)."""
    golden = GOLDENS[name]
    family = _FAMILY_OF[golden["family"]]
    result = get_engine().analyze(
        (FIXTURES / name).read_bytes(), family=family, inputs=dfm_default_inputs(family)
    )
    fired = {w["type"]: w["count"] for w in result.feedback}
    assert fired == golden.get("feedback", {})
