"""M4.5 — Lathe stock recommendation + turning features (pure engine).

Tests ``analyze(family="LATHE")`` against the analytic lathe goldens
(``fixtures/cad/goldens.json``, key ``lathe``). The v1 scope is pinned by the
v2.15 decision (spec ``#geometry-engine``; DECISIONS.md 2026-07-14 M4.0 GO):
**attributes + recommended stock, no full turning feature tree** — the
load-bearing outputs are ``stock_radius`` / ``stock_length`` / ``setup_count``
(GEOMETRY.md §5: stock recommendation probed exact), the radial-vs-axial cut
distinction is carried as aggregate ``external_cut`` / ``internal_cut``
feature properties, and off-axis work is **flagged, not costed**
(``off_axis_hole`` / ``asymmetric_cavity`` live-tooling callouts).

Geometry asserts use the M4.0 0.1% relative gate (as in M4.1/M4.2/M4.4);
count asserts are exact. Lathe emits NO runtime and NO confidence
(INTERROGATION-ENGINE-SPEC §2 gives those to milling only). No DB, no API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.geometry import (
    FAMILY_LATHE,
    RECOGNIZED_FAMILIES,
    AnalysisResult,
    GeometryError,
    get_engine,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
GOLDENS = json.loads((FIXTURES / "goldens.json").read_text(encoding="utf-8"))

GEOMETRY_RTOL = 1e-3

#: Fixtures carrying a lathe golden (stock/setups/cut split).
LATHE_FIXTURES = sorted(name for name, golden in GOLDENS.items() if "lathe" in golden)


def analyze(name: str, inputs: dict[str, Any] | None = None) -> AnalysisResult:
    return get_engine().analyze((FIXTURES / name).read_bytes(), family=FAMILY_LATHE, inputs=inputs)


def assert_close(measured: float, golden: float, what: str) -> None:
    assert measured == pytest.approx(golden, rel=GEOMETRY_RTOL, abs=1e-9), (
        f"{what}: {measured} vs golden {golden}"
    )


def features_named(result: AnalysisResult, name: str) -> list[dict[str, Any]]:
    return [f for f in result.features if f["name"] == name]


def test_lathe_family_is_recognized() -> None:
    assert FAMILY_LATHE in RECOGNIZED_FAMILIES


# --------------------------------------------------------------------------- #
# Recommended stock + setups vs the analytic goldens (the acceptance core)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", LATHE_FIXTURES)
def test_stock_and_setups_match_goldens(name: str) -> None:
    golden = GOLDENS[name]["lathe"]
    result = analyze(name)
    assert result.family == FAMILY_LATHE
    scalars = result.family_scalars

    assert_close(scalars["stock_radius"], golden["stock_radius"], "stock_radius (mm)")
    assert_close(scalars["stock_length"], golden["stock_length"], "stock_length (mm)")
    assert scalars["setup_count"] == golden["setup_count"]

    setups = features_named(result, "setup")
    assert len(setups) == golden["setup_count"]
    for i, (setup, direction) in enumerate(zip(setups, golden["setup_directions"], strict=True)):
        for axis, (measured, expected) in enumerate(
            zip(setup["properties"]["direction"], direction, strict=True)
        ):
            assert measured == pytest.approx(expected, abs=1e-6), f"setup[{i}] dir[{axis}]"

    # lathe never estimates runtime -> no confidence rating (sub-spec §2)
    assert result.confidence is None
    assert result.feedback == []  # DFM warnings arrive with M4.7


@pytest.mark.parametrize("name", LATHE_FIXTURES)
def test_lathe_stock_feature_matches_goldens(name: str) -> None:
    """The viewer's Lathe Stock tree entry (DemoN/04): one feature carrying
    the recommended cylindrical stock."""
    golden = GOLDENS[name]["lathe"]
    (stock,) = features_named(analyze(name), "lathe_stock")
    props = stock["properties"]
    assert_close(props["radius"], golden["stock_radius"], "lathe_stock radius")
    assert_close(props["diameter"], 2 * golden["stock_radius"], "lathe_stock diameter")
    assert_close(props["length"], golden["stock_length"], "lathe_stock length")


# --------------------------------------------------------------------------- #
# External / internal cuts — the radial-vs-axial distinction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", LATHE_FIXTURES)
def test_external_cut_split_matches_goldens(name: str) -> None:
    golden = GOLDENS[name]["lathe"]["external_cut"]
    (external,) = features_named(analyze(name), "external_cut")
    props = external["properties"]
    assert_close(props["axial_area"], golden["axial_area"], "external axial_area")
    assert_close(props["radial_area"], golden["radial_area"], "external radial_area")
    assert_close(props["area"], golden["axial_area"] + golden["radial_area"], "external area")


@pytest.mark.parametrize("name", LATHE_FIXTURES)
def test_internal_cuts_match_goldens(name: str) -> None:
    golden = GOLDENS[name]["lathe"]["internal_cuts"]
    internals = features_named(analyze(name), "internal_cut")
    assert len(internals) == len(golden)
    for i, (feature, gold) in enumerate(zip(internals, golden, strict=True)):
        props = feature["properties"]
        assert_close(props["radius"], gold["radius"], f"internal[{i}] radius")
        assert_close(props["diameter"], gold["diameter"], f"internal[{i}] diameter")
        assert_close(props["depth"], gold["depth"], f"internal[{i}] depth")
        assert props["thru"] is gold["thru"], f"internal[{i}] thru"
        assert_close(props["axial_area"], gold["axial_area"], f"internal[{i}] axial_area")
        assert_close(props["radial_area"], gold["radial_area"], f"internal[{i}] radial_area")


# --------------------------------------------------------------------------- #
# Live-tooling callouts — flagged, not costed (GEOMETRY.md §5)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", LATHE_FIXTURES)
def test_off_axis_holes_match_goldens(name: str) -> None:
    golden = GOLDENS[name]["lathe"]["off_axis_holes"]
    holes = features_named(analyze(name), "off_axis_hole")
    assert len(holes) == golden["count"]
    for hole in holes:
        props = hole["properties"]
        assert_close(props["diameter"], golden["diameter"], "off_axis diameter")
        assert_close(props["depth"], golden["depth"], "off_axis depth")


@pytest.mark.parametrize("name", LATHE_FIXTURES)
def test_asymmetric_faces_match_goldens(name: str) -> None:
    golden = GOLDENS[name]["lathe"]["asymmetric_faces"]
    cavities = features_named(analyze(name), "asymmetric_cavity")
    if golden == 0:
        assert cavities == []
    else:
        (cavity,) = cavities
        assert cavity["properties"]["face_count"] == golden


def test_flatted_shaft_flags_asymmetric_cavity() -> None:
    """A milled flat on a turned shaft is live-tooling work: the body stays
    turnable (stock + setups recognized) and the flat is FLAGGED as an
    asymmetric cavity, never silently costed (capability map: flagged, not
    costed). The STEP is built in-test (the M4.1 transform-test precedent)."""
    import tempfile

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    shaft = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 15.0, 60.0).Shape()
    # flat at x = 13: box spanning the flat's half-space over the full length
    box = BRepPrimAPI_MakeBox(gp_Pnt(13.0, -20.0, -1.0), gp_Pnt(30.0, 20.0, 61.0)).Shape()
    flatted = BRepAlgoAPI_Cut(shaft, box).Shape()

    writer = STEPControl_Writer()
    assert writer.Transfer(flatted, STEPControl_AsIs) == IFSelect_RetDone
    with tempfile.NamedTemporaryFile(suffix=".step") as f:
        assert writer.Write(f.name) == IFSelect_RetDone
        step_bytes = Path(f.name).read_bytes()

    result = get_engine().analyze(step_bytes, family=FAMILY_LATHE)
    scalars = result.family_scalars
    assert_close(scalars["stock_radius"], 15.0, "flatted stock_radius")
    assert_close(scalars["stock_length"], 60.0, "flatted stock_length")
    assert scalars["setup_count"] == 1
    (cavity,) = features_named(result, "asymmetric_cavity")
    assert cavity["properties"]["face_count"] == 1
    # flat plane area = length x chord width, w = 2*sqrt(r^2 - d^2)
    assert_close(cavity["properties"]["area"], 60.0 * 2 * (225 - 169) ** 0.5, "flat area")


# --------------------------------------------------------------------------- #
# Honest ceilings: never fabricate on a non-turned body; junk inputs rejected
# --------------------------------------------------------------------------- #
def test_non_turned_body_yields_nothing() -> None:
    """A milled block assigned a LATHE process must yield NO scalars and NO
    features — a fabricated stock recommendation for a prismatic body would
    be arithmetic dressed up as measurement (the M4.2 constant-thickness-gate
    precedent)."""
    result = get_engine().analyze(
        (FIXTURES / "block-milled-80x50x20.step").read_bytes(), family=FAMILY_LATHE
    )
    assert result.family_scalars == {}
    assert result.features == []
    # the family-agnostic dims pass still ran (M4.1 core)
    assert result.dimensions.volume > 0


def test_mostly_prismatic_body_with_a_bore_yields_nothing() -> None:
    """A plate with one drilled hole HAS a cylinder (a candidate axis) but is
    not a turned part — the coaxial-coverage gate must reject it."""
    result = get_engine().analyze(
        (FIXTURES / "plate-hole-20x20x10-d8.step").read_bytes(), family=FAMILY_LATHE
    )
    assert result.family_scalars == {}
    assert result.features == []


@pytest.mark.parametrize(
    "inputs",
    [
        {"max_tool_protrusion_length": -1.0},
        {"axial_max_hooked_tool_radius": float("nan")},
        {"radial_max_hooked_tool_radius": "wide"},
        {"should_perform_live_tooling": "yes"},
    ],
)
def test_junk_strategy_inputs_are_rejected(inputs: dict[str, Any]) -> None:
    """Strategy inputs become org-authorable with custom interrogations
    (M4.8) — reject junk at the boundary (the M4.4 milling precedent)."""
    with pytest.raises(GeometryError):
        analyze("shaft-stepped-d30-d20-d12.step", inputs=inputs)


def test_analysis_is_deterministic() -> None:
    """Same body -> identical scalars + features across runs (the M1.8 / M4.1
    determinism discipline)."""
    a = analyze("shaft-stepped-d30-d20-d12.step")
    b = analyze("shaft-stepped-d30-d20-d12.step")
    assert a.family_scalars == b.family_scalars
    assert a.features == b.features
