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
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCP.GC import GC_MakeArcOfCircle
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
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


# --- 2. Milled block 80x50x20: pocket 40x20x8 + 2 through holes d8 + blind d6x10 ---
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
        "shaft-stepped-d30-d20-d12.step": shaft,
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
