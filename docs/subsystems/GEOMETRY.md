# GEOMETRY.md — OCCT Capability Map (M4.0 spike verdict)

**Status:** M4.0 deliverable, 2026-07-16. The per-family OCCT capability map the build plan
requires (`build-plan/M4-geometry-manufacturing.md` M4.0) — cross-walked to the
`family_scalars` lists (`INTERROGATION-ENGINE-SPEC.md` §2, folded at spec `#geometryservice`)
and the `PartGeometry-Attribute-Catalog.md` v1 column. Also the home for
Spatial-upgradeable capabilities per `DECISIONS.md` [2026-06-14] and the geometry-signature
algorithm per spec `#geometry-engine`.

**How it was produced:** throwaway probe scripts (`scripts/spike-m4.0/`, PEP 723/`uv run`)
against synthetic ground-truth STEP fixtures (`fixtures/cad/`, constructed from OCCT
primitives with exact analytic goldens — `goldens.json`). Probe outputs:
`scripts/spike-m4.0/results/probe_[a–f].json`. This is a knowledge artifact, not a CI test;
M4.1–M4.6 build against it. **Real Fechner fixtures must re-validate the map when they land**
(`DECISIONS.md` [2026-07-12] OPEN: Fechner fixture packages).

**Overall verdict: GO with OCCT — no Core-4 family is Spatial-required.**

Legend: `✓` probed and working · `~` partial / feasible on probed primitives but recognizer
work or a mini-spike remains · `✗` no OCCT support (in-house heuristic or Spatial/post-pilot).

---

## 0. Packaging & runtime (the import/parse path)

| Item | Verdict | Evidence / note |
|---|---|---|
| OCCT 7.9 via pip (`cadquery-ocp` 7.9.3, OCP bindings) | ✓ | Wheels for cp312 macOS arm64 + manylinux_2_31 x86_64/aarch64. `uv run` PEP 723 probes install and pass locally; linux container run below. pythonocc-core has **no** pip wheels (conda-forge only; PyPI stub is dead 0.16) → binding = **OCP**, see DECISIONS [2026-07-16]. API is 1:1 OCCT C++; a later pythonocc/Spatial move is mechanical behind `GeometryService`. |
| Linux (Hetzner path) | ✓ | **All six probes pass inside the production `tolera-worker` image** (python:3.12-slim base, linux/aarch64) after `pip install cadquery-ocp` + **`apt-get install libgl1`** — OCP links libGL even headless (vtk linkage); that one system package goes into the worker Dockerfile in M4.1. Run log: `results/linux_worker_run.txt`. x86_64: the manylinux_2_31 wheel is published; not executed in this spike (local amd64 image pull stalled) — verify on first Hetzner deploy. |
| Cross-platform hash determinism | ✓ | The signature fingerprint is **byte-identical on macOS arm64 and linux aarch64** for five fixtures — safe to index in the Part Library regardless of where it was computed. Evidence: `results/hashes_linux.json` vs `results/hashes_macos.json`. |
| Dependency weight | note | `cadquery-ocp` wheel ~60 MB + transitive **vtk ~102 MB** + libgl1. Acceptable for the worker image; keep OCP out of the API image (interrogation runs on Celery workers only). |
| STEP read/write round-trip | ✓ | Re-exported solids fingerprint identically (probe a re-export case), and volumes of all read-back fixtures match their analytic goldens to ≤3e-14 rel. STEP-only solids per spec v2.15 (`#geometry-engine`); SLDPRT stays out until Spatial. |

## 1. Core dimensions (`PartGeometry` §1 — all families)

| Attribute | v1 | Verdict | Evidence (probe a, 9 fixtures) |
|---|---|---|---|
| `volume`, `area` | ✓ | ✓ | `BRepGProp` vs analytic goldens: volume rel ≤3e-14; surface area gated at 0.1%, measured ≤1e-9. |
| `size_x/y/z` (AABB path) | ✓ | ✓ | `Bnd_Box` exact on all fixtures. |
| `max/med/min_dim` (optimal bbox) | ✓ | **~** | `Bnd_OBB(theIsOptimal=True)` is **approximate** (PCA-based): tight on prisms/cylinders, but on the bracket it returned 71.3×50×35.5 (volume-larger than the 60×50×40 AABB). **M4.1 must take the tighter of OBB/AABB** (min volume) for the `overwrite › optimal-bbox › AABB` precedence. |
| `weight` | ✓ | ✓ | `weight_g = (volume_mm³ / 1000) × density_g/cm³` — 20 mm cube × 7.9 g/cm³ = 63.20 g (mind the mm³→cm³ factor). Density is `man` (material record), per the catalog. |
| Units | — | ✓ | STEP files are mm-native; all probes metric (mm/mm²/mm³/g). |

## 2. Geometry signature (`compute_signature`) — **the make-or-break: PASS**

