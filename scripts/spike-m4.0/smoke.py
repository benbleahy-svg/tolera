# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 smoke probe: can OCP (pip OCCT 7.9 wheels) import, model, write and re-read STEP?

Throwaway spike scaffold (build-plan M4.0). Run: uv run scripts/spike-m4.0/smoke.py
"""

import sys

from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer


def main() -> int:
    box = BRepPrimAPI_MakeBox(20.0, 20.0, 20.0).Shape()
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(box, props)
    vol = props.Mass()
    print(f"modelled box volume: {vol:.1f} mm^3 (expect 8000.0)")

    out = "/tmp/m40-smoke.step"
    writer = STEPControl_Writer()
    writer.Transfer(box, STEPControl_AsIs)
    status = writer.Write(out)
    assert status == IFSelect_RetDone, f"STEP write failed: {status}"

    reader = STEPControl_Reader()
    assert reader.ReadFile(out) == IFSelect_RetDone, "STEP read failed"
    reader.TransferRoots()
    shape = reader.OneShape()
    props2 = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props2)
    print(f"round-tripped volume:  {props2.Mass():.1f} mm^3")

    ok = abs(props2.Mass() - 8000.0) < 1e-6
    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
