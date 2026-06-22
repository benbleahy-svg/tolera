# PartGeometry — Attribute Catalog (the geometry ↔ pricing contract)

**Status:** Spec appendix for Tolera (Bid Factory). **Provenance:** the `part` object table in Paperless Parts' `operation-p3l-cheat-sheet` (+ `pricing-items-p3l-cheat-sheet` confirmation). This is the **single most load-bearing contract in the product**: it is simultaneously the **output schema of `GeometryService`** and the **input surface of Kalk's `part` object**. Pin it and every consumer (3D viewer, DFM, costing formulas, nesting, part-library hashing) gets a stable contract. (Feeds Gap-Audit §3; expands spec `Data Model → PartGeometry`.)

**Units:** metric by default; imperial values apply after `units_in()` in a Kalk formula. Implement storage in metric; convert at read time.

**v1 column:** can OCCT (per `DECISIONS.md`) populate this for v1, or is it Spatial-only / manual / assembly-only? (`✓` yes · `~` partial/family-specific · `man` manual or non-geometric fallback · `asm` assembly-derived). Validate against real Fechner fixtures.

---

## 1. Core geometry & dimensions

| Attribute | Description | Metric | Imperial | v1 |
|---|---|---|---|:--:|
| `part.size_x` | X dim — 3D: overwritten X › max dim of optimal bbox › X of axis-aligned bbox; 2D: file/overwritten X; non-geo: manual | mm | in | ✓ |
| `part.size_y` | Y dim — 3D: overwritten Y › median dim of optimal bbox › Y of AABB; 2D: file/overwritten; non-geo: manual | mm | in | ✓ |
| `part.size_z` | Z dim — 3D: overwritten Z › min dim of optimal bbox › Z of AABB; 2D: thickness/overwritten; non-geo: manual | mm | in | ✓ |
| `part.max_dim` | Max dimension of optimal bounding box | mm | in | ✓ |
| `part.med_dim` | Median dimension of optimal bounding box | mm | in | ✓ |
| `part.min_dim` | Min dimension of optimal bounding box | mm | in | ✓ |
| `part.area` | Surface area | mm² | in² | ✓ |
| `part.volume` | Volume | mm³ | in³ | ✓ |

> Note `size_*` are **resolved** values (overwrite › optimal-bbox › AABB › manual). Store both the raw extraction and any override so the precedence is reproducible.

## 2. Material

| Attribute | Description | Metric | Imperial | v1 |
|---|---|---|---|:--:|
| `part.material` | Material name, respecting custom naming (e.g. *Aluminum 6061-T6*) | — | — | man |
| `part.global_material` | Material name in the global materials DB | — | — | man |
| `part.material_family` | Family (e.g. *Aluminum*, *Stainless Steel*) | — | — | man |
| `part.material_class` | Class (e.g. *Metal*, *Polymer*) | — | — | man |
| `part.weight` | Part weight | g | lb | ✓ |
| `part.density` | Material density | g/cm³ | lb/in³ | man |
| `part.mat_cost_per_volume` | Material cost per unit volume | $/mm³ | $/in³ | man |
| `part.mat_added_lead_time` | Added lead time for material selection (process config) | days | days | man |

> **DACH:** map `material`/`material_family` to DIN/EN designations (1.4301 etc.); seed a DIN↔global-material crosswalk.

## 3. Quantities

| Attribute | Description | v1 |
|---|---|:--:|
| `part.qty` | Make quantity (for the current break) | ✓ |
| `part.bom_qty` | Quantity to deliver to customer for this break | ✓ |
| `part.innate_quantity` | Deliver quantity for a single top-level part (break = 1) | ✓ |
| `part.quantities` | List of quantities on the part | ✓ |
| `part.bom_quantities` | List of BOM quantities (index-aligned to `quantities`) | ✓ |
| `part.make_quantities` | List of make quantities (index-aligned) | ✓ |

