"""M4.2 — Sheet-metal unfold + bend detection (pure engine).

Tests ``analyze(family="SHEET_METAL")`` against the analytic sheet-metal
goldens (``fixtures/cad/goldens.json``): thickness, bend count/radius/angle/
line-length, the k-factor unfold (``k = (0.65 + 0.5*log10(r/t)) * 0.5``,
BASE_K frozen — build-plan M4.2), flat area, total cut length and pierce
count. The 3-bend fixture is the flagged mini-spike in executable form:
mixed bend directions, one non-90° bend, a through hole.

Geometry asserts use the M4.0 0.1% relative gate (as in M4.1); count asserts
are exact. No DB, no API.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.geometry import FAMILY_SHEET_METAL, AnalysisResult, get_engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
GOLDENS = json.loads((FIXTURES / "goldens.json").read_text(encoding="utf-8"))

GEOMETRY_RTOL = 1e-3

SHEET_FIXTURES = sorted(
    name for name, golden in GOLDENS.items() if golden.get("family") == "sheet_metal"
)


def analyze(name: str) -> AnalysisResult:
    return get_engine().analyze((FIXTURES / name).read_bytes(), family=FAMILY_SHEET_METAL)


def assert_close(measured: float, golden: float, what: str) -> None:
    assert measured == pytest.approx(golden, rel=GEOMETRY_RTOL), (
        f"{what}: {measured} vs golden {golden}"
    )


# --------------------------------------------------------------------------- #
# family_scalars vs the analytic goldens (the M4 exit criterion)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", SHEET_FIXTURES)
def test_sheet_metal_scalars_match_goldens(name: str) -> None:
    golden = GOLDENS[name]
    result = analyze(name)
    assert result.family == FAMILY_SHEET_METAL
    scalars = result.family_scalars

    assert_close(scalars["thickness"], golden["thickness"], "thickness")
    assert scalars["bend_count"] == golden["bend_count"]
    assert_close(scalars["flat_area"], golden["flat_area"], "flat_area")
    assert_close(scalars["total_cut_length"], golden["total_cut_length"], "total_cut_length")
    assert scalars["pierce_count"] == golden["pierce_count"]
    # unfolded size (k-factor developed length x width), within tolerance
    assert_close(scalars["size_x"], golden["unfolded_size"][0], "size_x (unfolded)")
    assert_close(scalars["size_y"], golden["unfolded_size"][1], "size_y (unfolded)")


@pytest.mark.parametrize("name", SHEET_FIXTURES)
def test_bend_features_match_goldens(name: str) -> None:
    """Each bend feature: name 'bend' (catalog), properties radius/angle/length
    + the per-bend k-factor; geometry_refs carried (empty until the viewer
    face-id export lands)."""
    golden = GOLDENS[name]
    result = analyze(name)
    bends = [f for f in result.features if f["name"] == "bend"]
    assert len(bends) == golden["bend_count"]

    expected = sorted(golden["bends"], key=lambda b: (b["angle_deg"], b["radius"]))
    measured = sorted(bends, key=lambda f: (f["properties"]["angle"], f["properties"]["radius"]))
    for feat, gold in zip(measured, expected, strict=True):
        props = feat["properties"]
        assert_close(props["radius"], gold["radius"], "bend radius")
        assert_close(props["angle"], gold["angle_deg"], "bend angle")
        assert_close(props["length"], gold["line_length"], "bend line length")
        assert_close(props["k_factor"], gold["k_factor"], "k_factor")
        assert feat["geometry_refs"] == []


@pytest.mark.parametrize("name", SHEET_FIXTURES)
def test_flat_pattern_bend_lines(name: str) -> None:
    """The thumbnail contract: unfolded outline dims + ordered bend-line
    positions along the developed length (the chain walk)."""
    golden = GOLDENS[name]
    pattern = analyze(name).family_scalars["flat_pattern"]
    assert_close(pattern["size_x"], golden["unfolded_size"][0], "flat_pattern.size_x")
    assert_close(pattern["size_y"], golden["unfolded_size"][1], "flat_pattern.size_y")
    positions = [line["position"] for line in pattern["bend_lines"]]
    assert positions == sorted(positions)
    for measured_pos, golden_pos in zip(positions, golden["bend_line_positions"], strict=True):
        assert_close(measured_pos, golden_pos, "bend line position")


def test_k_factor_formula_frozen() -> None:
    """BASE_K = 0.65 is NOT configurable (build-plan M4.2): the emitted k for
    the bracket must equal the spec formula exactly."""
    golden = GOLDENS["bracket-L-60x40x2-r3.step"]
    result = analyze("bracket-L-60x40x2-r3.step")
    (bend,) = [feature for feature in result.features if feature["name"] == "bend"]
    k = bend["properties"]["k_factor"]
    r, t = golden["bend_inner_radius"], golden["thickness"]
    assert k == pytest.approx((0.65 + 0.5 * math.log10(r / t)) * 0.5, rel=1e-9)


# --------------------------------------------------------------------------- #
# Degenerate and non-sheet bodies: return what was found, never fabricate
# --------------------------------------------------------------------------- #
def test_flat_plate_zero_bends() -> None:
    """A flat plate with a hole is the zero-bend case: thickness from the big
    face pair, no bends, one pierce, unfolded size = the plate itself."""
    golden = GOLDENS["plate-hole-20x20x10-d8.step"]
    result = get_engine().analyze(
        (FIXTURES / "plate-hole-20x20x10-d8.step").read_bytes(), family=FAMILY_SHEET_METAL
    )
    scalars = result.family_scalars
    assert_close(scalars["thickness"], 10.0, "thickness")
    assert scalars["bend_count"] == 0
    assert scalars["pierce_count"] == 1
    assert_close(scalars["flat_area"], golden["volume"] / 10.0, "flat_area")
    # mid-line cut = outer perimeter + hole circumference
    assert_close(scalars["total_cut_length"], 80 + 8 * math.pi, "total_cut_length")
    assert_close(scalars["size_x"], 20.0, "size_x")
    assert_close(scalars["size_y"], 20.0, "size_y")
    assert result.features == []


def test_milled_billet_yields_no_sheet_scalars() -> None:
    """A machined block assigned a sheet-metal process must return NO scalars
    (constant-thickness gate): flat_area/cut_length identities on a billet
    would be arithmetic dressed up as measurement (fresh-eyes review)."""
    result = get_engine().analyze(
        (FIXTURES / "block-milled-80x50x20.step").read_bytes(), family=FAMILY_SHEET_METAL
    )
    assert result.family_scalars == {}
    assert result.features == []


def test_cube_yields_no_sheet_scalars() -> None:
    """Same gate for the degenerate cube — three 'skin pairs', none a sheet."""
    result = get_engine().analyze(
        (FIXTURES / "cube-20mm.step").read_bytes(), family=FAMILY_SHEET_METAL
    )
    assert result.family_scalars == {}


def test_dims_only_run_unchanged() -> None:
    """No family → the M4.1 dims-only pass: empty scalars and features."""
    result = get_engine().analyze((FIXTURES / "bracket-L-60x40x2-r3.step").read_bytes())
    assert result.family is None
    assert result.family_scalars == {}
    assert result.features == []


def test_unknown_family_returns_dims_only() -> None:
    """A family without a recognizer (M4.5+ families) degrades to dims-only —
    no fabricated scalars."""
    result = get_engine().analyze(
        (FIXTURES / "bracket-L-60x40x2-r3.step").read_bytes(), family="LATHE"
    )
    assert result.family == "LATHE"
    assert result.family_scalars == {}
