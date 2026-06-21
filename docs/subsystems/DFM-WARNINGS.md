# DFM Warnings & Interrogation Catalogue (v1 seed)

**Status:** Spec appendix for Tolera (Bid Factory). **Provenance:** Paperless Parts interrogation articles (`paperless-parts-kb-reference/articles/06-part-analysis-interrogation/` + `New-Sheet-Metal-Interrogation-Warnings`). Closes the catalogue half of Gap-Audit §3 ("DFM warnings are names, not formulas") and seeds `{interrogations-config}` / the Geometry Recognition & DFM section.

> **Threshold caveat:** the default values below are Paperless Parts' published defaults. Treat them as **seed defaults**, every one **shop-calibratable** (your spec already makes thresholds authorable). Each warning has a `should_detect_*` toggle. **Units are inches** for milling/lathe/tube inputs unless noted; sheet-metal thresholds are mostly **multiples of material thickness (×t)**.
> **v1 caveat:** warnings depend on feature recognition. v1 OCCT will recognize a **reduced** feature set per family vs. the source product — treat this list as the *target*, and gate each warning on whether the underlying feature is detectable in v1 (see `GEOMETRY.md`).

---

## Model

- **Seven process interrogations:** Sheet Metal · Tube Laser · CNC Milling · CNC Lathe/Turning · Wire EDM · Cast Urethane · Additive. (Sheet Metal/Milling/Lathe/Tube Laser are documented in depth; Wire EDM/Cast Urethane/Additive are named with `analyze_*()` hooks but have thinner public DFM docs — see their `*-process` articles.)
- **Single-body only:** only non-assembly parts are interrogated (assemblies reference multiple bodies). File-size limits: Milling/Lathe/Wire EDM/Cast Urethane ≤ **20 MB**; Sheet Metal/Tube Laser ≤ **50 MB**; Additive **none**.
- **Two trigger paths:** (1) manually in the Part Viewer "Geometric Features" tab; (2) automatically when a Kalk operation calls `analyze_*()` (e.g. a laser op with `analyze_sheet_metal()`). Only path (2) feeds costing.
- **Custom interrogations** = a named bundle of "task inputs" (the thresholds below) linked to material class / family / material and/or operation defs. The system applies the **most-applicable** interrogation to a part by material specificity. ⚠️ Linking different custom interrogations of the same task type to multiple ops in one process dispatches duplicate interrogations (slower) — consolidate.
- Each warning is surfaced in the viewer **and** exposed to Kalk (some carry a P3L feature name, e.g. tube-laser additional-ops = `machining_required`).

---

## Sheet Metal (`analyze_sheet_metal()`)

**Marking machine flavor** (drives which features are called out): `is_laser` (default **True**), `is_punch` (False), `is_punch_laser` (False). Laser → cut-out features; Punch → single-hit (circular, obround, rectangular, square, slot) + multi-hit; Punch-laser → both.

**Strategy inputs**

| Input | Meaning | Default |
|---|---|---|
| `smallest_cutout_size` | Smallest markable feature (×t). Smaller simple holes become manual drilled holes | 1.0 (laser & punch) |
| `single_hit_max_size_threshold` | Largest simple contour cut in one punch hit | 6 in |
| `max_offset_height` | Max offset between opposed bends to count as an offset (else 2 bends) | 0.25 in |
| `should_detect_offsets` | — | True |
| `press_length` | Max press working length (bends longer are flagged / not combined) | 240 in (article also cites 20 ft) |
| K-factor | `k = (0.65 + 0.5*log10(radius/thickness)) * 0.5` (BASE_K=0.65; not configurable) | — |

**Warnings**

