"""M4.4 — Milling setup-detection + runtime estimation (pure engine).

Tests ``analyze(family="MILLING")`` against the analytic milling goldens
(``fixtures/cad/goldens.json``, key ``milling``): deterministic setup
allocation (greedy direction cover, ordered by attributed removal volume),
the in-house runtime heuristic (roughing volume + drilling depths + profiled
/ surfaced areas — GEOMETRY.md §4: runtime has NO OCCT support, in-house is
the designed path), and the confidence rubric (KB milling-feature-iteration:
parameterized-removal fraction, "usually above 80%" = High).

Feature taxonomy follows the KB feature reference (milling-feature-iteration):
``machine_direction`` / ``hole`` / ``circular_pocket`` / ``pocket`` are
FEATURES; chamfer/fillet/tapered-wall/tight-corner/uncut-face objects are
FEEDBACK and land with the DFM catalogue (M4.7) — ``feedback`` stays empty
here.

Geometry asserts use the M4.0 0.1% relative gate (as in M4.1/M4.2); count and
confidence asserts are exact. No DB, no API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.geometry import FAMILY_MILLING, RECOGNIZED_FAMILIES, AnalysisResult, get_engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
GOLDENS = json.loads((FIXTURES / "goldens.json").read_text(encoding="utf-8"))

GEOMETRY_RTOL = 1e-3

#: Fixtures carrying a milling golden (setups/runtime/confidence).
MILL_FIXTURES = sorted(name for name, golden in GOLDENS.items() if "milling" in golden)


def analyze(name: str, inputs: dict[str, Any] | None = None) -> AnalysisResult:
    return get_engine().analyze(
        (FIXTURES / name).read_bytes(), family=FAMILY_MILLING, inputs=inputs
    )


def assert_close(measured: float, golden: float, what: str) -> None:
    assert measured == pytest.approx(golden, rel=GEOMETRY_RTOL, abs=1e-9), (
        f"{what}: {measured} vs golden {golden}"
    )


def machine_direction_of(setup: dict[str, Any]) -> dict[str, Any]:
    (md,) = (f for f in setup["features"] if f["name"] == "machine_direction")
    return dict(md)


def test_milling_family_is_recognized() -> None:
    assert FAMILY_MILLING in RECOGNIZED_FAMILIES


# --------------------------------------------------------------------------- #
# Setups + runtime + confidence vs the analytic goldens (the acceptance core)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", MILL_FIXTURES)
def test_setups_match_goldens(name: str) -> None:
    golden = GOLDENS[name]["milling"]
    result = analyze(name)
    assert result.family == FAMILY_MILLING
    scalars = result.family_scalars

    assert scalars["setup_count"] == golden["setup_count"]
    assert len(scalars["setups"]) == golden["setup_count"]
    # aggregate scalars for the Kalk single-operation pattern
    # (KB milling-process example 1: mill3.runtime / mill3.setup_time)
    assert_close(scalars["runtime"], golden["runtime_hr"], "runtime (hr)")
    assert_close(scalars["setup_time"], golden["setup_time_hr"], "setup_time (hr)")
    assert result.confidence == golden["confidence"]

    for i, (setup, gold) in enumerate(zip(scalars["setups"], golden["setups"], strict=True)):
        assert setup["confidence"] == gold["confidence"], f"setup[{i}] confidence"
        assert_close(setup["setup_time"], gold["setup_time_hr"], f"setup[{i}] setup_time")
        assert_close(setup["runtime"], gold["runtime_hr"], f"setup[{i}] runtime")
        for axis, (measured, expected) in enumerate(
            zip(setup["direction"], gold["direction"], strict=True)
        ):
            assert measured == pytest.approx(expected, abs=1e-6), f"setup[{i}] dir[{axis}]"
        assert setup["feedback"] == []  # DFM warnings arrive with M4.7


@pytest.mark.parametrize("name", MILL_FIXTURES)
def test_machine_direction_areas_match_goldens(name: str) -> None:
    """Each setup carries a ``machine_direction`` feature with the KB area
    split: profiled (walls, parallel to the direction), derived (floors,
    perpendicular), surfaced (neither — tapers/freeform)."""
    golden = GOLDENS[name]["milling"]
    result = analyze(name)
    for i, (setup, gold) in enumerate(
        zip(result.family_scalars["setups"], golden["setups"], strict=True)
    ):
        props = machine_direction_of(setup)["properties"]
        expected = gold["machine_direction"]
        for key in ("profiled_area", "derived_area", "surfaced_area"):
            assert_close(props[key], expected[key], f"setup[{i}] {key}")
        assert_close(
            props["area"],
            expected["profiled_area"] + expected["derived_area"] + expected["surfaced_area"],
            f"setup[{i}] area",
        )


@pytest.mark.parametrize("name", MILL_FIXTURES)
def test_hole_features_match_goldens(name: str) -> None:
    """Hole features (KB reference: area/volume/depth/bottom_type/min_radius)
    grouped by (bottom_type, diameter) match the golden counts + measures."""
    golden = GOLDENS[name]["milling"]
    result = analyze(name)
    holes = [f for f in result.features if f["name"] == "hole"]
    assert len(holes) == sum(g["count"] for g in golden["holes"])
    for gold in golden["holes"]:
        matched = [
            h
            for h in holes
            if h["properties"]["bottom_type"] == gold["bottom_type"]
            and h["properties"]["min_radius"] == pytest.approx(gold["diameter"] / 2, rel=1e-6)
        ]
        assert len(matched) == gold["count"], f"holes {gold['bottom_type']} d{gold['diameter']}"
        for hole in matched:
            props = hole["properties"]
            assert_close(props["depth"], gold["depth"], "hole depth")
            assert_close(props["volume"], gold["volume"], "hole volume")
            assert_close(props["area"], gold["area"], "hole area")


@pytest.mark.parametrize("name", MILL_FIXTURES)
def test_pocket_features_match_goldens(name: str) -> None:
    golden = GOLDENS[name]["milling"]
    result = analyze(name)
    pockets = [f for f in result.features if f["name"] == "pocket"]
    assert len(pockets) == len(golden["pockets"])
    measured = sorted(pockets, key=lambda f: f["properties"]["volume"])
    expected = sorted(golden["pockets"], key=lambda p: p["volume"])
    for feat, gold in zip(measured, expected, strict=True):
        props = feat["properties"]
        assert_close(props["area"], gold["area"], "pocket area")
        assert_close(props["volume"], gold["volume"], "pocket volume")
        assert_close(props["max_depth"], gold["max_depth"], "pocket max_depth")
        assert props["bottom_type"] == gold["bottom_type"]
        assert props["has_transition"] == gold["has_transition"]


# --------------------------------------------------------------------------- #
# The honest ceiling: low confidence + never fabricate
# --------------------------------------------------------------------------- #
def test_low_confidence_dome() -> None:
    """The freeform dome removes ~68% of the material without a parameterized
    feature → confidence Low on the result AND every setup — the designed
    signal to fall back to a manual runtime override (build-plan M4.4)."""
    result = analyze("block-dome-50x50x20.step")
    assert result.confidence == "Low"
    assert all(s["confidence"] == "Low" for s in result.family_scalars["setups"])
    # the estimate still exists (overridable), it is just not trusted
    assert result.family_scalars["runtime"] > 0


def test_blank_body_yields_no_setups() -> None:
    """A bare prismatic blank (nothing to mill) returns zero setups and zero
    runtime — never a fabricated setup."""
    result = analyze("cube-20mm.step")
    scalars = result.family_scalars
    assert scalars["setup_count"] == 0
    assert scalars["setups"] == []
    assert scalars["runtime"] == 0.0
    assert scalars["setup_time"] == 0.0


def test_other_family_yields_no_milling_scalars() -> None:
    """Family gating: the milled block analyzed WITHOUT a family stays a
    dims-only pass (M4.1 behaviour unchanged)."""
    engine = get_engine()
    result = engine.analyze((FIXTURES / "block-milled-80x50x20.step").read_bytes())
    assert result.family_scalars == {}
    assert result.features == []
    assert result.confidence is None


# --------------------------------------------------------------------------- #
# Strategy inputs (metric defaults; KB milling-interrogation semantics)
# --------------------------------------------------------------------------- #
def test_maximum_hole_diameter_reclassifies_to_circular_pocket() -> None:
    """Holes wider than ``maximum_hole_diameter`` become circular pockets
    (profiled, not drilled) — KB milling-interrogation 'Set Max Hole
    Diameter'. Override 7 mm: the two d8 through holes reclassify, d6 stays."""
    result = analyze("block-milled-80x50x20.step", inputs={"maximum_hole_diameter": 7.0})
    pockets = [f for f in result.features if f["name"] == "circular_pocket"]
    holes = [f for f in result.features if f["name"] == "hole"]
    assert len(pockets) == 2
    assert all(p["properties"]["bottom_type"] == "thru" for p in pockets)
    assert len(holes) == 1
    assert holes[0]["properties"]["min_radius"] == pytest.approx(3.0, rel=1e-6)
    assert result.family_scalars["setup_count"] == 1
    assert result.family_scalars["runtime"] > 0


