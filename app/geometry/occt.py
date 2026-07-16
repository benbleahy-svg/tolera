"""OCCT-backed ``GeometryService`` — the ONLY module that imports OCP (M4.1).

Productionizes the M4.0 probe scaffold (``scripts/spike-m4.0/common.py``)
behind the :mod:`app.geometry.contract` boundary. Everything OCP-specific stays
inside this file: callers see STEP bytes in, dataclasses out. OCP is installed
in the Celery worker image only (DECISIONS.md 2026-07-16), so this module must
be imported lazily — via :func:`app.geometry.get_engine`, never at module scope
of API code.

Signature recipe (frozen as ``gs1`` — GEOMETRY.md §2, spec ``#geometry-engine``):
``ShapeUpgrade_UnifySameDomain`` canonicalization → payload of quantized
(volume, area, OBB-sorted dims, face/edge-type histograms, per-type areas) at
6 significant digits → SHA-256. Proven byte-identical across macOS arm64 and
linux aarch64 (M4.0 ``hashes_*.json``). Known limitation: placement-invariant
by construction, so mirror (chiral) parts hash identically — matches stay
suggestions (M4.11). Re-validate the 6-digit freeze when the real Fechner
fixtures land (DECISIONS.md 2026-07-12 OPEN).
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections import Counter
from typing import Any

from OCP.Bnd import Bnd_Box, Bnd_OBB
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

from .contract import (
    SIGNATURE_VERSION,
    AnalysisResult,
    Dimensions,
    GeometryError,
    MultiBodyError,
    StepParseError,
)

#: Quantization for the gs1 fingerprint — 6 significant digits passed every
#: M4.0 stability case (4/6/8 all passed; 6 is the probe's verdict recipe).
_SIG_DIGITS = 6

# GeomAbs surface/curve type enums → stable names (same tables as the probe;
# the names are part of the hashed payload, so they are FROZEN with gs1).
_SURFACE_TYPES = {
    0: "plane",
    1: "cylinder",
    2: "cone",
    3: "sphere",
    4: "torus",
    5: "bezier",
    6: "bspline",
    7: "revolution",
    8: "extrusion",
    9: "offset",
    10: "other",
}
_CURVE_TYPES = {
    0: "line",
    1: "circle",
    2: "ellipse",
    3: "hyperbola",
    4: "parabola",
    5: "bezier",
    6: "bspline",
    7: "offset",
    8: "other",
}


def _read_step(step_bytes: bytes) -> TopoDS_Shape:
    """Parse STEP bytes into a single shape; enforce the single-solid invariant.

    ``STEPControl_Reader`` only reads from a path, so the bytes go through a
    temp file (deleted immediately after the parse)."""
    reader = STEPControl_Reader()
    with tempfile.NamedTemporaryFile(suffix=".step") as f:
        f.write(step_bytes)
        f.flush()
        if reader.ReadFile(f.name) != IFSelect_RetDone:
            raise StepParseError("not a readable STEP file")
    if reader.TransferRoots() == 0:
        raise StepParseError("STEP transfer produced no shapes")
    shape = reader.OneShape()
    solids = _count(shape, TopAbs_SOLID)
    if solids == 0:
        # Surface/wireframe-only STEP: not an assembly — a body we can't interrogate.
        raise StepParseError("STEP contains no solid body")
    if solids > 1:
        raise MultiBodyError(solids)
    return shape


def _count(shape: TopoDS_Shape, kind: Any) -> int:
    n = 0
    ex = TopExp_Explorer(shape, kind)
    while ex.More():
        n += 1
        ex.Next()
    return n


def _volume_area(shape: TopoDS_Shape) -> tuple[float, float]:
    vp, sp = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    BRepGProp.SurfaceProperties_s(shape, sp)
    return vp.Mass(), sp.Mass()


def _aabb_dims(shape: TopoDS_Shape) -> list[float]:
    box = Bnd_Box()
    box.SetGap(0.0)
    BRepBndLib.Add_s(shape, box, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return [x1 - x0, y1 - y0, z1 - z0]


def _obb_dims(shape: TopoDS_Shape) -> list[float]:
    obb = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, obb, True, True, False)
    return [2 * obb.XHSize(), 2 * obb.YHSize(), 2 * obb.ZHSize()]


def _winning_box(shape: TopoDS_Shape) -> tuple[list[float], str]:
    """The tighter of OBB/AABB by volume, dims sorted descending.

    ``Bnd_OBB(theIsOptimal)`` is PCA-approximate and can return a box LARGER
    than the AABB (M4.0: bracket 71.3x50x35.5 vs 60x50x40) — the min-volume
    box fills the catalog's optimal-bbox precedence slot (GEOMETRY.md §1)."""
    obb = _obb_dims(shape)
    aabb = _aabb_dims(shape)
    obb_vol = obb[0] * obb[1] * obb[2]
    aabb_vol = aabb[0] * aabb[1] * aabb[2]
    if obb_vol <= aabb_vol:
        return sorted(obb, reverse=True), "obb"
    return sorted(aabb, reverse=True), "aabb"


