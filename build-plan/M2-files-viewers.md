# M2 — Files & Viewers

**Spec:** [#milestones](../docs/spec/Bid-Factory-Build-Spec.html#milestones) (M2 row) · **Exit criteria (authoritative):** open a fixture **STEP + drawing**; **redact + save a copy**; a **face annotation → Dashboard task**; the Part-Library **match buckets populate**.

**Goal.** Make the golden thread's part **inspectable**: build the PDF/print viewer (PDF.js — annotate/measure/redact/whiteout/split/compare), the 3D viewer (three.js + occt-import-js — face pick, selection data, render modes, rendering limits), the viewer-side **collaboration** (TEAM/EXTERNAL chat + face annotations + tasks), the **Part Setup** panel *scaffold*, and the **Part Library** with exact-file / name / part# / historical match buckets. M2 is rendering + inspection on top of files already uploaded in M1.2 — **not** upload, **not** extraction (Lens click-to-fill is M3), **not** interrogation (GeometryService is M4).

**Golden-thread role: minimal.** M2 does not advance the thread's data — it is *how the thread's part is looked at*. The Part Setup panel is scaffolded here; its click-to-fill extraction wiring lands in **M3**. The geometric match bucket is stubbed here and lit up in **M4** (it depends on the geometry-signature algorithm defined there). The thread's CI test must stay green (M2 touches viewers, not pricing).

**Stack (spec-decided, M2 row):** PDF = **PDF.js** (this milestone owns annotate/redact/measure/whiteout built on top); 3D = **three.js + occt-import-js** on the GeometryService tessellation; one platform **`MAX_UPLOAD_MB = 200`** (resolved in `VIEWER-AND-FILE-TYPES`).

**Sequence:** two orthogonal tracks off M1.2 (file storage) + M1.5 (part model), joined at the end.
- **PDF track:** `M2.1 → M2.2 → M2.3 → M2.4 → M2.5`  (core → annotate → measure → redact → split)
- **3D track (⟂ to PDF):** `M2.6 → M2.7 → M2.8 → M2.9`  (core → selection/face-pick → measure → display/limits)
- **Join:** `M2.10` (Part Setup scaffold) ⟂ ; `M2.11` (collaboration: chat + annotations + tasks) needs M2.6 + M2.1; `M2.12` (Part Library + buckets) ⟂ off M1.2.

---

### M2.1 — PDF viewer core (PDF.js: load · navigate · search · pages)   `[L]`  ⟂
- **Vertical slice:** open a fixture drawing PDF, pan/zoom/fit, page through it, search it, and rotate/extract/delete pages — including revision compare.
- **Scope (in):** PDF.js mount + render of a stored PDF; layouts (continuous / page-by-page; single / double / cover-facing spread); pan (`P`) + zoom (% field / `Cmd±` / fit-width / fit-page / marquee `Z`); rotate whole document or single page; thumbnail panel with multi-select (`1,3,5` / `1-5`), per-page **rotate / extract (download selected pages locally) / delete**; in-document **search** with case-sensitive + whole-word toggles; **revision compare** (load a comparison file; **red = removed / blue = added / black = identical**; eye toggle); persisted collapsed-sidebar state; dark mode + viewer-language setting.
- **Scope (out):** annotate/shapes (→ M2.2); measure + scale calibrate (→ M2.3); redact (→ M2.4); **Split PDF** into N saved files (→ M2.5); **global Parts-Library search** across all PDFs (→ M2.12); Lens extraction overlay + callout popovers (→ M3).
- **Depends on:** M1.2 (stored PDF + supported-type allow-list)   ·   ⟂ with the 3D track
- **Implements (spec):** [#pdf](../docs/spec/Bid-Factory-Build-Spec.html#pdf), [#pdf-capabilities](../docs/spec/Bid-Factory-Build-Spec.html#pdf-capabilities)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§4 PDF capability set)
- **KB:** [KB: pdf-viewer-guide](https://help.paperlessparts.com/s/article/pdf-viewer-guide), [KB: quoting-from-pdfs--tips-and-tricks](https://help.paperlessparts.com/s/article/quoting-from-pdfs--tips-and-tricks)
- **Acceptance criteria:** a fixture PDF loads and renders; layout/zoom/pan/fit/marquee work; thumbnail multi-select extracts selected pages; search finds a known title-block string with case + whole-word honored; revision-compare colors a known rev B→C diff red/blue/black and the eye toggle hides it; sidebar-collapsed state survives reload.
- **Test plan (fixtures):** load `/fixtures/drawings` rev-B + rev-C PDFs; assert search hit count for a known string under each toggle, and that the diff overlay marks the added note blue.
- **Golden-thread role:** the surface the thread's drawing is read on (no data change).

### M2.2 — PDF annotation + shapes + undo/redo   `[M]`  ⟂
- **Vertical slice:** mark up a drawing with annotations and shapes, with styling presets and full undo/redo, persisted to the file's annotation layer.
- **Scope (in):** annotate tools — underline (`U`), highlight (`H`), rectangle (`R`), free text (`T`), free-hand highlight, free-hand (`F`), note (`N`), squiggly (`G`), strikeout (`K`), eraser (`E`); shapes — rectangle, line (`L`), polyline, arrow (`A`), arc, ellipse (`O`), polygon; styling **presets**; **undo/redo**; persist the annotation layer per file; **download-with-annotations**.
- **Scope (out):** measure tools + scale calibration (→ M2.3); saving annotations *into the collaboration thread* (the chat plumbing is → M2.11; this block persists the layer + exposes "save to collaboration" as a stub hook); redact (→ M2.4).
- **Depends on:** M2.1
- **Implements (spec):** [#pdf-capabilities](../docs/spec/Bid-Factory-Build-Spec.html#pdf-capabilities)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§4 Annotate / Shapes)
- **KB:** [KB: pdf-viewer-guide](https://help.paperlessparts.com/s/article/pdf-viewer-guide)
- **Acceptance criteria:** each annotation/shape type places and persists; undo/redo restores prior state exactly; a preset applies its styling; downloading with annotations embeds them; the bare download (M2.1) is unaffected.
- **Test plan (fixtures):** add one of each annotation/shape to a fixture PDF, reload, assert the layer round-trips; assert undo then redo returns the identical layer.
- **Golden-thread role:** none (markup surface; no thread data change).

### M2.3 — PDF measure + scale calibration   `[M]`  ⟂
- **Vertical slice:** set the drawing scale (ratio or calibrate from a known dimension), then measure distance / arc / perimeter / area / count with snapping.
- **Scope (in):** **set scale first** — pick a ratio (e.g. 1:2) **or calibrate** by clicking two ends of a known dimension and typing its real length; measure tools — **distance**, **arc** (length / radius / center-angle), **perimeter**, **area** (custom / circle / rectangle), **count**; **snapping**; undo/redo/erase on measurements; measurements honor the unit/precision presets.
- **Scope (out):** 3D measure (that is a distinct engine → M2.8); persisting measurements into collaboration (→ M2.11).
- **Depends on:** M2.2
- **Implements (spec):** [#pdf-capabilities](../docs/spec/Bid-Factory-Build-Spec.html#pdf-capabilities)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§4 Measure — set scale / calibrate)
- **KB:** [KB: pdf-viewer-guide](https://help.paperlessparts.com/s/article/pdf-viewer-guide), [KB: quoting-from-pdfs--tips-and-tricks](https://help.paperlessparts.com/s/article/quoting-from-pdfs--tips-and-tricks)
- **Acceptance criteria:** with no scale set, measure warns/blocks; after calibrating from a known length, a distance reads correct within tolerance; arc/area/count each return a plausible value; snapping locks to vertices/edges.
- **Test plan (fixtures):** on a fixture drawing with a known dimension, calibrate then assert a second known distance computes within tolerance.
- **Golden-thread role:** none.

### M2.4 — PDF redaction + whiteout + supporting-file generation   `[M]`
- **Vertical slice:** redact text / a section / a page on a drawing and **save a new supporting file** (original retained), with recolourable fill and a whiteout/spotlight mode.
- **Scope (in):** redact **text**, **rectangular sections**, or **entire pages** → renders a **new supporting file** stored alongside the original (one PRIMARY, per M1.2); **recolour redaction fill/stroke** (incl. white-on-white to hide that a redaction happened); **Whiteout** mode (per-section + global) that clears callout clutter so bare geometry is readable, with **spotlight a single callout** while whited-out; the new file enters the M1.2 file list as a supporting file.
- **Scope (out):** *scoped external-collaboration share* of the redacted file (the ExternalShare model + per-recipient permissions/expiry → **M6** Vendor RFQ; here, just generate the file); Lens "Contains ITAR/CUI" findings driving redaction (→ M3).
- **Depends on:** M2.1, M1.2 (supporting-file storage)
- **Implements (spec):** [#pdf-capabilities](../docs/spec/Bid-Factory-Build-Spec.html#pdf-capabilities), [#collab](../docs/spec/Bid-Factory-Build-Spec.html#collab) (PDF redaction → exact redacted copy)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§4 Redact; §6 GDPR redaction → new file)
- **KB:** [KB: pdf-viewer-guide](https://help.paperlessparts.com/s/article/pdf-viewer-guide), [KB: swap-primary-and-supporting-files](https://help.paperlessparts.com/s/article/swap-primary-and-supporting-files)
- **Acceptance criteria:** redacting a region produces a **new** file (e.g. `*-redacted.pdf`) with the content irrecoverably removed from that copy while the original is byte-unchanged; the new file appears as a supporting file; whiteout hides callout clutter and spotlight re-reveals one; fill recolour applies.
- **Test plan (fixtures):** redact a title-block region on a fixture drawing; assert original bytes unchanged, new supporting file created, and the redacted text is absent from the new file's extracted text (**satisfies the "redact + save a copy" exit check**).
- **Golden-thread role:** none (produces a derivative file; thread data unchanged).

### M2.5 — Split PDF into single-page files   `[S]`  ⟂
- **Vertical slice:** split a multi-page drawing PDF into N single-page files (one part per page) with a progress/success toast, original retained.
- **Scope (in):** Split PDF action → generate **N single-page files** stored as new files (M1.2); progress + success toasts; original retained; the per-page *extract/download* affordance from M2.1 is the local-download cousin — this block is the server-side split into persisted files.
- **Scope (out):** auto-bundling split pages back to distinct parts / merge (Part-Library merge → M2.12); per-page interrogation (→ M4).
- **Depends on:** M2.1, M1.2
- **Implements (spec):** [#pdf-capabilities](../docs/spec/Bid-Factory-Build-Spec.html#pdf-capabilities) (Pages: extract / split one-page-per-part)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§4 Pages — extract = split one-page-per-part)
- **KB:** [KB: pdf-viewer-guide](https://help.paperlessparts.com/s/article/pdf-viewer-guide)
- **Acceptance criteria:** a 3-page fixture PDF splits into 3 single-page files; toasts fire on progress + success; the original remains intact and listed.
- **Test plan (fixtures):** split a multi-page `/fixtures/drawings` PDF; assert file count = page count and each new file has exactly one page; original byte-identical.
- **Golden-thread role:** none.

### M2.6 — 3D viewer core (three.js + occt-import-js: load STEP · orbit/pan/zoom · render modes)   `[L]`  ⟂
- **Vertical slice:** open a fixture STEP, orbit/pan/zoom it, switch render modes, and reset the camera via the orientation cube.
- **Scope (in):** **occt-import-js** parse of a stored STEP → tessellation; **three.js** scene + orbit / pan / zoom; **orientation cube** (Left/Top/…) + reset view; render modes **shaded / transparent (x-ray) / wireframe**; the assembly/feature **tree** panel (structure only); whole-file readout shell (Volume / Surface Area / Weight placeholders, filled by selection in M2.7). STEP is the v1 primary format (zero licensing).
- **Scope (out):** face/edge selection + per-entity property readout (→ M2.7); 3D measure (→ M2.8); display-options gear + unit toggle + rendering-limit simplified-reps (→ M2.9); **interrogation feature highlighting** (`SELECT INTERROGATION`, recognized features/DFM colors) — that is GeometryService output → **M4**; native CAD formats needing the Spatial/HOOPS import kernel (→ M4/post-pilot; STEP only here).
- **Depends on:** M1.2 (stored STEP), M1.5 (part/file model)   ·   ⟂ with the PDF track
- **Implements (spec):** [#cad](../docs/spec/Bid-Factory-Build-Spec.html#cad), [#viewer3d-tools](../docs/spec/Bid-Factory-Build-Spec.html#viewer3d-tools)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§1 3D tools — render/navigate subset)
- **KB:** [KB: 3d-viewer-tools](https://help.paperlessparts.com/s/article/3d-viewer-tools)
- **Acceptance criteria:** a fixture STEP loads and tessellates; orbit/pan/zoom respond; shaded/transparent/wireframe switch; orientation-cube faces snap the camera; reset restores default; the model tree lists bodies.
- **Test plan (fixtures):** load a `/fixtures/cad` STEP; assert tessellation succeeds (triangle count > 0) and each render mode renders without error (**half of the "open fixture STEP + drawing" exit check**, the PDF half being M2.1).
- **Golden-thread role:** the surface the thread's STEP is viewed on (no data change; real interrogation overlay is M4).

### M2.7 — 3D selection + face pick + property readout   `[M]`
- **Vertical slice:** click a face/edge and see its geometric properties live, with a cumulative-sum selection set and whole-file totals.
- **Scope (in):** ray-pick a face/edge → **selection data overlay**: Type (cylinder / plane / …), **Area**, **Height**, **Diameter**, **Angle**; whole-file Volume / Surface Area / Weight (from the loaded tessellation/B-rep); **cumulative selection sums** (area across a multi-pick); axis-aligned X/Y/Z dims + **optimal bounding box** + wireframe-feature mapping; expose a stable face/entity id so a picked face can be referenced (consumed by collaboration in M2.11).
- **Scope (out):** measure-between-entities exact-vs-approximate (→ M2.8); feature *recognition* (DFM/feature colors come from GeometryService → M4 — this block reads raw topology props, not recognized features); annotate-to-chat (the chat side is → M2.11).
- **Depends on:** M2.6
- **Implements (spec):** [#viewer3d-tools](../docs/spec/Bid-Factory-Build-Spec.html#viewer3d-tools), [#cad](../docs/spec/Bid-Factory-Build-Spec.html#cad) (selection data overlay)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§1 Selection / axis dims / OBB / wireframe)
- **KB:** [KB: 3d-viewer-tools](https://help.paperlessparts.com/s/article/3d-viewer-tools)
- **Acceptance criteria:** picking a cylindrical face reports Type=cylinder with a diameter; picking a plane reports its area; multi-pick sums area; whole-file volume/area/weight display; axis dims + OBB render; a picked face exposes a referencible id.
- **Test plan (fixtures):** on a `/fixtures/cad` STEP with a known hole, assert the picked cylinder's diameter and the planar face area match expected within tolerance.
- **Golden-thread role:** none (read-only topology inspection).

### M2.8 — 3D measure: exact-vs-approximate   `[M]`
- **Vertical slice:** measure distance / caliper / angle in 3D, where the result is mathematically **exact** on special orientations and flagged **`~` approximate** otherwise — the estimator trust signal.
- **Scope (in):** measure **distance** between two features/faces/edges; **caliper** behaviour on parallel faces / concentric cylinders (circular entities measure from the **parametric center**); **angle between two selected faces**; the **exact** guarantee on **parallel planes / concentric cylinders / perpendicular cylinder+plane**, with everything else prefixed **`~`** (approximate) — preserve this distinction precisely.
- **Scope (out):** PDF measure (separate engine → M2.3); section/cutaway tool (defer — note as a viewer enhancement); exploded/focused-body views (assembly-gated → M4).
- **Depends on:** M2.7
- **Implements (spec):** [#viewer3d-tools](../docs/spec/Bid-Factory-Build-Spec.html#viewer3d-tools)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§1 Measure + §2 Exact vs approximate)
- **KB:** [KB: 3d-viewer-tools](https://help.paperlessparts.com/s/article/3d-viewer-tools)
- **Acceptance criteria:** a distance between two **parallel planes** returns **exact** (no `~`); a distance between two arbitrary points returns a **`~`-prefixed** value; the angle between two faces reads correctly; concentric-cylinder distance measures center-to-center.
- **Test plan (fixtures):** on a STEP fixture, assert parallel-plane distance is unprefixed and within tight tolerance, and a skew measurement carries the `~` prefix.
- **Golden-thread role:** none.

### M2.9 — 3D display options + unit toggle + rendering limits   `[M]`
- **Vertical slice:** the gear popover toggles units (metric default), native-colours, and precision; over-budget bodies become blue/orange simplified reps with tree affordances.
- **Scope (in):** display-options gear — **units toggle** (dims/area/volume in↔mm, weight lb↔kg; **Tolera default = metric mm/kg/deg**, comma-decimal per `de-DE`/`de-CH`/`de-AT`, never default to imperial); **native-model-colours/opacity** toggle (restores feature-highlight contrast when export colours clash); user-set **decimal precision** (applies live); **rendering limits** — 25 M-vertex concurrent budget; multi-body over budget → smallest bodies become **blue** bounding-box simplified reps (**blue cube** tree icons), restored by **isolating** a subassembly; single body over budget → **orange** bounding-box rep (**orange cube** tree icons) which also suppresses its (future M4) interrogation results; enforce one platform **`MAX_UPLOAD_MB = 200`** with a soft-warning band.
- **Scope (out):** the interrogation-results suppression *content* (no results to suppress until M4 — wire the flag, leave the panel empty); ISO-GPS GD&T symbology (renders only once Lens/GeometryService emit GD&T → M3/M4).
- **Depends on:** M2.6 (M2.7/M2.8 may merge in any order before this)
- **Implements (spec):** [#viewer3d-limits](../docs/spec/Bid-Factory-Build-Spec.html#viewer3d-limits), [#cad](../docs/spec/Bid-Factory-Build-Spec.html#cad) (display options)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§2 display options; §3 rendering limits; §6 DACH metric default)
- **KB:** [KB: part-viewer-display-options](https://help.paperlessparts.com/s/article/part-viewer-display-options)
- **Decisions:** PDF.js stack + single `MAX_UPLOAD_MB = 200` are resolved in `VIEWER-AND-FILE-TYPES` (no open item); if the 25 M-vertex budget needs a device-tier override, log `OPEN:` in ../docs/decisions/DECISIONS.md rather than guessing.
- **Acceptance criteria:** viewer **opens in metric** (mm/kg, comma-decimal); the toggle flips dims/area/volume/weight; native-colour toggle restores contrast; precision applies live; a synthetic >25 M-vertex multi-body file substitutes blue boxes and restores on isolate; an over-budget single body shows an orange box.
- **Test plan (fixtures):** assert default units = metric on load; drive a synthetic over-budget body and assert the blue/orange simplified-rep substitution + isolate-restore.
- **Golden-thread role:** none (DACH metric default is a cross-cutting constraint, not a thread datum).

### M2.10 — Part Setup panel scaffold (identity · processes · specs fields)   `[M]`  ⟂
- **Vertical slice:** the print-side Part Setup panel renders next to the drawing with all data-entry fields wired to the part model — but click-to-fill from extractions is stubbed for M3.
- **Scope (in):** the Part Setup right panel (alt to collaboration) — **Part fields** tab with sections: **Quote Setup** (Part Number, Revision, Description, Print Default Units), **Requirements** (Processes, Specifications, Likely Global Material), **Features** (Datums, Feature Control Frames, Holes), **Dimensions** (X/Y/Z, accepting math/units per M1.5); the **NUM/REV** radio governing which title-block field a click targets; per-section **Whiteout** toggle hook (reuses M2.4 whiteout); the **Found in files [n]** tab present but empty; manual entry persists to the part (M1.5). Two pagers: top steps line items, bottom steps assembly children.
- **Scope (out):** **click-to-fill from a drawing extraction**, the **callout popover** (plain-language + Mark-inaccurate + Create-rule), **Add-missing-extraction**, units auto-detection, the Review-Items panel — **all → M3** (Lens + Rules). This block is the *container + manual-entry fields only*; the extraction wiring lands on top in M3.
- **Depends on:** M2.1 (renders beside the PDF), M1.5 (part identity/dims/processes model)   ·   ⟂ with the 3D track
- **Implements (spec):** [#pdf](../docs/spec/Bid-Factory-Build-Spec.html#pdf) (Part Setup panel), [#partview](../docs/spec/Bid-Factory-Build-Spec.html#partview) (identity/costing-inputs fields)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (PDF viewer = where Part Setup + extraction live)
- **KB:** [KB: part-setup-tool](https://help.paperlessparts.com/s/article/part-setup-tool), [KB: found-in-files-extractions](https://help.paperlessparts.com/s/article/found-in-files-extractions)
- **Acceptance criteria:** the panel renders beside a fixture drawing with all sections; manual entry into Part Number/Rev/Description/Processes/Specs/Dimensions persists to the part; the NUM/REV toggle switches the active title-block target; the Found-in-files tab shows its (empty) badge; whiteout toggles per section.
- **Test plan (fixtures):** type identity + a dimension (incl. a math expression) into the panel for the golden-thread part; assert persistence and that re-opening reflects the values.
- **Golden-thread role:** scaffolds the panel the thread's part is set up in; **its extraction-driven click-to-fill is M3** (the thread's part keeps its M1.5 manual dims until then).

### M2.11 — TEAM/EXTERNAL chat + annotations + tasks   `[L]`
- **Vertical slice:** select a face (3D) or a drawing region (PDF), post a face/region annotation to the TEAM/EXTERNAL chat, assign a task, and see that task on the Dashboard.
- **Scope (in):** viewer collaboration panel with **TEAM** (internal) and **EXTERNAL** (per customer/vendor) channels; post a message **bound to a selected feature/face** (3D, via the M2.7 entity id) or a **drawing annotation** (PDF, via the M2.2 layer) — `@mention` a teammate; **Reply / Edit / Delete**; **Tag Teammate**; **Assign Task**; clicking a message's annotation re-opens the document/feature zoomed to it; **annotations + tasks surface on the Dashboard**; "Add annotation" from the PDF viewer threads to the quote's chat (closes the M2.2/M2.3 "save to collaboration" hook).
- **Scope (out):** secure **external vendor sharing** (the email-style composer, per-recipient file scope/permissions/expiry, `ExternalShare`) → **M6** Vendor RFQ; supplier sourcing punchouts (Tolera Source/Advisor/Online Metals) → **M6**; the Dashboard *redesign/work-queue* → **M6** (this block only emits the task onto the existing dashboard surface).
- **Depends on:** M2.6 (3D face pick from M2.7), M2.1 (PDF annotations from M2.2)
- **Implements (spec):** [#collab](../docs/spec/Bid-Factory-Build-Spec.html#collab), [#cad](../docs/spec/Bid-Factory-Build-Spec.html#cad) (TEAM/EXTERNAL face annotation)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (§4 save annotations through Collaboration; §1 annotate face into chat)
- **KB:** [KB: internal-collaboration](https://help.paperlessparts.com/s/article/internal-collaboration), [KB: tasks](https://help.paperlessparts.com/s/article/tasks)
- **Acceptance criteria:** a TEAM message binds to a picked 3D face and an EXTERNAL message binds to a PDF annotation; `@mention` notifies; **Assign Task creates a task that appears on the Dashboard**; clicking the message's annotation re-focuses the exact feature; channels are org-scoped.
- **Test plan (fixtures):** select a face on the golden-thread STEP, post a face annotation with Assign Task, assert the task is queryable on the Dashboard (**satisfies the "face annotation → Dashboard task" exit check**).
- **Golden-thread role:** none to thread data; proves the inspection-collaboration loop on the thread's part.

### M2.12 — Part Library + matching buckets (exact-file / name / part# / historical)   `[L]`
- **Vertical slice:** every uploaded part is indexed; opening a line item shows historical match buckets, and selecting a match copies its router/operations/overrides onto the current part.
- **Scope (in):** the **Part Library** (`/parts`) — Team / Shared-with-me / Archived tabs, card grid (thumbnail, filename, part#, rev, process), search by part name/number/revision; **global Parts-Library PDF search** (full-text over `pdf_text` extracted at upload — the M2.1 in-doc search's platform-wide cousin); the **"N matching parts"** modal with buckets computed **now**: **Exact File Match** (SHA-256 `file_hash`), **File Name Match** (normalized filename), **Part Number Match** (`part_number_extracted` + manual part#), **Similar/Historical** (prior quotes by part#/name); **selecting a match copies** the historical router, operations, and per-quote-item **manual overrides** (yellow-highlighted, `source:'manual'`) onto the current part; auto-bundling (matching-name CAD+PDF → one part, CAD primary) + manual **Merge Parts as Supporting Files**; archive/delete lifecycle (quotes preserve costing on delete).
- **Scope (out):** **Exact Geometric Match** + **Similar Geometries** (fuzzy) buckets — **gated on M4**: both need the OCCT **`geometry_signature`** / `geometry_vector` (pgvector ANN) from the GeometryService geometry sprint; **stub these two buckets as "geometry indexing pending"** until M4 lands; SFTP bulk historical import (post-pilot); 3D thumbnail *generation* may reuse the M2.6 tessellation but server-side render hardening is optional here.
- **Depends on:** M1.2 (file hash at ingest), M1.5 (part identity), M1.7 (operations/overrides to copy)   ·   ⟂ off the viewer tracks
- **Implements (spec):** [#partlib](../docs/spec/Bid-Factory-Build-Spec.html#partlib)
- **Internals (provenance):** ../docs/spec/folded-subspecs/INTERROGATION-ENGINE-SPEC.md (`compute_signature` — the geometric-match dependency, defined in M4)
- **KB:** [KB: navigate-and-manage-the-part-library](https://help.paperlessparts.com/s/article/navigate-and-manage-the-part-library), [KB: uploading-parts-to-your-part-library](https://help.paperlessparts.com/s/article/uploading-parts-to-your-part-library), [KB: similar-parts-search-beta](https://help.paperlessparts.com/s/article/similar-parts-search-beta)
- **Decisions:** geometric/fuzzy buckets depend on the M4 geometry-signature algorithm (per `INTERROGATION-ENGINE-SPEC` `compute_signature` + pgvector); v1 scope (scalar feature vector → pgvector) is decided in the spec — if the exact feature-vector schema is unresolved when M4 starts, log `OPEN:` in ../docs/decisions/DECISIONS.md.
- **Acceptance criteria:** uploading two byte-identical files yields an **Exact File Match**; same-filename and same-part-number files populate the **Name** and **Part#** buckets; selecting a historical match copies operations + manual overrides (overrides flagged `source:'manual'`); global Parts-Library search finds a part by a string that exists **only in a PDF title block**; the geometric/similar buckets render a "pending M4" placeholder.
- **Test plan (fixtures):** seed two parts sharing a file hash and two sharing a part#; assert the correct buckets populate (**satisfies the "match buckets populate" exit check**); assert importing a match copies the router + a manual override.
- **Golden-thread role:** lets the thread's part discover historical matches (exact/name/part# now; **geometric match lit up at M4**).

---

**M2 done when:** a fixture **STEP + drawing** open in their viewers; a drawing **redacts to a saved copy** (original intact); a **3D face annotation creates a Dashboard task**; and the Part-Library **match buckets populate** (exact-file / name / part#) — the spec's M2 exit. The Part Setup panel is scaffolded for M3's click-to-fill, the geometric match bucket is stubbed for M4, and the golden-thread integration test stays green.
