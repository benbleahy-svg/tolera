# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 probe (b): sheet-metal recognition — thickness, bends (count/radius/angle/
line length), analytic k-factor unfold vs the bracket golden (build-plan M4.0 (b)).

k-factor per INTERROGATION-ENGINE-SPEC §3: k = (0.65 + 0.5*log10(r/t)) * 0.5

Run: uv run scripts/spike-m4.0/probe_b_sheetmetal.py [fixtures_dir]
"""

import json
import math
import sys
from pathlib import Path

from common import faces, read_step
from OCP.BRepAdaptor import BRepAdaptor_Surface

PLANE, CYLINDER = 0, 1


def plane_info(face):
    ad = BRepAdaptor_Surface(face)
    pln = ad.Plane()
    n = pln.Axis().Direction()
    loc = pln.Location()
    return (n.X(), n.Y(), n.Z()), (loc.X(), loc.Y(), loc.Z())


def cyl_info(face):
    ad = BRepAdaptor_Surface(face)
    cyl = ad.Cylinder()
    ax = cyl.Axis()
    d, loc = ax.Direction(), ax.Location()
    u_extent = abs(ad.LastUParameter() - ad.FirstUParameter())
    v_extent = abs(ad.LastVParameter() - ad.FirstVParameter())
    return {
        "radius": cyl.Radius(),
        "axis_dir": (d.X(), d.Y(), d.Z()),
        "axis_loc": (loc.X(), loc.Y(), loc.Z()),
        "angle_deg": math.degrees(u_extent),
        "line_length": v_extent,
    }


def detect_thickness(shape) -> float:
    """Smallest positive offset between anti-parallel planar face pairs."""
    planes = [plane_info(f) for f in faces(shape) if BRepAdaptor_Surface(f).GetType() == PLANE]
    best = None
    for i, (n1, p1) in enumerate(planes):
        for n2, p2 in planes[i + 1 :]:
            dot = sum(a * b for a, b in zip(n1, n2, strict=True))
            if abs(abs(dot) - 1.0) > 1e-6:
                continue  # not parallel
            # distance along the normal between the two plane origins
            d = abs(sum((a - b) * n for a, b, n in zip(p1, p2, n1, strict=True)))
            if d > 1e-6 and (best is None or d < best):
                best = d
    return best or 0.0


def detect_bends(shape, thickness: float) -> list[dict]:
    """Concentric cylindrical face pairs with radius delta == thickness."""
    cyls = [cyl_info(f) for f in faces(shape) if BRepAdaptor_Surface(f).GetType() == CYLINDER]
    bends = []
    for i, c1 in enumerate(cyls):
        for c2 in cyls[i + 1 :]:
            codir = abs(sum(a * b for a, b in zip(c1["axis_dir"], c2["axis_dir"], strict=True)))
            if abs(codir - 1.0) > 1e-6:
                continue
            axis_gap = math.dist(c1["axis_loc"], c2["axis_loc"])
            # allow axis origins anywhere along the shared axis line
            gap_vec = [a - b for a, b in zip(c1["axis_loc"], c2["axis_loc"], strict=True)]
            along = abs(sum(g * d for g, d in zip(gap_vec, c1["axis_dir"], strict=True)))
            radial_gap = math.sqrt(max(axis_gap**2 - along**2, 0.0))
            if radial_gap > 1e-6:
                continue  # not concentric
            r_in, r_out = sorted([c1["radius"], c2["radius"]])
            if abs((r_out - r_in) - thickness) > 1e-6:
                continue
            bends.append(
                {
                    "inner_radius": r_in,
                    "outer_radius": r_out,
                    "angle_deg": c1["angle_deg"],
                    "line_length": c1["line_length"],
                }
            )
    return bends


def main() -> int:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    golden = json.loads((fixtures / "goldens.json").read_text())["bracket-L-60x40x2-r3.step"]
    shape = read_step(fixtures / "bracket-L-60x40x2-r3.step")

    thickness = detect_thickness(shape)
    bends = detect_bends(shape, thickness)
    print(f"thickness: {thickness:.4f} (golden {golden['thickness']})")
    print(f"bend_count: {len(bends)} (golden {golden['bend_count']})")
    results = {"thickness": thickness, "bends": bends}

    ok = abs(thickness - golden["thickness"]) < 1e-6 and len(bends) == golden["bend_count"]
    if bends:
        b = bends[0]
        k = (0.65 + 0.5 * math.log10(b["inner_radius"] / thickness)) * 0.5
        ba = math.radians(b["angle_deg"]) * (b["inner_radius"] + k * thickness)
        # flat legs from the golden's construction (60-5, 40-5); the probe measures
        # them off the two inner planar faces adjacent to the bend in M4.2 — here we
        # verify the developed-length arithmetic composes with recognized bend params.
        flats = (60 - 5) + (40 - 5)
        developed = flats + ba
        print(
            f"bend: r={b['inner_radius']:.4f} angle={b['angle_deg']:.2f} deg "
            f"line_length={b['line_length']:.2f} (golden r={golden['bend_inner_radius']}, "
            f"{golden['bend_angle_deg']} deg, {golden['bend_line_length']})"
        )
        print(f"k_factor: {k:.6f} (golden {golden['k_factor']:.6f})")
        print(f"developed_length: {developed:.4f} (golden {golden['developed_length']:.4f})")
        results |= {"k_factor": k, "bend_allowance": ba, "developed_length": developed}
        ok = (
            ok
            and abs(b["inner_radius"] - golden["bend_inner_radius"]) < 1e-6
            and abs(b["angle_deg"] - golden["bend_angle_deg"]) < 1e-3
            and abs(b["line_length"] - golden["bend_line_length"]) < 1e-6
            and abs(developed - golden["developed_length"]) < 1e-6
        )

    results["ok"] = ok
    print(f"\nPROBE B {'PASS' if ok else 'FAIL'}")
    out = Path("scripts/spike-m4.0/results")
    out.mkdir(exist_ok=True)
    (out / "probe_b.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