| Warning | Detects | Threshold input(s) | Default | Toggle default |
|---|---|---|---|:--:|
| Small Cut | Marked feature < min feature size; also splits drilled-by-hand holes | `smallest_cutout_size` (×t) | 1.0 | `should_detect_small_cuts` True |
| (Drilled-hole feedback) | Count countersinks/counterbores/simple drilled holes as issues | `should_count_drilled_holes_as_feedback` | — | False |
| Close Cutouts | Two cut features too close | `close_cutouts_threshold` (×t) | 1.0 laser / 2.0 punch | True |
| Cutouts Close To Edge | Cut feature too near material edge | `cutout_edge_proximity` (×t) | 2.0 | True |
| Close Countersinks/Bores | Two c'sinks/bores too close (edge-edge) | `countersink_bore_proximity_threshold` (×t) | 8.0 | True |
| Countersink/Bore Close To Edge | C'sink/bore too near outer edge | `countersink_bore_edge_proximity_threshold` (×t) | 4.0 | True |
| Tight Corners | Corner discontinuities from connecting faces | `should_detect_tight_corners` | — | **False** |
| Cut Near Bend | Internal cut too close to a bend (deforms when forming) | `cut_near_bend_threshold` (×t + bend radius) | 3.0 | True |
| Tight Curl | Curl outer radius too small | `tight_curl_threshold` (×t) | 2.0 | True |
| Curl Near Bend | Curl too close to a bend | `curl_near_bend_threshold` (×t) | 5.0 | True |
| Tight Hem | Hem diameter too small | `tight_hem_threshold` (×t) | 1.0 | True |
| Short Hem Return | Hem return flange too short | `short_hem_threshold` (×t) | 4.0 | True |
| Hem Near Bend | Hem too close to a bend | `hem_near_bend_threshold` (×t + bend radius) | 5.0 | True |
| Large Bend Radius | Radius too large → springback | `max_bend_radius` (×t) | 150 | `should_detect_large_bend_radius` True |
| Small Bend Radius | Radius too small → cracking/orange-peel | `min_bend_radius` (×t) | 0.75 | `should_detect_small_bend_radius` True |
| Bend Relief Issues | No / thin / shallow bend relief | `thin_bend_relief_threshold` (×t) = 1.5; `shallow_bend_relief_threshold` (×t+radius) = 2.0 | — | `should_detect_bend_relief_issues` True |
| Short Flange / Short Bend | Flange/bend too short (press marks, tolerance) | `min_flange_length` (×t) = 4.0; `short_flange_threshold` (L:t) = 1.0 | — | `should_detect_short_bends` / `should_detect_short_flanges` True |
| Abnormal Bend Angle | Bends ≠ 90° (excl. hems/curls) | `should_detect_non_ninety_bends` | — | True |
| Different Bend Directions | Bends formed in different directions, same plane | `should_detect_different_bend_directions` | — | True |
| Split Bends | One bend formable as split sections | `should_detect_split_bends`; `can_split_die` | — | **False** / False |
| Close Bends | Parallel bends too close (U or Z); bends within ±15° of 90° | `close_bends_same_orientation_threshold` = 1.0; `close_bends_opposite_orientation_threshold` = 1.0 | — | `should_detect_close_bends` True |
| W-Bending May Be Required | Deep U where shortest-leg ÷ bend-separation > threshold | `w_bending_threshold` | 1.0 | `should_detect_w_bending` True |
| Additional Operations Required | Faces not hittable with standard/secondary tooling | — | — | **always on** |
| Exceeds Press Length | Bend length > press | `press_length` | 240 in | — |
| Dimensions Exceed Limits | Folded/unfolded part too large | `max_length/width/height` = 144 in; `max_unfolded_length/width` = 144 in | — | `should_detect_size_restrictions` True |

## CNC Milling — 3-axis (`analyze_mill3()`)

**Strategy inputs**

| Input | Meaning | Default |
|---|---|---|
| `depth_profiling_threshold` | Max depth a profiled cut can be performed | 2.0 in |
| `depth_surfacing_threshold` | Max depth of a surfaced cut | 1.80 in |
| `minimum_area_for_setup` | Min face area to justify a new setup for profiling vs surfacing | 1.55 in² (1000 mm²) |
| `maximum_hole_diameter` | Above this, a hole is treated as a circular pocket (profiled, not drilled) | 2.0 in |

**Warnings**

| Warning | Detects | Threshold input(s) | Default | Toggle default |
|---|---|---|---|:--:|
| Work Envelope Size | Part exceeds machine envelope | `max_part_length/width/height` | 64 / 38 / 32 in | `should_detect_size_restrictions` True |
| Deep Hole | Cut-depth ÷ hole-dia too high | `deep_hole_ratio_threshold` | 8.0 | True |
| Deep Radial Cut / Deep Circular Pocket | Concave profiled face, depth÷tool-dia high | `deep_cut_radiused_ratio_threshold` = 3.0; `max_tool_diameter` = 0.5 in | — | `should_detect_deep_cut_radiused` / `…circular_pocket` True |
| Deep Planar Cut | Planar profiled face, depth÷tool-dia high | `deep_cut_planar_ratio_threshold` = 4.0; `max_tool_diameter` = 0.5 in | — | True |
| Small Internal Radius | Internal radius below min | `small_internal_radius_threshold` | 1/32 in (0.79 mm) | True |
| Small Hole Diameter | Hole below min dia | `small_hole_diameter` | 1/16 in (1.59 mm) | True |
| Blind Holes (Tipped / Flat-Bottom) | Harder chip clearing | `should_detect_tipped_hole`; `should_detect_flat_bottom_hole` | — | True / True |
| Slanted Hole | Entry/exit normal deviates from axis | `slanted_hole_angle_threshold` | 0.035 rad (2°) | True |
| Partial Hole | <360° tool contact | `should_detect_partial_hole` | — | True |
| Holes Through Cavity | Coaxial holes split by a cavity | `should_detect_hole_through_cavity` | — | True |
| Transitions | Concave fillet, convex fillet, chamfer | `should_detect_transitions` | — | True |
| Tapered Walls | Slanted plane needing surfacing | `should_detect_tapered_walls` | — | True |
| Tight Corners | Internal 90° corners / square pockets (no round tool) | — | — | (on) |
| Uncut Faces | Inaccessible to 3-axis tooling | — | — | **always on** |

