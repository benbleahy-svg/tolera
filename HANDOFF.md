# HANDOFF — M2.4 PDF redaction + whiteout + supporting-file generation

## Block & branch
- **Block:** M2.4 — PDF redaction + whiteout + supporting-file generation (`build-plan/M2-files-viewers.md`).
- **Branch:** `feature/m2.4-pdf-redaction` (off `develop`; base develop tip is the M2.3 merge `badb1b1`).
- **Issue/PR:** none opened yet — `/ship` opens the PR at the end.
- **Deps (both merged to develop):** M2.1 (PDF viewer core, PR #26), M1.2 (supporting-file storage).

## State
**Done + proven (committed WIP):**
- **Backend — complete & green.** `POST /api/parts/{part_id}/files/{file_id}/redacted-copy`
  in `app/parts.py`: accepts the viewer-rendered redacted PDF as multipart, stores it as a
  **SUPPORTING** file named `<stem>-redacted.pdf`, flags it `is_redacted=True`, never touches
  the source blob or the PRIMARY assignment; validates PDF magic + size cap; cleans up the blob
  on failure. Tests in `tests/test_annotations_m22.py` (`test_redacted_copy_is_a_new_supporting_file`,
  `test_redacted_copy_validates_pdf`) — **7 passed** against Postgres
  (`TEST_DATABASE_URL=postgresql+asyncpg://tolera:tolera@localhost:5432/tolera_test`).
  ruff + mypy clean on `app/parts.py`. No new migration (reused `part_file`/`is_redacted` from M1.2).
- **Frontend model — only `redact.ts` written & typechecks (`tsc -b` = 0, NO tests yet):**
  - `frontend/src/viewer/redact.ts` — `Redaction`/`WhiteoutSection` types, `buildRedactionPlan`
    (solid pages / raster pages / untouched), `redactedFilename`, `REDACTION_PRESETS`
    (schwarz + weiss white-on-white). Compiles standalone; not imported anywhere yet.
  - **`renderRedactedCopy` in `pdf.ts` is NOT written yet** (its edit was blocked and never ran —
    `pdf.ts` is unchanged from HEAD). It is the first sub-step of Next step below; the intended
    shape is spelled out there.

**In progress / untouched (the remaining M2.4 work):**
- No redact **toolbar + overlay** in `PdfViewerPage.tsx` yet (draw redaction regions / mark whole
  page / recolour fill / Whiteout mode + spotlight-one-callout).
- No `parts/api.ts` client method to POST the redacted copy (build a `File`/FormData from the
  `renderRedactedCopy` bytes → `apiUpload`).
- No frontend tests for redact.ts / the overlay / the save flow.
- **Whiteout + spotlight** (session view-state that clears callout clutter, spotlight one) — modelled
  in `redact.ts` (`WhiteoutSection`) but no UI/behaviour built.

## Next step
1. **Write `renderRedactedCopy(bytes, doc, redactions)` in `pdf.ts`** (blocked last session; `redact.ts`
   already exports `buildRedactionPlan` for it). Intended shape: load the source with pdf-lib, walk
   pages using the plan — untouched pages `copyPages` vector-identical; fully-redacted (`solidPages`)
   become a new blank page with a solid `drawRectangle` fill; region-redacted (`rasterPages`) are
   RASTERIZED — `doc.renderPagePixels(page, 2)` → canvas → `context.fillRect` each region (× renderScale)
   → `canvas.toDataURL('image/png')` → `target.embedPng` → `drawImage` full-page. Return `target.save()`.
   (This is what makes redacted content irrecoverable — see Gotchas.)
2. Wire the redact UI in `PdfViewerPage.tsx`: a redact toolbar row (region / whole-page / fill-colour
   presets + Whiteout toggle + spotlight), a `RedactOverlay` sibling of
   `AnnotationOverlay`/`MeasureOverlay` (reuse the `pointer-events: none` when-inactive contract —
   see Gotchas; selecting a redact tool clears `tool` + `measureTool`), and a **"Geschwärzte Kopie
   speichern"** action → `renderRedactedCopy` → new `parts/api.ts` `saveRedactedCopy(partId, fileId, bytes)`
   (build a `File`/FormData, `apiUpload` to the endpoint) → refresh the file list.
3. Frontend tests: `buildRedactionPlan` page buckets; an overlay drag → region → save flow
   (mock `renderRedactedCopy` + the api like `viewer.test.tsx` does).
Backend + its tests are already done and green — do **not** rebuild them.

## Sources loaded (load only these next session)
- Spec anchors: `#pdf-capabilities` (Redact bullet), `#collab` (PDF redaction → exact redacted copy).
- Folded sub-spec: `docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md` §4 Redact + §6 (GDPR redaction → new file).
- KB slugs: `pdf-viewer-guide`, `swap-primary-and-supporting-files`.
- Code already in place to build on: `frontend/src/viewer/{redact.ts,pdf.ts,PdfViewerPage.tsx,AnnotationOverlay.tsx,MeasureOverlay.tsx}`, `app/parts.py` (the endpoint), `frontend/src/parts/api.ts`.

## Gotchas
- **Overlay stacking (from M2.3, load-bearing):** stacked full-page `<svg class="pdf-annotation-overlay">`
  layers must keep `.pdf-annotation-overlay:not([data-active]) { pointer-events: none }` — otherwise an
  idle top overlay swallows the gestures of the layer beneath (a real browser-only bug jsdom can't catch).
  The new RedactOverlay must follow the same active-only-hit-testing contract, and only one tool
  (annotate / measure / redact) is active at a time — selecting a redact tool must clear `tool` and
  `measureTool` (mirror how measure clears annotate).
- **Redaction must rasterize, not overlay.** A black `<rect>` over text leaves the text extractable —
  the M2 exit check asserts the redacted text is **absent from the new file's extracted text**. That's
  why `renderRedactedCopy` renders affected pages to PNG. Keep it that way.
- **Rotation gating:** markup/measure input is blocked while a page rotation is applied (coords are
  unrotated page-space); redaction regions must do the same.
- **Coordinates:** overlays store scale-1 pdf.js viewport coordinates (top-left origin, y down); the
  `<g transform={scale(zoom)}>` handles display. `renderRedactedCopy` fills canvas regions at
  `renderScale=2`, so multiply region coords by `renderScale` (already done).
- **Test DB:** the local Postgres is up; new migrations need a fresh `tolera_test` (none this block).
  Node 26 locally lacks Web Storage — `src/test/setup.ts` polyfills `localStorage` (already in place).
- **Repo junk:** `clerk-nextjs/` and various `"* 2.*"` Finder-duplicate files are untracked noise —
  do not stage them (the `/ship` cleanup ignores them).

## OPEN candidates
- None that are irreversible. The rasterization fidelity knob (`renderScale=2`) and the two
  fill presets (schwarz/weiss) are reversible UI choices; no `DECISIONS.md` entry needed.
  (If Whiteout/spotlight turns out to need persistence beyond the session, that would be an
  OPEN for M2.11 collaboration — not this block.)
