# UI Comparison — Tolera vs. Demo/KB Reference Frames · 2026-07-19

Screen-by-screen comparison of the live app (localhost, working tree at PR #84 + reskin) against the reference frames in `docs/reference/kb/screenshots/`. Skin is the adopted **Ruhig (Attio-quiet)** — so *colour/spacing follow our tokens deliberately; structure follows the frames*. "Fixed today" = applied by hand in this session (CSS-only, live-verified in Chrome). "Owner" = the chartered pipeline block for what CSS can't do.

| Screen | Reference frame | Verdict | Fixed today | Remaining (owner) |
|---|---|---|---|---|
| **Quotes list** | DemoB/02 | **Close match.** Saved-views sidebar with grouped views, status filter, table columns (Quote/RFQ#/Status/Priority/Account/Salesperson/Created), Draft pill, pager — all present. | — (already correct after reskin) | Filter-chip row instead of the bare status dropdown; per-row "Fwd:" subtitle + line-item progress; view search + pin (M6.9d) |
| **Estimating — costing band + sections** | DemoA/06 lower half, DemoB/15 | **Close match.** Process/Material/Finishes band, Materials + Operations with Setup/Run/qty columns, summaries, Yield, Make Quantity, Review Items, NO-RATE guard. | Card sections, muted uppercase table headers, quiet indigo add-buttons, primary Send quote, **calc-values render accent-blue vs bold overrides (the PP convention)**, ADD LINE ITEM pill | The whole **upper half** — part card, geometry readout, files strip, Pricing & Quantities at top, Status & Workflow steps, Notes (**M6.9c**) |
| **Estimating — Costing/Pricing** | DemoB/16 | **Close match.** Category chips (MATERIAL/INSIDE/OUTSIDE/PURCHASED), cost rows, pricing items with % + €, Total/Unit price. | Same table/card treatment; calc-blue convention | Components FLAT/CHILD BOM toggle styling detail (M6.9d) |
| **Add-ons / Lead times** | DemoB/17 | **Match** (sections exist with same rows). | Card treatment via shared section chrome | — |
| **CAD viewer** | DemoB/10 | **Was the worst screen — now structurally right.** Model renders with orientation cube + geometry readout (verified: 80×50×20 fixture reads correctly). The collaboration panel had **no stylesheet at all** (M2.11 shipped unstyled — root cause of the floating chat elements). | **New `collab.css`**: right-hand panel column, channel pills, message cards, composer pinned bottom, assignee popover | Part-Setup panel on the CAD side + remaining M2.10 fields (**M6.9c**); mention-popover show/hide logic is component behaviour (M6.9d) |
| **Print/PDF viewer + Part Setup** | DemoC/02 | **Partial.** Panel exists (Part fields + Found in files tabs, whiteout, chips) but slim — identity + X/Y/Z only. | Panel inherits reskin tokens | Processes/Specs/Material/Features/NUM-REV fields (**M6.9c**, folds in skipped M2.10) |
| **Dashboard** | DemoA/03 | **Intentionally different** — M6.1 redesigned this (work queue + KPI row + recents supersede the classic Workflows table, which lives on as a saved view). Right elements present. | KPI row → proper stat tiles (bordered cards, big tabular numerals) | Notifications feed richness needs data; queue rows appear with seeded data |
| **Part Library** | DemoB/09 | **Match** (Team/Shared/Archived tabs, search, upload, cards). Match-category buckets appear when matches exist (M2.12 logic present). | — | Thumbnails need geometry-derived previews (M6.9d polish) |
| **Orders** | (orders frames) | **Match** — tabs (All/Buyer Portal/Facilitated/Awaiting Shipment), search + date + customer filters. | — | — |
| **Suppliers** | M6.3 frames | **Match** — directory + filters + Add vendor; built post-path-fix so it was born closer to the frames. | — | — |
| **Configure** | PP Configure | **Functional, plainer than PP.** Sub-nav now reads as a proper tab bar. | Tab bar with active underline + alignment | Deeper Configure IA (left sub-nav, per-section polish) → M6.9d |

## The three systemic fixes behind most of this

1. **`collab.css` did not exist** — the M2.11 collaboration panel had zero styles, which wrecked the whole viewer layout. Written today.
2. **Alias tokens** (`--muted`, `--accent`, `--surface-hover`, …) — blind-built blocks referenced token names that were never defined, so browsers rendered their random fallback colours. Bound to the palette yesterday; every screen inherits.
3. **Native-control baseline** — buttons/inputs on screens that never adopted `.btn` classes now default to the quiet look.

## What CSS cannot fix (already chartered, in queue order)

**M6.6** Vendor Quotes panel (skipped block — M6.7c depends on it) → **M6.9b** test-seed endpoint (arms the demo replay) → **M6.9c** part-view upper half + M2.10 remainder → **M6.9d** full demo-fidelity sweep with before/after screenshots per screen. Plus the other skipped blocks from the gap audit (M3.12, M4.7b/9b/10b, M5.10–12).

**Data note:** every comparison above was made against a nearly-empty database. The frames show a shop full of quotes; run `scripts/checkpoint.sh M6` (seeds + boots + click-guide) to compare like-for-like.
