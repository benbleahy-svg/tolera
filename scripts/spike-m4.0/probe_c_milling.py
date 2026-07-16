# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 probe (c): milling — hole recognition (through/blind, diameter, depth),
pocket reach, machine-direction/setup heuristic inputs, removal volume
(build-plan M4.0 (c)). Runtime estimation itself has NO OCCT support — that is
the expected honest-ceiling finding, recorded in the capability map.

Run: uv run scripts/spike-m4.0/probe_c_milling.py [fixtures_dir]
"""

import json
import math
import sys
from pathlib import Path

from common import aabb_dims, face_area, faces, read_step, volume_area
from OCP.BRepAdaptor import BRepAdaptor_Surface

PLANE, CYLINDER = 0, 1


def main() -> int:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    golden = json.loads((fixtures / "goldens.json").read_text())["block-milled-80x50x20.step"]
    shape = read_step(fixtures / "block-milled-80x50x20.step")
    bbox = aabb_dims(shape)
    z_top = 20.0

    holes, plane_normals, pocket_floors = [], [], []
    for f in faces(shape):
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() == CYLINDER:
            cyl = ad.Cylinder()
            v0, v1 = ad.FirstVParameter(), ad.LastVParameter()
            u_extent = abs(ad.LastUParameter() - ad.FirstUParameter())
            if u_extent < 2 * math.pi - 1e-6:
                continue  # partial cylinder (fillet etc.), not a hole bore
            length = abs(v1 - v0)
            z0 = cyl.Axis().Location().Z()
            span = sorted(
                [z0 + v0 * cyl.Axis().Direction().Z(), z0 + v1 * cyl.Axis().Direction().Z()]
            )
            through = span[0] <= 1e-6 and span[1] >= z_top - 1e-6
            holes.append(
                {
                    "diameter": 2 * cyl.Radius(),
                    "length": length,
                    "axis": "Z" if abs(cyl.Axis().Direction().Z()) > 0.999 else "other",
                    "through": through,
                }
            )
        elif ad.GetType() == PLANE:
            n = ad.Plane().Axis().Direction()
            plane_normals.append((round(n.X(), 6), round(n.Y(), 6), round(n.Z(), 6)))
            # pocket floor candidate: horizontal plane strictly between bottom and top
            z = ad.Plane().Location().Z()
            if abs(n.Z()) > 0.999 and 1e-6 < z < z_top - 1e-6:
                pocket_floors.append({"z": z, "depth": z_top - z, "area": face_area(f)})

    # a blind hole's flat bottom is also a horizontal plane — attribute it to its
    # bore (area == pi*r^2 of a blind hole) instead of counting it as a pocket floor
    blind_bottom_areas = [math.pi * (h["diameter"] / 2) ** 2 for h in holes if not h["through"]]
    pocket_floors = [
        p for p in pocket_floors if not any(abs(p["area"] - a) < 1e-3 for a in blind_bottom_areas)
    ]

    # crude machine-direction heuristic input: hole axes + pocket floor normals all +/-Z
    directions = {h["axis"] for h in holes} | ({"Z"} if pocket_floors else set())
    vol, _ = volume_area(shape)
    removal = bbox[0] * bbox[1] * bbox[2] - vol

    through = [h for h in holes if h["through"]]
    blind = [h for h in holes if not h["through"]]
    # blind bore face excludes the drill-point/floor: depth = bore length (flat-bottom here)
    d_thru = sorted({round(h["diameter"], 3) for h in through})
    d_blind = sorted({round(h["diameter"], 3) for h in blind})
    print(
        f"holes: {len(through)} through (d={d_thru}), {len(blind)} blind "
        f"(d={d_blind}, depth={[round(h['length'], 3) for h in blind]})"
    )
    print(f"pocket floors: {[{k: round(v, 3) for k, v in p.items()} for p in pocket_floors]}")
    print(f"machine directions (heuristic input): {sorted(directions)} -> setup_count >= 1")
    print(f"removal volume: {removal:.2f} mm^3 (stock bbox - part)")
    print("runtime estimation: NO OCCT SUPPORT — in-house heuristic + confidence (finding)")

    ok = (
        len(through) == golden["through_holes"]["count"]
        and abs(through[0]["diameter"] - golden["through_holes"]["diameter"]) < 1e-6
        and len(blind) == golden["blind_holes"]["count"]
        and abs(blind[0]["diameter"] - golden["blind_holes"]["diameter"]) < 1e-6
        and abs(blind[0]["length"] - golden["blind_holes"]["depth"]) < 1e-6
        and len(pocket_floors) == 1
        and abs(pocket_floors[0]["depth"] - golden["pocket"]["depth"]) < 1e-6
        and sorted(directions) == golden["machine_directions_expected"]
        and abs(removal - (80 * 50 * 20 - golden["volume"])) / (80 * 50 * 20 - golden["volume"])
        < 1e-6
    )
    print(f"\nPROBE C {'PASS' if ok else 'FAIL'}")
    out = Path("scripts/spike-m4.0/results")
    out.mkdir(exist_ok=True)
    (out / "probe_c.json").write_text(
        json.dumps(
            {
                "holes": holes,
                "pocket_floors": pocket_floors,
                "directions": sorted(directions),
                "removal_volume": removal,
                "runtime_estimation": "no OCCT support — in-house heuristic (honest ceiling)",
                "ok": ok,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
