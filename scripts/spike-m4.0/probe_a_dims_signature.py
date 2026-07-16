# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 probe (a): dims/volume/area/OBB vs analytic goldens + geometry-signature
stability on the topology-variant pair (build-plan M4.0 scope (a)).

Run: uv run scripts/spike-m4.0/probe_a_dims_signature.py [fixtures_dir]
"""

import json
import math
import sys
import tempfile
from pathlib import Path

from common import (
    aabb_dims,
    canonicalize,
    face_histogram,
    fingerprint,
    obb_dims,
    read_step,
    volume_area,
)
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

STEEL_DENSITY_G_CM3 = 7.9


def rel(a: float, b: float) -> float:
    return abs(a - b) / b if b else abs(a - b)


def roundtrip(shape) -> object:
    """Write shape to a fresh STEP file and read it back (a 'second CAD export')."""
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    writer.Write(path)
    return read_step(path)


def rotated(shape) -> object:
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(7, -3, 11), gp_Dir(1, 2, 3)), math.radians(33.7))
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def main() -> int:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    goldens = json.loads((fixtures / "goldens.json").read_text())
    results: dict = {"dims": {}, "signature": {}}
    failures = 0

    # --- dims/volume/area vs analytic goldens -------------------------------
    print("== dims/volume/area vs analytic goldens (tolerance 0.1%) ==")
    for name, golden in goldens.items():
        if "volume" not in golden:
            continue
        shape = read_step(fixtures / name)
        vol, area = volume_area(shape)
        row = {
            "volume_rel_err": rel(vol, golden["volume"]),
            "aabb": aabb_dims(shape),
            "obb_sorted": obb_dims(shape),
            "area": area,
        }
        ok = row["volume_rel_err"] < 1e-3
        if "bbox" in golden:
            pairs = zip(sorted(row["aabb"]), sorted(golden["bbox"]), strict=True)
            bbox_ok = all(rel(m, g) < 1e-3 for m, g in pairs)
            row["bbox_ok"] = bbox_ok
            ok = ok and bbox_ok
        row["ok"] = ok
        failures += 0 if ok else 1
        results["dims"][name] = row
        print(
            f"  {name}: vol rel {row['volume_rel_err']:.2e} "
            f"aabb {[round(d, 3) for d in row['aabb']]} "
            f"obb {[round(d, 3) for d in row['obb_sorted']]} -> {'OK' if ok else 'FAIL'}"
        )

    # weight = volume x density demonstration (PartGeometry: weight in g, volume mm^3)
    vol_cube, _ = volume_area(read_step(fixtures / "cube-20mm.step"))
    weight_g = vol_cube / 1000.0 * STEEL_DENSITY_G_CM3
    results["dims"]["weight_demo"] = {"cube_volume_mm3": vol_cube, "weight_g_at_7.9": weight_g}
    print(f"  weight demo: 20mm cube x 7.9 g/cm3 = {weight_g:.2f} g (expect 63.20)")

    # --- signature stability -------------------------------------------------
    print("\n== geometry signature (quantized fingerprint -> SHA-256) ==")
    cube = read_step(fixtures / "cube-20mm.step")
    split = read_step(fixtures / "cube-20mm-splitface.step")

    fc_raw = sum(face_histogram(split)[0].values())
    fc_unified = sum(face_histogram(canonicalize(split))[0].values())
    print(f"  split-face cube: {fc_raw} faces raw -> {fc_unified} after UnifySameDomain")

    cases = {
        "reexport": (cube, roundtrip(cube)),  # same solid, two CAD exports
        "rotated": (cube, rotated(cube)),  # same solid, moved in space
        "split_vs_single": (cube, split),  # split face vs single face
        "rotated_split": (cube, rotated(split)),  # both perturbations at once
    }
    for sig_digits in (4, 6, 8):
        for unify in (False, True):
            key = f"sig{sig_digits}_unify={unify}"
            res = {}
            for case, (s1, s2) in cases.items():
                h1, _ = fingerprint(s1, sig_digits, unify)
                h2, _ = fingerprint(s2, sig_digits, unify)
                res[case] = h1 == h2
            # different geometry must NOT collide
            h_cube, _ = fingerprint(cube, sig_digits, unify)
            h_other, _ = fingerprint(
                read_step(fixtures / "plate-hole-20x20x10-d8.step"), sig_digits, unify
            )
            res["distinct_parts_differ"] = h_cube != h_other
            results["signature"][key] = res
            print(f"  {key}: " + " ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in res.items()))

    verdict = results["signature"].get("sig6_unify=True", {})
    stable = all(verdict.values())
    results["verdict"] = {
        "topology_tolerant_hash": stable,
        "recipe": "UnifySameDomain + OBB-sorted dims + 6-sig-digit quantization",
    }
    print(f"\nVERDICT: topology-tolerant stable hash = {stable}")

    out = Path("scripts/spike-m4.0/results")
    out.mkdir(exist_ok=True)
    (out / "probe_a.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    return 0 if (failures == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
