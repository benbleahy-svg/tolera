"""M4.1 — GeometryService core: dimensions + geometry signature (pure engine).

Tests the OCCT engine against the M4.0 analytic goldens (``fixtures/cad/
goldens.json``) and the frozen signature recipe (GEOMETRY.md §2). Geometry
asserts use the 0.1% relative tolerance the M4.0 probes gated on
(SEED-AND-FIXTURES Part 2: tolerances for geometry, exact for pricing);
signature asserts are exact equality — that is the point of the hash.

No DB, no API: the ``GeometryService`` contract takes STEP bytes and returns
plain dataclasses (no OCP type may leak — DECISIONS.md 2026-06-14).
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from app.geometry import (
    SIGNATURE_VERSION,
    AnalysisResult,
    MultiBodyError,
    StepParseError,
    get_engine,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
GOLDENS = json.loads((FIXTURES / "goldens.json").read_text(encoding="utf-8"))

#: The M4.0 probe gate: 0.1% relative error on volume/area/bbox.
GEOMETRY_RTOL = 1e-3

#: Single-body fixtures with analytic dims goldens (the assembly is excluded —
#: single-body invariant, INTERROGATION-ENGINE-SPEC §5.1).
DIMS_FIXTURES = sorted(
    name
    for name, golden in GOLDENS.items()
    if golden.get("family") != "assembly" and "volume" in golden and "bbox" in golden
)


def step_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def rel(measured: float, golden: float) -> float:
    return abs(measured - golden) / golden if golden else abs(measured - golden)


# --------------------------------------------------------------------------- #
# Dimensions vs analytic goldens
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", DIMS_FIXTURES)
def test_dimensions_match_goldens(name: str) -> None:
    """volume / area / sorted bbox dims within the Part-2 geometry tolerance."""
    golden = GOLDENS[name]
    result = get_engine().analyze(step_bytes(name))
    dims = result.dimensions

    assert rel(dims.volume, golden["volume"]) < GEOMETRY_RTOL
    assert rel(dims.area, golden["area"]) < GEOMETRY_RTOL

    got = [dims.size_x, dims.size_y, dims.size_z]
    expected = sorted(golden["bbox"], reverse=True)
    for measured, target in zip(got, expected, strict=True):
        assert rel(measured, target) < GEOMETRY_RTOL, (name, got, expected)

    # size_* ARE the max/med/min of the winning box (catalog §1: X = max dim of
    # the optimal bbox, …) — one source of truth for both attribute sets.
    assert (dims.size_x, dims.size_y, dims.size_z) == (dims.max_dim, dims.med_dim, dims.min_dim)
    assert dims.size_x >= dims.size_y >= dims.size_z > 0


def test_result_shape_is_m41_scope() -> None:
    """M4.1 populates dimensions only: family scalars/features/feedback stay
    empty (→ M4.2/M4.4-M4.7), and the result is a plain dataclass."""
    result = get_engine().analyze(step_bytes("cube-20mm.step"))
    assert isinstance(result, AnalysisResult)
    assert result.family is None
    assert result.family_scalars == {}
    assert result.features == []
    assert result.feedback == []
    assert result.confidence is None


def test_tighter_box_wins_on_bracket() -> None:
    """The M4.0 caveat made concrete: on the L-bracket, ``Bnd_OBB`` returns a
    LARGER box (~71.3x50x35.5) than the AABB (60x50x40) — the engine must take
    the tighter (min-volume) box for the optimal-bbox precedence slot
    (GEOMETRY.md §1)."""
    result = get_engine().analyze(step_bytes("bracket-L-60x40x2-r3.step"))
    dims = result.dimensions
    assert dims.bbox_source == "aabb"
    for measured, target in zip((dims.size_x, dims.size_y, dims.size_z), (60, 50, 40), strict=True):
        assert rel(measured, target) < GEOMETRY_RTOL


def test_weight_from_density() -> None:
    """weight_g = volume_mm3 / 1000 x density_g/cm3 (GEOMETRY.md §1: mind the
    mm3-to-cm3 factor). 20 mm cube @ 7.9 g/cm³ (1.4301) = 63.20 g."""
    engine = get_engine()
    with_density = engine.analyze(step_bytes("cube-20mm.step"), density_g_cm3=7.9)
    assert with_density.dimensions.weight is not None
    assert math.isclose(with_density.dimensions.weight, 63.2, rel_tol=GEOMETRY_RTOL)

    # No density → no weight (density is `man` — never invented; catalog §2).
    without = engine.analyze(step_bytes("cube-20mm.step"))
    assert without.dimensions.weight is None


# --------------------------------------------------------------------------- #
# Geometry signature (compute_signature) — exact equality
# --------------------------------------------------------------------------- #
def test_signature_topology_variant_pair_hashes_identically() -> None:
    """The M4.1 acceptance criterion: the M4.0 topology-variant pair (6-face
    cube vs the same solid with split side faces) yields the SAME hash —
    UnifySameDomain canonicalization is what makes the recipe
    topology-tolerant (GEOMETRY.md §2)."""
    engine = get_engine()
    single = engine.compute_signature(step_bytes("cube-20mm.step"))
    split = engine.compute_signature(step_bytes("cube-20mm-splitface.step"))
    assert single == split


def test_signature_is_placement_invariant() -> None:
    """Same solid rotated+translated in space → same hash (probe-a case).
    The rotated variant is constructed here exactly as in the M4.0 probe."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer

    reader = STEPControl_Reader()
    with tempfile.NamedTemporaryFile(suffix=".step") as src:
        src.write(step_bytes("cube-20mm.step"))
        src.flush()
        assert reader.ReadFile(src.name) == IFSelect_RetDone
    reader.TransferRoots()
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(7, -3, 11), gp_Dir(1, 2, 3)), math.radians(33.7))
    moved = BRepBuilderAPI_Transform(reader.OneShape(), tr, True).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(moved, STEPControl_AsIs)
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as dst:
        writer.Write(dst.name)
        rotated_bytes = Path(dst.name).read_bytes()
    Path(dst.name).unlink()

    engine = get_engine()
    assert engine.compute_signature(rotated_bytes) == engine.compute_signature(
        step_bytes("cube-20mm.step")
    )


