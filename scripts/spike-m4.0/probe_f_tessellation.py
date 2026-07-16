# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 probe (f): server-side tessellation via BRepMesh — feeds the viewer
mesh-source decision (DECISIONS.md M2.6 entry, recommended default (b): the
viewer renders what GeometryService tessellates) and render_thumbnail.

Run: uv run scripts/spike-m4.0/probe_f_tessellation.py [fixtures_dir]
"""

import json
import sys
from pathlib import Path

from common import faces, read_step
from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopLoc import TopLoc_Location


def tessellate(shape, deflection: float = 0.1) -> tuple[int, int, int]:
    """Mesh the shape; return (face_count, total_vertices, total_triangles)."""
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
    nf = nv = nt = 0
    for f in faces(shape):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        nf += 1
        nv += tri.NbNodes()
        nt += tri.NbTriangles()
    return nf, nv, nt


def main() -> int:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    results = {}
    ok = True
    for name in (
        "bracket-L-60x40x2-r3.step",
        "shaft-stepped-d30-d20-d12.step",
        "asm-plate-2pins.step",
    ):
        nf, nv, nt = tessellate(read_step(fixtures / name))
        results[name] = {"meshed_faces": nf, "vertices": nv, "triangles": nt}
        this_ok = nt > 0 and nf > 0
        ok = ok and this_ok
        print(
            f"{name}: {nf} faces meshed, {nv} vertices, {nt} triangles "
            f"-> {'OK' if this_ok else 'FAIL'}"
        )

    print(
        f"\nPROBE F {'PASS' if ok else 'FAIL'} — per-face triangulation with stable "
        "face indexing available server-side (viewer overlay + thumbnails feasible)"
    )
    out = Path("scripts/spike-m4.0/results")
    out.mkdir(exist_ok=True)
    (out / "probe_f.json").write_text(json.dumps(results | {"ok": ok}, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
