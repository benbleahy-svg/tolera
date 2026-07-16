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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from OCP.Bnd import Bnd_Box, Bnd_OBB
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from .contract import (
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
#: its diameter vertices), so vertices alone understate panel extents.
_CURVE_SAMPLES = 32


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


def _detect_bends(cylinders: list[_CylFace], thickness: float) -> list[_Bend]:
    bends = []
    used: set[int] = set()
    for i, a in enumerate(cylinders):
        if i in used:
            continue
        for j in range(i + 1, len(cylinders)):
            if j in used:
                continue
            b = cylinders[j]
            if abs(abs(_v_dot(a.axis_dir, b.axis_dir)) - 1.0) > _DIR_TOL:
                continue
            gap = _v_sub(a.axis_loc, b.axis_loc)
            along = _v_dot(gap, a.axis_dir)
            radial = math.sqrt(max(_v_dot(gap, gap) - along * along, 0.0))
            if radial > _DIST_TOL:
                continue  # parallel but not concentric — two different bends
            if abs(abs(a.radius - b.radius) - thickness) > _DIST_TOL:
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

    pierce_wires = sum(_inner_wire_count(f.face) for p in panels for f in p.faces)

    scalars: dict[str, Any] = {
        "thickness": thickness,
        "bend_count": len(bends),
        # mid-surface identities, exact for constant-thickness bodies: the flat
        # pattern's area and its total contour length (outer + cutouts)
        "flat_area": volume / thickness,
        "total_cut_length": (area - 2.0 * volume / thickness) / thickness,
        "pierce_count": pierce_wires // 2,
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
        if family == FAMILY_SHEET_METAL:
            family_scalars, features = _analyze_sheet_metal(shape, volume, area)
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
        )

    def compute_signature(self, step_bytes: bytes) -> str:
        return _fingerprint(_read_step(step_bytes))
