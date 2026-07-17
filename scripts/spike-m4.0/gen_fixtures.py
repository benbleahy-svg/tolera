# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 fixture generator — synthetic ground-truth STEP fixtures for the OCCT probe.

Throwaway spike scaffold (build-plan M4.0). Every fixture is constructed from OCCT
primitives with exact known dimensions, so the goldens (goldens.json) are analytic,
not measured. Units: mm (metric-native, CLAUDE.md §5).

Run: uv run scripts/spike-m4.0/gen_fixtures.py [outdir]   (default: fixtures/cad)
"""

import json
import math
import sys
from pathlib import Path
from shutil import copy2

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakePrism,
    BRepPrimAPI_MakeSphere,
)
from OCP.GC import GC_MakeArcOfCircle
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool

MM = 1.0  # all values mm


def volume_of(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def face_count(shape) -> int:
    n, ex = 0, TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        n += 1
        ex.Next()
    return n


def write_step(shape, path: Path) -> None:
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise RuntimeError(f"STEP transfer failed for {path}")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed for {path}")


def edge_line(p1, p2):
    return BRepBuilderAPI_MakeEdge(gp_Pnt(*p1), gp_Pnt(*p2)).Edge()


def edge_arc(p1, pmid, p2):
    arc = GC_MakeArcOfCircle(gp_Pnt(*p1), gp_Pnt(*pmid), gp_Pnt(*p2)).Value()
    return BRepBuilderAPI_MakeEdge(arc).Edge()


def prism_from_profile(edges, vec):
    wire_mk = BRepBuilderAPI_MakeWire()
    for e in edges:
        wire_mk.Add(e)
    face = BRepBuilderAPI_MakeFace(wire_mk.Wire()).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(*vec)).Shape()


# --- 1. Sheet-metal L-bracket: legs 60/40, width 50, t=2, inner bend r=3, 90 deg ---
def bracket() -> tuple[object, dict]:
    c = (5.0, 0.0, 5.0)  # bend arc centre in XZ

    def on_arc(r, deg):
        a = math.radians(deg)
        return (c[0] + r * math.cos(a), 0.0, c[2] + r * math.sin(a))

    edges = [
        edge_line((60, 0, 0), (5, 0, 0)),
        edge_arc((5, 0, 0), on_arc(5, 225), (0, 0, 5)),  # outer bend r5 = r+t
        edge_line((0, 0, 5), (0, 0, 40)),
        edge_line((0, 0, 40), (2, 0, 40)),
        edge_line((2, 0, 40), (2, 0, 5)),
        edge_arc((2, 0, 5), on_arc(3, 225), (5, 0, 2)),  # inner bend r3
        edge_line((5, 0, 2), (60, 0, 2)),
        edge_line((60, 0, 2), (60, 0, 0)),
    ]
    shape = prism_from_profile(edges, (0, 50, 0))
    k = (0.65 + 0.5 * math.log10(3 / 2)) * 0.5
    bend_allowance = (math.pi / 2) * (3 + k * 2)
    golden = {
        "family": "sheet_metal",
        "volume": (55 * 2 + 35 * 2 + (math.pi / 4) * (25 - 9)) * 50,
        "area": (184 + 4 * math.pi) * 50 + 2 * (180 + 4 * math.pi),
        "bbox": [60, 50, 40],
        "thickness": 2.0,
        "bend_count": 1,
        "bend_inner_radius": 3.0,
        "bend_angle_deg": 90.0,
        "bend_line_length": 50.0,
        "k_factor": k,
        "developed_length": 55 + 35 + bend_allowance,
        "unfolded_size": [55 + 35 + bend_allowance, 50.0],
        # M4.2 additions (analytic): mid-surface flat area = volume/t; cut length
        # = flat-pattern perimeter at the mid-line (2*dev_mid + 2*width)
        "bends": [{"radius": 3.0, "angle_deg": 90.0, "line_length": 50.0, "k_factor": k}],
        "bend_line_positions": [55 + bend_allowance / 2],
        "flat_area": (55 * 2 + 35 * 2 + (math.pi / 4) * (25 - 9)) * 50 / 2,
        "total_cut_length": 2 * (90 + (math.pi / 2) * 4) + 2 * 50,
        "pierce_count": 0,
    }
    return shape, golden


# --- 1b. Sheet-metal bend chain (M4.2): generic turtle builder + 3-bend fixture ---
def bend_chain_profile(flats: list[float], bends: list[tuple[float, int]], t: float, r: float):
    """Outline edges (XZ plane, y=0) for a sheet strip: flats[i] are the FLAT
    panel lengths between bend tangents; bends[i] = (angle_deg, direction) with
    +1 bending toward the sheet's top skin, -1 away. Inner radius r, thickness t.
    Returns closed profile edges for ``prism_from_profile``."""

    def perp(v):
        return (-v[1], v[0])

    def rot(v, a):
        c, s = math.cos(a), math.sin(a)
        return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)

    def add(a, b):
        return (a[0] + b[0], a[1] + b[1])

    def mul(v, k):
        return (v[0] * k, v[1] * k)

    p = (0.0, 0.0)
    h = (1.0, 0.0)
    bottom: list[tuple] = []  # ('line', p1, p2) | ('arc', p1, pmid, p2), 2D
    top: list[tuple] = []
    for i, flat in enumerate(flats):
        n = perp(h)
        p_end = add(p, mul(h, flat))
        bottom.append(("line", p, p_end))
        top.append(("line", add(p, mul(n, t)), add(p_end, mul(n, t))))
        p = p_end
        if i < len(bends):
            angle_deg, direction = bends[i]
            sweep = direction * math.radians(angle_deg)
            n = perp(h)
            centre = add(p, mul(n, r + t if direction > 0 else -r))

            def about(q, ang, c=centre):
                return add(c, rot((q[0] - c[0], q[1] - c[1]), ang))

            p_top = add(p, mul(n, t))
            bottom.append(("arc", p, about(p, sweep / 2), about(p, sweep)))
            top.append(("arc", p_top, about(p_top, sweep / 2), about(p_top, sweep)))
            p = about(p, sweep)
            h = rot(h, sweep)
    # close the outline: bottom forward → far cap → top reversed → near cap
    n = perp(h)
    segs = list(bottom)
    segs.append(("line", p, add(p, mul(n, t))))
    for seg in reversed(top):
        if seg[0] == "line":
            segs.append(("line", seg[2], seg[1]))
        else:
            segs.append(("arc", seg[3], seg[2], seg[1]))
    segs.append(("line", top[0][1], bottom[0][1]))

    def p3(q):
        return (q[0], 0.0, q[1])

    edges = []
    for seg in segs:
        if seg[0] == "line":
            edges.append(edge_line(p3(seg[1]), p3(seg[2])))
        else:
            edges.append(edge_arc(p3(seg[1]), p3(seg[2]), p3(seg[3])))
    return edges


def bracket_z3() -> tuple[object, dict]:
    """3-bend strip (M4.2 acceptance fixture): mixed bend directions (up/down/up),
    one non-90° bend, plus a d6 through hole in the first panel (pierce_count).
    All bend axes parallel (+Y) — the v1 analytic-unfold envelope."""
    flats = [40.0, 30.0, 25.0, 15.0]
    bends = [(90.0, 1), (90.0, -1), (45.0, 1)]
    t, r, w = 2.0, 3.0, 50.0
    shape = prism_from_profile(bend_chain_profile(flats, bends, t, r), (0, w, 0))
    hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(20, 25, -1), gp_Dir(0, 0, 1)), 3.0, 4.0).Shape()
    shape = BRepAlgoAPI_Cut(shape, hole).Shape()

    sum_flats = sum(flats)
    sweep = [math.radians(a) for a, _ in bends]
    profile_area = t * sum_flats + sum(a * t * (r + t / 2) for a in sweep)
    hole_r = 3.0
    volume = profile_area * w - math.pi * hole_r**2 * t
    # skins (flats + arcs at the direction-dependent radius) - 2 hole disks,
    # + 2 profile side walls + 2 strip-end caps + the hole wall
    bottom_len = sum_flats + sum(
        a * ((r + t) if d > 0 else r) for a, (_, d) in zip(sweep, bends, strict=True)
    )
    top_len = sum_flats + sum(
        a * (r if d > 0 else (r + t)) for a, (_, d) in zip(sweep, bends, strict=True)
    )
    area = (
        (bottom_len + top_len) * w
        - 2 * math.pi * hole_r**2
        + 2 * profile_area
        + 2 * t * w
        + 2 * math.pi * hole_r * t
    )
    k = (0.65 + 0.5 * math.log10(r / t)) * 0.5
    allowances = [a * (r + k * t) for a in sweep]
    developed = sum_flats + sum(allowances)
    # bend-line positions = centre of each bend region along the unfold
    positions, cursor = [], 0.0
    for flat, ba in zip(flats, allowances, strict=False):
        cursor += flat
        positions.append(cursor + ba / 2)
        cursor += ba
    # no "bbox" golden: the engine's min-volume OBB/AABB tie-break legitimately
    # beats the construction-frame AABB on this tilted-end profile, and an
    # analytic optimal OBB is not worth deriving — this fixture exists for the
    # sheet-metal scalars (volume/area stay analytic below).
    golden = {
        "family": "sheet_metal",
        "volume": volume,
        "area": area,
        "thickness": t,
        "bend_count": 3,
        "bends": [{"radius": r, "angle_deg": a, "line_length": w, "k_factor": k} for a, _ in bends],
        "k_factor": k,
        "developed_length": developed,
        "unfolded_size": [developed, w],
        "bend_line_positions": positions,
        "flat_area": volume / t,
        "total_cut_length": (area - 2 * volume / t) / t,
        "pierce_count": 1,
    }
    return shape, golden


# --- 2. Milling fixtures (M4.4) -------------------------------------------------
# Runtime-heuristic constants — MUST mirror app/geometry/occt.py (the engine's
# _MILL_* block). The goldens below hand-compute the per-setup runtimes from
# these, so a silent drift of either side fails tests/test_milling_m44.py.
# All are ASSUMED calibratable engineering defaults (build-plan M4.4: runtime
# is the in-house honest-ceiling heuristic — no OCCT/spec formula exists).
MILL_MRR_MM3_MIN = 15000.0  # roughing removal rate
MILL_DRILL_MM_MIN = 300.0  # drill axial penetration rate
MILL_HOLE_HANDLING_MIN = 0.5  # per-hole positioning/tool time
MILL_SURF_MM2_MIN = 1500.0  # surfacing area rate
MILL_PROFILE_MM2_MIN = 6000.0  # wall-profiling finish area rate


def mill_minutes(
    rough_mm3: float = 0.0,
    hole_depths: tuple[float, ...] = (),
    profiled_mm2: float = 0.0,
    surfaced_mm2: float = 0.0,
) -> float:
    """The M4.4 per-setup runtime heuristic, in minutes (engine mirror)."""
    return (
        rough_mm3 / MILL_MRR_MM3_MIN
        + sum(d / MILL_DRILL_MM_MIN + MILL_HOLE_HANDLING_MIN for d in hole_depths)
        + profiled_mm2 / MILL_PROFILE_MM2_MIN
        + surfaced_mm2 / MILL_SURF_MM2_MIN
    )


# --- 2a. Milled block 80x50x20: pocket 40x20x8 + 2 through holes d8 + blind d6x10 ---
def milled_block() -> tuple[object, dict]:
    shape = BRepPrimAPI_MakeBox(80, 50, 20).Shape()
    pocket = BRepPrimAPI_MakeBox(gp_Pnt(20, 15, 12), 40, 20, 8).Shape()
    shape = BRepAlgoAPI_Cut(shape, pocket).Shape()
    for x in (15.0, 65.0):
        hole = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(x, 25, -1), gp_Dir(0, 0, 1)), 4.0, 22.0
        ).Shape()
        shape = BRepAlgoAPI_Cut(shape, hole).Shape()
    blind = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(40, 8, 10), gp_Dir(0, 0, 1)), 3.0, 11.0).Shape()
    shape = BRepAlgoAPI_Cut(shape, blind).Shape()
    golden = {
        "family": "milling",
        "volume": 80 * 50 * 20 - 40 * 20 * 8 - 2 * math.pi * 16 * 20 - math.pi * 9 * 10,
        # box 13200 + pocket walls/floor net + 2 through holes net + blind net
        "area": 13200 + 960 + 256 * math.pi + 60 * math.pi,
        "bbox": [80, 50, 20],
        "through_holes": {"count": 2, "diameter": 8.0},
        "blind_holes": {"count": 1, "diameter": 6.0, "depth": 10.0},
        "pocket": {"size": [40, 20], "depth": 8.0},
        "machine_directions_expected": ["Z"],
        # M4.4 golden: everything is cut from +Z → one setup; every removed mm³
        # is feature-parameterized (pocket + 3 holes) → confidence High (KB
        # milling-feature-iteration: parameterized-removal fraction ≥ 0.8).
        "milling": _milled_block_milling_golden(),
    }
    return shape, golden


def _milled_block_milling_golden() -> dict:
    pocket_walls = 2 * (40 * 8) + 2 * (20 * 8)  # 960 — profiled
    pocket_floor = 40 * 20.0  # derived
    runtime_min = mill_minutes(
        rough_mm3=40 * 20 * 8,
        hole_depths=(20.0, 20.0, 10.0),
        profiled_mm2=pocket_walls,
    )
    return {
        "setup_count": 1,
        "setup_time_hr": 1.0,
        "runtime_hr": runtime_min / 60.0,
        "confidence": "High",
        "setups": [
            {
                "direction": [0, 0, 1],
                "setup_time_hr": 1.0,
                "runtime_hr": runtime_min / 60.0,
                "confidence": "High",
                "machine_direction": {
                    "profiled_area": pocket_walls,
                    "derived_area": pocket_floor,
                    "surfaced_area": 0.0,
                },
            }
        ],
        "holes": [
            {
                "bottom_type": "thru",
                "diameter": 8.0,
                "depth": 20.0,
                "volume": math.pi * 16 * 20,
                "area": math.pi * 8 * 20,
                "count": 2,
            },
            {
                "bottom_type": "flat",
                "diameter": 6.0,
                "depth": 10.0,
                "volume": math.pi * 9 * 10,
                "area": math.pi * 6 * 10 + math.pi * 9,
                "count": 1,
            },
        ],
        "pockets": [
            {
                "area": pocket_floor + pocket_walls,
                "volume": 40 * 20 * 8.0,
                "max_depth": 8.0,
                "bottom_type": "flat",
                "has_transition": False,
            }
        ],
    }


# --- 2b. Three-setup block 60x40x20 (M4.4): pocket from +Z, blind holes from +X / -Y ---
def block_3setups() -> tuple[object, dict]:
    shape = BRepPrimAPI_MakeBox(60, 40, 20).Shape()
    pocket = BRepPrimAPI_MakeBox(gp_Pnt(10, 12.5, 14), 20, 15, 6).Shape()
    shape = BRepAlgoAPI_Cut(shape, pocket).Shape()
    # blind flat-bottom d8x12 along +X (entry on the x=60 face)
    hole_x = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(48, 20, 8), gp_Dir(1, 0, 0)), 4.0, 13.0).Shape()
    shape = BRepAlgoAPI_Cut(shape, hole_x).Shape()
    # blind flat-bottom d6x10 along -Y (entry on the y=0 face)
    hole_y = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(40, -1, 10), gp_Dir(0, 1, 0)), 3.0, 11.0
    ).Shape()
    shape = BRepAlgoAPI_Cut(shape, hole_y).Shape()

    pocket_walls = 2 * (20 * 6) + 2 * (15 * 6)  # 420 — profiled
    pocket_floor = 20 * 15.0  # derived
    # deterministic setup order: attributed removal volume desc → +Z, +X, -Y
    runtimes_min = [
        mill_minutes(rough_mm3=20 * 15 * 6, profiled_mm2=pocket_walls),
        mill_minutes(hole_depths=(12.0,)),
        mill_minutes(hole_depths=(10.0,)),
    ]
    golden = {
        "family": "milling",
        "volume": 60 * 40 * 20 - 20 * 15 * 6 - math.pi * 16 * 12 - math.pi * 9 * 10,
        # box 8800 + pocket walls net +420 + hole X net bore 96π + hole Y net 60π
        "area": 8800 + 420 + 96 * math.pi + 60 * math.pi,
        "bbox": [60, 40, 20],
        "milling": {
            "setup_count": 3,
            "setup_time_hr": 3.0,
            "runtime_hr": sum(runtimes_min) / 60.0,
            "confidence": "High",
            "setups": [
                {
                    "direction": [0, 0, 1],
                    "setup_time_hr": 1.0,
                    "runtime_hr": runtimes_min[0] / 60.0,
                    "confidence": "High",
                    "machine_direction": {
                        "profiled_area": pocket_walls,
                        "derived_area": pocket_floor,
                        "surfaced_area": 0.0,
                    },
                },
                {
                    "direction": [1, 0, 0],
                    "setup_time_hr": 1.0,
                    "runtime_hr": runtimes_min[1] / 60.0,
                    "confidence": "High",
                    "machine_direction": {
                        "profiled_area": 0.0,
                        "derived_area": 0.0,
                        "surfaced_area": 0.0,
                    },
                },
                {
                    "direction": [0, -1, 0],
                    "setup_time_hr": 1.0,
                    "runtime_hr": runtimes_min[2] / 60.0,
                    "confidence": "High",
                    "machine_direction": {
                        "profiled_area": 0.0,
                        "derived_area": 0.0,
                        "surfaced_area": 0.0,
                    },
                },
            ],
            "holes": [
                {
                    "bottom_type": "flat",
                    "diameter": 8.0,
                    "depth": 12.0,
                    "volume": math.pi * 16 * 12,
                    "area": math.pi * 8 * 12 + math.pi * 16,
                    "count": 1,
                },
                {
                    "bottom_type": "flat",
                    "diameter": 6.0,
                    "depth": 10.0,
                    "volume": math.pi * 9 * 10,
                    "area": math.pi * 6 * 10 + math.pi * 9,
                    "count": 1,
                },
            ],
            "pockets": [
                {
                    "area": pocket_floor + pocket_walls,
                    "volume": 20 * 15 * 6.0,
                    "max_depth": 6.0,
                    "bottom_type": "flat",
                    "has_transition": False,
                }
            ],
        },
    }
    return shape, golden


# --- 2c. Dome block 50x50x20 (M4.4 low-confidence): pocket from +Z + hemisphere r10 ---
def block_dome() -> tuple[object, dict]:
    shape = BRepPrimAPI_MakeBox(50, 50, 20).Shape()
    pocket = BRepPrimAPI_MakeBox(gp_Pnt(25, 20, 15), 20, 10, 5).Shape()
    shape = BRepAlgoAPI_Cut(shape, pocket).Shape()
    dome = BRepPrimAPI_MakeSphere(gp_Pnt(12, 25, 20), 10.0).Shape()
    shape = BRepAlgoAPI_Cut(shape, dome).Shape()

    pocket_walls = 2 * (20 * 5) + 2 * (10 * 5)  # 300 — profiled
    pocket_floor = 20 * 10.0  # derived
    dome_area = 2 * math.pi * 100  # hemisphere skin — surfaced (freeform)
    dome_volume = (2.0 / 3.0) * math.pi * 1000  # NOT feature-parameterized
    # unparameterized removal is roughed in the primary setup; the sphere face
    # is surfaced from +Z — but the parameterized fraction 1000/3094 ≈ 0.32
    # < 0.5 makes the whole estimate Low (KB's ≥80% High band).
    runtime_min = mill_minutes(
        rough_mm3=20 * 10 * 5 + dome_volume,
        profiled_mm2=pocket_walls,
        surfaced_mm2=dome_area,
    )
    golden = {
        "family": "milling",
        "volume": 50 * 50 * 20 - 20 * 10 * 5 - dome_volume,
        # box 9000 + pocket net +300 + dome net (-100pi opening + 200pi dome)
        "area": 9000 + 300 + 100 * math.pi,
        "bbox": [50, 50, 20],
        "milling": {
            "setup_count": 1,
            "setup_time_hr": 1.0,
            "runtime_hr": runtime_min / 60.0,
            "confidence": "Low",
            "setups": [
                {
                    "direction": [0, 0, 1],
                    "setup_time_hr": 1.0,
                    "runtime_hr": runtime_min / 60.0,
                    "confidence": "Low",
                    "machine_direction": {
                        "profiled_area": pocket_walls,
                        "derived_area": pocket_floor,
                        "surfaced_area": dome_area,
                    },
                }
            ],
            "holes": [],
            "pockets": [
                {
                    "area": pocket_floor + pocket_walls,
                    "volume": 20 * 10 * 5.0,
                    "max_depth": 5.0,
                    "bottom_type": "flat",
                    "has_transition": False,
                }
            ],
        },
    }
    return shape, golden


# --- 2d. Bevel block 40x40x20 (M4.4): only work is a 400 mm2 tapered face ---
def block_bevel() -> tuple[object, dict]:
    """The minimum_area_for_setup fixture: a 3-4-5 bevel (slant 10 x 40 =
    400 mm2, outward normal (-0.6, 0, -0.8) -> dominant -Z) along the bottom
    x=0 edge. Below the default 1000 mm2 gate no setup is allocated (nothing
    else needs cutting): setups stay empty, confidence Low, runtime 0 — the
    manual-override path, never a fabricated estimate."""
    shape = BRepPrimAPI_MakeBox(40, 40, 20).Shape()
    wedge = prism_from_profile(
        [
            edge_line((0, 0, 0), (8, 0, 0)),
            edge_line((8, 0, 0), (0, 0, 6)),
            edge_line((0, 0, 6), (0, 0, 0)),
        ],
        (0, 40, 0),
    )
    shape = BRepAlgoAPI_Cut(shape, wedge).Shape()
    # no "bbox" golden (bracket-Z3 precedent): the min-volume OBB legitimately
    # beats the construction-frame AABB on this beveled profile.
    golden = {
        "family": "milling",
        "volume": 40 * 40 * 20 - 0.5 * 8 * 6 * 40,
        # box 6400 - bottom strip 320 - x=0 strip 240 + slant 400
        "area": 6400 - 320 - 240 + 400,
        "milling": {
            "setup_count": 0,
            "setup_time_hr": 0.0,
            "runtime_hr": 0.0,
            "confidence": "Low",
            "setups": [],
            "holes": [],
            "pockets": [],
        },
    }
    return shape, golden


# --- 3. Lathe stepped shaft: d30x30 + d20x30 + d12x20 along Z ---
def shaft() -> tuple[object, dict]:
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    s = BRepPrimAPI_MakeCylinder(ax, 15.0, 30.0).Shape()
    s2 = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 30), gp_Dir(0, 0, 1)), 10.0, 30.0).Shape()
    s3 = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 60), gp_Dir(0, 0, 1)), 6.0, 20.0).Shape()
    shape = BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(s, s2).Shape(), s3).Shape()
    golden = {
        "family": "lathe",
        "volume": math.pi * (225 * 30 + 100 * 30 + 36 * 20),
        # laterals 2*(450+300+120) + step annuli (225-100)+(100-36) + both ends 225+36
        "area": math.pi * (2 * 870 + 125 + 64 + 225 + 36),
        "bbox": [30, 30, 80],
        "stock_radius": 15.0,
        "stock_length": 80.0,
        "diameters": [30.0, 20.0, 12.0],
        # M4.5 lathe golden: both shoulders face +Z -> one work side -> 1 setup;
        # axial (lateral) vs radial (facing) split is exact arithmetic.
        "lathe": {
            "setup_count": 1,
            "setup_directions": [[0, 0, 1]],
            "stock_radius": 15.0,
            "stock_length": 80.0,
            "external_cut": {
                "axial_area": math.pi * 2 * 870,
                "radial_area": math.pi * (125 + 64 + 225 + 36),
            },
            "internal_cuts": [],
            "off_axis_holes": {"count": 0},
            "asymmetric_faces": 0,
        },
    }
    return shape, golden


# --- 3b. Lathe bushing: OD d40x20 + d30x40, blind axial bore d16 depth 30 from z=0 ---
def bushing() -> tuple[object, dict]:
    z = gp_Dir(0, 0, 1)
    body = BRepAlgoAPI_Fuse(
        BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), z), 20.0, 20.0).Shape(),
        BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 20), z), 15.0, 40.0).Shape(),
    ).Shape()
    bore = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), z), 8.0, 31.0).Shape()
    shape = BRepAlgoAPI_Cut(body, bore).Shape()
    golden = {
        "family": "lathe",
        "volume": math.pi * (400 * 20 + 225 * 40 - 64 * 30),
        # OD laterals 2*(400+600) + shoulder (400-225) + ends (400-64)+225
        # + bore wall 2*8*30 + bore bottom 64
        "area": math.pi * (2000 + 175 + 336 + 225 + 480 + 64),
        "bbox": [40, 40, 60],
        # M4.5: shoulder faces +Z, blind-bore bottom faces -Z -> 2 setups.
        "lathe": {
            "setup_count": 2,
            "setup_directions": [[0, 0, 1], [0, 0, -1]],
            "stock_radius": 20.0,
            "stock_length": 60.0,
            "external_cut": {
                "axial_area": math.pi * 2000,
                "radial_area": math.pi * (175 + 336 + 225),
            },
            "internal_cuts": [
                {
                    "radius": 8.0,
                    "diameter": 16.0,
                    "depth": 30.0,
                    "thru": False,
                    "axial_area": math.pi * 480,
                    "radial_area": math.pi * 64,
                }
            ],
            "off_axis_holes": {"count": 0},
            "asymmetric_faces": 0,
        },
    }
    return shape, golden


# --- 3c. Lathe flange (DemoN/04 shape class): disc d40x15, centre bore d10 thru,
#         4 bolt holes d5 on a d28 bolt circle -> off-axis live-tooling callouts ---
def flange() -> tuple[object, dict]:
    z = gp_Dir(0, 0, 1)
    shape = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), z), 20.0, 15.0).Shape()
    for cx, cy, r in [(0, 0, 5.0), (14, 0, 2.5), (-14, 0, 2.5), (0, 14, 2.5), (0, -14, 2.5)]:
        hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(cx, cy, -1), z), r, 17.0).Shape()
        shape = BRepAlgoAPI_Cut(shape, hole).Shape()
    golden = {
        "family": "lathe",
        "volume": math.pi * 15 * (400 - 25 - 4 * 6.25),
        # OD lateral 600 + 2 ends 2*(400-25-25) + centre bore 150 + 4 bolt bores 300
        "area": math.pi * (600 + 700 + 150 + 300),
        "bbox": [40, 40, 15],
        # M4.5: no intermediate shoulder / blind bottom -> 1 setup (the drilled
        # bolt circle is live-tooling work, not a second chucking).
        "lathe": {
            "setup_count": 1,
            "setup_directions": [[0, 0, 1]],
            "stock_radius": 20.0,
            "stock_length": 15.0,
            "external_cut": {
                "axial_area": math.pi * 600,
                "radial_area": math.pi * 700,
            },
            "internal_cuts": [
                {
                    "radius": 5.0,
                    "diameter": 10.0,
                    "depth": 15.0,
                    "thru": True,
                    "axial_area": math.pi * 150,
                    "radial_area": 0.0,
                }
            ],
            "off_axis_holes": {"count": 4, "diameter": 5.0, "depth": 15.0},
            "asymmetric_faces": 0,
        },
    }
    return shape, golden


# --- 3d. Lathe domed pin: cylinder d20x40 + hemispherical end (turned profile) ---
def pin_domed() -> tuple[object, dict]:
    z = gp_Dir(0, 0, 1)
    body = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), z), 10.0, 40.0).Shape()
    dome = BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, 40), 10.0).Shape()
    shape = BRepAlgoAPI_Fuse(body, dome).Shape()
    golden = {
        "family": "lathe",
        "volume": math.pi * (100 * 40 + (2.0 / 3.0) * 1000),
        # lateral 2*10*40 + flat end 100 + hemisphere 2*100
        "area": math.pi * (800 + 100 + 200),
        "bbox": [20, 20, 50],
        # M4.5: the dome is turned profile work (no plane), no intermediate
        # shoulders -> 1 setup; sphere counts into the axial (lateral) split.
        "lathe": {
            "setup_count": 1,
            "setup_directions": [[0, 0, 1]],
            "stock_radius": 10.0,
            "stock_length": 50.0,
            "external_cut": {
                "axial_area": math.pi * (800 + 200),
                "radial_area": math.pi * 100,
            },
            "internal_cuts": [],
            "off_axis_holes": {"count": 0},
            "asymmetric_faces": 0,
        },
    }
    return shape, golden


# --- 4/5. Tubes ---
def tube_round() -> tuple[object, dict]:
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    outer = BRepPrimAPI_MakeCylinder(ax, 15.0, 200.0).Shape()
    inner = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), gp_Dir(0, 0, 1)), 13.0, 202.0).Shape()
    shape = BRepAlgoAPI_Cut(outer, inner).Shape()
    golden = {
        "family": "tube_laser",
        "stock_type": "round",
        "volume": math.pi * (225 - 169) * 200,
        "area": math.pi * (2 * 15 * 200 + 2 * 13 * 200 + 2 * (225 - 169)),
        "thickness": 2.0,
        "diameter": 30.0,
        "length": 200.0,
    }
    return shape, golden


def tube_rect() -> tuple[object, dict]:
    outer = BRepPrimAPI_MakeBox(40, 20, 200).Shape()
    inner = BRepPrimAPI_MakeBox(gp_Pnt(2, 2, -1), 36, 16, 202).Shape()
    shape = BRepAlgoAPI_Cut(outer, inner).Shape()
    golden = {
        "family": "tube_laser",
        "stock_type": "rectangular",
        "volume": (800 - 576) * 200,
        "area": 120 * 200 + 104 * 200 + 2 * (800 - 576),
        "thickness": 2.0,
        "width": 40.0,
        "height": 20.0,
        "length": 200.0,
    }
    return shape, golden


# --- 6/7. Open profiles (angle, U-channel) ---
def profile_angle() -> tuple[object, dict]:
    pts = [(0, 0), (40, 0), (40, 4), (4, 4), (4, 40), (0, 40)]
    edges = [edge_line((*pts[i], 0), (*pts[(i + 1) % len(pts)], 0)) for i in range(len(pts))]
    shape = prism_from_profile(edges, (0, 0, 100))
    golden = {
        "family": "tube_laser",
        "stock_type": "angle",
        "volume": (40 * 4 + 36 * 4) * 100,
        "area": 160 * 100 + 2 * (40 * 4 + 36 * 4),
        "leg_lengths": [40.0, 40.0],
        "thickness": 4.0,
        "length": 100.0,
    }
    return shape, golden


def profile_u_channel() -> tuple[object, dict]:
    pts = [(0, 0), (40, 0), (40, 20), (37, 20), (37, 3), (3, 3), (3, 20), (0, 20)]
    edges = [edge_line((*pts[i], 0), (*pts[(i + 1) % len(pts)], 0)) for i in range(len(pts))]
    shape = prism_from_profile(edges, (0, 0, 100))
    golden = {
        "family": "tube_laser",
        "stock_type": "u_channel",
        "volume": (40 * 3 + 2 * 17 * 3) * 100,
        "area": 154 * 100 + 2 * (40 * 3 + 2 * 17 * 3),
        "width": 40.0,
        "height": 20.0,
        "thickness": 3.0,
        "length": 100.0,
    }
    return shape, golden


# --- 8. Topology variant: 20mm cube built as fuse of two stacked 20x20x10 boxes ---
def cube_splitface() -> tuple[object, dict]:
    lower = BRepPrimAPI_MakeBox(20, 20, 10).Shape()
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(0, 0, 10))
    upper = BRepBuilderAPI_Transform(BRepPrimAPI_MakeBox(20, 20, 10).Shape(), tr, True).Shape()
    shape = BRepAlgoAPI_Fuse(lower, upper).Shape()
    golden = {
        "family": "milling",
        "volume": 8000.0,
        "area": 2400.0,
        "bbox": [20, 20, 20],
        "note": "same solid as cube-20mm.step; side faces split at z=10 seam",
        "expected_face_count_split": face_count(shape),
    }
    return shape, golden


# --- 9. XCAF assembly: plate + 2 pin occurrences, names + AP214 material/density ---
def write_assembly(path: Path) -> dict:
    from OCP.TCollection import TCollection_HAsciiString

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    mat_tool = XCAFDoc_DocumentTool.MaterialTool_s(doc.Main())

    plate = BRepPrimAPI_MakeBox(60, 40, 5).Shape()
    pin = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 3.0, 20.0).Shape()

    lbl_asm = shape_tool.NewShape()
    TDataStd_Name.Set_s(lbl_asm, TCollection_ExtendedString("ASM-PLATE-2PINS"))
    lbl_plate = shape_tool.AddShape(plate, False)
    TDataStd_Name.Set_s(lbl_plate, TCollection_ExtendedString("PLATE-60x40x5"))
    lbl_pin = shape_tool.AddShape(pin, False)
    TDataStd_Name.Set_s(lbl_pin, TCollection_ExtendedString("PIN-D6x20"))

    def hstr(s: str):
        return TCollection_HAsciiString(s)

    lbl_mat_steel = mat_tool.AddMaterial(
        hstr("1.4301"), hstr("X5CrNi18-10 stainless"), 7.9, hstr("g/cm3"), hstr("DENSITY")
    )
    lbl_mat_alu = mat_tool.AddMaterial(
        hstr("AlMg3"), hstr("EN AW-5754"), 2.66, hstr("g/cm3"), hstr("DENSITY")
    )
    mat_tool.SetMaterial(lbl_pin, lbl_mat_steel)
    mat_tool.SetMaterial(lbl_plate, lbl_mat_alu)

    shape_tool.AddComponent(lbl_asm, lbl_plate, TopLoc_Location(gp_Trsf()))
    for i, (x, y) in enumerate([(15.0, 20.0), (45.0, 20.0)], start=1):
        tr = gp_Trsf()
        tr.SetTranslation(gp_Vec(x, y, 5.0))
        lbl_occ = shape_tool.AddComponent(lbl_asm, lbl_pin, TopLoc_Location(tr))
        TDataStd_Name.Set_s(lbl_occ, TCollection_ExtendedString(f"PIN-{i}"))
    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetMaterialMode(True)
    if not writer.Transfer(doc, STEPControl_AsIs):
        raise RuntimeError("XCAF transfer failed")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError("assembly STEP write failed")
    return {
        "family": "assembly",
        "products": 2,
        "occurrences": {"PLATE-60x40x5": 1, "PIN-D6x20": 2},
        "materials": {"PIN-D6x20": "1.4301 @ 7.9 g/cm3", "PLATE-60x40x5": "AlMg3 @ 2.66 g/cm3"},
        "plate_volume": 60 * 40 * 5,
        "pin_volume": math.pi * 9 * 20,
    }


def main() -> int:
    # --sync (M4.2): refresh goldens.json from the builders but only write STEP
    # files that are missing on disk — existing fixture bytes stay untouched
    # (STEP headers carry timestamps; a no-op regeneration would still churn
    # every file and invalidate nothing but diffs).
    args = [a for a in sys.argv[1:] if a != "--sync"]
    sync_only = "--sync" in sys.argv[1:]
    outdir = Path(args[0]) if args else Path("fixtures/cad")
    outdir.mkdir(parents=True, exist_ok=True)
    # the probes also read these two pre-existing fixtures (M1.13/M2.6) — copy them
    # into a custom outdir so a regenerated set is self-contained
    canonical = Path(__file__).resolve().parents[2] / "fixtures/cad"
    for name in ("cube-20mm.step", "plate-hole-20x20x10-d8.step"):
        if (canonical / name).resolve() != (outdir / name).resolve():
            copy2(canonical / name, outdir / name)
    goldens: dict[str, dict] = {
        # analytic goldens for the pre-existing fixtures (cube 20^3; 20x20x10 plate
        # with a through hole d8)
        "cube-20mm.step": {
            "family": "milling",
            "volume": 8000.0,
            "area": 2400.0,
            "bbox": [20, 20, 20],
        },
        "plate-hole-20x20x10-d8.step": {
            "family": "milling",
            "volume": 4000 - math.pi * 16 * 10,
            "area": 1600 + 48 * math.pi,
            "bbox": [20, 20, 10],
        },
    }

    solids = {
        "bracket-L-60x40x2-r3.step": bracket,
        "bracket-Z3-3bend-t2-r3.step": bracket_z3,
        "block-milled-80x50x20.step": milled_block,
        "block-3setups-60x40x20.step": block_3setups,
        "block-dome-50x50x20.step": block_dome,
        "block-bevel-40x40x20.step": block_bevel,
        "shaft-stepped-d30-d20-d12.step": shaft,
        "bushing-d40-d30-bore-d16.step": bushing,
        "flange-d40-4bolt.step": flange,
        "pin-domed-d20-l50.step": pin_domed,
        "tube-round-d30-t2-l200.step": tube_round,
        "tube-rect-40x20-t2-l200.step": tube_rect,
        "profile-angle-40x40x4-l100.step": profile_angle,
        "profile-u-channel-40x20x3-l100.step": profile_u_channel,
        "cube-20mm-splitface.step": cube_splitface,
    }
    for name, builder in solids.items():
        shape, golden = builder()
        vol, expect = volume_of(shape), golden["volume"]
        rel = abs(vol - expect) / expect
        print(
            f"{name}: modelled vol {vol:.2f} vs analytic {expect:.2f} (rel {rel:.2e}), "
            f"faces {face_count(shape)}"
        )
        if rel >= 1e-6:
            raise RuntimeError(f"{name}: modelled volume deviates from analytic golden")
        if not sync_only or not (outdir / name).exists():
            write_step(shape, outdir / name)
        else:
            # Drift guard (CodeRabbit, M4.2): --sync refreshes goldens from the
            # BUILDERS while keeping existing STEP bytes — verify the on-disk
            # file still IS the built shape (volume vs the analytic golden),
            # so an edited builder can't silently mismatch fixture and golden.
            reader = STEPControl_Reader()
            if reader.ReadFile(str(outdir / name)) != IFSelect_RetDone:
                raise RuntimeError(f"{name}: existing STEP unreadable")
            reader.TransferRoots()
            disk_vol = volume_of(reader.OneShape())
            if abs(disk_vol - expect) / expect >= 1e-6:
                raise RuntimeError(
                    f"{name}: on-disk fixture (vol {disk_vol:.4f}) no longer matches its "
                    f"builder golden ({expect:.4f}) — regenerate without --sync"
                )
        goldens[name] = golden

    asm_path = outdir / "asm-plate-2pins.step"
    if sync_only and asm_path.exists():
        existing = json.loads((outdir / "goldens.json").read_text())
        goldens["asm-plate-2pins.step"] = existing["asm-plate-2pins.step"]
    else:
        goldens["asm-plate-2pins.step"] = write_assembly(asm_path)
    (outdir / "goldens.json").write_text(json.dumps(goldens, indent=2) + "\n")
    print(f"\nwrote {len(goldens)} fixtures + goldens.json to {outdir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
