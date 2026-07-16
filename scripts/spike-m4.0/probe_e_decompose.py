# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["cadquery-ocp>=7.9,<7.10"]
# ///
"""M4.0 probe (e): decompose_bom on an assembly STEP via XCAF — unique products
vs occurrences (Parts vs Nodes, DOMAIN-MODEL §1), occurrence names, and AP214
material/density reach (feeds M4.9b node.cad_metadata) (build-plan M4.0 (e)).

Run: uv run scripts/spike-m4.0/probe_e_decompose.py [fixtures_dir]
"""

import json
import sys
from pathlib import Path

from common import volume_area
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_Material


def label_name(lbl) -> str:
    attr = TDataStd_Name()
    if lbl.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return TCollection_AsciiString(attr.Get()).ToCString()
    return "<unnamed>"


def main() -> int:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/cad")
    path = fixtures / "asm-plate-2pins.step"
    golden = json.loads((fixtures / "goldens.json").read_text())["asm-plate-2pins.step"]

    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetMatMode(True)
    assert reader.ReadFile(str(path)) == IFSelect_RetDone, "read failed"
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    assert reader.Transfer(doc), "XCAF transfer failed"

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    mat_tool = XCAFDoc_DocumentTool.MaterialTool_s(doc.Main())

    # --- product structure: assemblies -> components (occurrences) -> products ---
    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)
    occurrences: list[dict] = []
    products: dict[str, dict] = {}

    def walk(lbl, depth=0):
        if shape_tool.IsAssembly_s(lbl):
            comps = TDF_LabelSequence()
            shape_tool.GetComponents_s(lbl, comps)
            for i in range(1, comps.Length() + 1):
                comp = comps.Value(i)
                referred = TDF_Label()
                shape_tool.GetReferredShape_s(comp, referred)
                # key products by XCAF label entry (unique), never by display name —
                # two distinct products may share a name
                entry = TCollection_AsciiString()
                TDF_Tool.Entry_s(referred, entry)
                pkey = entry.ToCString()
                pname = label_name(referred)
                if pkey not in products:
                    shape = shape_tool.GetShape_s(referred)
                    vol, _ = volume_area(shape)
                    products[pkey] = {"name": pname, "volume": vol}
                loc = shape_tool.GetLocation_s(comp).Transformation()
                occurrences.append(
                    {
                        "occurrence": label_name(comp),
                        "product": pname,
                        "parent": label_name(lbl),
                        "depth": depth,
                        "translation": [
                            round(loc.TranslationPart().Coord(i), 3) for i in (1, 2, 3)
                        ],
                    }
                )
                walk(referred, depth + 1)

    for i in range(1, free.Length() + 1):
        walk(free.Value(i))

    # --- material/density reach (AP214 DENSITY props) -----------------------
    mat_labels = TDF_LabelSequence()
    mat_tool.GetMaterialLabels(mat_labels)
    materials = []
    for i in range(1, mat_labels.Length() + 1):
        attr = XCAFDoc_Material()
        if mat_labels.Value(i).FindAttribute(XCAFDoc_Material.GetID_s(), attr):
            materials.append(
                {
                    "name": attr.GetName().ToCString(),
                    "density": attr.GetDensity(),
                    "density_unit": attr.GetDensName().ToCString(),
                }
            )

    by_name = {v["name"]: v for v in products.values()}
    print(
        f"products ({len(products)}): "
        f"{ {v['name']: round(v['volume'], 2) for v in products.values()} }"
    )
    print(f"occurrences ({len(occurrences)}):")
    for o in occurrences:
        print(f"  {o['occurrence']} -> {o['product']} @ {o['translation']}")
    print(f"materials via XCAF: {materials}")

    occ_by_product: dict[str, int] = {}
    for o in occurrences:
        occ_by_product[o["product"]] = occ_by_product.get(o["product"], 0) + 1
    ok = (
        len(products) == golden["products"]
        and occ_by_product == golden["occurrences"]
        and len(materials) == 2
        and any(m["name"] == "1.4301" and abs(m["density"] - 7.9) < 1e-9 for m in materials)
        and abs(by_name["PLATE-60x40x5"]["volume"] - golden["plate_volume"]) < 1e-3
        and abs(by_name["PIN-D6x20"]["volume"] - golden["pin_volume"]) < 1e-3
    )
    print(f"\nPROBE E {'PASS' if ok else 'FAIL'}")
    out = Path("scripts/spike-m4.0/results")
    out.mkdir(exist_ok=True)
    (out / "probe_e.json").write_text(
        json.dumps(
            {
                "products": products,
                "occurrences": occurrences,
                "materials": materials,
                "material_link_note": (
                    "global material table + densities readable (above); resolving WHICH "
                    "body carries which material via TDataStd_TreeNode/MaterialRefGUID "
                    "segfaulted OCP 7.9.3 twice — per-body link deferred to M4.9b "
                    "(alternate XCAF API or STEP-entity parse)"
                ),
                "ok": ok,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
