# Interrogation Engine (GeometryService) — Sub-Spec

**Status:** Engine sub-spec for Tolera (Bid Factory). **Provenance:** the KB interrogation + process articles (`06-part-analysis-interrogation/`) + `interrogations-basics`. Implements Gap-Analysis rec #3 and closes Gap-Audit §3 (no `GeometryService` API contract). Engine = OCCT for v1 (`DECISIONS.md`), Spatial swap-in later.

**Companion docs:** DFM warnings → `DFM-WARNINGS.md`; the part attribute contract → `PartGeometry-Attribute-Catalog.md`; how output is consumed → `PRICING-ENGINE-SPEC.md`; entities → `DOMAIN-MODEL.md`.

> **Role:** the CAD analysis engine. One Part (single CAD body) in → a structured **AnalysisResult** out, consumed by four clients: **Kalk** (costing, via `analyze_*()`), the **3D viewer** (feature overlay), the **DFM/Review** layer (warnings), and the **Part Library** (geometry signature for historical match). Get the output schema right and everything else is CRUD around it.

---

## 1. Service interface

```
GeometryService.analyze(
  body: CadBody,            # single solid body (assemblies are decomposed first)
  family: ProcessFamily,    # SHEET_METAL | MILLING | LATHE | TUBE_LASER | WIRE_EDM | CAST_URETHANE | ADDITIVE
  material: MaterialRef?,   # drives custom-interrogation selection
  inputs: InterrogationInputs?   # the per-family "task inputs" / thresholds (see DFM-WARNINGS.md)
) -> AnalysisResult
```
Supporting methods (same engine):
- `decompose_bom(file) -> {parts[], nodes[]}` — unpack an assembly CAD into Parts + Nodes (DOMAIN-MODEL §1).
- `compute_signature(body) -> GeomHash` — geometry hash powering Part-Library historical match + purchased-component memory (named in spec, **design here**).
- `render_thumbnail(body|drawing) -> image` — 2D/3D server-side thumbnails.
- `vectorize_pdf(page) -> DXF` — flat-pattern PDF → DXF (feeds sheet-metal as primary file; E4-j).
- `extract_pmi(body) -> PMI[]` — **post-pilot** (Spatial-grade; E4-e stub).

**Two trigger paths** (KB `interrogations-basics`): (1) **viewer** — manual, does *not* feed costing; (2) **Kalk `analyze_*()`** — auto-runs when an operation's formula calls it, results **feed costing**. Cache per (body, family, resolved-inputs) so the viewer and costing share one run.

---

## 2. AnalysisResult schema (the contract)

```
AnalysisResult {
  family: ProcessFamily
  dimensions: { ...PartGeometry attrs... }   # size_x/y/z, max/med/min_dim, area, volume, weight … (PartGeometry-Attribute-Catalog.md)
  family_scalars: { ... }                     # per-family table below
  features: Feature[]                         # m[].name + .properties{...} + geometry_refs (face/edge ids)
  feedback: Warning[]                         # DFM warnings (DFM-WARNINGS.md): {type, count, threshold_used, geometry_refs, can_disable}
  confidence?: 'High'|'Medium'|'Low'          # where the engine estimates runtime (milling)
}
```
- `features` and `feedback` are the same P3LList objects Kalk reads as `result.features` / `result.feedback`; each `Feature` exposes `.name` and `.properties.*` (e.g. `length, radius, volume, area, depth, side_length, side_width`).
- `Warning` carries the threshold that fired so the UI can show "why" and the value is auditable.

### Per-family `family_scalars` (verbatim from the process articles — these ARE the Kalk inputs)

**Sheet Metal** (`analyze_sheet_metal`): `bend_count`, `thickness`, `size_x`, `size_y` (unfolded), `total_cut_length`, `total_air_move_length`, `pierce_count` (internal features only), `punch_single_hit_cut_length`, `punch_multi_hit_cut_length`, `punch_single_hit_setups`, `punch_single_hit_count`, `counter_sink_setups`/`counter_sink_count`, `counter_bore_setups`/`counter_bore_count`, `simple_drilled_hole_setups`/`simple_drilled_hole_count`, `total_hole_setups`, `total_hole_count`, `features`, `feedback`.

**Milling** (`analyze_mill3`): `setups[]` (each: `setup_time` hrs [default 1], `runtime` hrs, `confidence` High/Med/Low, `features`, `feedback`), `setup_count`, `features`, `feedback`. Global `INDEX` for per-setup operations (0-based). **Engine estimates runtime + confidence** — load-bearing for the honest ceiling (low confidence → manual override).

**Lathe** (`analyze_lathe`): `setup_count`, `stock_radius`, `stock_length` (recommended cylindrical stock), `features`, `feedback`. Radial vs axial cut distinction; live-tooling callouts.

**Tube Laser** (`analyze_tube_laser`): `stock_type` (`round|rectangular|rectangular_radiused|angle|u_channel|incompatible`), `thickness`, `length`, `width`, `height`, `diameter`, `internal_radius`, `outside_corner_radius`, `leg_edge_radius`, `is_outside_corner_round`, `is_leg_edge_round`, `leg_angle`, `total_cut_length`, `pierce_count`, `features`, `feedback`.

**Wire EDM / Cast Urethane / Additive** — `analyze_wire_edm()` / `analyze_casting()` / `analyze_additive()`; schemas thinner in the KB — define when those families enter scope (post-pilot).

