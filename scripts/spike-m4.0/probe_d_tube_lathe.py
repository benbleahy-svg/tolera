# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 probe (d): tube-laser cross-section classification via mid-length section
(round / rectangular / angle / u_channel; rectangular_radiused untested — no
fixture, expected same mechanism) + lathe stock recommendation on the stepped
shaft (build-plan M4.0 (d), M4.5/M4.6 thin-block inputs).

Run: uv run scripts/spike-m4.0/probe_d_tube_lathe.py [fixtures_dir]
"""

import json
import math
import sys
from pathlib import Path

from common import aabb_dims, faces, read_step
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

LINE, CIRCLE = 0, 1
CYLINDER = 1


def section_edges(shape, plane_origin, plane_normal):
    sec = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(*plane_origin), gp_Dir(*plane_normal)))
    sec.Build()
    result = sec.Shape()
    edges = []
    ex = TopExp_Explorer(result, TopAbs_EDGE)
    while ex.More():
        edges.append(TopoDS.Edge_s(ex.Current()))
        ex.Next()
    return edges


def edge_kind(edge) -> tuple[str, float]:
    ad = BRepAdaptor_Curve(edge)
    t = ad.GetType()
    if t == CIRCLE:
        return "circle", ad.Circle().Radius()
    return {LINE: "line"}.get(t, "other"), 0.0


def endpoints(edge):
    pts = []
    ex = TopExp_Explorer(edge, TopAbs_VERTEX)
    while ex.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(ex.Current()))
        pts.append((round(p.X(), 6), round(p.Y(), 6), round(p.Z(), 6)))
        ex.Next()
    return pts


def loop_count(edges) -> int:
    """Union-find over edge endpoints -> connected components of the section."""
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        pts = endpoints(e)
        for p in pts[1:]:
            parent[find(pts[0])] = find(p)
    return len({find(p) for p in parent})


def classify_tube(shape) -> dict:
    dims = aabb_dims(shape)
    axis_idx = dims.index(max(dims))
    normal = [0, 0, 0]
    normal[axis_idx] = 1
    # section at the true bbox midpoint so the cut lands inside the solid even
    # when the fixture is not anchored at the origin
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    origin = [(lo.X() + hi.X()) / 2, (lo.Y() + hi.Y()) / 2, (lo.Z() + hi.Z()) / 2]

    edges = section_edges(shape, origin, normal)
    kinds = [edge_kind(e) for e in edges]
    circles = sorted((r for k, r in kinds if k == "circle"), reverse=True)
    lines = [e for e, (k, _) in zip(edges, kinds, strict=True) if k == "line"]
    arcs = [k for k, _ in kinds if k == "other"]

    if len(circles) == 2 and not lines:
        return {
            "stock_type": "round",
            "diameter": 2 * circles[0],
            "thickness": circles[0] - circles[1],
            "length": dims[axis_idx],
        }
    if lines and not circles:
        loops = loop_count(lines)
        n = len(lines)
        if loops == 2:
            return {"stock_type": "rectangular", "length": dims[axis_idx], "edges": n}
        if loops == 1 and n == 6:
            return {"stock_type": "angle", "length": dims[axis_idx], "edges": n}
        if loops == 1 and n == 8:
            return {"stock_type": "u_channel", "length": dims[axis_idx], "edges": n}
    if arcs or (lines and circles):
        return {"stock_type": "rectangular_radiused?", "note": "mixed section — untested"}
    return {"stock_type": "incompatible"}


def probe_lathe(shape) -> dict:
    """All cylindrical faces on ONE common centerline -> turnable; stock =
    max radius x extent of the part projected onto that axis."""
    axes, radii = [], []
    for f in faces(shape):
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() == CYLINDER:
            cyl = ad.Cylinder()
            ax = cyl.Axis()
            d, loc = ax.Direction(), ax.Location()
            axes.append(((d.X(), d.Y(), d.Z()), (loc.X(), loc.Y(), loc.Z())))
            radii.append(cyl.Radius())
    coaxial = bool(axes)
    d0, p0 = axes[0] if axes else ((0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
    for d, pnt in axes[1:]:
        dot = abs(sum(a * b for a, b in zip(d, d0, strict=True)))
        gap = [a - b for a, b in zip(pnt, p0, strict=True)]
        along = sum(g * a for g, a in zip(gap, d0, strict=True))
        radial = math.sqrt(max(sum(g * g for g in gap) - along**2, 0.0))
        if abs(dot - 1.0) > 1e-6 or radial > 1e-6:
            coaxial = False
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    corners = [
        (x, y, z) for x in (lo.X(), hi.X()) for y in (lo.Y(), hi.Y()) for z in (lo.Z(), hi.Z())
    ]
    proj = [sum(c * a for c, a in zip(corner, d0, strict=True)) for corner in corners]
    return {
        "turnable": coaxial,
        "stock_radius": max(radii) if radii else None,
        "stock_length": max(proj) - min(proj) if axes else None,
        "step_diameters": sorted({round(2 * r, 3) for r in radii}, reverse=True),
    }


def main() -> int:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    goldens = json.loads((fixtures / "goldens.json").read_text())
    results: dict = {}
    ok = True

    tube_fixtures = [
        "tube-round-d30-t2-l200.step",
        "tube-rect-40x20-t2-l200.step",
        "profile-angle-40x40x4-l100.step",
        "profile-u-channel-40x20x3-l100.step",
    ]
    for name in tube_fixtures:
        res = classify_tube(read_step(fixtures / name))
        want = goldens[name]["stock_type"]
        got = res["stock_type"]
        this_ok = got == want
        if got == "round":
            this_ok = (
                this_ok
                and abs(res["diameter"] - goldens[name]["diameter"]) < 1e-6
                and abs(res["thickness"] - goldens[name]["thickness"]) < 1e-6
            )
        ok = ok and this_ok
        results[name] = res | {"want": want, "ok": this_ok}
        print(f"{name}: {got} (want {want}) -> {'OK' if this_ok else 'FAIL'}  {res}")

    # a solid that is no tube profile at all must classify incompatible
    res = classify_tube(read_step(fixtures / "cube-20mm.step"))
    this_ok = res["stock_type"] == "incompatible"
    ok = ok and this_ok
    results["cube-20mm.step"] = res | {"want": "incompatible", "ok": this_ok}
    print(
        f"cube-20mm.step: {res['stock_type']} (want incompatible) -> {'OK' if this_ok else 'FAIL'}"
    )

    lathe = probe_lathe(read_step(fixtures / "shaft-stepped-d30-d20-d12.step"))
    g = goldens["shaft-stepped-d30-d20-d12.step"]
    lathe_ok = (
        lathe["turnable"]
        and abs(lathe["stock_radius"] - g["stock_radius"]) < 1e-6
        and abs(lathe["stock_length"] - g["stock_length"]) < 1e-6
        and lathe["step_diameters"] == g["diameters"]
    )
    ok = ok and lathe_ok
    results["lathe"] = lathe | {"ok": lathe_ok}
    print(
        f"lathe shaft: stock r={lathe['stock_radius']} l={lathe['stock_length']} "
        f"steps={lathe['step_diameters']} turnable={lathe['turnable']} "
        f"-> {'OK' if lathe_ok else 'FAIL'}"
    )

    print(f"\nPROBE D {'PASS' if ok else 'FAIL'}")
    print(
        "note: rectangular_radiused untested (no fixture) — same section mechanism, "
        "flagged '~' in the capability map, not claimed"
    )
    out = Path("scripts/spike-m4.0/results")
    out.mkdir(exist_ok=True)
    (out / "probe_d.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