def test_signature_distinct_parts_differ() -> None:
    engine = get_engine()
    assert engine.compute_signature(step_bytes("cube-20mm.step")) != engine.compute_signature(
        step_bytes("plate-hole-20x20x10-d8.step")
    )


def test_signature_is_deterministic_and_versioned() -> None:
    """Same body → the identical hash across repeated parse+hash runs (the
    M1.8 determinism discipline), carrying the recipe-version prefix so a
    future recipe change re-indexes instead of silently mismatching."""
    engine = get_engine()
    body = step_bytes("shaft-stepped-d30-d20-d12.step")
    hashes = {engine.compute_signature(body) for _ in range(3)}
    assert len(hashes) == 1
    (geom_hash,) = hashes
    assert geom_hash.startswith(f"{SIGNATURE_VERSION}:")
    assert len(geom_hash.split(":", 1)[1]) == 64  # sha256 hex


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def test_assembly_is_rejected() -> None:
    """Single-body invariant (INTERROGATION-ENGINE-SPEC §5.1): assemblies are
    decomposed first (M4.9b) — direct interrogation must refuse, not guess."""
    with pytest.raises(MultiBodyError) as exc:
        get_engine().analyze(step_bytes("asm-plate-2pins.step"))
    assert exc.value.solid_count == 3

    with pytest.raises(MultiBodyError):
        get_engine().compute_signature(step_bytes("asm-plate-2pins.step"))


def test_garbage_bytes_raise_parse_error() -> None:
    with pytest.raises(StepParseError):
        get_engine().analyze(b"not a step file at all")