> Material-specific tuning example (from `custom-interrogations`): Aluminum deep hole/radial/planar = 20× / 6× / 8× tool-dia; Stainless = 6× / 2× / 3×.

## CNC Lathe / Turning (`analyze_lathe()`)

**Strategy inputs:** `max_tool_protrusion_length` = 5.0 in · `axial_max_hooked_tool_radius` = 0.75 in · `radial_max_hooked_tool_radius` = 0.5 in · live tooling toggles `should_perform_live_tooling` / `can_perform_axial_live_tooling` / `can_perform_radial_live_tooling` (all True).

**Warnings**

| Warning | Detects | Threshold input(s) | Default | Toggle default |
|---|---|---|---|:--:|
| Work Envelope Size | Part exceeds turning envelope | `max_part_length` = 36 in; `max_part_diameter` = 18 in | — | `should_detect_size_restrictions` True |
| Bored Hole Without Relief | Relief-distance ÷ dia too low | `bore_hole_relief_ratio` | 0.25 | True |
| Slender Part | Total-length ÷ smallest-dia too high | `slender_part_ratio` | 8.0 | True |
| Small Internal Radius | Internal radius below min | `small_internal_radius_threshold` | 0.0394 in (1.0 mm) | True |
| Steep Profile | External face angle to axis too steep | `steep_profile_angle_threshold` | 1 rad (57.3°) | True |
| Tight Corners (live tooling) | Non-radiused internal profiled corner | `should_detect_tight_corners` | — | True |
| Off-Axis Hole (live tooling) | Hole not machinable axial/perpendicular | `should_detect_off_axis_holes` | — | True |
| Asymmetric Cavity (live tooling) | Cavity not symmetric about axis | `should_detect_asymmetric_cavities` | — | True |

## Tube Laser (`analyze_tube_laser()`)

Supports 5 tube cross-sections. Strategy: `should_countersinks_be_lasered` (True → countersinks count toward cut length & pierce count).

**Warnings**

| Warning | Detects | Threshold input(s) | Default | Toggle default |
|---|---|---|---|:--:|
| Angled Cut | Non-perpendicular cut to tube axis (needs extra axis). Beyond `max_angled_cut_threshold` → reclassified as Additional Operations Required (`machining_required`) | `max_angled_cut_threshold` = 45° | — | `should_detect_angled_cuts` True; `…_on_round_tubes` False |
| Close Cutouts | Two lasered features too close (dist÷t) | `close_cutouts_threshold` | 1.0 | True |
| Cutouts Close To Edge | Cutout too near edge (dist÷t) | `cutout_edge_proximity` | 2.0 | True |
| Close Countersinks | Two countersinks too close (dist÷t) | `close_countersinks_threshold` | 8.0 | True |
| Countersinks Close To Edge | Countersink too near edge (dist÷t) | `countersink_edge_proximity_threshold` | 4.0 | True |

## Wire EDM · Cast Urethane · Additive

Named interrogations with `analyze_wire_edm()` / `analyze_casting()` / `analyze_additive()` hooks; public DFM warning catalogues are thinner than the four above. Capture feature/output details from `wire-edm-process`, `cast-urethane-process`, `additive-process` when those families enter scope (your spec marks additive/cast as likely post-"Core 4").

---

## Implementation guidance

1. **Seed table shape:** `family → warning → detects → threshold field(s) → default → enabled-by-default → P3L/Kalk name`. The table above is that seed; load it as the default `Configure → Interrogations` profile (e.g. "Default Sheet Metal (Laser)").
2. **Authorability:** every threshold + `should_detect_*` toggle must be editable per custom-interrogation, linkable to material class/family/material and operation — and resolved by **most-specific match**.
3. **Always-on warnings** (sheet-metal "Additional Operations Required", milling "Uncut Faces") cannot be disabled — enforce.
4. **Units:** store/seed in the documented units (mostly inches or ×thickness); apply the same metric/imperial handling as Kalk (`units_in()`), and present metric-first for DACH.
5. **v1 gating:** wire each warning to a recognized feature; if v1 OCCT can't recognize the feature, mark the warning "v2/Spatial" rather than silently dropping it. These warnings drive **Review Items / Rules**, so a missing feature = a missing review signal.
6. **Source:** `sheet-metal-interrogation`, `milling-interrogation`, `lathe-interrogation`, `tube-laser-interrogation`, `interrogations-basics`, `custom-interrogations`, `New-Sheet-Metal-Interrogation-Warnings`.
