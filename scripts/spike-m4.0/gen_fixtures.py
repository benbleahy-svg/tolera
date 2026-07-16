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
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(path))
    assert status == IFSelect_RetDone, f"STEP write failed for {path}"


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
        "bbox": [60, 50, 40],
        "thickness": 2.0,
        "bend_count": 1,
        "bend_inner_radius": 3.0,
        "bend_angle_deg": 90.0,
        "bend_line_length": 50.0,
        "k_factor": k,
        "developed_length": 55 + 35 + bend_allowance,
        "unfolded_size": [55 + 35 + bend_allowance, 50.0],
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
        "bbox": [80, 50, 20],
        "through_holes": {"count": 2, "diameter": 8.0},
        "blind_holes": {"count": 1, "diameter": 6.0, "depth": 10.0},
        "pocket": {"size": [40, 20], "depth": 8.0},
        "machine_directions_expected": ["+Z"],
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
    ok = writer.Transfer(doc, STEPControl_AsIs)
    assert ok, "XCAF transfer failed"
    status = writer.Write(str(path))
    assert status == IFSelect_RetDone, "assembly STEP write failed"
    return {
        "family": "assembly",
        "products": 2,
        "occurrences": {"PLATE-60x40x5": 1, "PIN-D6x20": 2},
        "materials": {"PIN-D6x20": "1.4301 @ 7.9 g/cm3", "PLATE-60x40x5": "AlMg3 @ 2.66 g/cm3"},
        "plate_volume": 60 * 40 * 5,
        "pin_volume": math.pi * 9 * 20,
    }


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    outdir.mkdir(parents=True, exist_ok=True)
    goldens: dict[str, dict] = {}

    # cube-20mm.step and plate-hole-20x20x10-d8.step are pre-existing (M1.13/M2.6)
    # fixtures the probes also read — regenerating into a fresh outdir needs both
    # copied in, or probe_a/probe_d will fail on the missing files.
    solids = {
        "bracket-L-60x40x2-r3.step": bracket,
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
        assert rel < 1e-6, f"{name}: modelled volume deviates from analytic golden"
        write_step(shape, outdir / name)
        goldens[name] = golden

    goldens["asm-plate-2pins.step"] = write_assembly(outdir / "asm-plate-2pins.step")
    (outdir / "goldens.json").write_text(json.dumps(goldens, indent=2) + "\n")
    print(f"\nwrote {len(goldens)} fixtures + goldens.json to {outdir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
