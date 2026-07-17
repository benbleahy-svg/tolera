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
import itertools
import json
import math
import tempfile
from collections import Counter
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

from OCP.Bnd import Bnd_Box, Bnd_OBB
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Pnt, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from .contract import (
    FAMILY_LATHE,
    FAMILY_MILLING,
    FAMILY_SHEET_METAL,
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


# --------------------------------------------------------------------------- #
# Sheet-metal recognizer (M4.2) — thickness, bends, analytic k-factor unfold
# --------------------------------------------------------------------------- #
#: Matching tolerances for the recognizer: directions (unit-vector dots) vs
#: distances/radii in mm. 1e-4 mm is far below sheet tolerance yet loose enough
#: for foreign-CAD STEP round-trips (our own fixtures round-trip at ~1e-9).
_DIR_TOL = 1e-6
_DIST_TOL = 1e-4

#: The spec k-factor (INTERROGATION-ENGINE-SPEC §3): BASE_K = 0.65 is NOT
#: configurable (build-plan M4.2).
_BASE_K = 0.65


def _k_factor(radius: float, thickness: float) -> float:
    return (_BASE_K + 0.5 * math.log10(radius / thickness)) * 0.5


def _v_sub(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _v_dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _v_cross(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _v_unit(a: tuple[float, ...]) -> tuple[float, float, float]:
    n = math.sqrt(_v_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _face_area(face: TopoDS_Face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return float(props.Mass())


#: Samples per curved boundary edge for extent measurement — a convex arc's
#: extreme point lies BETWEEN vertices (an obround strap end bulges w/2 past
#: its diameter vertices), so vertices alone understate panel extents. At 256
#: samples the worst-case understatement is r·(1-cos(pi/256)) ~ 7.5e-5·r —
#: micrometres at sheet scale, far inside the 0.1% geometry gate.
_CURVE_SAMPLES = 256


def _face_vertices(face: TopoDS_Face) -> list[tuple[float, float, float]]:
    """Boundary points of the face: edge vertices plus sampled points along
    every non-line edge, so extents measured over these points are true face
    extents for curved outlines too (fresh-eyes review, M4.2)."""
    pts = []
    ex = TopExp_Explorer(face, TopAbs_VERTEX)
    while ex.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(ex.Current()))
        pts.append((p.X(), p.Y(), p.Z()))
        ex.Next()
    ee = TopExp_Explorer(face, TopAbs_EDGE)
    while ee.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(ee.Current()))
        if curve.GetType() != 0:  # anything but a straight line
            first, last = curve.FirstParameter(), curve.LastParameter()
            for i in range(1, _CURVE_SAMPLES):
                p = curve.Value(first + (last - first) * i / _CURVE_SAMPLES)
                pts.append((p.X(), p.Y(), p.Z()))
        ee.Next()
    return pts


def _extent(points: list[tuple[float, float, float]], direction: tuple[float, ...]) -> float:
    values = [_v_dot(p, direction) for p in points]
    return max(values) - min(values)


def _inner_wire_count(face: TopoDS_Face) -> int:
    outer = BRepTools.OuterWire_s(face)
    n = 0
    ex = TopExp_Explorer(face, TopAbs_WIRE)
    while ex.More():
        if not ex.Current().IsSame(outer):
            n += 1
        ex.Next()
    return n


class _PlanarFace:
    def __init__(self, face: TopoDS_Face) -> None:
        surface = BRepAdaptor_Surface(face)
        plane = surface.Plane()
        direction = plane.Axis().Direction()
        origin = plane.Location()
        self.face = face
        self.normal = (direction.X(), direction.Y(), direction.Z())
        self.origin = (origin.X(), origin.Y(), origin.Z())
        self.area = _face_area(face)
        self.vertices = _face_vertices(face)

    def in_plane_axes(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        seed = (0.0, 0.0, 1.0) if abs(self.normal[2]) < 0.9 else (1.0, 0.0, 0.0)
        u = _v_unit(_v_cross(self.normal, seed))
        return u, _v_unit(_v_cross(self.normal, u))


class _CylFace:
    def __init__(self, face: TopoDS_Face) -> None:
        surface = BRepAdaptor_Surface(face)
        cylinder = surface.Cylinder()
        axis = cylinder.Axis()
        direction, location = axis.Direction(), axis.Location()
        self.face = face
        self.radius = cylinder.Radius()
        self.axis_dir = (direction.X(), direction.Y(), direction.Z())
        self.axis_loc = (location.X(), location.Y(), location.Z())
        self.angle_deg = math.degrees(abs(surface.LastUParameter() - surface.FirstUParameter()))
        self.length = abs(surface.LastVParameter() - surface.FirstVParameter())


class _Panel:
    """A flat region of the sheet: two anti-parallel planar skins at offset t."""

    def __init__(self, a: _PlanarFace, b: _PlanarFace, offset: float) -> None:
        self.faces = (a, b)
        self.offset = offset
        self.area = a.area + b.area


class _Bend:
    """A bend: two concentric cylindrical skins with radius delta == t."""

    def __init__(self, inner: _CylFace, outer: _CylFace, thickness: float) -> None:
        self.faces = (inner, outer)
        self.radius = inner.radius
        self.angle_deg = inner.angle_deg
        self.length = inner.length
        self.axis_dir = inner.axis_dir
        self.k = _k_factor(inner.radius, thickness)
        self.allowance = math.radians(inner.angle_deg) * (inner.radius + self.k * thickness)


def _overlapping(a: _PlanarFace, b: _PlanarFace) -> bool:
    """Projected bounding rectangles of the two faces intersect in-plane —
    rejects accidental parallel pairs (a strip-end cap vs a far skin)."""
    for axis in a.in_plane_axes():
        a_vals = [_v_dot(p, axis) for p in a.vertices]
        b_vals = [_v_dot(p, axis) for p in b.vertices]
        if min(a_vals) > max(b_vals) - _DIST_TOL or min(b_vals) > max(a_vals) - _DIST_TOL:
            return False
    return True


def _planar_pairs(planes: list[_PlanarFace]) -> list[_Panel]:
    pairs = []
    for i, a in enumerate(planes):
        for b in planes[i + 1 :]:
            if abs(abs(_v_dot(a.normal, b.normal)) - 1.0) > _DIR_TOL:
                continue
            offset = abs(_v_dot(_v_sub(a.origin, b.origin), a.normal))
            if offset <= _DIST_TOL or not _overlapping(a, b):
                continue
            pairs.append(_Panel(a, b, offset))
    return pairs


#: A bend is an open cylindrical sweep; (near-)full cylinders are hole /
#: counterbore walls, which are coaxial and can sit exactly t apart —
#: pairing those would fabricate a bend (CodeRabbit, M4.2).
_MAX_BEND_SWEEP_DEG = 350.0


def _detect_bends(cylinders: list[_CylFace], thickness: float) -> list[_Bend]:
    bends = []
    used: set[int] = set()
    for i, a in enumerate(cylinders):
        if i in used or a.angle_deg > _MAX_BEND_SWEEP_DEG:
            continue
        for j in range(i + 1, len(cylinders)):
            if j in used:
                continue
            b = cylinders[j]
            if b.angle_deg > _MAX_BEND_SWEEP_DEG:
                continue
            if abs(abs(_v_dot(a.axis_dir, b.axis_dir)) - 1.0) > _DIR_TOL:
                continue
            gap = _v_sub(a.axis_loc, b.axis_loc)
            along = _v_dot(gap, a.axis_dir)
            radial = math.sqrt(max(_v_dot(gap, gap) - along * along, 0.0))
            if radial > _DIST_TOL:
                continue  # parallel but not concentric — two different bends
            if abs(abs(a.radius - b.radius) - thickness) > _DIST_TOL:
                continue
            # The two skins of one bend sweep the same angle over the same
            # width — coaxial but unrelated surfaces (stepped bores) do not.
            if abs(a.angle_deg - b.angle_deg) > 1e-3 or abs(a.length - b.length) > _DIST_TOL:
                continue
            inner, outer = (a, b) if a.radius < b.radius else (b, a)
            bends.append(_Bend(inner, outer, thickness))
            used.update((i, j))
            break
    return bends


def _edge_adjacency(
    shape: TopoDS_Shape, panels: list[_Panel], bends: list[_Bend]
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """panel-index ↔ bend-index adjacency via shared B-rep edges."""
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)

    def owner(face: TopoDS_Shape, groups: Sequence[_Panel | _Bend]) -> int | None:
        for idx, group in enumerate(groups):
            if any(face.IsSame(member.face) for member in group.faces):
                return idx
        return None

    panel_bends: dict[int, set[int]] = {i: set() for i in range(len(panels))}
    bend_panels: dict[int, set[int]] = {i: set() for i in range(len(bends))}
    for e in range(1, edge_faces.Extent() + 1):
        members = list(edge_faces.FindFromIndex(e))  # NCollection_List is iterable in OCP
        panel_hits = {hit for f in members if (hit := owner(f, panels)) is not None}
        bend_hits = {hit for f in members if (hit := owner(f, bends)) is not None}
        for p in panel_hits:
            for b in bend_hits:
                panel_bends[p].add(b)
                bend_panels[b].add(p)
    return panel_bends, bend_panels


def _walk_chain(
    panels: list[_Panel],
    bends: list[_Bend],
    panel_bends: dict[int, set[int]],
    bend_panels: dict[int, set[int]],
) -> tuple[list[int], list[int]] | None:
    """Order panels/bends into a single open chain (panel-bend-panel-...).
    Returns None when the topology is not a simple chain — the honest ceiling:
    curls/hems/branches stay unrecognized rather than mis-unfolded."""
    if any(len(p) != 2 for p in bend_panels.values()):
        return None
    if any(len(b) > 2 for b in panel_bends.values()):
        return None
    ends = [i for i, linked in panel_bends.items() if len(linked) == 1]
    if len(panels) != len(bends) + 1 or len(ends) != 2:
        return None
    # deterministic mirror choice: start from the larger end panel
    start = max(ends, key=lambda i: panels[i].area)
    panel_order, bend_order = [start], []
    seen_bends: set[int] = set()
    current = start
    while len(panel_order) < len(panels):
        next_bends = panel_bends[current] - seen_bends
        if len(next_bends) != 1:
            return None
        bend = next_bends.pop()
        seen_bends.add(bend)
        bend_order.append(bend)
        (nxt,) = bend_panels[bend] - {current}
        panel_order.append(nxt)
        current = nxt
    return panel_order, bend_order


def _analyze_sheet_metal(
    shape: TopoDS_Shape, volume: float, area: float
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The M4.2 recognizer: thickness + bends from the B-rep, analytic k-factor
    unfold over the panel-bend chain (GEOMETRY.md §3 — full geometric
    flattening is NOT required). Returns what it found, never fabricates:
    an unrecognizable body yields fewer scalars, not guessed ones."""
    shape = _canonicalize(shape)
    planes: list[_PlanarFace] = []
    cylinders: list[_CylFace] = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        kind = BRepAdaptor_Surface(face).GetType()
        if kind == 0:
            planes.append(_PlanarFace(face))
        elif kind == 1:
            cylinders.append(_CylFace(face))
        ex.Next()

    pairs = _planar_pairs(planes)
    if not pairs:
        return {}, []  # nothing sheet-like recognized
    # thickness = offset of the dominant (largest combined area) skin pair
    thickness = max(pairs, key=lambda p: p.area).offset
    panels = [p for p in pairs if abs(p.offset - thickness) <= _DIST_TOL]
    bends = _detect_bends(cylinders, thickness)

    # Constant-thickness gate (fresh-eyes review): the mid-surface identities
    # below are exact ONLY for a constant-thickness shell, and every prismatic
    # solid has some anti-parallel planar pair — a milled billet assigned a
    # sheet-metal process must yield NO scalars, not arithmetic dressed up as
    # measurement. For a real sheet the two skins account for the whole
    # surface except the cut walls: sum(panel skins) + sum(bend skins)
    # == 2·volume/thickness. Small extra features (chamfers, countersinks)
    # stay within the 2% envelope; anything larger is not a sheet body.
    skin_area = sum(p.area for p in panels) + sum(
        math.radians(b.angle_deg) * (2.0 * b.radius + thickness) * b.length for b in bends
    )
    expected_skins = 2.0 * volume / thickness
    if abs(skin_area - expected_skins) > 0.02 * expected_skins:
        return {}, []  # not a constant-thickness sheet — nothing recognized

    # A through-piercing shows an inner wire on BOTH skins of its panel; a
    # one-sided recess (blind opening small enough to pass the skin gate)
    # shows on one only — per-panel min() counts pairs, never fabricates a
    # piercing out of two unrelated openings (CodeRabbit, M4.2). Cutouts
    # crossing a bend zone sit on cylinder faces and stay uncounted (v1).
    pierce_count = sum(
        min(_inner_wire_count(p.faces[0].face), _inner_wire_count(p.faces[1].face)) for p in panels
    )

    scalars: dict[str, Any] = {
        "thickness": thickness,
        "bend_count": len(bends),
        # mid-surface identities, exact for constant-thickness bodies: the flat
        # pattern's area and its total contour length (outer + cutouts)
        "flat_area": volume / thickness,
        "total_cut_length": (area - 2.0 * volume / thickness) / thickness,
        "pierce_count": pierce_count,
    }
    features: list[dict[str, Any]] = [
        {
            "name": "bend",
            "properties": {
                "radius": b.radius,
                "angle": b.angle_deg,
                "length": b.length,
                "k_factor": b.k,
            },
            "geometry_refs": [],  # face ids arrive with the server-mesh export
        }
        for b in bends
    ]

    unfold = _unfold(shape, panels, bends, thickness)
    if unfold is not None:
        developed, width, bend_lines = unfold
        scalars["size_x"] = developed
        scalars["size_y"] = width
        scalars["flat_pattern"] = {
            "size_x": developed,
            "size_y": width,
            "bend_lines": bend_lines,
        }
    return scalars, features


def _unfold(
    shape: TopoDS_Shape, panels: list[_Panel], bends: list[_Bend], thickness: float
) -> tuple[float, float, list[dict[str, float]]] | None:
    """Developed length + width + bend-line positions, or None when the body
    is outside the v1 analytic envelope (non-parallel bend axes, branched or
    broken chains) — omitted rather than fabricated."""
    if not bends:
        # zero-bend: the flat pattern is the dominant panel itself; measure its
        # extents along its own boundary-edge direction (axis-robust)
        panel = max(panels, key=lambda p: p.area)
        face = panel.faces[0]
        u = _longest_edge_direction(face.face)
        if u is None:
            return None
        v = _v_unit(_v_cross(face.normal, u))
        size = sorted([_extent(face.vertices, u), _extent(face.vertices, v)], reverse=True)
        return size[0], size[1], []

    axis = bends[0].axis_dir
    if any(abs(abs(_v_dot(axis, b.axis_dir)) - 1.0) > _DIR_TOL for b in bends):
        return None  # bends about different axes: not a v1 analytic chain
    if any(b.allowance <= 0.0 for b in bends):
        # r/t below ~0.045 drives the frozen k-formula negative past the bend
        # radius itself — outside the formula's physical domain, so the unfold
        # is omitted rather than emitted with a negative allowance.
        return None
    panel_bends, bend_panels = _edge_adjacency(shape, panels, bends)
    chain = _walk_chain(panels, bends, panel_bends, bend_panels)
    if chain is None:
        return None
    panel_order, bend_order = chain

    developed = 0.0
    width = max(b.length for b in bends)
    bend_lines: list[dict[str, float]] = []
    for position, panel_idx in enumerate(panel_order):
        face = panels[panel_idx].faces[0]
        u = _v_unit(_v_cross(face.normal, axis))
        developed += _extent(face.vertices, u)
        width = max(width, _extent(face.vertices, axis))
        if position < len(bend_order):
            bend = bends[bend_order[position]]
            bend_lines.append(
                {"position": developed + bend.allowance / 2.0, "angle": bend.angle_deg}
            )
            developed += bend.allowance
    return developed, width, bend_lines


def _longest_edge_direction(face: TopoDS_Face) -> tuple[float, float, float] | None:
    best: tuple[float, tuple[float, float, float]] | None = None
    ex = TopExp_Explorer(face, TopAbs_EDGE)
    while ex.More():
        edge = TopoDS.Edge_s(ex.Current())
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() == 0:  # line
            p1 = curve.Value(curve.FirstParameter())
            p2 = curve.Value(curve.LastParameter())
            d = (p2.X() - p1.X(), p2.Y() - p1.Y(), p2.Z() - p1.Z())
            length = math.sqrt(_v_dot(d, d))
            if length > _DIST_TOL and (best is None or length > best[0]):
                best = (length, _v_unit(d))
        ex.Next()
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# Milling recognizer (M4.4) — setups, features, in-house runtime + confidence
# --------------------------------------------------------------------------- #
# Verdicts from the M4.0 capability map (GEOMETRY.md §4): hole/pocket
# recognition is OCCT-proven; the setup-ALLOCATION heuristic and the runtime
# estimate are in-house (runtime has NO OCCT support — the designed honest
# ceiling). Everything below is estimation-grade with surfaced confidence;
# low confidence → manual override drives cost. 5-axis is never auto-costed:
# work the 3-axis model cannot reach stays UNCOVERED (degrading confidence)
# instead of being priced.
#
# v1 ceilings (return what is found, never fabricate — GEOMETRY.md §9):
# feature taxonomy follows the KB reference (milling-feature-iteration):
# ``machine_direction`` / ``hole`` / ``circular_pocket`` / ``pocket`` are the
# emitted FEATURES; chamfer/fillet/tapered-wall/tight-corner/uncut-face
# objects are FEEDBACK and arrive with the DFM catalogue (M4.7). Not detected
# in v1: partial holes, holes-through-cavity, counterbore/-sink children,
# through-pockets (no floor), non-axis-aligned bores (their removal degrades
# the parameterized fraction instead). Surfaced-face reachability is judged
# from one mid-parameter normal + untrimmed UV samples — estimation-grade
# attribution of the surfacing AREA only; the parameterized-volume confidence
# fraction (not this sampling) is what gates trust in the estimate.

#: Strategy-input defaults, metric-native (DACH delta overrides the KB inch
#: defaults; 1000 mm² is KB's own metric value). 45.72 mm = exactly 1.80 in —
#: the KB parenthetical "45.65 mm" is a rounding slip of its inch default.
_MILL_DEFAULT_INPUTS = {
    "depth_profiling_threshold": 50.8,  # mm (2.0 in) — max profiled-cut depth
    "depth_surfacing_threshold": 45.72,  # mm (1.80 in) — max surfaced-cut depth
    "minimum_area_for_setup": 1000.0,  # mm² — gate for surfacing-only setups
    "maximum_hole_diameter": 50.8,  # mm (2.0 in) — above: circular pocket
}

# In-house runtime heuristic constants — ASSUMED calibratable engineering
# defaults (no spec/OCCT formula exists; build-plan M4.4). MUST mirror
# scripts/spike-m4.0/gen_fixtures.py MILL_* so the goldens pin them.
_MILL_MRR_MM3_MIN = 15000.0  # roughing removal rate
_MILL_DRILL_MM_MIN = 300.0  # drill axial penetration rate
_MILL_HOLE_HANDLING_MIN = 0.5  # per-hole positioning/tool time
_MILL_SURF_MM2_MIN = 1500.0  # surfacing area rate
_MILL_PROFILE_MM2_MIN = 6000.0  # wall-profiling finish area rate

#: Confidence rubric: share of removed material that is feature-parameterized
#: (KB milling-feature-iteration: "usually above 80%" for straightforward
#: 3-axis parts). Any uncovered face additionally caps the rating at Medium.
_CONF_HIGH_FRACTION = 0.8
_CONF_MEDIUM_FRACTION = 0.5
_CONF_ORDER = {"High": 2, "Medium": 1, "Low": 0}

#: The six 3-axis tool directions, canonical order = the deterministic
#: tie-break for setup ordering.
_AXIS_DIRS: tuple[tuple[float, float, float], ...] = (
    (1.0, 0.0, 0.0),
    (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 0.0, -1.0),
)

#: Minimum |dot| for a surfaced face to be reachable from an existing setup.
_SURFACE_REACH_DOT = 0.1


def _snap_dir(v: tuple[float, float, float]) -> int | None:
    """Index into ``_AXIS_DIRS`` when ``v`` is axis-aligned, else None."""
    for i, d in enumerate(_AXIS_DIRS):
        if _v_dot(v, d) > 1.0 - _DIR_TOL:
            return i
    return None


def _outward_normal(face: TopoDS_Face) -> tuple[float, float, float]:
    """The solid's outward normal at the face's mid-parameter point
    (``BRepGProp_Face`` accounts for the face orientation)."""
    surf = BRepAdaptor_Surface(face)
    u = 0.5 * (surf.FirstUParameter() + surf.LastUParameter())
    v = 0.5 * (surf.FirstVParameter() + surf.LastVParameter())
    p, vn = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face).Normal(u, v, p, vn)
    return _v_unit((vn.X(), vn.Y(), vn.Z()))


def _surface_grid_points(face: TopoDS_Face, n: int = 8) -> list[tuple[float, float, float]]:
    """UV-grid samples — extents of curved faces whose extreme points lie in
    the face INTERIOR (a dome's pole has no boundary vertex)."""
    surf = BRepAdaptor_Surface(face)
    u0, u1 = surf.FirstUParameter(), surf.LastUParameter()
    v0, v1 = surf.FirstVParameter(), surf.LastVParameter()
    pts = []
    for i in range(n + 1):
        for j in range(n + 1):
            p = surf.Value(u0 + (u1 - u0) * i / n, v0 + (v1 - v0) * j / n)
            pts.append((p.X(), p.Y(), p.Z()))
    return pts


class _MillBore:
    """A full-sweep concave cylinder — a drilled bore (or circular pocket)."""

    def __init__(self, face: TopoDS_Face, surf: BRepAdaptor_Surface, axis_idx: int) -> None:
        cyl = surf.Cylinder()
        direction = cyl.Axis().Direction()
        location = cyl.Axis().Location()
        e = _AXIS_DIRS[axis_idx]
        sign = 1.0 if _v_dot((direction.X(), direction.Y(), direction.Z()), e) > 0 else -1.0
        s_loc = _v_dot((location.X(), location.Y(), location.Z()), e)
        v0, v1 = surf.FirstVParameter(), surf.LastVParameter()
        self.face = face
        self.radius = float(cyl.Radius())
        self.axis = axis_idx  # POSITIVE axis index (0/2/4)
        self.axis_point = (location.X(), location.Y(), location.Z())
        self.s_lo = float(min(s_loc + sign * v0, s_loc + sign * v1))
        self.s_hi = float(max(s_loc + sign * v0, s_loc + sign * v1))
        self.area = _face_area(face)


class _MillHole:
    """One (possibly compound) hole feature along a single axis."""

    def __init__(self, bores: list[_MillBore]) -> None:
        self.bores = bores
        self.axis = bores[0].axis
        self.s_lo = min(b.s_lo for b in bores)
        self.s_hi = max(b.s_hi for b in bores)
        self.min_radius = min(b.radius for b in bores)
        self.volume = sum(math.pi * b.radius**2 * (b.s_hi - b.s_lo) for b in bores)
        self.area = sum(b.area for b in bores)
        self.depth = self.s_hi - self.s_lo
        self.bottom_type = "obstructed"
        self.entry_dir: int | None = None  # _AXIS_DIRS index; None = flexible
        self.is_circular_pocket = False
        #: False = both ends closed (an internal void): no 3-axis tool reaches
        #: it — excluded from setups AND from the parameterized volume, so it
        #: degrades confidence instead of being priced (fresh-eyes, M4.4).
        self.reachable = True


class _MillPocket:
    """A 2.5D pocket: an axis-normal floor + its edge-adjacent walls."""

    def __init__(self, direction: int, floor_area: float, depth: float) -> None:
        self.direction = direction
        self.floor_area = floor_area
        self.depth = depth
        self.wall_faces: list[tuple[float, float]] = []  # (area, depth along dir)
        self.has_transition = False

    @property
    def volume(self) -> float:
        return self.floor_area * self.depth  # prismatic v1

    @property
    def area(self) -> float:
        return self.floor_area + sum(a for a, _ in self.wall_faces)


class _MillSetup:
    """One machine direction with its attributed work."""

    def __init__(self, direction: int) -> None:
        self.direction = direction
        self.holes: list[_MillHole] = []
        self.pockets: list[_MillPocket] = []
        self.rough_mm3 = 0.0
        self.profiled = 0.0
        self.derived = 0.0
        self.surfaced = 0.0

    @property
    def volume(self) -> float:
        # each feature counted exactly once (circular pockets live in
        # ``holes``; ``rough_mm3`` carries only the unparameterized leftover)
        return (
            sum(h.volume for h in self.holes) + sum(p.volume for p in self.pockets) + self.rough_mm3
        )

    def runtime_hours(self) -> float:
        drilled = [h for h in self.holes if not h.is_circular_pocket]
        roughed = (
            self.rough_mm3
            + sum(p.volume for p in self.pockets)
            + sum(h.volume for h in self.holes if h.is_circular_pocket)
        )
        minutes = (
            roughed / _MILL_MRR_MM3_MIN
            + sum(h.depth / _MILL_DRILL_MM_MIN + _MILL_HOLE_HANDLING_MIN for h in drilled)
            + self.profiled / _MILL_PROFILE_MM2_MIN
            + self.surfaced / _MILL_SURF_MM2_MIN
        )
        return minutes / 60.0


def _aabb_bounds(shape: TopoDS_Shape) -> tuple[tuple[float, float, float], ...]:
    box = Bnd_Box()
    box.SetGap(0.0)
    BRepBndLib.Add_s(shape, box, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return ((x0, y0, z0), (x1, y1, z1))


def _s_bound_max(lo: tuple[float, ...], hi: tuple[float, ...], d: tuple[float, ...]) -> float:
    """max over the AABB of the position along direction ``d``."""
    return sum(max(a * c, b * c) for a, b, c in zip(lo, hi, d, strict=True))


def _analyze_mill3(
    shape: TopoDS_Shape, volume: float, inputs: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, Any]], Literal["High", "Medium", "Low"]]:
    """The M4.4 recognizer: 3-axis features → deterministic setup allocation →
    in-house runtime + confidence. Returns ``(family_scalars, features,
    confidence)``; a body with no reachable work returns zero setups and zero
    runtime — never a fabricated estimate."""
    resolved = {**_MILL_DEFAULT_INPUTS, **(inputs or {})}
    # strategy inputs become org-authorable with custom interrogations (M4.8):
    # reject junk here instead of silently mis-allocating setups (CodeRabbit)
    for name in _MILL_DEFAULT_INPUTS:
        value = resolved[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value < 0
        ):
            raise GeometryError(f"milling input {name} must be a finite non-negative number")
        resolved[name] = float(value)
    if resolved["maximum_hole_diameter"] == 0:
        raise GeometryError("maximum_hole_diameter must be positive")
    shape = _canonicalize(shape)
    lo, hi = _aabb_bounds(shape)
    stock_volume = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
    total_removal = max(stock_volume - volume, 0.0)

    # -- classify faces ----------------------------------------------------- #
    skin: list[TopoDS_Face] = []
    planes: list[tuple[TopoDS_Face, tuple[float, float, float], float]] = []  # face, n_out, area
    bores: list[_MillBore] = []
    surface_candidates: list[TopoDS_Face] = []  # tapers, partial cyls, cones, freeform
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        surf = BRepAdaptor_Surface(face)
        kind = surf.GetType()
        if kind == 0:  # plane
            n_out = _outward_normal(face)
            idx = _snap_dir(n_out)
            if idx is not None:
                # stock skin: an axis-normal plane ON the AABB boundary
                point = surf.Plane().Location()
                s = _v_dot((point.X(), point.Y(), point.Z()), _AXIS_DIRS[idx])
                if abs(s - _s_bound_max(lo, hi, _AXIS_DIRS[idx])) <= _DIST_TOL:
                    skin.append(face)
                    ex.Next()
                    continue
            planes.append((face, n_out, _face_area(face)))
        elif kind == 1 and abs(surf.LastUParameter() - surf.FirstUParameter()) >= (
            2 * math.pi - 1e-6
        ):
            cyl_dir = surf.Cylinder().Axis().Direction()
            axis_idx = _snap_dir((cyl_dir.X(), cyl_dir.Y(), cyl_dir.Z()))
            if axis_idx is None:
                axis_idx = _snap_dir((-cyl_dir.X(), -cyl_dir.Y(), -cyl_dir.Z()))
            n_out = _outward_normal(face)
            cyl = surf.Cylinder()
            mid = surf.Value(
                0.5 * (surf.FirstUParameter() + surf.LastUParameter()),
                0.5 * (surf.FirstVParameter() + surf.LastVParameter()),
            )
            axis_loc = cyl.Axis().Location()
            axis_d = cyl.Axis().Direction()
            to_mid = _v_sub((mid.X(), mid.Y(), mid.Z()), (axis_loc.X(), axis_loc.Y(), axis_loc.Z()))
            along = _v_dot(to_mid, (axis_d.X(), axis_d.Y(), axis_d.Z()))
            radial = _v_sub(
                to_mid,
                (along * axis_d.X(), along * axis_d.Y(), along * axis_d.Z()),
            )
            concave = _v_dot(n_out, radial) < 0
            if axis_idx is not None and concave:
                # normalize to the positive axis of the pair for grouping
                bores.append(_MillBore(face, surf, axis_idx - (axis_idx % 2)))
            elif concave:
                surface_candidates.append(face)  # tilted bore: not 3-axis work
            # convex full cylinders (bosses/pins) bound the stock — their
            # surround is roughed; nothing to allocate directly (v1)
        else:
            surface_candidates.append(face)  # partial cyl, cone, sphere, freeform
        ex.Next()

    # -- holes (merge coaxial contiguous bores; classify ends) -------------- #
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)

    def adjacent(face: TopoDS_Face) -> list[TopoDS_Shape]:
        out: list[TopoDS_Shape] = []
        ee = TopExp_Explorer(face, TopAbs_EDGE)
        while ee.More():
            if edge_faces.Contains(ee.Current()):
                out.extend(list(edge_faces.FindFromKey(ee.Current())))
            ee.Next()
        return out

    holes: list[_MillHole] = []
    used_bores: set[int] = set()
    for i, bore in enumerate(bores):
        if i in used_bores:
            continue
        stack = [bore]
        used_bores.add(i)
        for j in range(i + 1, len(bores)):
            if j in used_bores or bores[j].axis != bore.axis:
                continue
            gap = _v_sub(bores[j].axis_point, bore.axis_point)
            e = _AXIS_DIRS[bore.axis]
            along = _v_dot(gap, e)
            off_axis = math.sqrt(max(_v_dot(gap, gap) - along * along, 0.0))
            if off_axis > _DIST_TOL:
                continue
            spans = sorted([*stack, bores[j]], key=lambda b: b.s_lo)
            if all(b.s_lo <= a.s_hi + _DIST_TOL for a, b in itertools.pairwise(spans)):
                stack.append(bores[j])
                used_bores.add(j)
        holes.append(_MillHole(stack))

    consumed_planes: set[int] = set()  # indices into ``planes``

    def plane_index(face: TopoDS_Shape) -> int | None:
        for k, (pf, _, _) in enumerate(planes):
            if face.IsSame(pf):
                return k
        return None

    def consume_cap(hole: _MillHole, end_s: float) -> bool:
        """Claim the axis-normal planar face closing the bore at ``end_s`` so
        it can never double as a pocket floor. True when one was found."""
        e = _AXIS_DIRS[hole.axis]
        for neighbor in {id(n): n for b in hole.bores for n in adjacent(b.face)}.values():
            k = plane_index(neighbor)
            if k is None or k in consumed_planes:
                continue
            face_k, n_out, _ = planes[k]
            if abs(abs(_v_dot(n_out, e)) - 1.0) > _DIR_TOL:
                continue
            pnt = BRepAdaptor_Surface(face_k).Plane().Location()
            if abs(_v_dot((pnt.X(), pnt.Y(), pnt.Z()), e) - end_s) <= _DIST_TOL:
                hole.area += planes[k][2]
                consumed_planes.add(k)
                return True
        return False

    for hole in holes:
        e = _AXIS_DIRS[hole.axis]
        lo_open = abs(hole.s_lo - (-_s_bound_max(lo, hi, tuple(-c for c in e)))) <= _DIST_TOL
        hi_open = abs(hole.s_hi - _s_bound_max(lo, hi, e)) <= _DIST_TOL
        if lo_open and hi_open:
            hole.bottom_type = "thru"
        elif not lo_open and not hi_open:
            # both ends closed: an internal void no 3-axis tool reaches —
            # never fabricated into drillable work (fresh-eyes, M4.4). Both
            # caps are claimed so they cannot masquerade as pocket floors.
            hole.reachable = False
            consume_cap(hole, hole.s_lo)
            consume_cap(hole, hole.s_hi)
        else:
            closed_s = hole.s_lo if not lo_open else hole.s_hi
            hole.entry_dir = hole.axis if not lo_open else hole.axis + 1  # +e or -e
            if consume_cap(hole, closed_s):
                hole.bottom_type = "flat"
            else:
                # a conical end (drill tip) among the adjacent faces → tipped
                for neighbor in {id(n): n for b in hole.bores for n in adjacent(b.face)}.values():
                    nf = TopoDS.Face_s(neighbor)
                    if BRepAdaptor_Surface(nf).GetType() == 2:  # cone
                        hole.bottom_type = "tipped"
                        break
        hole.is_circular_pocket = (
            hole.reachable and 2 * hole.min_radius > resolved["maximum_hole_diameter"]
        )

    # -- pockets (floor + adjacent walls) ------------------------------------ #
    pockets: list[_MillPocket] = []
    floor_order = sorted(
        (k for k in range(len(planes)) if k not in consumed_planes),
        key=lambda k: -planes[k][2],
    )
    uncovered_area = 0.0
    for k in floor_order:
        if k in consumed_planes:
            continue
        face_k, n_out, area_k = planes[k]
        idx = _snap_dir(n_out)
        if idx is None:
            continue  # tapered plane → surfacing path below
        e = _AXIS_DIRS[idx]
        pnt = BRepAdaptor_Surface(face_k).Plane().Location()
        depth = _s_bound_max(lo, hi, e) - _v_dot((pnt.X(), pnt.Y(), pnt.Z()), e)
        if depth <= _DIST_TOL:
            continue
        pocket = _MillPocket(idx, area_k, depth)
        consumed_planes.add(k)
        for neighbor in {id(n): n for n in adjacent(face_k)}.values():
            w = plane_index(neighbor)
            if w is None or w in consumed_planes:
                continue
            wall_face, wall_n, wall_area = planes[w]
            if abs(_v_dot(wall_n, e)) > _DIR_TOL:
                continue  # not parallel to the tool axis
            # depth below the setup's entry surface (the KB gate semantic),
            # not the face's own span — a short wall at the bottom of a deep
            # cavity is still deep work (fresh-eyes, M4.4)
            wall_depth = _s_bound_max(lo, hi, e) - min(
                _v_dot(p, e) for p in _face_vertices(wall_face)
            )
            consumed_planes.add(w)
            pocket.wall_faces.append((wall_area, wall_depth))
        for neighbor in {id(n): n for n in adjacent(face_k)}.values():
            nf = TopoDS.Face_s(neighbor)
            if BRepAdaptor_Surface(nf).GetType() in (1, 2) and not any(
                nf.IsSame(b.face) for b in bores
            ):
                pocket.has_transition = True
        pockets.append(pocket)

    # -- allocate setups ------------------------------------------------------ #
    setups: dict[int, _MillSetup] = {}

    def setup_for(idx: int) -> _MillSetup:
        if idx not in setups:
            setups[idx] = _MillSetup(idx)
        return setups[idx]

    for pocket in pockets:
        setup_for(pocket.direction).pockets.append(pocket)
    for hole in holes:
        if hole.entry_dir is not None:
            setup_for(hole.entry_dir).holes.append(hole)
    for hole in holes:
        if not hole.reachable:
            uncovered_area += hole.area  # internal void: no setup, no runtime
        elif hole.entry_dir is None:  # through: prefer an existing setup
            pair = (hole.axis, hole.axis + 1)
            existing = [p for p in pair if p in setups]
            if len(existing) == 2:
                chosen = max(existing, key=lambda p: (setups[p].volume, -p))
            elif existing:
                chosen = existing[0]
            else:
                chosen = hole.axis  # canonical positive direction (ASSUMED)
            setup_for(chosen).holes.append(hole)

    def depth_below_entry(pts: list[tuple[float, float, float]], idx: int) -> float:
        """Deepest point of the face below the setup's stock-entry surface —
        the KB depth-gate semantic (fresh-eyes, M4.4)."""
        d = _AXIS_DIRS[idx]
        return _s_bound_max(lo, hi, d) - min(_v_dot(p, d) for p in pts)

    # surfaced work: tapers/cones/partial cylinders/freeform faces
    orphans: dict[int, list[tuple[TopoDS_Face, float, float]]] = {}
    for k in range(len(planes)):
        if k not in consumed_planes:
            surface_candidates.append(planes[k][0])
            consumed_planes.add(k)
    for face in surface_candidates:
        n_rep = _outward_normal(face)
        f_area = _face_area(face)
        pts = _surface_grid_points(face)
        best, best_dot = None, _SURFACE_REACH_DOT
        for idx in setups:
            reach = _v_dot(n_rep, _AXIS_DIRS[idx])
            if reach > best_dot:
                best, best_dot = idx, reach
        if best is not None and depth_below_entry(pts, best) <= (
            resolved["depth_surfacing_threshold"] + _DIST_TOL
        ):
            setups[best].surfaced += f_area
            continue
        dominant = max(range(3), key=lambda a: abs(n_rep[a]))
        idx = 2 * dominant + (0 if n_rep[dominant] > 0 else 1)
        if idx in setups:
            uncovered_area += f_area  # reachable direction exists but depth fails
        else:
            orphans.setdefault(idx, []).append((face, f_area, 0.0))
    for idx, faces_ in orphans.items():
        group_area = sum(a for _, a, _ in faces_)
        depth_ok = all(
            depth_below_entry(_surface_grid_points(f), idx)
            <= resolved["depth_surfacing_threshold"] + _DIST_TOL
            for f, _, _ in faces_
        )
        if group_area >= resolved["minimum_area_for_setup"] and depth_ok:
            setup_for(idx).surfaced += group_area
        else:
            uncovered_area += group_area

    # pocket walls: profiled in the pocket's setup, gated by profiling depth
    for setup in setups.values():
        for pocket in setup.pockets:
            setup.derived += pocket.floor_area
            for wall_area, wall_depth in pocket.wall_faces:
                if wall_depth <= resolved["depth_profiling_threshold"] + _DIST_TOL:
                    setup.profiled += wall_area
                else:
                    uncovered_area += wall_area
        for hole in setup.holes:
            if hole.is_circular_pocket:  # profiled, not drilled
                setup.profiled += hole.area

    # deterministic order: attributed removal volume desc, then canonical axis
    ordered = sorted(setups.values(), key=lambda s: (-s.volume, s.direction))
    parameterized = sum(h.volume for h in holes if h.reachable) + sum(p.volume for p in pockets)
    # provably-unreachable volume (internal voids) is never charged as
    # roughing either — it only degrades confidence (CodeRabbit, M4.4)
    unreachable_mm3 = sum(h.volume for h in holes if not h.reachable)
    if ordered:
        ordered[0].rough_mm3 += max(total_removal - parameterized - unreachable_mm3, 0.0)

    # -- confidence ---------------------------------------------------------- #
    # relative guard: Bnd_Box is conservative, so a bare blank shows an
    # epsilon of phantom "removal" — measured certainty, not a guess
    confidence: Literal["High", "Medium", "Low"]
    fraction = parameterized / total_removal if total_removal > 1e-6 * stock_volume else 1.0
    if fraction >= _CONF_HIGH_FRACTION:
        confidence = "High"
    elif fraction >= _CONF_MEDIUM_FRACTION:
        confidence = "Medium"
    else:
        confidence = "Low"
    if uncovered_area > _DIST_TOL and _CONF_ORDER[confidence] > _CONF_ORDER["Medium"]:
        confidence = "Medium"

    # -- emit ------------------------------------------------------------------ #
    def hole_dict(hole: _MillHole) -> dict[str, Any]:
        return {
            "name": "circular_pocket" if hole.is_circular_pocket else "hole",
            "properties": {
                "area": hole.area,
                "volume": hole.volume,
                "depth": hole.depth,
                "bottom_type": hole.bottom_type,
                "min_radius": hole.min_radius,
                "diameter": 2 * hole.min_radius,
            },
            "geometry_refs": [],
        }

    def pocket_dict(pocket: _MillPocket) -> dict[str, Any]:
        return {
            "name": "pocket",
            "properties": {
                "area": pocket.area,
                "volume": pocket.volume,
                "max_depth": pocket.depth,
                "bottom_type": "flat",
                "has_transition": pocket.has_transition,
            },
            "geometry_refs": [],
        }

    setup_dicts: list[dict[str, Any]] = []
    all_features: list[dict[str, Any]] = []
    for setup in ordered:
        md = {
            "name": "machine_direction",
            "properties": {
                "direction": list(_AXIS_DIRS[setup.direction]),
                "area": setup.profiled + setup.derived + setup.surfaced,
                "profiled_area": setup.profiled,
                "derived_area": setup.derived,
                "surfaced_area": setup.surfaced,
            },
            "geometry_refs": [],
        }
        features = [md, *map(hole_dict, setup.holes), *map(pocket_dict, setup.pockets)]
        setup_dicts.append(
            {
                "direction": list(_AXIS_DIRS[setup.direction]),
                "setup_time": 1.0,  # hours — the spec/KB default
                "runtime": setup.runtime_hours(),
                "confidence": confidence,  # v1: uniform body-level rating
                "features": features,
                "feedback": [],  # DFM warnings arrive with M4.7
            }
        )
        all_features.extend(features)

    scalars: dict[str, Any] = {
        "setup_count": len(setup_dicts),
        "setups": setup_dicts,
        # aggregates for the Kalk single-operation pattern (KB milling-process)
        "runtime": sum(s["runtime"] for s in setup_dicts),
        "setup_time": sum(s["setup_time"] for s in setup_dicts),
    }
    return scalars, all_features, confidence


# --------------------------------------------------------------------------- #
# Lathe recognizer (M4.5) — recommended stock + setups + turned-cut split
# --------------------------------------------------------------------------- #
# The v2.15 decision caps lathe at ATTRIBUTES + STOCK RECOMMENDATION — no full
# turning feature tree (that arrives with Spatial; spec #geometry-engine,
# DECISIONS.md 2026-07-14 M4.0 GO item 5). What v1 emits, per the capability
# map (GEOMETRY.md §5):
#   * stock_radius / stock_length — probe-proven exact (the load-bearing math),
#   * setup_count — the in-house "feature ends/faces per side" heuristic,
#   * ONE aggregate external_cut + one internal_cut per bore, carrying the
#     radial-vs-axial split as area properties (laterals = axial feed,
#     axis-normal turned planes = radial feed) — estimation-grade, not a tree,
#   * live-tooling callouts: off_axis_hole (coaxial-vs-off-axis is the `~`
#     item) and asymmetric_cavity (the residual bucket) — FLAGGED, NOT COSTED.
#     Tight-corner detection is NOT in v1 (needs corner geometry beyond the
#     probe's verdict); it lands with the DFM catalogue work (M4.7).
# A body that is not dominantly turned yields {} — never a fabricated stock.

#: Strategy-input defaults, metric-native (DACH delta over the KB inch values:
#: 5.0 in / 0.75 in / 0.5 in). v1 validates + resolves them at the boundary —
#: their EVALUATION (bored-hole relief, protrusion, live-tooling warnings) is
#: the M4.7 DFM engine's job; callout FEATURES are geometry facts and are
#: emitted regardless of the toggles (the toggles gate the M4.7 Warning).
_LATHE_DEFAULT_INPUTS: dict[str, Any] = {
    "max_tool_protrusion_length": 127.0,  # mm (5.0 in)
    "axial_max_hooked_tool_radius": 19.05,  # mm (0.75 in)
    "radial_max_hooked_tool_radius": 12.7,  # mm (0.5 in)
    "should_perform_live_tooling": True,
    "can_perform_axial_live_tooling": True,
    "can_perform_radial_live_tooling": True,
}
_LATHE_NUMERIC_INPUTS = (
    "max_tool_protrusion_length",
    "axial_max_hooked_tool_radius",
    "radial_max_hooked_tool_radius",
)
_LATHE_BOOLEAN_INPUTS = (
    "should_perform_live_tooling",
    "can_perform_axial_live_tooling",
    "can_perform_radial_live_tooling",
)

#: A turned axis-normal plane is a full ring: area == pi*(max_r^2 - min_r^2).
#: The tolerance absorbs small piercings (a bolt circle through a flange face
#: deviates ~7%) while rejecting anything wall-like (a keyway end sits at ~95%
#: deviation) — ASSUMED calibratable recognizer internal.
_RING_RTOL = 0.2

#: Turnability gate: the coaxially-classified (+ flagged off-axis-hole) area
#: must dominate the body, else nothing is recognized — a prismatic part with
#: one drilled hole has a candidate axis but is NOT a turned part. ASSUMED
#: calibratable recognizer internal.
_TURNED_COVERAGE_MIN = 0.8

#: Off-axis concave cylinders only group into a HOLE callout when their
#: combined sweep closes the bore (mirrors the bend-sweep guard: a partial
#: concave fillet must not masquerade as a drilled hole).
_MIN_HOLE_SWEEP_DEG = 350.0


def _canonical_dir(d: tuple[float, float, float]) -> tuple[float, float, float]:
    """Sign-canonical axis direction (first above-tolerance component made
    positive) so the reported axis is stable across CAD exports that flip the
    surface axis. First-nonzero (not largest-|component|) keeps a diagonal
    axis's sign stable when a sub-tolerance perturbation reorders which
    component is largest (fresh-eyes review, M4.5)."""
    lead = next((c for c in d if abs(c) > _DIR_TOL), 1.0)
    return d if lead > 0 else (-d[0], -d[1], -d[2])


class _LatheFace:
    """One face classified against the turning axis."""

    def __init__(self, face: TopoDS_Face) -> None:
        surf = BRepAdaptor_Surface(face)
        self.face = face
        self.kind = surf.GetType()
        self.area = _face_area(face)
        self.points = _face_vertices(face)
        if self.kind != 0:
            # curved: interior extremes (a dome pole, a groove torus's OD)
            # matter — n=32 bounds the sampling understatement of a radial
            # extreme to ~0.12% of the local radius, inside the 0.1%-ish
            # geometry gate (fresh-eyes review, M4.5)
            self.points = self.points + _surface_grid_points(face, n=32)
        self.axis: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
        self.radius: float | None = None
        self.sweep_deg = 0.0
        self.center = (0.0, 0.0, 0.0)
        self.origin = (0.0, 0.0, 0.0)
        # classification scratch, filled by the recognizer pass
        self.s_lo = 0.0
        self.s_hi = 0.0
        self.max_r = 0.0
        self.s_face = 0.0
        self.bore: list[_LatheFace] | None = None
        if self.kind == 1:
            cyl = surf.Cylinder()
            d, o = cyl.Axis().Direction(), cyl.Axis().Location()
            self.axis = ((d.X(), d.Y(), d.Z()), (o.X(), o.Y(), o.Z()))
            self.radius = float(cyl.Radius())
            self.sweep_deg = math.degrees(abs(surf.LastUParameter() - surf.FirstUParameter()))
        elif self.kind == 2:
            cone = surf.Cone()
            d, o = cone.Axis().Direction(), cone.Axis().Location()
            self.axis = ((d.X(), d.Y(), d.Z()), (o.X(), o.Y(), o.Z()))
        elif self.kind == 3:
            sph = surf.Sphere()
            o = sph.Location()
            self.center = (o.X(), o.Y(), o.Z())
            self.radius = float(sph.Radius())
        elif self.kind == 4:
            tor = surf.Torus()
            d, o = tor.Axis().Direction(), tor.Axis().Location()
            self.axis = ((d.X(), d.Y(), d.Z()), (o.X(), o.Y(), o.Z()))
        self.normal = _outward_normal(face)
        if self.kind == 0:
            plane_pnt = surf.Plane().Location()
            self.origin = (plane_pnt.X(), plane_pnt.Y(), plane_pnt.Z())


def _radial_offset(
    point: tuple[float, float, float],
    axis_dir: tuple[float, float, float],
    axis_loc: tuple[float, float, float],
) -> float:
    gap = _v_sub(point, axis_loc)
    along = _v_dot(gap, axis_dir)
    return math.sqrt(max(_v_dot(gap, gap) - along * along, 0.0))


def _is_concave(lf: _LatheFace) -> bool:
    """Outward normal points toward the surface's own axis/centre — a bore or
    cavity wall (the mill-bore concavity test, generalized)."""
    surf = BRepAdaptor_Surface(lf.face)
    mid = surf.Value(
        0.5 * (surf.FirstUParameter() + surf.LastUParameter()),
        0.5 * (surf.FirstVParameter() + surf.LastVParameter()),
    )
    p = (mid.X(), mid.Y(), mid.Z())
    if lf.kind == 3:
        outward = _v_sub(p, lf.center)
    else:
        assert lf.axis is not None
        d, o = lf.axis
        gap = _v_sub(p, o)
        along = _v_dot(gap, d)
        outward = _v_sub(gap, (along * d[0], along * d[1], along * d[2]))
    return _v_dot(lf.normal, outward) < 0


def _face_contains_axis_point(face: TopoDS_Face, point: tuple[float, float, float]) -> bool:
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_State

    classifier = BRepClass_FaceClassifier()
    classifier.Perform(face, gp_Pnt(*point), 1e-6)
    return classifier.State() in (TopAbs_State.TopAbs_IN, TopAbs_State.TopAbs_ON)


def _analyze_lathe(
    shape: TopoDS_Shape, inputs: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The M4.5 recognizer. Returns ``(family_scalars, features)`` — or
    ``({}, [])`` when the body is not dominantly turned (never fabricates)."""
    resolved = {**_LATHE_DEFAULT_INPUTS, **(inputs or {})}
    for name in _LATHE_NUMERIC_INPUTS:
        value = resolved[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value < 0
        ):
            raise GeometryError(f"lathe input {name} must be a finite non-negative number")
        resolved[name] = float(value)
    for name in _LATHE_BOOLEAN_INPUTS:
        if not isinstance(resolved[name], bool):
            raise GeometryError(f"lathe input {name} must be a boolean")

    shape = _canonicalize(shape)
    faces: list[_LatheFace] = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        faces.append(_LatheFace(TopoDS.Face_s(ex.Current())))
        ex.Next()
    total_area = sum(f.area for f in faces)
    if total_area <= 0.0:
        return {}, []

    # -- turning axis: the coaxial cylinder cluster with the most area -------- #
    clusters: list[dict[str, Any]] = []
    for lf in faces:
        if lf.kind != 1:
            continue
        assert lf.axis is not None
        d = _canonical_dir(_v_unit(lf.axis[0]))
        for cluster in clusters:
            if (
                abs(abs(_v_dot(d, cluster["dir"])) - 1.0) <= _DIR_TOL
                and _radial_offset(lf.axis[1], cluster["dir"], cluster["loc"]) <= _DIST_TOL
            ):
                cluster["area"] += lf.area
                break
        else:
            clusters.append({"dir": d, "loc": lf.axis[1], "area": lf.area})
    if not clusters:
        return {}, []  # no cylindrical structure at all: nothing turnable
    winner = max(enumerate(clusters), key=lambda pair: (pair[1]["area"], -pair[0]))[1]
    axis_dir: tuple[float, float, float] = winner["dir"]
    axis_loc: tuple[float, float, float] = winner["loc"]

    def s_of(p: tuple[float, float, float]) -> float:
        return _v_dot(p, axis_dir)

    def r_of(p: tuple[float, float, float]) -> float:
        return _radial_offset(p, axis_dir, axis_loc)

    def coaxial(lf: _LatheFace) -> bool:
        if lf.kind == 3:
            return r_of(lf.center) <= _DIST_TOL
        if lf.axis is None:
            return False
        return (
            abs(abs(_v_dot(_v_unit(lf.axis[0]), axis_dir)) - 1.0) <= _DIR_TOL
            and _radial_offset(lf.axis[1], axis_dir, axis_loc) <= _DIST_TOL
        )

    # -- classify every face --------------------------------------------------- #
    external_axial: list[_LatheFace] = []
    internal_axial: list[_LatheFace] = []  # coaxial bore walls (cyl/cone/torus)
    turned_planes: list[_LatheFace] = []  # axis-normal, ring-symmetric
    off_axis_cyls: list[_LatheFace] = []
    asymmetric: list[_LatheFace] = []
    for lf in faces:
        if lf.kind == 0:
            if abs(abs(_v_dot(lf.normal, axis_dir)) - 1.0) <= _DIR_TOL:
                radii = [r_of(p) for p in lf.points]
                max_r = max(radii)
                s_face = s_of(lf.origin)
                axis_point = (
                    axis_loc[0] + (s_face - s_of(axis_loc)) * axis_dir[0],
                    axis_loc[1] + (s_face - s_of(axis_loc)) * axis_dir[1],
                    axis_loc[2] + (s_face - s_of(axis_loc)) * axis_dir[2],
                )
                min_r = 0.0 if _face_contains_axis_point(lf.face, axis_point) else min(radii)
                ring_area = math.pi * (max_r**2 - min_r**2)
                if ring_area > 0 and abs(lf.area - ring_area) <= _RING_RTOL * ring_area:
                    lf.max_r, lf.s_face = max_r, s_face
                    turned_planes.append(lf)
                    continue
            asymmetric.append(lf)
        elif lf.kind in (1, 2, 4):
            if coaxial(lf):
                (internal_axial if _is_concave(lf) else external_axial).append(lf)
            elif lf.kind == 1 and _is_concave(lf):
                off_axis_cyls.append(lf)
            else:
                asymmetric.append(lf)
        elif lf.kind == 3:
            if coaxial(lf):
                (internal_axial if _is_concave(lf) else external_axial).append(lf)
            else:
                asymmetric.append(lf)
        else:
            asymmetric.append(lf)

    # -- stock: max radial reach x axial extent (GEOMETRY.md §5, probed exact) - #
    all_points = [p for lf in faces for p in lf.points]
    s_values = [s_of(p) for p in all_points]
    body_lo, body_hi = min(s_values), max(s_values)
    stock_length = body_hi - body_lo
    stock_radius = max(r_of(p) for p in all_points)
    for lf in (*external_axial, *internal_axial):
        # exact promotion for CYLINDERS only: a coaxial cylinder's defining
        # radius IS its radial extent. A sphere's defining radius is not — a
        # shallow SR-crowned face would inflate the stock 5x (fresh-eyes
        # review, M4.5); spheres/tori rely on the sampled extent above.
        if lf.kind == 1 and lf.radius is not None:
            stock_radius = max(stock_radius, lf.radius)
    if stock_radius <= 0.0 or stock_length <= 0.0:
        return {}, []

    # -- bores: contiguous coaxial concave spans -> internal_cut each ---------- #
    bore_walls = [lf for lf in internal_axial if lf.kind == 1]
    for lf in bore_walls:
        spans = sorted(s_of(p) for p in lf.points)
        lf.s_lo, lf.s_hi = spans[0], spans[-1]
    bore_walls.sort(key=lambda lf: (lf.s_lo, -(lf.radius or 0.0)))
    bores: list[list[_LatheFace]] = []
    for lf in bore_walls:
        for group in bores:
            if lf.s_lo <= max(g.s_hi for g in group) + _DIST_TOL:
                group.append(lf)
                break
        else:
            bores.append([lf])

    # internal turned planes = bore bottoms: within a bore's radius at its end
    internal_planes: list[_LatheFace] = []
    for plane in turned_planes:
        max_r = plane.max_r
        s_face = plane.s_face
        for group in bores:
            radius = max(g.radius or 0.0 for g in group)
            lo = min(g.s_lo for g in group)
            hi = max(g.s_hi for g in group)
            if max_r <= radius + _DIST_TOL and (
                abs(s_face - lo) <= _DIST_TOL or abs(s_face - hi) <= _DIST_TOL
            ):
                plane.bore = group
                internal_planes.append(plane)
                break
    external_planes = [p for p in turned_planes if p not in internal_planes]

    # -- off-axis holes: group coaxial-among-themselves concave cylinders ------ #
    # (grouped BEFORE the coverage gate so a partial concave fillet that fails
    # the sweep guard counts as asymmetric — not as recognized hole area that
    # would weaken the non-turned rejection; fresh-eyes review, M4.5)
    hole_groups: list[list[_LatheFace]] = []
    for lf in off_axis_cyls:
        assert lf.axis is not None
        for group in hole_groups:
            g0 = group[0]
            assert g0.axis is not None
            if (
                abs(abs(_v_dot(_v_unit(lf.axis[0]), _v_unit(g0.axis[0]))) - 1.0) <= _DIR_TOL
                and _radial_offset(lf.axis[1], _v_unit(g0.axis[0]), g0.axis[1]) <= _DIST_TOL
            ):
                group.append(lf)
                break
        else:
            hole_groups.append([lf])
    off_axis_holes: list[dict[str, Any]] = []
    accepted_hole_area = 0.0
    for group in hole_groups:
        if sum(g.sweep_deg for g in group) < _MIN_HOLE_SWEEP_DEG:
            asymmetric.extend(group)  # a partial concave fillet, not a hole
            continue
        g0 = group[0]
        assert g0.axis is not None
        # min radius over the group: a counterbored hole reports its drill
        # size for the full depth (facts), not a traversal-order-dependent
        # mix of the largest bore with the whole span (fresh-eyes, M4.5)
        radius = min(g.radius or 0.0 for g in group)
        own_dir = _v_unit(g0.axis[0])
        spans = [_v_dot(p, own_dir) for g in group for p in g.points]
        accepted_hole_area += sum(g.area for g in group)
        off_axis_holes.append(
            {
                "name": "off_axis_hole",
                "properties": {
                    "radius": radius,
                    "diameter": 2 * radius,
                    "depth": max(spans) - min(spans),
                    "area": sum(g.area for g in group),
                },
                "geometry_refs": [],
            }
        )
    off_axis_holes.sort(
        key=lambda h: (h["properties"]["radius"], h["properties"]["depth"], h["properties"]["area"])
    )

    # -- coverage gate: recognized area must dominate, else nothing ------------ #
    recognized = (
        sum(lf.area for lf in external_axial)
        + sum(lf.area for lf in internal_axial)
        + sum(lf.area for lf in turned_planes)
        + accepted_hole_area
    )
    if recognized / total_area < _TURNED_COVERAGE_MIN:
        return {}, []

    # -- setups: distinct axial sides carrying INTERMEDIATE turned work -------- #
    # (shoulders + blind-bore bottoms + concave cone tips; the extreme end
    # faces exist on every part and do not force a chucking side — in-house
    # heuristic per the capability map, ASSUMED)
    sides: set[int] = set()
    for plane in turned_planes:
        s_face = plane.s_face
        if body_lo + _DIST_TOL < s_face < body_hi - _DIST_TOL:
            sides.add(1 if _v_dot(plane.normal, axis_dir) > 0 else -1)
    for lf in internal_axial:
        if lf.kind == 2:  # drill-tip cone: opens toward its outward axial side
            axial = _v_dot(lf.normal, axis_dir)
            if abs(axial) > _DIR_TOL:
                sides.add(1 if axial > 0 else -1)
    ordered_sides = sorted(sides, reverse=True) or [1]
    setup_count = len(ordered_sides)

    # -- emit ------------------------------------------------------------------ #
    features: list[dict[str, Any]] = [
        {
            "name": "lathe_stock",
            "properties": {
                "radius": stock_radius,
                "diameter": 2 * stock_radius,
                "length": stock_length,
            },
            "geometry_refs": [],
        }
    ]
    for side in ordered_sides:
        features.append(
            {
                "name": "setup",
                "properties": {"direction": [side * c for c in axis_dir]},
                "geometry_refs": [],
            }
        )
    ext_axial_area = sum(lf.area for lf in external_axial)
    ext_radial_area = sum(lf.area for lf in external_planes)
    if ext_axial_area + ext_radial_area > 0:
        features.append(
            {
                "name": "external_cut",
                "properties": {
                    "axial_area": ext_axial_area,
                    "radial_area": ext_radial_area,
                    "area": ext_axial_area + ext_radial_area,
                    "max_radius": stock_radius,
                    "length": stock_length,
                },
                "geometry_refs": [],
            }
        )
    for group in sorted(
        bores,
        key=lambda g: (-max(f.radius or 0.0 for f in g), min(f.s_lo for f in g)),
    ):
        lo = min(f.s_lo for f in group)
        hi = max(f.s_hi for f in group)
        radius = min(f.radius or 0.0 for f in group)
        bottoms = [p for p in internal_planes if getattr(p, "bore", None) is group]
        thru = lo <= body_lo + _DIST_TOL and hi >= body_hi - _DIST_TOL
        features.append(
            {
                "name": "internal_cut",
                "properties": {
                    "radius": radius,
                    "diameter": 2 * radius,
                    "depth": hi - lo,
                    "thru": thru,
                    "axial_area": sum(f.area for f in group),
                    "radial_area": sum(p.area for p in bottoms),
                    "area": sum(f.area for f in group) + sum(p.area for p in bottoms),
                },
                "geometry_refs": [],
            }
        )
    features.extend(off_axis_holes)
    if asymmetric:
        features.append(
            {
                "name": "asymmetric_cavity",
                "properties": {
                    "face_count": len(asymmetric),
                    "area": sum(lf.area for lf in asymmetric),
                },
                "geometry_refs": [],
            }
        )

    scalars: dict[str, Any] = {
        "setup_count": setup_count,
        "stock_radius": stock_radius,
        "stock_length": stock_length,
    }
    return scalars, features


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
        family_scalars: dict[str, Any] = {}
        features: list[dict[str, Any]] = []
        confidence: Literal["High", "Medium", "Low"] | None = None
        if family == FAMILY_SHEET_METAL:
            family_scalars, features = _analyze_sheet_metal(shape, volume, area)
        elif family == FAMILY_MILLING:
            family_scalars, features, confidence = _analyze_mill3(shape, volume, inputs)
        elif family == FAMILY_LATHE:
            # attributes + stock only (v2.15); no runtime -> no confidence
            family_scalars, features = _analyze_lathe(shape, inputs)
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
            family_scalars=family_scalars,
            features=features,
            confidence=confidence,
        )

    def compute_signature(self, step_bytes: bytes) -> str:
        return _fingerprint(_read_step(step_bytes))