Spec recipe (`#geometry-engine`): normalized fingerprint = quantized (volume, area,
bbox-sorted dims, face/edge-type histogram, per-type areas) → SHA-256, plus exact file hash.

| Test (probe a) | raw | + `ShapeUpgrade_UnifySameDomain` |
|---|---|---|
| Same solid, two CAD exports (re-export round-trip) | PASS | PASS |
| Same solid, rotated/translated in space | PASS | PASS |
| **Split-face vs single-face** (10-face fused cube vs 6-face cube) | FAIL | **PASS** |
| Rotated **and** split | FAIL | **PASS** |
| Distinct parts must differ | PASS | PASS |

Stable at 4, 6 and 8 significant-digit quantization. **Verdict: OCCT yields a stable,
topology-tolerant hash** — recipe = UnifySameDomain canonicalization → OBB-sorted dims +
quantized props + type histograms → SHA-256. M4.1/M4.11 greenlit (Exact-Geometric bucket
not degraded).

Caveats to pin in M4.1: (i) quantization digits are a tuning knob — 6 passed everywhere,
pick and freeze it with the real fixtures; (ii) `Bnd_OBB` approximation feeds the dims —
canonicalize first, and consider dropping dims to 4 digits; (iii) the fingerprint is
placement-invariant by construction, so **mirror (chiral) parts hash identically** — known
limitation, acceptable for match-*suggestion* buckets (M4.11 surfaces candidates, humans
confirm); (iv) exact file hash rides alongside for Exact-File match, unaffected.

## 3. Sheet Metal (`analyze_sheet_metal`) — verdict: **OCCT-sufficient for M4.1/M4.2 core; mini-spike flagged for complex unfold** (matches build-plan M4.2)

Probe b on the L-bracket fixture (t=2, r=3, 90°, width 50): thickness and all bend
parameters recovered exactly from the B-rep; the developed length then composes to the
analytic golden via the spec k-factor (flat-leg measurement itself is M4.2 recognizer work).

| Scalar | Verdict | Evidence / note |
|---|---|---|
| `thickness` | ✓ | Anti-parallel planar-pair offset → 2.0000 exact. |
| `bend_count` | ✓ | Concentric cylinder pairs with Δr = thickness → 1 exact. |
| bend radius / angle / line length (features) | ✓ | r=3.0000, 90.00°, 50.00 exact (cylinder U/V parameterization). |
| `size_x`,`size_y` (unfolded) | ~ | **Analytic unfold** from recognized bends: k=(0.65+0.5·log₁₀(r/t))·0.5 → developed length 95.8717 = golden to 4 dp. Proven on a single 90° bend; multi-bend chains, non-90° bends, curls/hems/offsets, bend-direction conflicts are recognizer work → **M4.2 mini-spike** before hardening. Full geometric flattening is NOT required for the family_scalars (sub-spec §3 wants k-factor unfold). |
| `total_cut_length`, `pierce_count` | ~ | = contour/loop arithmetic on the unfolded profile (same edge machinery probe d uses); not separately probed. |
| `punch_*`, `counter_sink/bore_*`, `*_hole_*` | ~ | Shape classification over recognized cutouts (circular/obround/rect/square/slot) — feasible on OCCT primitives (cf. probe c hole recognition), recognizer work in M4.2/M4.7. |
| `total_air_move_length` | ✗ | Nesting-path estimation, in-house (estimation-grade per sub-spec §6) → M4.3. |

## 4. Milling (`analyze_mill3`) — verdict: **OCCT-sufficient for feature inputs; runtime is in-house (honest ceiling); setup-detection hardening = M4.4 mini-spike** (matches build-plan M4.4)

Probe c on the milled-block fixture (pocket 40×20×8, 2× through Ø8, blind Ø6×10):

| Scalar | Verdict | Evidence / note |
|---|---|---|
| Holes (through/blind, Ø, depth) | ✓ | Full-cylinder faces + span test: 2 through Ø8.000, 1 blind Ø6.000 depth 10.000 exact; blind-bottom plane correctly attributed to its bore, not counted as pocket floor. |
| Pockets | ~ | Prismatic floor detection exact (depth 8.000, area 800). General pockets, transitions (fillets/chamfers), tapered walls, tight corners = recognizer work on B-rep topology. |
| `setups[]` / `setup_count` | ~ | Machine-direction inputs (face normals, hole axes → {±Z} on fixture) proven; the allocation heuristic itself is in-house → M4.4 (may need its own mini-spike, per build plan). |
| `runtime` | ✗ OCCT | **No OCCT support — expected finding.** In-house heuristic from removal volume (probed: 8693.36 mm³, within bbox read-tolerance of the analytic 8693.36), feature counts, material. Surface honestly. |
| `confidence` | ✓ | Ours to emit; low confidence → manual override is the designed path (sub-spec §6). 5-axis not auto-costed. |