def test_depth_profiling_threshold_degrades_confidence() -> None:
    """Walls deeper than ``depth_profiling_threshold`` cannot be profiled with
    the declared strategy: their area drops out of the setup and the estimate
    is no longer High — never silently priced as if reachable."""
    result = analyze("block-milled-80x50x20.step", inputs={"depth_profiling_threshold": 5.0})
    assert result.confidence == "Medium"
    (setup,) = result.family_scalars["setups"]
    assert machine_direction_of(setup)["properties"]["profiled_area"] == pytest.approx(
        0.0, abs=1e-9
    )


def test_depth_surfacing_threshold_uncovers_freeform() -> None:
    """The dome (10 mm deep) with ``depth_surfacing_threshold`` 5 mm: the
    sphere face is no longer surfaceable → excluded from the setup's surfaced
    area and from runtime; confidence stays Low."""
    default = analyze("block-dome-50x50x20.step")
    result = analyze("block-dome-50x50x20.step", inputs={"depth_surfacing_threshold": 5.0})
    assert result.confidence == "Low"
    (setup,) = result.family_scalars["setups"]
    assert machine_direction_of(setup)["properties"]["surfaced_area"] == pytest.approx(
        0.0, abs=1e-9
    )
    assert result.family_scalars["runtime"] < default.family_scalars["runtime"]