Iterators: `get_quantities()`, `get_bom_quantities()`, `get_make_quantities()`.

## 4. Identity & assembly position

| Attribute | Description | v1 |
|---|---|:--:|
| `part.part_number` | Part number | man |
| `part.revision` | Revision | man |
| `part.is_root_component` | True if root of the assembly tree | asm |
| `part.is_assembly` | True if a subassembly | asm |
| `part.obtain_method` | `PURCHASED` or `MANUFACTURED` | asm |
| `part.count_manufactured_children` | Count of MANUFACTURED components in child BOM (incl. subassemblies) | asm |
| `part.count_purchased_children` | Count of PURCHASED components in child BOM | asm |
| `part.purchased_component` | Linked purchased component or `None` (see §5) | asm |

`get_children(obtain_method=None, is_assembly=None, recursive=False)` → `child` objects: `.obtain_method`, `.is_assembly`, `.part_number`, `.revision`, `.count`, `.purchased_component`.

## 5. `part.purchased_component` (or `None`)

| Attribute | Description | Units |
|---|---|---|
| `.oem_part_number` | OEM part number (usual display name) | — |
| `.internal_part_number` | Internal part number (optional) | — |
| `.piece_price` | Piece price (4 dp) | $ |
| `.description` | Description | — |
| *custom columns* | Any column configured on the Processes → Purchased Components tab (e.g. `.insertion_time`, `.bag_price`) | per config |

## 6. Analyzer-derived geometry (NOT on the static `part` object)

These come from `analyze_*()` results (`.features` + family attributes), i.e. the deeper `GeometryService` output. Per-family feature trees & DFM warnings → `DFM-WARNINGS.md`.

| Source | Example attributes |
|---|---|
| `analyze_sheet_metal()` | `.thickness`, `.pierce_count`, `.total_cut_length`, `.features[*]` (`bend`, `curl`, `open_hem`, `tear_drop`, `offset`, `circular_punch`, `obround_punch`, `rectangular_punch`, `slot_punch`, `square_punch` … with `.properties.length/width/radius/side_length/side_width`) |
| `analyze_lathe()` | `.stock_radius`, `.stock_length`, turning features |
| `analyze_mill3()` | `.runtime`, milled features (holes, pockets …) with `.properties.volume/area/depth` |
| `analyze_tube_laser()` / `analyze_wire_edm()` / `analyze_casting()` / `analyze_additive()` | family-specific |

## 7. Related objects (for completeness)

- **`op_def`**: `.name`, `.erp_code`
- **`line_item`**: `.is_export_controlled` *(DACH: reframe per Gap-Analysis §B)*
- **`quote`** (empty-safe): `quote.account{.name,.erp_code,.UUID}`, `quote.contact{.email,.first_name,.last_name,.full_name,.uuid}`, `quote.estimator{…,.erp_code}`, `quote.salesperson{…,.erp_code}`, `quote.facility{.name,.uuid}`
- **Custom part attributes**: arbitrary top-level key/values via `set_custom_attribute(k,v)` / `get_custom_attribute(k,default)`; defaults configurable in settings.

---

## Implementation guidance

1. **Make this `PartGeometry` (+ linked `PurchasedComponent`).** Spec `Data Model → PartGeometry` should enumerate §1–§5 as fields; §6 belongs to per-family analysis result types behind `GeometryService`.
2. **Store raw + override + resolved** for `size_*` (and any overwrite-able dim) so precedence is reproducible and auditable.
3. **`v1` column = your geometry-engine acceptance checklist** — each `✓`/`~` is a thing the OCCT pipeline must output for a fixture; `man` fields need a manual-entry UI path (non-geometric/PDF files).
4. **One source of truth:** Kalk's `part` object, the 3D viewer's data overlay, DFM rules, and part-library hashing must all read these same names/units.
5. **Source:** `paperless-parts-kb-reference/articles/05-pricing-costing-p3l/operation-p3l-cheat-sheet.md` (§"The Part Object").
