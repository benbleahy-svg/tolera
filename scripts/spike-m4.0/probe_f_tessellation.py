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


def face_mesh_seq(path, deflection: float = 0.1) -> tuple[list[tuple[int, int]], int]:
    """Fresh parse + mesh; per-face (vertices, triangles) in topology order,
    plus the count of faces that produced NO triangulation."""
    shape = read_step(path)
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
    seq: list[tuple[int, int]] = []
    unmeshed = 0
    for f in faces(shape):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            unmeshed += 1
            continue
        seq.append((tri.NbNodes(), tri.NbTriangles()))
    return seq, unmeshed


def main() -> int:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    results = {}
    ok = True
    for name in (
        "bracket-L-60x40x2-r3.step",
        "shaft-stepped-d30-d20-d12.step",
        "asm-plate-2pins.step",
    ):
        # two independent parse+mesh runs: every face must mesh, and the per-face
        # (vertex, triangle) sequence must be identical across fresh loads — the
        # determinism the viewer feature->face overlay relies on
        seq1, unmeshed1 = face_mesh_seq(fixtures / name)
        seq2, unmeshed2 = face_mesh_seq(fixtures / name)
        results[name] = {
            "meshed_faces": len(seq1),
            "vertices": sum(v for v, _ in seq1),
            "triangles": sum(t for _, t in seq1),
            "unmeshed_faces": unmeshed1,
            "deterministic_across_loads": seq1 == seq2,
        }
        this_ok = bool(seq1) and unmeshed1 == 0 and unmeshed2 == 0 and seq1 == seq2
        ok = ok and this_ok
        print(
            f"{name}: {len(seq1)} faces meshed, {sum(t for _, t in seq1)} triangles, "
            f"deterministic={seq1 == seq2} -> {'OK' if this_ok else 'FAIL'}"
        )

    print(
        f"\nPROBE F {'PASS' if ok else 'FAIL'} — full per-face triangulation, identical "
        "face-order mesh sequence across fresh loads (viewer overlay + thumbnails feasible)"
    )
    out = Path("scripts/spike-m4.0/results")
    out.mkdir(exist_ok=True)
    (out / "probe_f.json").write_text(json.dumps(results | {"ok": ok}, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
