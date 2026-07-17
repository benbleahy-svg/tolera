"""M4.6 — Tube-laser cross-section classification (pure engine).

Tests ``analyze(family="TUBE_LASER")`` against the analytic tube goldens
(``fixtures/cad/goldens.json``, sub-key ``tube_laser``): the 5 stock profiles
(round / rectangular / rectangular_radiused / angle / u_channel — the radiused
profile is this block's mini-spike, M4.0 flagged it ``~``), section dims,
``total_cut_length`` + ``pierce_count``, the angled-cut features with the
``machining_required`` reclassification beyond ``max_angled_cut_threshold``
(45°, DFM-WARNINGS §Tube), and the ``should_countersinks_be_lasered`` strategy
input. A non-tube body classifies ``incompatible`` — never a fabricated guess
(build-plan M4.6 acceptance).

Geometry asserts use the M4.0 0.1% relative gate; classification and count
asserts are exact. No DB, no API.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from app.geometry import FAMILY_TUBE_LASER, RECOGNIZED_FAMILIES, AnalysisResult, get_engine
from app.geometry.contract import GeometryError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
GOLDENS = json.loads((FIXTURES / "goldens.json").read_text(encoding="utf-8"))

GEOMETRY_RTOL = 1e-3

#: Fixtures carrying a tube-laser recognizer golden.
TUBE_FIXTURES = sorted(name for name, golden in GOLDENS.items() if "tube_laser" in golden)
_EXPECTED_TUBE_FIXTURES = {
    "tube-round-d30-t2-l200.step",
    "tube-rect-40x20-t2-l200.step",
    "profile-angle-40x40x4-l100.step",
    "profile-u-channel-40x20x3-l100.step",
    "tube-rect-radiused-40x20-t2-r4-l150.step",
    "tube-rect-cutout-40x20-t2-d10-l150.step",
    "tube-rect-angled30-40x20-t2-l150.step",
    "tube-rect-angled60-40x20-t2-l80.step",
    "tube-rect-csk-40x20-t3-d8-l120.step",
}
assert set(TUBE_FIXTURES) >= _EXPECTED_TUBE_FIXTURES, (
    f"missing tube goldens: {_EXPECTED_TUBE_FIXTURES - set(TUBE_FIXTURES)}"
)

#: The section-dim scalar keys asserted numerically when the golden pins them.
_DIM_KEYS = (
    "thickness",
    "length",
    "width",
    "height",
    "diameter",
    "internal_radius",
    "outside_corner_radius",
    "leg_angle",
    "total_cut_length",
)


def analyze(name: str, inputs: dict[str, Any] | None = None) -> AnalysisResult:
    return get_engine().analyze(
        (FIXTURES / name).read_bytes(), family=FAMILY_TUBE_LASER, inputs=inputs
    )


def assert_close(measured: float, golden: float, what: str) -> None:
    assert measured == pytest.approx(golden, rel=GEOMETRY_RTOL, abs=1e-9), (
        f"{what}: {measured} vs golden {golden}"
    )


def test_tube_laser_family_is_recognized() -> None:
    """TUBE_LASER routes to a recognizer (resolve_part_family gates on this)."""
    assert FAMILY_TUBE_LASER in RECOGNIZED_FAMILIES


# --------------------------------------------------------------------------- #
# Classification + section dims vs the analytic goldens (the acceptance core)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", TUBE_FIXTURES)
def test_stock_type_matches_goldens(name: str) -> None:
    golden = GOLDENS[name]["tube_laser"]
    result = analyze(name)
    assert result.family == FAMILY_TUBE_LASER
    assert result.family_scalars["stock_type"] == golden["stock_type"]


@pytest.mark.parametrize("name", TUBE_FIXTURES)
def test_section_dims_match_goldens(name: str) -> None:
    golden = GOLDENS[name]["tube_laser"]
    scalars = analyze(name).family_scalars
    for key in _DIM_KEYS:
        if key in golden:
            assert_close(scalars[key], golden[key], key)
    for key in ("is_outside_corner_round",):
        if key in golden:
            assert scalars[key] is golden[key]


@pytest.mark.parametrize("name", TUBE_FIXTURES)
def test_pierce_count_matches_goldens(name: str) -> None:
    golden = GOLDENS[name]["tube_laser"]
    assert analyze(name).family_scalars["pierce_count"] == golden["pierce_count"]


# --------------------------------------------------------------------------- #
# Angled cuts: feature + the >45° machining_required reclassification
# --------------------------------------------------------------------------- #
def _angled_cut_features(result: AnalysisResult) -> list[dict[str, Any]]:
    return [f for f in result.features if f["name"] == "angled_cut"]


def test_angled_cut_below_threshold_stays_lasered() -> None:
    golden = GOLDENS["tube-rect-angled30-40x20-t2-l150.step"]["tube_laser"]
    result = analyze("tube-rect-angled30-40x20-t2-l150.step")
    angled = _angled_cut_features(result)
    assert [pytest.approx(f["properties"]["angle"], abs=0.5) for f in angled] == golden[
        "angled_cut_degrees"
    ]
    assert result.family_scalars.get("machining_required", False) is False
    assert_close(
        result.family_scalars["total_cut_length"], golden["total_cut_length"], "cut length"
    )


def test_angled_cut_beyond_threshold_requires_machining() -> None:
    golden = GOLDENS["tube-rect-angled60-40x20-t2-l80.step"]["tube_laser"]
    result = analyze("tube-rect-angled60-40x20-t2-l80.step")
    assert result.family_scalars["machining_required"] is True
    angled = _angled_cut_features(result)
    assert len(angled) == 1
    assert angled[0]["properties"]["angle"] == pytest.approx(60.0, abs=0.5)
    assert angled[0]["properties"]["machining_required"] is True
    # the reclassified cut is a secondary op — excluded from the laser length
    assert_close(
        result.family_scalars["total_cut_length"], golden["total_cut_length"], "cut length"
    )


def test_angled_cut_threshold_is_an_input() -> None:
    """Raising max_angled_cut_threshold above 60° keeps the cut lasered."""
    result = analyze(
        "tube-rect-angled60-40x20-t2-l80.step", inputs={"max_angled_cut_threshold": 75.0}
    )
    assert result.family_scalars.get("machining_required", False) is False
    assert_close(
        result.family_scalars["total_cut_length"],
        112.0 + 112.0 / math.cos(math.radians(60.0)),
        "cut length with raised threshold",
    )


# --------------------------------------------------------------------------- #
# Cutouts + the should_countersinks_be_lasered strategy input
# --------------------------------------------------------------------------- #
def test_cutout_feature_carries_perimeter() -> None:
    result = analyze("tube-rect-cutout-40x20-t2-d10-l150.step")
    cutouts = [f for f in result.features if f["name"] == "cutout"]
    assert len(cutouts) == 1
    assert_close(cutouts[0]["properties"]["perimeter"], 10 * math.pi, "cutout perimeter")


def test_countersink_lasered_by_default() -> None:
    golden = GOLDENS["tube-rect-csk-40x20-t3-d8-l120.step"]["tube_laser"]
    result = analyze("tube-rect-csk-40x20-t3-d8-l120.step")
    assert result.family_scalars["pierce_count"] == 1
    assert_close(
        result.family_scalars["total_cut_length"], golden["total_cut_length"], "cut length"
    )
    csk = [f for f in result.features if f["name"] == "countersink"]
    assert len(csk) == 1
    assert_close(csk[0]["properties"]["hole_diameter"], 8.0, "hole diameter")
    assert_close(csk[0]["properties"]["sink_diameter"], 12.0, "sink diameter")
    assert csk[0]["properties"]["lasered"] is True


def test_countersink_excluded_when_not_lasered() -> None:
    """should_countersinks_be_lasered=False -> secondary op: no pierce, no cut
    length (DFM-WARNINGS §Tube strategy line)."""
    golden = GOLDENS["tube-rect-csk-40x20-t3-d8-l120.step"]["tube_laser"]
    result = analyze(
        "tube-rect-csk-40x20-t3-d8-l120.step", inputs={"should_countersinks_be_lasered": False}
    )
    assert result.family_scalars["pierce_count"] == 0
    assert_close(
        result.family_scalars["total_cut_length"],
        golden["total_cut_length_not_lasered"],
        "cut length without lasered countersink",
    )
    csk = [f for f in result.features if f["name"] == "countersink"]
    assert len(csk) == 1 and csk[0]["properties"]["lasered"] is False


def test_plain_cutout_ignores_countersink_toggle() -> None:
    """The toggle only moves countersinks — a plain cutout always counts."""
    result = analyze(
        "tube-rect-cutout-40x20-t2-d10-l150.step",
        inputs={"should_countersinks_be_lasered": False},
    )
    golden = GOLDENS["tube-rect-cutout-40x20-t2-d10-l150.step"]["tube_laser"]
    assert result.family_scalars["pierce_count"] == golden["pierce_count"]
    assert_close(
        result.family_scalars["total_cut_length"], golden["total_cut_length"], "cut length"
    )


# --------------------------------------------------------------------------- #
# The honest path: non-tube bodies + input validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["cube-20mm.step", "block-milled-80x50x20.step"])
def test_non_tube_classifies_incompatible(name: str) -> None:
    """A body that matches no profile returns ``incompatible`` and nothing else
    — never a fabricated guess (build-plan M4.6 Decisions)."""
    result = analyze(name)
    assert result.family_scalars == {"stock_type": "incompatible"}
    assert result.features == []
    # dims-only outputs still present (the family-agnostic pass)
    assert result.dimensions.volume > 0


def test_feedback_stays_empty_until_m47() -> None:
    """DFM warnings are M4.7 — the recognizer never emits feedback."""
    for name in TUBE_FIXTURES:
        assert analyze(name).feedback == []


def test_invalid_strategy_inputs_are_rejected() -> None:
    step = (FIXTURES / "tube-rect-40x20-t2-l200.step").read_bytes()
    engine = get_engine()
    with pytest.raises(GeometryError):
        engine.analyze(
            step, family=FAMILY_TUBE_LASER, inputs={"max_angled_cut_threshold": float("nan")}
        )
    with pytest.raises(GeometryError):
        engine.analyze(step, family=FAMILY_TUBE_LASER, inputs={"max_angled_cut_threshold": -5.0})
    with pytest.raises(GeometryError):
        engine.analyze(
            step, family=FAMILY_TUBE_LASER, inputs={"should_countersinks_be_lasered": "yes"}
        )
