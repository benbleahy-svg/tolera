"""Shared probe helpers — M4.0 throwaway spike scaffold (no production use).

Implements the spec's candidate geometry signature (spec#geometry-engine → Resolved
Decisions → Geometry): normalized fingerprint = quantized (volume, area, bbox-sorted
dims, face/edge type histogram, per-type areas) → SHA-256.
"""

import hashlib
import json
from collections import Counter

from OCP.Bnd import Bnd_Box, Bnd_OBB
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

SURFACE_TYPES = {
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
CURVE_TYPES = {
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


def read_step(path: str):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed: {path}")
    if reader.TransferRoots() == 0:
        raise RuntimeError(f"STEP transfer produced no roots: {path}")
    return reader.OneShape()


def volume_area(shape) -> tuple[float, float]:
    vp, sp = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    BRepGProp.SurfaceProperties_s(shape, sp)
    return vp.Mass(), sp.Mass()


def aabb_dims(shape) -> list[float]:
    box = Bnd_Box()
    box.SetGap(0.0)
    BRepBndLib.Add_s(shape, box, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return [x1 - x0, y1 - y0, z1 - z0]


def obb_dims(shape) -> list[float]:
    obb = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, obb, True, True, False)
    return sorted([2 * obb.XHSize(), 2 * obb.YHSize(), 2 * obb.ZHSize()], reverse=True)


def faces(shape):
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        yield TopoDS.Face_s(ex.Current())
        ex.Next()


def edges(shape):
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        yield TopoDS.Edge_s(ex.Current())
        ex.Next()


def face_area(face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.Mass()


def face_histogram(shape) -> tuple[Counter, dict[str, float]]:
    """Face-type counts + summed area per surface type."""
    hist: Counter = Counter()
    areas: dict[str, float] = {}
    for f in faces(shape):
        t = SURFACE_TYPES.get(BRepAdaptor_Surface(f).GetType(), "other")
        hist[t] += 1
        areas[t] = areas.get(t, 0.0) + face_area(f)
    return hist, areas


def edge_histogram(shape) -> Counter:
    hist: Counter = Counter()
    for e in edges(shape):
        t = CURVE_TYPES.get(BRepAdaptor_Curve(e).GetType(), "other")
        hist[t] += 1
    return hist


def canonicalize(shape):
    """Merge same-domain faces/edges (split-face tolerance) before fingerprinting."""
    unify = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
    unify.Build()
    return unify.Shape()


def q(value: float, sig: int) -> str:
    return f"{value:.{sig}g}"


def fingerprint(shape, sig_digits: int = 6, unify: bool = True) -> tuple[str, dict]:
    """Spec candidate signature. Returns (sha256 hex, the payload that was hashed)."""
    s = canonicalize(shape) if unify else shape
    vol, area = volume_area(s)
    dims = obb_dims(s)
    fhist, fareas = face_histogram(s)
    ehist = edge_histogram(s)
    payload = {
        "volume": q(vol, sig_digits),
        "area": q(area, sig_digits),
        "dims": [q(d, sig_digits) for d in dims],
        "face_hist": dict(sorted(fhist.items())),
        "edge_hist": dict(sorted(ehist.items())),
        "area_by_type": {k: q(v, sig_digits) for k, v in sorted(fareas.items())},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest(), payload
