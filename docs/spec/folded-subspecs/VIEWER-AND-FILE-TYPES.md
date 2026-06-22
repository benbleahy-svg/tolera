# Part Viewer UX & Supported File Types — Reference

**Status:** Build-readiness appendix for Tolera (Bid Factory). The UI/UX + capability contract for the **3D viewer**, the **PDF/print viewer**, the **rendering limits**, and the **supported-file-type matrix**. This is the front-end counterpart to the engine specs: the 3D viewer renders what **GeometryService** analyzes; the PDF viewer is where **Lens** findings overlay and where estimators mark up prints. **Provenance:** `3d-viewer-tools`, `part-viewer-display-options`, `3D-viewing-limits`, `pdf-viewer-guide`, `supported-file-types`. Companions: `INTERROGATION-ENGINE-SPEC.md`, `AI-LENS-ENGINE-SPEC.md`, `RULES-ENGINE-SPEC.md`, `DACH-DELTA-LAYER.md`, `DECISIONS.md`.

> **Build-vs-buy flag (log in `DECISIONS.md`).** The PDF viewer in PP is a heavyweight component (continuous/spread layouts, search, page extract, **revision compare**, full annotate/measure/redact, dark mode, i18n) — almost certainly a commercial SDK (Apryse/PDFTron-class), not hand-built. Tolera should **buy** the PDF engine and **build** the 3D viewer on the GeometryService tessellation (three.js-class WebGL). Decide the PDF SDK before committing the viewer milestone.

---

## 1. 3D viewer — tools (`3d-viewer-tools`)

| Tool | What it does | v1 dependency |
|---|---|---|
| **Selection** | Click an edge/face to see its geometric properties; annotate the feature/face into the collaboration chat. | GeometryService topology + per-entity props |
| **Measure** | Distance between two features/faces/edges. Behaves like a **caliper** on parallel faces / concentric cylinders; circular entities measure from the **parametric center**. Shows **angle between two selected faces** (bottom-right). | exact-geometry queries |
| **Axis-aligned dimensions** | X/Y/Z extents **as the model was designed/oriented** in 3D space. | bounding query |
| **Optimal bounding box** | Smallest box that fits the active body's geometry (≠ axis-aligned). | OBB compute |
| **Wireframe** | Render the body as wireframe. | tessellation edges |
| **Highlight features** | Make faces/edges from the features + manufacturability analysis more prominent. | interrogation feature → face/edge map |
| **Highlight focused bodies** | Focused bodies solid/opaque; other selected bodies semi-transparent. | assembly/body set |
| **Exploded view** | Expand an assembly in space (keep relative orientation) to see components. | assembly support |
| **Reset view** | Return camera to default. | — |

**v1 note.** Selection / measure / axis dims / bounding box / wireframe / feature-highlight depend only on a single-body tessellation + topology and are **v1** with OCCT. **Exploded view** and **highlight focused bodies** need assembly/body-set handling — gate with assembly support (see `DOMAIN-MODEL.md` Node/Component layers). The measure tool's *exact-vs-approximate* guarantee (below) requires real B-rep queries, not just mesh.

---

## 2. 3D viewer — display options (`part-viewer-display-options`)

Gear icon (top-right of viewer) → popover:

