# Demo Traceability — the acceptance oracle, mapped to blocks

**What this is.** The fourteen demo recordings ([#demos](../docs/spec/Bid-Factory-Build-Spec.html#demos)) are the product's **acceptance oracle** — together they define the build scope, and "all 14 replayable on fixtures/seeds" is the **M6 exit criterion**. This file is the connective tissue: each demo → the blocks that implement it → the `DemoX` screenshots that show it → the fixture that replays it.

**A demo lives in three coordinated views — never copied (DRY):**

1. **Narrative** — [#demos](../docs/spec/Bid-Factory-Build-Spec.html#demos) (overview) + [#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance) (Demo A–E step scripts): *what the flow is.* Authoritative (tier-2). Read it; don't restate it in code or here.
2. **Traceability** — *this file*: which blocks realize each demo step, and where the visual truth lives.
3. **Fixture / golden test** — the machine-checkable replay (`docs/fixtures/`, the M1.13 harness): *proof.* Demos A–E have exact figures; breadth demos assert their key behaviours.

**How Claude Code uses it (per the build-time protocol in `CLAUDE.md` / `README.md` §1):** when a block lists a demo here, load that demo's **narrative** ([#demos]/[#acceptance]) and its **`DemoX/` screenshots** — the screenshots are the **UI ground truth** (pixel layout, control placement, copy). The [Screenshot Index](../docs/spec/Bid-Factory-Build-Spec.html#screenshots-index) + [Screenshot-Mapping.md](../docs/reference/Screenshot-Mapping.md) give the file-level map (154 images under [`../docs/reference/kb/screenshots/DemoA…O/`](../docs/reference/kb/screenshots/)). Build to the screenshot; verify against the fixture.

> **Screenshots are tier-4 reference for *layout/behaviour*, not binding requirements** — where a screenshot shows US/imperial/ITAR/QuickBooks, the **DACH delta wins** (metric, EUR/CHF + MwSt, DIN/EN, dual-use). The spec text + `DECISIONS.md` outrank a pixel.

---

## Master matrix

| Demo | Title | First fully replayable | Primary milestones | Screenshots | Replay fixture / exit |
|---|---|---|---|---|---|
| **A** | Precision Cut + Global Shop ERP | **M4** | M4 · M1 · M2 · M6 | `DemoA/` | M4: assembly PDF → BOM → nest → cost rollup |
| **B** | Arch Medial Solutions | **M5** | M3 · M2 · M4 · M1 · M5 | `DemoB/` | M5: RFQ email → quote → … → Build Order |
| **C** | Requirements Review | **M3** | M2 · M3 · M1 | `DemoC/` | M3 exit: rule library works end-to-end |
| **D** | Meet the BOM Builder | **M4** | M2 · M3 · M4 | `DemoD/` | M4: split → detect → publish multi-level BOM |
| **E** | Custom Markups & Margins | **M1** | M1 | `DemoE/` | **M1.13: all six figures incl. $2,160.84** |
| **F** | Free Part Viewer / Collab / Sourcing | **M6** | M2 · M6 | `DemoF/` | M6: vendor RFQ round-trip |
| **G** | Costing Templates & Dynamic Routing | **M4** | M1 · M4 | `DemoG/` | M4: auto-routing generates the router |
| **H** | 2025 "Hidden Gems" Roundup | *progressive* | M1 · M2 · M5 | `DemoH/` | per-feature (no single fixture) |
| **I** | Sheet Metal Fabricators (overview) | **M4** | M4 · M1 (→M5) | `DemoI/` | M4: sheet-metal interrogate → nest → cost |
| **J** | Nesting deep-dive | **M4** | M4 | `DemoJ/` | M4 exit: nest math = hand-calc |
| **K** | CNC Machine Shops (overview) | **M5** | M4 · M1 · M5 | `DemoK/` | M5: milling quote → order |
| **L** | Real-time Purchased Components | **M6** | M4 · M6 | `DemoL/` | M6: Würth adapter live pricing |
| **M** | Assembly Table Updates | **M4** | M4 | `DemoM/` | M4: bulk-edit components + table ops |
| **N** | Geometric Feature Overview (no CAD license) | **M4** *(Core-4 full; lathe/wire-EDM attrs-only per OCCT ceiling)* | M4 | `DemoN/` | M4: per-family interrogation goldens |
| **O** | Quoting Assemblies | **M4** | M4 · M1 · M2 | `DemoO/` | M4: assembly root → child BOM → rollup |

**Progression sanity-check:** E→M1, C→M3, {A,D,G,I,J,M,N,O}→M4, {B,K}→M5, {F,L}→M6. This validates the milestone ordering — the demos light up in dependency order, and **M6.10 replays all 14** as the pilot's definition of done.

---

## Per-demo detail

### Demo A — Precision Cut + Global Shop ERP  ·  [#demos](../docs/spec/Bid-Factory-Build-Spec.html#demos) · [#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance)
Large multi-level server-rack assembly (47/1000 unique parts); BOM Builder; sheet-metal interrogation + nesting across line items; DTMA markup + inside/outside margins; expedite; ERP item codes per stock sheet; Workflow header.
- **Blocks:** M4.9 (BOM Builder) · M4.2 (sheet-metal interrogation) · M4.3 (nesting + ERP stock code) · M4.10 (bulk-edit components) · M1.10 (costing/pricing rollup) · M1.6 (multi-qty) · M1.11 (expedite) · M1.4 (Workflow header) · M2.1 (PDF viewer) · M3.8 (review items) · M6.8 (ERP push stub).
- **Screenshots:** [`DemoA/`](../docs/reference/kb/screenshots/DemoA/) (dashboard, quote detail, BOM builder, sheet-metal interrogation, PDF+AI review, multi-qty pricing, nesting config/overview, bulk-edit, costing summary, quote general).
- **Replay:** M4 sheet-metal + assembly fixture → BOM published, nest math, cost rollup vs golden.

### Demo B — Arch Medial Solutions  ·  [#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance)
End-to-end RFQ-email-to-order: auto-created quote, Bulk Create, auto Review Items (7 parts), Part Library match, assembly BOM, 3D viewer + feature recognition, face annotation + chat, Create Rule, CNC ops per qty, layered margins, add-ons (FAI) + lead times, Build Order checkout.
- **Blocks:** M3.3 (email→quote) · M3.4 (bulk create) · M3.8 (review items + Create Rule) · M3.6 (rule schema) · M2.12 (part library match) · M2.6/M2.7 (3D viewer + face pick) · M2.11 (face annotation + chat) · M4.4 (feature recognition) · M4.9/M4.10 (assembly BOM) · M1.7 (CNC ops) · M1.10 (layered pricing) · M1.11 (FAI add-on + lead times) · **M5.2 (Build Order checkout)**.
- **Screenshots:** [`DemoB/`](../docs/reference/kb/screenshots/DemoB/) (quotes list/saved views, workflow tracker, bulk-create modal, review-items sidebar, assembly/child BOM, part detail + geometry, part library, CAD viewer + part-setup, face annotation + chat, geometric features, feature highlighting, create-rule, operations costing, costing/pricing, add-ons, build order, shipping & payment).
- **Replay:** M5 — the fixture `.eml` carries the whole spine to a PO order; this is the golden thread made fully real.

### Demo C — Requirements Review  ·  [#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance) · [#rules](../docs/spec/Bid-Factory-Build-Spec.html#rules)
Part Setup panel; GD&T/callout extraction + plain-language popovers; Whiteout + spotlight; Add Missing Extraction + Mark inaccurate (training loop); units detection; full Create Rule dialog (signal chips, path picker, ADD FILTER/COUNT, AND/OR, stacked resolutions, assignee, live preview); cascading signal tree; quote-level SET ALL; router ops after Machining→Milling→5-axis.
- **Blocks:** M2.10 (Part Setup panel) · M2.4 (whiteout/spotlight) · M3.1 (GD&T extraction + popovers + units) · M3.2 (Found-in-Files + Add Missing/Mark inaccurate) · M3.6 (signal AST + tree) · M3.7 (evaluator) · M3.8 (Create Rule + Review panel + SET ALL) · M1.7 + M4.10 (set process → add router ops).
- **Screenshots:** [`DemoC/`](../docs/reference/kb/screenshots/DemoC/) (part setup, print viewer + extractions, callout popover, whiteout, add-missing modal, create-rule empty/filled, resolution dropdown, signal tree, line-item review panel, quote-level summary).
- **Replay:** M3 exit — the Demo C rule library works end-to-end (needs M2 viewer green).

### Demo D — Meet the BOM Builder  ·  [#bombuilder](../docs/spec/Bid-Factory-Build-Spec.html#bombuilder)
Split PDF (progress/success toasts, original retained); Lens BOM badges; assign parent → root line item; BOM Builder modal pre-populated; Add Files title-block matching; child BOM expansion (10→25→43); purchased auto-match; Check & Publish.
- **Blocks:** M2.5 (Split PDF) · M3.1 (Lens BOM-table detection/badges) · M4.9 (BOM Builder modal → child BOMs → publish).
- **Screenshots:** [`DemoD/`](../docs/reference/kb/screenshots/DemoD/) (assembly drawing, actions dropdown, split toasts, files after split, BOM builder loaded/add-files/subassemblies, complete 43 parts, published BOM line item).
- **Replay:** M4 — assembly PDF → published multi-level BomNodes; unique-parts counter climbs.

### Demo E — Custom Markups & Margins  ·  [#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance) · [#costing](../docs/spec/Bid-Factory-Build-Spec.html#costing) · [#kalk](../docs/spec/Bid-Factory-Build-Spec.html#kalk)
New Pricing Item (Calc Type + cost category + colour); custom category via Kalk (`get_components` → `set_custom_cost`); markup applied to only that category's cost; the **six worked examples**; discounts; complexity-driven (PartLevel op, L3→L2 changes 30%→20%).
- **Blocks:** M1.9 (Kalk variable system + pricing context) · M1.10 (pricing items + custom category + markup/margin/target-margin + discounts) · M1.13 (golden harness reproduces the six) · M4.10 (complexity op via auto-routing, for the live example) · M6.10/M5 (Excel export).
- **Screenshots:** [`DemoE/`](../docs/reference/kb/screenshots/DemoE/) (pricing-today slide, custom-markups overview, P3L how-it-works, demo quote, examples 1–6 costing/pricing, configure pricing/processes).
- **Replay:** **M1.13 — reproduces all six figures exactly (incl. Difficult-Material $2,160.84). The M1 exit.**

### Demo F — Free Part Viewer, Collaboration & Sourcing  ·  [#collab](../docs/spec/Bid-Factory-Build-Spec.html#collab) · [#vendor-rfq](../docs/spec/Bid-Factory-Build-Spec.html#vendor-rfq)
Free part viewer (no CAD license); internal/external collaboration; outside-process sourcing.
- **Blocks:** M2.6–M2.9 (3D viewer) · M2.11 (collaboration: chat/annotations/tasks) · M6.2–M6.6 (Vendor RFQ portal + library + send + ingest + apply).
- **Screenshots:** [`DemoF/`](../docs/reference/kb/screenshots/DemoF/).
- **Replay:** M6 — vendor RFQ outbound → portal/email response → apply to outside-service cost.

### Demo G — Costing Templates (Processes) & Dynamic Routing  ·  [#oplibrary](../docs/spec/Bid-Factory-Build-Spec.html#oplibrary)
Process/router templates as costing templates; dynamic (auto) routing generating operations from geometry.
- **Blocks:** M1.12 (seed Core-4 processes + routers) · M1.7 (operations) · M4.10 (auto-routing / operation-generation Kalk context).
- **Screenshots:** [`DemoG/`](../docs/reference/kb/screenshots/DemoG/).
- **Replay:** M4 — fixture part auto-routes to the expected operation set.

### Demo H — 2025 "Hidden Gems" Roundup  ·  [#partview](../docs/spec/Bid-Factory-Build-Spec.html#partview)
A grab-bag of smaller features (e.g. Edit Dimensions click-to-set + math/unit inputs — `SS DemoH 06/07`).
- **Blocks:** M1.5 (Edit Dimensions: math expressions + typed units) + the individual gem's owning block (spread across M1/M2/M5).
- **Screenshots:** [`DemoH/`](../docs/reference/kb/screenshots/DemoH/).
- **Replay:** progressive — each gem is verified in its owning block; no single fixture.

### Demo I — Bid Factory for Sheet Metal Fabricators  ·  [#sheetmetal](../docs/spec/Bid-Factory-Build-Spec.html#sheetmetal)
End-to-end sheet-metal: interrogation → nesting → DFM → cost → quote.
- **Blocks:** M4.2 (unfold/bend) · M4.3 (nesting) · M4.7 (DFM) · M1.10 (cost) · (→ M5 for order).
- **Screenshots:** [`DemoI/`](../docs/reference/kb/screenshots/DemoI/).
- **Replay:** M4 quote-level; M5 order-level.

### Demo J — Nesting Deep-Dive  ·  [#nesting](../docs/spec/Bid-Factory-Build-Spec.html#nesting)
Single + multi-component nesting; per-break sheets + allocated material cost.
- **Blocks:** M4.3 (nesting).
- **Screenshots:** [`DemoJ/`](../docs/reference/kb/screenshots/DemoJ/).
- **Replay:** M4 exit — nest math matches a hand-calc.

### Demo K — Bid Factory for CNC Machine Shops  ·  [#sheetmetal](../docs/spec/Bid-Factory-Build-Spec.html#sheetmetal) *(milling)*
End-to-end milling: setup-detection + runtime → DFM → cost → quote → order.
- **Blocks:** M4.4 (milling) · M4.7 (DFM) · M1.10 (cost) · M5.2 (order).
- **Screenshots:** [`DemoK/`](../docs/reference/kb/screenshots/DemoK/).
- **Replay:** M5 — milling quote to order. *(5-axis runtime is manual-override per the OCCT ceiling — M4.4.)*

### Demo L — Real-Time Visibility Into Purchased Components  ·  [#integrations](../docs/spec/Bid-Factory-Build-Spec.html#integrations)
Convert-to-purchased + Smart Match; real-time distributor availability/pricing.
- **Blocks:** M4.10 (Smart Match / convert-to-purchased) · M6.7 (Würth adapter, mock→fixture→real).
- **Screenshots:** [`DemoL/`](../docs/reference/kb/screenshots/DemoL/).
- **Replay:** M6 — Würth adapter returns availability/pricing into Make Quantities.

### Demo M — Assembly Table Updates  ·  [#assembly](../docs/spec/Bid-Factory-Build-Spec.html#assembly)
Assembly table: bulk-update components (process/material/finish + regeneration warning), drag-reorder, breadcrumb, thumbnail hover, flat-BOM supplier warnings, copy pricing.
- **Blocks:** M4.10 (assembly components + bulk edit) · M4.9 (BOM table ops).
- **Screenshots:** [`DemoM/`](../docs/reference/kb/screenshots/DemoM/).
- **Replay:** M4 — bulk reassign across selected components with regeneration warning.

### Demo N — Geometric Feature Overview (native engine, no CAD license)  ·  [#geometry](../docs/spec/Bid-Factory-Build-Spec.html#geometry) · [#geometryservice](../docs/spec/Bid-Factory-Build-Spec.html#geometryservice)
All six process families: milling, lathe, sheet metal, wire EDM, additive, waterjet/laser-flat — features + warnings, no customer CAD license.
- **Blocks:** M4.1 (core dims/signature) · M4.2 (sheet metal) · M4.4 (milling) · M4.5 (lathe) · M4.6 (tube/waterjet-laser) · M4.7 (DFM per family). **Gated by M4.0 (OCCT probe).**
- **Scope caveat:** v1 OCCT = **Core-4 full** (milling, lathe, sheet metal, tube laser); **wire-EDM / additive = attributes-only / partial** per `DECISIONS.md` (Spatial swap-in restores full). So Demo N replays Core-4 fully; the other two show dims + the honest-ceiling note.
- **Screenshots:** [`DemoN/`](../docs/reference/kb/screenshots/DemoN/) (milling/lathe/sheet-metal/wire-EDM/additive/waterjet-laser feature + warning frames).
- **Replay:** M4 — per-family interrogation goldens vs hand-counted ground truth.

### Demo O — Quoting Assemblies  ·  [#assembly](../docs/spec/Bid-Factory-Build-Spec.html#assembly) · [#assemblies-model](../docs/spec/Bid-Factory-Build-Spec.html#assemblies-model)
Assembly root overview + qty pricing; parent-level process router; flat/child BOM toggle; 3D preview hover; child sheet-metal interrogation; operations + part complexity; add-ons + lead times; pricing rollup.
- **Blocks:** M4.9 (assembly BOM) · M4.10 (parent router + components) · M4.2 (child interrogation) · M2.6 (3D preview) · M1.6 (qty) · M1.10 (rollup) · M1.11 (add-ons/lead times).
- **Screenshots:** [`DemoO/`](../docs/reference/kb/screenshots/DemoO/).
- **Replay:** M4 — assembly root → child BOM → rollup; pricing from M1.

---

## The two kinds of demo

- **Spine demos (A, B, E)** are the **golden thread** (`README.md` §4): the RFQ→quote→price→send path kept green from M1 (E), made real through M3/M4/M5 (B), with A the assembly-heavy variant. Their fixtures assert **exact** figures.
- **Breadth demos (C, D, F, G, H, I, J, K, L, M, N, O)** exercise one slice deeply; each asserts its key behaviour against a fixture in its milestone.

**M6.10** runs the **full 14-demo acceptance replay** across the seeded demo tenants — the pilot's definition of done ([#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance), [#milestones](../docs/spec/Bid-Factory-Build-Spec.html#milestones) M6 exit).