def test_minimum_area_for_setup_gates_surfacing_setup() -> None:
    """The bevel body's only work is a 400 mm² tapered face: below the default
    1000 mm² gate no setup is created (the face stays uncovered, confidence
    Low, runtime 0 — manual override territory); lowering the gate under
    400 mm² allocates the -Z surfacing setup and the estimate appears."""
    gated = analyze("block-bevel-40x40x20.step")
    assert gated.family_scalars["setup_count"] == 0
    assert gated.family_scalars["runtime"] == 0.0
    assert gated.confidence == "Low"

    allocated = analyze("block-bevel-40x40x20.step", inputs={"minimum_area_for_setup": 300.0})
    scalars = allocated.family_scalars
    assert scalars["setup_count"] == 1
    (setup,) = scalars["setups"]
    assert setup["direction"] == pytest.approx([0.0, 0.0, -1.0], abs=1e-6)
    props = machine_direction_of(setup)["properties"]
    assert_close(props["surfaced_area"], 400.0, "bevel surfaced_area")
    # runtime = leftover roughing (960 mm3) + surfacing (400 mm2), heuristic
    # constants mirrored in gen_fixtures.py
    assert_close(scalars["runtime"], (960.0 / 15000.0 + 400.0 / 1500.0) / 60.0, "bevel runtime")
    assert allocated.confidence == "Low"  # nothing is feature-parameterized
