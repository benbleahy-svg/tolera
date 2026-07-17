"""M4.11 — the ``gv1`` similarity feature vector (pure builder, no OCP/DB).

The Part-Library "Similar Geometries" bucket runs pgvector ANN over a
deterministic scalar feature vector (spec ``#partlib``: the decided v1 —
learned embeddings are post-pilot). The builder maps a persisted
``AnalysisResult`` dict to a fixed-dimension vector; these tests pin the
recipe so a silent change can't corrupt the index (same rationale as the
``gs1`` signature freeze, DECISIONS.md 2026-07-16).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from app.geometry.vector import (
    GV_DIM,
    GV_VERSION,
    SIMILAR_L2_THRESHOLD,
    build_geometry_vector,
)

#: A minimal succeeded-run result for a 20 mm cube (analytic golden).
CUBE: dict[str, Any] = {
    "family": None,
    "dimensions": {
        "size_x": 20.0,
        "size_y": 20.0,
        "size_z": 20.0,
        "max_dim": 20.0,
        "med_dim": 20.0,
        "min_dim": 20.0,
        "area": 2400.0,
        "volume": 8000.0,
        "weight": None,
        "bbox_source": "obb",
    },
    "family_scalars": {},
    "features": [],
    "feedback": [],
    "confidence": None,
}


def test_version_and_dimension_frozen() -> None:
    assert GV_VERSION == "gv1"
    assert GV_DIM == 10
    vec = build_geometry_vector(CUBE)
    assert vec is not None
    assert len(vec) == GV_DIM


def test_cube_vector_exact_math() -> None:
    """Every slot is plain arithmetic on the dims — pinned exactly."""
    vec = build_geometry_vector(CUBE)
    assert vec is not None
    log1p = math.log1p
    assert vec[0] == pytest.approx(log1p(20.0))  # size_x (max)
    assert vec[1] == pytest.approx(log1p(20.0))  # size_y (med)
    assert vec[2] == pytest.approx(log1p(20.0))  # size_z (min)
    assert vec[3] == pytest.approx(log1p(8000.0))  # volume mm³
    assert vec[4] == pytest.approx(log1p(2400.0))  # area mm²
    assert vec[5] == 0.0  # hole count — none
    assert vec[6] == 0.0  # bend count — none
    assert vec[7] == pytest.approx(log1p(1.0))  # aspect max/min
    assert vec[8] == pytest.approx(1.0)  # fill ratio: cube fills its bbox
    assert vec[9] == pytest.approx(log1p(2400.0 / 8000.0))  # thinness area/vol


def test_hole_count_from_milling_features() -> None:
    """Milling holes live in ``features`` (name ``hole``/``circular_pocket``)."""
    result = {
        **CUBE,
        "features": [
            {"name": "hole", "properties": {}},
            {"name": "hole", "properties": {}},
            {"name": "circular_pocket", "properties": {}},
            {"name": "pocket", "properties": {}},  # not a hole
            {"name": "machine_direction", "properties": {}},
        ],
    }
    vec = build_geometry_vector(result)
    assert vec is not None
    assert vec[5] == pytest.approx(math.log1p(3.0))


def test_sheet_metal_scalars() -> None:
    """Sheet metal: ``bend_count`` + ``pierce_count`` family scalars."""
    result = {
        **CUBE,
        "family": "sheet_metal",
        "family_scalars": {"bend_count": 3, "pierce_count": 2, "thickness": 2.0},
    }
    vec = build_geometry_vector(result)
    assert vec is not None
    assert vec[5] == pytest.approx(math.log1p(2.0))  # pierces are the holes
    assert vec[6] == pytest.approx(math.log1p(3.0))


def test_missing_or_degenerate_dimensions_yield_no_vector() -> None:
    assert build_geometry_vector({}) is None
    assert build_geometry_vector({"dimensions": {}}) is None
    flat = {**CUBE, "dimensions": {**CUBE["dimensions"], "volume": 0.0}}
    assert build_geometry_vector(flat) is None
    nulled = {**CUBE, "dimensions": {**CUBE["dimensions"], "size_z": None}}
    assert build_geometry_vector(nulled) is None
    # NaN/Inf sneak past ordering comparisons; pgvector rejects them at
    # write time — the builder must refuse them up front.
    for bad in (math.nan, math.inf):
        broken = {**CUBE, "dimensions": {**CUBE["dimensions"], "volume": bad}}
        assert build_geometry_vector(broken) is None


def test_deterministic() -> None:
    assert build_geometry_vector(CUBE) == build_geometry_vector(CUBE)


# --------------------------------------------------------------------------- #
# Threshold calibration pins (real engine, fixtures/cad — M4.11 acceptance)
# --------------------------------------------------------------------------- #
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"


def _fixture_vector(name: str) -> list[float]:
    from dataclasses import asdict

    from app.geometry import get_engine

    result = asdict(get_engine().analyze((FIXTURES / name).read_bytes()))
    vec = build_geometry_vector(result)
    assert vec is not None, f"{name} produced no vector"
    return vec


def _l2(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def test_topology_variant_pair_distance_zero() -> None:
    """Same manufactured geometry → identical vector (the exact-match twin)."""
    a = _fixture_vector("cube-20mm.step")
    b = _fixture_vector("cube-20mm-splitface.step")
    assert _l2(a, b) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # Same tube section, one d10 cutout vs plain — the near-neighbour pair.
        ("tube-rect-40x20-t2-l200.step", "tube-rect-cutout-40x20-t2-d10-l150.step"),
        # Prismatic blocks of comparable envelope.
        ("block-3setups-60x40x20.step", "block-dome-50x50x20.step"),
    ],
)
def test_similar_pairs_fall_under_threshold(left: str, right: str) -> None:
    assert _l2(_fixture_vector(left), _fixture_vector(right)) < SIMILAR_L2_THRESHOLD


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("cube-20mm.step", "tube-round-d30-t2-l200.step"),
        ("plate-hole-20x20x10-d8.step", "tube-rect-40x20-t2-l200.step"),
        ("bracket-tightbend-t2-r1.step", "block-milled-80x50x20.step"),
    ],
)
def test_dissimilar_pairs_exceed_threshold(left: str, right: str) -> None:
    assert _l2(_fixture_vector(left), _fixture_vector(right)) > SIMILAR_L2_THRESHOLD