---

## 3. Feature catalogs to detect (CAD-engine requirements)

The recognizer must classify these features per family (warnings keyed off them in `DFM-WARNINGS.md`):

- **Sheet Metal:** bends, curls, hems, offsets; cut-out contours; single-hit punch shapes (`circular_punch`, `obround_punch`, `rectangular_punch`, `square_punch`, `slot_punch`) + multi-hit; countersinks, counterbores, simple drilled holes; bend reliefs. Requires **unfold** (k-factor `k=(0.65+0.5·log10(r/t))·0.5`) → unfolded size + thickness.
- **Milling (3-axis):** setups + face allocation (profiled vs surfaced via `depth_profiling_threshold`/`depth_surfacing_threshold`); holes (blind, through, tipped, flat-bottom, slanted, partial, through-cavity), circular pockets (hole > `maximum_hole_diameter`), transitions (concave/convex fillets, chamfers), tapered walls, tight (square) corners, uncut faces; runtime + confidence estimate.
- **Lathe:** radial/axial cuts, setups, recommended stock; bored-hole relief; slender part; small internal radii; steep profiles; live-tooling: tight corners, off-axis holes, asymmetric cavities.
- **Tube Laser:** the 5 cross-sections; cut-out features; countersinks (laser vs secondary); angled cuts (`max_angled_cut_threshold`, else `machining_required`).

---

## 4. Custom interrogations (authorable thresholds)

`InterrogationInputs` = the per-family "task inputs" (all defaults in `DFM-WARNINGS.md`): strategy knobs (e.g. sheet-metal `is_laser/is_punch/is_punch_laser`, milling `depth_*_threshold`, lathe tool limits, tube `should_countersinks_be_lasered`) + every `should_detect_*` toggle + threshold. A **CustomInterrogation** binds an `InterrogationInputs` set to material **class / family / material** and/or **operation defs**; the engine resolves the **most-specific** match for a part's material (e.g. Carbon-Steel-12L14 beats Carbon-Steel family). ⚠️ Avoid linking same-type interrogations to multiple ops in one process (dispatches duplicates).

---

## 5. Pipeline

1. **Ingest** → file-type + size gate (Mill/Lathe/WireEDM/Cast ≤ **20 MB**; SheetMetal/TubeLaser ≤ **50 MB**; Additive none). **Single body only** — assemblies are decomposed (`decompose_bom`) into Parts/Nodes; each body interrogated separately.
2. **Resolve inputs** (most-specific CustomInterrogation by material/op).
3. **Recognize** (family-specific): unfold / setup-detection / feature recognition → `dimensions + family_scalars + features + feedback (+confidence)`.
4. **Persist + cache** the AnalysisResult keyed by (geom-hash, family, resolved-inputs); compute `GeomHash`.
5. **Serve**: Kalk `analyze_*()` reads it (sync wait or job); viewer overlays features/feedback; Part Library indexes the signature.
6. **Async/job model:** interrogations run as jobs; Kalk costing waits on the relevant job. (Spec a queue; surface "interrogating…" state.)

---

## 6. v1 scope (OCCT) & honest ceilings

- **v1 families = Core 4:** Sheet Metal, Milling, Lathe, Tube Laser (matches spec's "Core 4"). Wire EDM / Cast / Additive: **post-pilot**.
- **OCCT reduced set:** per family, mark which `family_scalars`/features OCCT can produce vs Spatial-only; Kalk authors must know which `.properties.*` are guaranteed (cross-ref `PartGeometry-Attribute-Catalog.md` v1 column).
- **Ceilings to state in acceptance:** 5-axis runtime is **not** auto-costed (manual override is the designed path); complex parts ≈ partial feature recognition — surface **confidence** and let manual overrides drive cost; **GD&T/PMI flagged, not costed** (E4-e post-pilot); nesting is **estimation-grade**. Don't over-claim.
- **Native SLDPRT / advanced recognition:** Spatial swap-in; `GeometryService` interface must be unchanged on swap (`DECISIONS.md`).

## 7. Non-geometric & manual fallback

PDF/print or manual line items have no body → no `analyze_*()`. Kalk must degrade gracefully: read manually-entered `part.*` (dims, material) + **custom part attributes** (`set/get_custom_attribute`) so the same formula prices geometric and non-geometric files (KB pattern). `vectorize_pdf` upgrades a flat-pattern PDF to a DXF primary so sheet-metal interrogation works (E4-j).

## 8. Acceptance criteria

- Per-fixture **golden AnalysisResult**: e.g. *this STEP → 3 bends, thickness 0.029 in, unfolded size X×Y, pierce_count N, total_cut_length L*; *this mill body → K setups, runtime R, confidence C*. Bind to the Fechner fixtures (`DECISIONS.md` fixtures item).
- File gates enforced; assemblies rejected for direct interrogation (decomposed first).
- Most-specific CustomInterrogation selected for a given material.
- DACH: metric-first storage; values convertible for Kalk `units_in()`.

**Sources:** `interrogations-basics`, `sheet-metal-process`, `milling-process`, `lathe-process`, `tube-laser-process`, `sheet-metal-/milling-/lathe-/tube-laser-interrogation`, `custom-interrogations`, `similar-parts-search-beta` (all in `paperless-parts-kb-reference/`).