def _face_histogram(shape: TopoDS_Shape) -> tuple[Counter[str], dict[str, float]]:
    hist: Counter[str] = Counter()
    areas: dict[str, float] = {}
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        kind = _SURFACE_TYPES.get(BRepAdaptor_Surface(face).GetType(), "other")
        hist[kind] += 1
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        areas[kind] = areas.get(kind, 0.0) + props.Mass()
        ex.Next()
    return hist, areas


def _edge_histogram(shape: TopoDS_Shape) -> Counter[str]:
    hist: Counter[str] = Counter()
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        edge = TopoDS.Edge_s(ex.Current())
        hist[_CURVE_TYPES.get(BRepAdaptor_Curve(edge).GetType(), "other")] += 1
        ex.Next()
    return hist


def _canonicalize(shape: TopoDS_Shape) -> TopoDS_Shape:
    """Merge same-domain faces/edges — the split-face tolerance that makes the
    fingerprint topology-tolerant (raw histograms fail the M4.0 split pair)."""
    unify = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
    unify.Build()
    return unify.Shape()


def _q(value: float, sig: int = _SIG_DIGITS) -> str:
    return f"{value:.{sig}g}"


def _fingerprint(shape: TopoDS_Shape) -> str:
    canonical = _canonicalize(shape)
    volume, area = _volume_area(canonical)
    dims = sorted(_obb_dims(canonical), reverse=True)
    face_hist, face_areas = _face_histogram(canonical)
    edge_hist = _edge_histogram(canonical)
    payload = {
        "volume": _q(volume),
        "area": _q(area),
        "dims": [_q(d) for d in dims],
        "face_hist": dict(sorted(face_hist.items())),
        "edge_hist": dict(sorted(edge_hist.items())),
        "area_by_type": {k: _q(v) for k, v in sorted(face_areas.items())},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{SIGNATURE_VERSION}:{hashlib.sha256(blob.encode()).hexdigest()}"


class OcctGeometryService:
    """v1 engine (OCCT via OCP). Implements :class:`GeometryService`."""

    def analyze(
        self,
        step_bytes: bytes,
        family: str | None = None,
        density_g_cm3: float | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        if density_g_cm3 is not None and not (math.isfinite(density_g_cm3) and density_g_cm3 > 0):
            raise GeometryError(f"density must be a positive finite g/cm3, got {density_g_cm3}")
        shape = _read_step(step_bytes)
        volume, area = _volume_area(shape)
        dims, bbox_source = _winning_box(shape)
        # weight_g = volume_mm3 / 1000 x density_g/cm3 (GEOMETRY.md §1).
        weight = (volume / 1000.0) * density_g_cm3 if density_g_cm3 is not None else None
        return AnalysisResult(
            family=family,
            dimensions=Dimensions(
                size_x=dims[0],
                size_y=dims[1],
                size_z=dims[2],
                max_dim=dims[0],
                med_dim=dims[1],
                min_dim=dims[2],
                area=area,
                volume=volume,
                weight=weight,
                bbox_source=bbox_source,  # type: ignore[arg-type]
            ),
        )

    def compute_signature(self, step_bytes: bytes) -> str:
        return _fingerprint(_read_step(step_bytes))