## 5. Lathe (`analyze_lathe`) — verdict: **OCCT-sufficient at the v2.15 scope (attributes + stock recommendation; no feature tree)**

Spec v2.15 (`#geometry-engine`) caps lathe at attributes-only; the load-bearing output is
the recommended stock (build-plan M4.5). Probe d on the stepped shaft (Ø30/Ø20/Ø12 × 80):

| Scalar | Verdict | Evidence / note |
|---|---|---|
| `stock_radius`, `stock_length` | ✓ | max cylinder radius × axis extent → 15.0 × 80.0 exact. |
| Turnability check | ✓ | All cylindrical faces coaxial → turnable; step diameters [30, 20, 12] exact. |
| `setup_count` | ~ | Heuristic from feature ends/faces per side — in-house, M4.5. |
| Radial vs axial cuts, live-tooling callouts | ~/✗ | Coaxial-vs-off-axis analysis feasible on OCCT topology (~); full turning feature tree is **Spatial** per v2.15 — flagged, not costed. |

## 6. Tube Laser (`analyze_tube_laser`) — verdict: **OCCT-sufficient; 4 of 5 profiles probed, `rectangular_radiused` expected-same-mechanism (mini-spike only if radiused stock matters at pilot)**

Probe d, mid-length section + loop/edge classification:

| Scalar | Verdict | Evidence / note |
|---|---|---|
| `stock_type` round / rectangular / angle / u_channel | ✓ | All four classified exactly; non-tube solid → `incompatible` (never a fabricated guess, per build-plan M4.6). |
| `stock_type` rectangular_radiused | ~ | No fixture; same section mechanism (mixed line+arc loop) — **not claimed**. |
| `thickness`, `diameter`, `length` | ✓ | Round: Ø30/t2/l200 exact from section circles + axis extent. |
| `width`/`height`, corner/leg radii, `leg_angle` | ~ | Derivable from the same section polygon; not separately probed. |
| `total_cut_length`, `pierce_count` | ~ | Cutout contours on the developed surface — same edge machinery; M4.6. |
| Angled cuts (`max_angled_cut_threshold`) | ~ | End-face normal vs axis — feasible, M4.6/M4.7. |

## 7. `decompose_bom` (assemblies) — verdict: **OCCT-sufficient** (probe e, M4.9b inputs confirmed)

| Item | Verdict | Evidence / note |
|---|---|---|
| Unique products → Parts; occurrences → Nodes | ✓ | XCAF (STEPCAFControl_Reader): 2 products (exact volumes), 3 placed occurrences with transforms. |
| Occurrence / product names | ✓ | Round-trip where authored (PIN-1/PIN-2); unnamed occurrences fall back to XCAF entry ids — capture raw, don't invent (Lens classifies later, M4.10b). |
| STEP AP214 material + density per body | ~ | `XCAFDoc_Material`: the material table (1.4301 @ 7.9 g/cm³, AlMg3 @ 2.66 g/cm³) reads back ✓ — but resolving **which body carries which material** via `TDataStd_TreeNode`/MaterialRefGUID **segfaulted the OCP 7.9.3 bindings** (twice). Raw-facts capture for `node.cad_metadata` stays feasible; the per-body link is M4.9b work (alternate XCAF API or STEP-entity parse). |
| Multi-level nesting | ~ | Traversal is recursive; probed one level deep — deep/large assemblies get exercised with real fixtures (M4.9b). |

## 8. Server-side tessellation & thumbnails — verdict: **feasible** (probe f)

`BRepMesh_IncrementalMesh` produces per-face triangulations (bracket 10 faces/76 tris;
assembly 12/212); every face meshes, and the per-face vertex/triangle sequence is
**identical across two independent parse+mesh runs** (measured, probe f) — face indexing
from the interrogation topology is deterministic, so the viewer
can render what GeometryService tessellates and feature→face-id overlays correlate
(resolves DECISIONS [2026-07-14] viewer-mesh entry to its recommended default (b); the
actual endpoint + client switch land in M4.1+). `render_thumbnail` composes on the same
mesh. `extract_pmi` stays a stub (post-pilot, Spatial-grade — E4-e).

## 9. Honest ceilings (restated for M4 acceptance)

- Runtime/setup estimation is heuristic with surfaced `confidence`; low confidence → manual
  override drives cost. 5-axis runtime is not auto-costed.
- Complex parts ⇒ partial feature recognition; recognizers return what they found, never
  fabricate. GD&T/PMI flagged, not costed. Nesting is estimation-grade.
- Signature: chirality-blind (mirror parts collide) — match results are suggestions.
- Everything above sits behind the unchanged `GeometryService` interface; Spatial swap-in
  replaces recognizer internals only (DECISIONS [2026-06-14]).
