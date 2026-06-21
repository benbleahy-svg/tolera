# AI Extraction & Email Ingest Engine ("Lens") — Sub-Spec

**Status:** Engine sub-spec for Tolera (Bid Factory). The **third hard subsystem** (alongside `INTERROGATION-ENGINE-SPEC.md` for geometry and `PRICING-ENGINE-SPEC.md` for Kalk). **Provenance:** `Found-in-files-extractions`, `PDF-Extraction-Beta`, `PDF-file-processing` (+ spec's "Lens" section). Closes Gap-Audit §4 ("outputs specified, system unspecified"). **Lens** = Tolera's AI layer; **purple signal / AI Governor** UI (55% opacity until accepted) per `DECISIONS.md`.

> **Boundary vs the geometry engine:** Lens reads **2D prints, PDFs, emails, and file metadata** (text + vision AI). The **GeometryService** reads **3D solid bodies** (and MBD/PMI). They are different engines; Lens does **not** parse DXF/DWG GD&T or MBD/PMI (those go to geometry). Both feed the part + Review layer.

---

## 1. What Lens does (four pipelines)

1. **File processing pipeline** (every uploaded file).
2. **Email / RFQ ingest** (inbound RFQ emails → Quote).
3. **Document extraction** ("Found in Files" — part-setup + requirements).
4. **BOM detection & assembly building** (BOM tables → BomNode tree).

Lens outputs are **suggestions**, surfaced via the AI-Governor pattern (purple, 55% opacity, explicit Accept). They feed: part-field suggestions, the Found-in-Files panel, the **Rules/Review** layer (each finding can seed a rule), and the viewer overlay. **Lens output is NOT fed directly into Kalk costing** (matches PP) — it informs the human + rules, which drive routing/manual inputs.

---

## 2. File processing pipeline (`PDF-file-processing`)

Ordered stages with explicit failure handling (spec each as a job step):
1. **Upload** — ≤ **250 MB**; drag-drop / click / API; to part library, quote sidebar, child components, or supporting files. Fail → stop (no processing).
2. **Virus scan** — malware → block download + prompt delete (part/line item may still be created).
3. **Unlock** — password-protected PDF → require password, then re-upload + re-scan.
4. **PDFs-as-ZIP unpack** — OEM "PDF that is really a ZIP" (PDF + STEP242 + HTML…) → extract siblings to the same file location.
5. **3D-PDF model extraction** — extract embedded model → **STL (+ PMI)** for rendering; if uploaded as a part's primary, the **STL becomes primary** and the PDF moves to supporting. (Distinct from #4.)
6. **Scanned-PDF OCR** — no text layer → OCR to make text selectable/extractable.
7. **Print content analysis** — text-search + vision AI → **part-field suggestions** + **extractions** (§4).

## 3. Email / RFQ ingest (Lens pipeline 1)

Inbound to **`{org-slug}@rfq.tolera.eu`** (Mailgun EU; pilot slug `fechner`, per `DECISIONS.md`):
- Parse sender, subject, body, **attachments incl. ZIPs** (→ file pipeline §2).
- Match sender email → **Contact** (+ Account); else create (or hold for review).
- Create **Quote** (from RequestForQuote), set `manual_rfq_received_date`, attach files, kick off extraction + interrogation.
- **Two-way threading** (spec's net-new) — keep `email_thread_id` on the quote; replies thread back. Fallback when no mailbox connected: forward-to-ingest address.
- LLM body parse → suggested contact/part/quantity/requested-date (AI Governor).

## 4. Document extraction — "Found in Files" (`Found-in-files-extractions`)

Runs on **PDF/TIFF prints, first 10 pages**. **Two passes:**
- **Quote-setup pass (whole file, on upload):** part number, revision, description, drawing number, **document units** (sets default in/**mm**), tables, **BOM tables**, **export-controlled** (keyword detect), **PII**.
- **Requirements pass (per page, only pages classified "print"):** the full taxonomy below. Purple glow/spinner while running. Tolerances detected as **unilateral / bilateral / limit**; units fall back to document default.

**Extraction taxonomy → `ExtractionFinding` (5 categories):**

| Category | Findings |
|---|---|
| **Quote setup** | part_number, revision, description, drawing_number, document_units, tables, bom_tables, export_controlled, pii |
| **Requirements** | process_keywords (heat-treat, anodize, passivate, weld, deburr, grind, etch, powder-coat, …), material (print text or CAD metadata keys), specifications (AMS/ASTM/MIL/NADCAP + OEM list), global_tolerances, flag_notes |
| **Features** | hole (Ø, depth, tol, thread), thread (class, Ø, hand, pitch, depth), countersink (Ø, depth, angle), counterbore (Ø, depth), control_frame (type, value, datum refs, material condition; incl. stacked), datum, chamfer (L1, L2, angle), surface_finish (class, removal type), bend_lines (direction, angle, internal radius), welds |
| **Dimensions & tolerances** | length, diameter, radius, angle — each with value, tolerance, **role** (basic / critical-to-quality / reference), indicators (STOCK, TYP) |
| **Regions** | title_block, notes_list, section_view_caption, profile_view_caption, 2d_view, 3d_view (hidden by default; spotlightable) |

**Actions on findings:** apply part#/rev/desc; set X/Y/Z from dims (no model); copy text/GD&T symbols; **mark inaccurate / replace** (training, §7); **build a Review rule** from the finding (§ Rules). Whiteout toggles to isolate categories.

## 5. BOM detection & assembly building

BOM tables (from prints/spreadsheets) → normalized BOM → **BomNode tree** (DOMAIN-MODEL §1). "Drag-to-detect" correction for missed/wrong tables. Feeds the BOM Builder (split PDF → detect → extract → child BOMs → publish).

## 6. Models, providers & routing (Gap-Audit §4)

- **v1 = vision-LLM pipeline, not a trained custom model.** Per-task model assignment:
  | Task | Approach |
  |---|---|
  | Is-this-a-print classification | vision LLM (cheap/fast) |
  | Part-field extraction (part#/rev/desc/material/units) | vision LLM + text search |
  | Table / BOM-table detection | layout model + LLM |
  | GD&T / callout OCR (control frames, dims, tolerances) | vision LLM (ISO GPS-aware) |
  | Email body parse | text LLM |
- **EU/GDPR routing** (resolve the audit's CUI-vs-cloud conflict): default = EU-region LLM under a **DPA/AVV**, no training on customer data. **Export-control / sensitive parts** (dual-use flag, §DACH) → a restricted path: either a no-external-LLM mode or explicit per-org opt-in; **never** send flagged files to a non-DPA endpoint. Make the provider + region **configurable** (`{ai-settings}` master + per-feature toggles + data/privacy).

## 7. Confidence, accuracy targets & training loop

- **Per-finding confidence**; below threshold → suggestion only (AI Governor 55% opacity, explicit Accept). Never auto-apply to costing.
- **Hard constraint (from PP):** the model may pick a *wrong existing string* but must **never hallucinate** a value not on the print.
- **v1 accuracy targets** (seed from PartBot's published behavior — calibrate against Fechner fixtures): print-classification ≈ 95%; field **recall** ≈ 65% (≤35% "field present but missed"); field **precision** ≈ 85% (≤15% wrong-but-real). Track per category.
- **Training feedback loop:** `mark_inaccurate` / `replace` / user fills a different value → persist `{finding, predicted, corrected, tenant, file_ref}`. Use for (a) **eval set** (regression), (b) **few-shot / prompt tuning**, (c) optional per-tenant correction memory. **Decide storage scope:** per-tenant by default; global only on opt-in/anonymized (log in `DECISIONS.md`).

## 8. Output contract — `ExtractionFinding`

```
ExtractionFinding {
  id, component_id, source_file_id, page,
  category: quote_setup|requirements|features|dimensions|regions,
  type: 'hole'|'control_frame'|'material'|'part_number'|...,
  raw_text, value, normalized_value, units,            # mm default (DACH)
  tolerance?: { kind: unilateral|bilateral|limit, upper, lower },
  role?: basic|critical_to_quality|reference,
  bbox/geometry_ref,                                   # for viewer overlay
  confidence: float,
  status: suggested|accepted|rejected|edited,
  gdt?: { symbol(ISO GPS), datum_refs[], material_condition }
}
```
Consumers: part-field suggestions, Found-in-Files panel, **Rules/Review signals**, viewer overlay. (Not Kalk.)

## 9. Scope & limits (state honestly)

- PDF/TIFF **prints, first 10 pages**; **digital** prints (OCR for scanned); **single part per print** (no multi-part field sets).
- **Not** DXF/DWG-with-GD&T, **not** MBD/PMI/3D-PDF annotations (→ geometry engine).
- v1 surface: part-setup suggestions (part#/rev/desc/material/units/dims) + export-control + PII + BOM-table detect + the requirements panel; deepen the full GD&T taxonomy progressively.

## 10. Acceptance criteria

- Per-fixture **golden extractions**: *this print → part# X, rev Y, material (DIN) Z, units mm, N holes with tolerances, M control frames*; assert category/type/value/tolerance/role + confidence calibration.
- **Never-hallucinate** test (no value absent from the print).
- **EU-routing** test (flagged dual-use file never leaves the DPA region).
- Email-ingest test: `.eml` + ZIP attachments → Quote + Contact + files + extraction triggered (bind to the Fechner `.eml` fixture).
- **DACH:** German title-block/keywords recognized; **ISO GPS** GD&T; mm units; export-control reframed as **dual-use**; PII handled under GDPR.

**Sources:** `Found-in-files-extractions`, `PDF-Extraction-Beta`, `PDF-file-processing`, `expanded-file-interrogation-support`, `requirements-review`, `building-review-rules` (all in `paperless-parts-kb-reference/`).