- **Units toggle** imperial ↔ metric: dims/area/volume switch in ↔ mm; **weight** lb ↔ kg. **Tolera default = metric (mm, kg)** — see §6.
- **Native model colors & opacity** toggle: STEP/proprietary files often carry export colors that clash with feature highlights (bends, holes, c'sinks, pockets). Toggle to Tolera's **default model color** for contrast when feature callouts are hard to see.
- **Decimal precision** for measurements/selection data — user-configurable.

**Exact vs approximate measurements.** When measuring between entities with *special* relative orientation — **parallel planes, concentric cylinders, perpendicular cylinder+plane** — the result is mathematically **exact**. Everything else is **approximate**, flagged with a leading **`~`**. Preserve this distinction in Tolera; it's a trust signal for estimators taking critical measurements off the model.

---

## 3. 3D rendering limits (`3D-viewing-limits`)

- **File size:** PP states the **3D viewer supports CAD files up to 250 MB**. *(⚠ The `supported-file-types` article separately says "we do not support files over 150 MB"; the Lens pipeline uses ≤250 MB. **Discrepancy — pick one configurable platform limit and log it in `DECISIONS.md`.** Recommend a single `MAX_UPLOAD_MB` config, default 250, with a soft warning band.)*
- **Vertex budget:** render up to **25 million vertices** concurrently (the triangle-mesh vertices behind visible faces/edges).
- **Collection over budget → blue simplified representations.** When multiple bodies collectively exceed the limit, Tolera replaces the **smallest / least-significant** bodies with bounding-box **blue simplified representations**, shown as **blue cube icons** in the BOM/CAD tree. Temporary + view-dependent: **isolating** a subassembly/body reduces the load and restores hidden bodies.
- **Single body over budget → orange simplified representation.** A single overly-complex body is replaced by an **orange** bounding-box rep (**orange cube icons**). Such a body **also likely exceeds interrogation limits** → **no interrogation feature results** will display for it (ties to `INTERROGATION-ENGINE-SPEC.md` honest-ceiling section).

**Build note.** Implement the vertex-budget tessellation guard + simplified-rep substitution in the viewer/GeometryService boundary; surface the blue/orange tree affordance so users understand *why* a body is boxed and how to restore it.

---

## 4. PDF / print viewer (`pdf-viewer-guide`)

The estimator's print cockpit. Capabilities to ship (group into tabs as PP does):

**View & navigate**
- Layouts: **Continuous page** (scroll as one) / **Page-by-page**; **Single** / **Double** page; **Cover-facing** spread (first page alone on the right — booklet review).
- Rotate **whole document** CW/CCW (single-page rotate via thumbnail panel).
- Move: scroll, or **Pan** mode (hand / `P`).
- Zoom: % field + dropdown, +/− (`Cmd+`/`Cmd-`), **Fit width**, **Fit page**, **Marquee zoom** (`Z`, drag a region).

**Search**
- In-document search (magnifier, top-right); **Case-sensitive** + **Whole-word** toggles; arrow between hits.
- **Global search** in the nav bar searches **all PDFs in the Parts Library** (platform-wide), not just the active doc.

**Pages (thumbnail panel)**
- Multi-select by list (`1,3,5`) or range (`1-5`).
- **Rotate** / **Extract** (download selected pages locally — split a multi-part PDF into one-page-per-part for traceability) / **Delete**.

**Compare PDFs (revision diff)**
- Upload a comparison file; differences are colored: **red = removed**, **blue = added**, **black = identical**. Toggle the comparison overlay (eye icon). The canonical use: a new print revision (e.g. rev B vs rev C) — instantly see an added packaging note or a changed radius. *Pairs with Lens BOM/extraction re-runs on revision.*

**Annotate / Shapes / Measure**
- Annotate: underline (U), highlight (H), rectangle (R), free text (T), free-hand highlight, free-hand (F), note (N), squiggly (G), strikeout (K), eraser (E); Presets for styling; Undo/Redo.
- Shapes: rectangle, freehand, line (L), polyline, arrow (A), arc, ellipse (O), polygon.
- Measure: **distance**, **arc** (length/radius/center-angle), **perimeter**, **area** (custom/circle/rectangle), **count**; **snapping**; Undo/Redo/erase.
  - **Set scale first** — pick a ratio (e.g. 1:2) or **calibrate** from one known dimension on the page (click both ends, type the real length). Accuracy depends on the scale being set.
- **Save annotations** through the **Collaboration** tool → *Add annotation* (threads to the quote's chat; reachable from the Build-a-Quote chat icon).

**Redact**
- Redact **text**, **rectangular sections**, or **entire pages** → saves a **new supporting file** (original retained). Recolor redaction fill/stroke (white-on-white to hide that redaction happened). Share the redacted file (excluding the original) via **External collaboration** by scoping recipient permissions to just the redacted file.

**Tips to preserve**
- Collapsed sidebars **persist** across documents/sessions (more screen for small text).
- **Advanced settings**: download PDF **with annotations**, change **language**, **dark mode**.

**Lens overlay (Tolera).** The PDF viewer is where `ExtractionFinding.bbox` overlays render (purple AI-Governor glow, 55% opacity, explicit accept — `AI-LENS-ENGINE-SPEC.md`), and where "build a rule from this finding" launches (`RULES-ENGINE-SPEC.md`). Found-in-Files whiteout/category isolation lives here too.

---

## 5. Supported file-type matrix (`supported-file-types`)

**Legend:** **V** = viewable, **I** = interrogable (geometry). v1 = supported in pilot given OCCT GeometryService; *later* = target once the format converter / Spatial swap-in lands (`INTERROGATION-ENGINE-SPEC.md`).

| Class | Formats | V | I | v1? |
|---|---|---|---|---|
| **Standard B-rep** | STEP `.step .stp .stpz`; Jupiter Tessellation `.jt` | ✓ | ✓ | **v1** (STEP is the primary recommended format) |
| **Converted B-rep** | Autodesk `.ipt`; ACIS `.sat .sab`; Rhino `.3dm`; CATIA V4 `.exp .model`; CATIA V5 `.catpart .catshape`; Solid Edge `.par .psm`; Parasolid `.x_b .x_t`; SolidWorks `.sldprt`; Creo `.neu .prt`; NX `.prt`; IFC `.ifc` | ✓ | ✓ | partial v1 (depends on converter coverage) |
| **Vector / Print** | AutoCAD `.dxf .dwg`; `.svg`; print `.pdf .tif .tiff .jpeg .png`; Office `.pptx .xlsx .ods .odp .csv .txt`; email `.msg .eml` (+ attachments parsed); + long legacy office list | ✓ (print) | sheet-metal only via **DXF/DWG/vectorized PDF** | **v1** for print viewing + Lens; DXF/DWG sheet-metal interrogation later |
| **Mesh** | `.stl .3mf`; 3D PDF; Autodesk `.3ds .dwf .dwfx`; CATIA V5 `.cgr`; CATIA V6 `.3dxml`; COLLADA `.dae`; `.glb`; `.fbx`; OBJ `.obj`; `.prc`; VRML `.vrml .wrl` | ✓ | mesh-limited (no B-rep features) | v1 view; interrogation limited |
| **Pack-and-go (ZIP)** | SLDPRT+SLDASM / PRT+ASM / catpart+catproduct / ipt+iam | ✓ | ✓ | later (assembly) |

**Interrogation-supported set (explicit):** `exp, step, stp, sldprt, iges, igs, ifc, catpart, catshape, cgr, 3dm, x_b, x_t, ipt, jt, model, neu, prt, psm, sab, sat, par, stpz`.

**Key behaviors to replicate:**
- **Pack-and-go:** the assembly file (SLDASM/ASM/catproduct/IAM) is the *instructions*; the part files (SLDPRT/PRT/catpart/IPT) hold the geometry — **both required**, zipped together, else "unable to display". Support drag-drop of **entire nested folders** (auto-parse out files).
- **IGS/non-solid/Spline "healing":** IGS (and any non-solid/Spline-face file) is minorly **healed** before interrogation (equivalent to a STEP conversion); surface a **"Resolved error"** warning; downloading a Resolved-error file returns the **original unmodified** file.
- **Best results:** STEP + native CAD maximize geometric analysis. Unsupported formats can be uploaded but won't render.
- **Sheet-metal-from-vector:** DXF/DWG/vectorized-PDF feed sheet-metal interrogation; PP exposes a **PDF Vectorization** feature (PDF → DXF). Tolera: needed for shops that quote flat patterns from prints.

---

## 6. DACH adaptations (vs PP defaults)

- **Metric-native default.** Viewer opens in **mm / kg / deg**; comma-decimal display per `de-DE`/`de-CH`/`de-AT` locale (`1.234,56`; CH `1'234.56`). Keep the unit toggle but never default to imperial — PP converts metric→imperial; Tolera **drops the imperial-first path** (`DACH-DELTA-LAYER.md`).
- **ISO GPS** symbology in feature/GD&T highlighting and in any measurement annotations surfaced from Lens.
- **i18n:** PDF viewer language = German by default (PP exposes a viewer language setting); units/precision presets seeded per region.
- **GDPR/redaction:** redaction → new supporting file + scoped external-collaboration sharing is the mechanism for sending prints to vendors without leaking PII/IP; align with the GDPR handling in the Lens spec (PII detection on ingest).

---

## 7. Acceptance criteria

- **3D tools:** selection shows entity props; measure returns **exact** results (no `~`) on parallel-plane / concentric-cylinder / perpendicular cylinder-plane pairs and **`~`** otherwise; axis dims + OBB + wireframe + feature-highlight render; exploded/focused-body views work on an assembly fixture.
- **Display:** unit toggle flips dims/area/volume/weight; native-color toggle restores feature contrast; decimal precision applies live; **default state = metric**.
- **Limits:** a >budget multi-body file substitutes **blue** boxes (tree icons) and restores on isolate; an over-budget single body shows an **orange** box and suppresses its interrogation results; the platform enforces one configured size limit (discrepancy resolved + logged).
- **PDF:** continuous/spread layouts, search (+ case/whole-word), global Parts-Library search, page extract/rotate/delete, **revision compare** (red/blue/black), annotate/shapes, measure with scale-set/calibrate, save-to-collaboration, redact-to-supporting-file with scoped share, download-with-annotations, dark mode.
- **File types:** every **interrogation-supported** extension ingests + interrogates (within v1 converter coverage); pack-and-go ZIP requires both files; IGS upload raises a Resolved-error warning and download returns the original; unsupported format uploads but does not render.
- **Lens overlay:** `bbox` findings render as purple 55%-opacity overlays in the PDF viewer with explicit accept; "build a rule from finding" launches the rules builder.

**Sources:** `3d-viewer-tools`, `part-viewer-display-options`, `3D-viewing-limits`, `pdf-viewer-guide`, `supported-file-types` (in `paperless-parts-kb-reference/`); cross-refs `INTERROGATION-ENGINE-SPEC.md`, `AI-LENS-ENGINE-SPEC.md`, `RULES-ENGINE-SPEC.md`, `DOMAIN-MODEL.md`, `DACH-DELTA-LAYER.md`, `DECISIONS.md`.
