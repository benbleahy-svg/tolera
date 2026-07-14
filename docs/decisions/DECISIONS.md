# DECISIONS.md
# Tolera — Ambiguity Log

**Purpose:** When Claude Code (or any developer) encounters a genuine ambiguity not resolved by `Bid-Factory-Build-Spec.html`, add an entry here. Do not guess — block and add an entry. Benjamin reviews and resolves entries before the next build session.

**Format:**
```
## [YYYY-MM-DD] Short description
**Status:** OPEN | RESOLVED
**Question:** What exactly is unclear?
**Options considered:** ...
**Decision:** (fill in when resolved)
**Affects:** Which milestone / module
```

---

## Pre-seeded open items (resolve before or during build)

---

## [2026-07-14] M2.7 face-only selection; edge picking deferred to M2.8

**Status:** RESOLVED (autonomous, scoping; flag for Benjamin's review)
**Question:** The M2.7 build-plan line says "ray-pick a **face/edge**", but occt-import-js emits only face triangulations — no B-rep edges. Deriving pickable edges (boundary-polyline extraction between face groups + line/circle classification) is ~⅓ of the block and widens the persisted-nothing entity-id shape. M2.8 (measure) is the first block that genuinely consumes edge entities.
**Decision:** M2.7 ships **face picking only**. The `EntityRef` shape already reserves `kind: 'face' | 'edge'` so M2.8 adds edges without reshaping it or the M2.11 annotation binding. PP's own selection-tool screenshot (DemoB/11) shows a *face* pick with the Selection-Data overlay, so the demo ground truth is satisfied. Edge derivation lands in M2.8 where the measure tool needs edge/vertex entities anyway. Face ids remain session-transient and unpersisted per the 2026-07-14 viewer-mesh-provenance OPEN (below).
**Resolved:** 2026-07-14 (M2.7 autonomous build; grill + fixture oracle cross-checked)
**Affects:** M2.7 (face pick), M2.8 (edge/vertex entities + measure), M2.11 (annotation binding reuses `EntityRef`).

---

## [2026-07-14] M2.7 Weight readout — density plumbed as an optional viewer prop

**Status:** RESOLVED (autonomous, low-stakes; flag for Benjamin's review)
**Question:** The File readout shows Weight = mesh-volume × density, but density lives on `component.material_id` (nullable), while the 3D viewer is opened **per file**. From the Parts library there is no component/quote context, and a part reused by several components could resolve to several materials — so "which density?" is undefined there.
**Decision:** `CadViewerPage` takes an **optional `densityGCm3` prop** (frontend seam only — no API/schema change, no invented multi-component resolution rule). The Parts-library route passes nothing → Weight renders an em-dash with a "no material assigned" tooltip (never a silent default, per CLAUDE.md AI/never-hallucinate spirit for derived numbers). When the viewer gains quote-item context (**M2.10** Part Setup panel), that block passes the component's material density and Weight lights up. Volume (cm³) and Surface Area (mm²) are always shown; the DACH default is mm / mm² / cm³ / kg / deg, comma-decimal, never imperial. Face type/diameter/OBB are **mesh-only fits** behind the `MeshProvider` seam — authoritative typing arrives with GeometryService in M4.
**Resolved:** 2026-07-14 (M2.7 autonomous build; grill-confirmed)
**Affects:** M2.7 (Weight readout), M2.10 (supplies density from component material), M4 (authoritative face types / true OBB from GeometryService).

---

## [2026-07-12] M2.2 annotation-layer bounds + geometric markup representation

**Status:** RESOLVED (autonomous, low-stakes; flag for Benjamin's review)
**Question:** (1) The persisted per-file markup layer needs abuse bounds the docs don't specify. (2) The spec's text-markup tools (underline/highlight/squiggly/strikeout) anchor to *text* in PP; Tolera's M2.1 viewer has no text layer yet.
**Decision:** (1) Bounds: **2000 objects per layer, 20 KB per object** (bounds freehand point clouds and text blobs; the 150-vs-250 MB upload-cap precedent) — org-invisible internals, revisit if a real print exceeds them. (2) v1 stores all tools as **geometric page-space objects** in unrotated pdf.js viewport coordinates; text-anchored refinement rides the future text layer (which M2.1's search-term highlight also wants). Markup is hidden and input blocked while a rotation is applied so exports stay position-honest.
**Resolved:** 2026-07-12 (M2.2 autonomous build; verifier + two-axis review cross-checked)
**Affects:** M2.2; M2.11 (collaboration threads reference these objects); M3 (Lens bbox overlay shares the coordinate convention).

---

## [2026-07-12] M1.14 APPLY-TO-ALL fills only unrated rates; banner is count-based

**Status:** RESOLVED (autonomous, doc-backed; flag for Benjamin's review)
**Question:** Spec `#operation-rates-banner` says the quick-start "APPLY TO ALL sets the run rate on **every** process in the org's catalog in one write" and calls the banner "dismissible … until at least one rate is saved". Filling *every* def would silently overwrite rates an admin already configured, and a dismiss-on-first-rate banner stops guarding long before the catalog is actually rated (the block AC wants the **count** of unrated ops/materials).
**Decision:** APPLY TO ALL fills only defs whose rate is still NULL/0 — the CLAUDE.md §5 never-destroy-human-input reading; in the banner's real use case (fresh org, nothing rated) the two are identical. The banner is count-based and non-dismissible until nothing is unrated (block AC over spec prose). The quote-side warning additionally flags **costless materials** (block scope "op/material"), beyond the spec's operation-only wording.
**Resolved:** 2026-07-12 (M1.14 autonomous build; verifier + two-axis review cross-checked)
**Affects:** M1.14; M6 Quick-Setup wizard (reuses the same apply-rate endpoint).

---

## [2026-07-12] OPEN: Fechner fixture packages — Core-4 coverage + starter rules
**Status:** OPEN
**Question:** SEED-AND-FIXTURES Part 2 names two shop-specific open items the M1.13 harness now depends on: (a) **which fixtures cover which Core-4 family** — the anonymised Fechner packages (original target 2026-06-23) should span Sheet Metal / Milling / Lathe / Tube Laser so each family has at least one golden; (b) **the starter rule set Fechner wants** (consumed by the M3 rules engine, seeded via the same harness).
**Options considered:** wait for the packages (harness ships with synthetic placeholders — done in M1.13); author provisional per-family fixtures from open CAD (risks divergence from real Fechner parts).
**Recommended default:** keep the synthetic placeholders until the packages land, then author one `/fixtures/parts` recipe + golden per Core-4 family from the real parts; collect the rule list in the same session.
**Affects:** M1.13 (fixture coverage), M3 (starter rules + extraction goldens), M4 (interrogation goldens).

---

## [2026-07-12] M1.12 Zuschlagskalkulation seed — doc conflicts resolved up the ladder

**Status:** RESOLVED (autonomous, doc-backed; flag for Benjamin's review)
**Question:** Four spec/fixture contradictions surfaced while seeding the §6 pricing defaults: (1) SEED-AND-FIXTURES §6 wants "standard markup/margin per category **+** the Zuschlagskalkulation seed", but stacking a general profit markup on the Zuschlag chain double-counts profit (Gewinn IS the chain's profit item) and pollutes `get_selbstkosten()`'s "everything before Gewinn" base — the spec's 100 € + 100 € example would price 305,80 instead of 261,80. (2) `#zuschlagskalkulation`'s prose chain folds MGK into Herstellkosten (→ VwGK base 210), while the same section's **"Kalk implementation" table** — explicitly the build instruction ("Two new Kalk helpers to build") — defines `get_herstellkosten() = Material + Inside cost categories` (→ 200). (3) The spec enumerates Selbstkosten as "Material, Inside, Outside, MGK, VwGK, VtGK" but also glosses it "sum of **all** cost categories … i.e. everything before Gewinn" — does purchased-component cost count? (4) `#oplibrary`'s table headers say "31 Machine+Operator / 23 Labour-Only" but its own numbered rows run 1-32 / 33-54.
**Decision:** Resolve each *up* the ladder: (1) tier-2 `#dach-costing` wins over tier-3 §6 — a DACH-mode org's seeded default is the **pure four-item chain**; `Standardaufschlag` seeds only when the mode is off. (2) The Kalk-implementation table is the build target: `get_herstellkosten() = Material + Inside` (VwGK 8 % of 200 = 16,00). (3) `get_selbstkosten() = TOTAL_COST + all prior pricing items in position order` — "all cost categories" includes purchased components, and "everything before Gewinn" fixes the item semantics (the seed positions Gewinn last). (4) The numbered rows are authoritative: 32 + 22 = 54. Also noted: the seed.skeleton expedite pair (5 d → 15 %, 10 d → 7 %) is non-monotonic and was seeded as 5 d → 7 %, 10 d → 15 % (faster costs more, per the dynamic-lead-times KB).
**Resolved:** 2026-07-12 (M1.12 autonomous build; verifier + spec review cross-checked)
**Affects:** M1.12 (configure seed + Kalk helpers), M1.13 (harness asserts 261,80), M5 (margin coach reads the same chain).

---

## [2026-07-09] M1.10 grill — Demo E golden reproduction + pricing-layer schema (six rulings)

**Status:** RESOLVED
**Question:** Six M1.10 grill points: (1) the spec's prose figures don't reproduce $2,160.84 under any single display rounding; (2) custom-cost-category shape (spec build-implication says a `CostCategory` entity, the folded DDL says `pricing_item.is_custom + formula`); (3) target-margin storage + edge semantics; (4) where Purchased-Components / Component-Overrides cost comes from before M4's `purchased_component` entity; (5) roll-up depth given root-only quantity breaks (M1.6); (6) where per-line pricing items/discounts originate (org config) + Refresh Pricing scope.
**Decision (Benjamin 2026-07-09, "go with your recommendations", DemoE frames supplied and analysed):**
1. **Rounding model verified from the DemoE frames:** the reference product's internals carry sub-cent precision; its per-row displays **truncate** to cents while summary rows (Total, Total Markup) round **half-up** — its row displays are cent-inconsistent on their face (e.g. Ex5 2,094.50 + 30.00 shown as 2,124.51). Tolera keeps its established model — `numeric(14,4)` internals, **ROUND_HALF_UP at every 2-dp display/total boundary** (kaufmännische Rundung; 2026-06-27/07-08 decisions) — and the golden fixtures use documented **4-dp inputs reverse-engineered to satisfy every displayed row and total simultaneously**, so all six Demo E totals are asserted **exactly** (2,160.84 / 1,837.10 / 2,028.72 / 1,957.74 / 2,124.51 / 928.64 + 857.20). Known cent-level display divergence on some intermediate rows (we show half-up where PP truncates, e.g. 53.94 vs 53.93) — deliberate, DACH-correct.
2. **No `CostCategory` table.** A custom category lives on its pricing item (folded-DDL shape + the Configure→Pricing frame: category chip per item): `pricing_item.is_custom + custom_category_name + color + formula`; per-break custom cost persisted as `pricing_item_cell.calc_custom_cost` (the colored Costing row + later Excel export read it). The five standard categories stay the `cost_category` enum.
3. **Target-margin** (`calc_type = 'target_margin'`, v1 differentiator, spec `#newscope`): back-solve `amount = target/(1−target) × TOTAL_COST − Σ other items' amounts`, holding other items fixed, solved against **Total excl. Discounts**. `amount < 0` ⇒ **unreachable**: contribution 0 + `unreachable` flag surfaced in UI. **At most one** target-margin item per stack (validation error). Target pct stored in the cell's `calc_pct`/`manual_pct` like the other types; computed amount in `calc_profit`.
4. **Purchased / Overrides buckets now, entity later:** `component.piece_price` (per-unit; a PURCHASED child contributes `piece_price × make_qty` to Purchased Components) and `component.manual_override_cost` (per-unit; when set, replaces a child's rolled-up cost and lands in Component Overrides). Full `purchased_component` entity unchanged at M4.
5. **Tree roll-up on the fly:** child components roll up now with `make_qty(child) = root break qty × Π qty_relative_to_parent` along the node path; child op costs computed per root break (mode arithmetic / Kalk) **without** child `component_quantity` or cell rows (those, plus scrap, stay M4). Manual per-cell cost overrides therefore exist only on root-component cells until M4.
6. **Org-level `pricing_item_def` + `discount_def`** (name, calc_type, category, custom fields, color, formula, default pct, position) behind Configure → Pricing/Discounts; **snapshot-on-attach** to every new quote item (mirrors the 2026-07-08 M1.9 ruling; E4-d freeze holds). **Refresh Pricing (single quote)** lands in M1.10 — re-snapshots `is_from_factory` rows from current defs, re-evaluates, preserves every `manual_*`; **Bulk Refresh** deferred to the quotes-list block (OPEN below).
**Resolved:** 2026-07-09 (M1.10 grill; DemoE screenshots supplied by Benjamin — figures encoded in the golden fixtures; `docs/reference/screenshots/` stays gitignored per .gitignore note)
**Affects:** M1.10 (schema + engine + goldens), M1.11 (VAT on the rounded totals), M1.12 (seeded pricing defaults), M1.13 (harness asserts the same six), M4 (purchased_component entity, child breaks/cells, scrap).

## [2026-07-09] OPEN: Bulk Refresh Pricing placement
**Status:** OPEN
**Question:** E4-d names both `Refresh Pricing` (single) and `Bulk Refresh Pricing` (quotes-list multi-select). Single lands in M1.10; the bulk action is a quotes-list concern (selection UI + batch job).
**Options:** (a) M1.10 loop endpoint without list UI; (b) defer to the quotes-list/M5 block where the multi-select UI lives.
**Recommended default:** (b) — the engine's re-evaluate-with-preserved-overrides mode ships in M1.10, so bulk is a thin loop over it later.
**Affects:** quotes list block (M5), E4-d completeness.

## [2026-07-08] M1.9 Kalk→money quantization — numeric(14,4) half-up at the cell, minor units only at quote totals

**Status:** RESOLVED
**Question:** M1.8 deferred the float→integer-minor-units rule to M1.9, when Kalk `COST` becomes the `calc_cost` source. Two dimensions: rounding mode (banker's half-even — Kalk `round()` parity — vs kaufmännische Rundung half-up) and quantization point (per op-cell vs only at the quote-total boundary).
**Options considered:** (1) quantize each cell to integer cents (roll-up = exact integer sums); (2) keep sub-cent precision through the roll-up, quantize to minor units only at the quote-total/display boundary.
**Decision:** **(2)**, extending the existing 2026-06-27 money convention already encoded in `app/costing.py`: Kalk `COST` (float) converts via `repr` → `Decimal` quantized to **4 dp, ROUND_HALF_UP** (`numeric(14,4)` — the same `_quant` M1.7 mode arithmetic uses) when persisted to `quote_cell.calc_cost`; integer minor units + currency appear only at the quote-total boundary (M1.10/M1.11). The tier-1 "money = integer minor units" invariant applies to quote-level money; unit-level `numeric(14,4)` is the established sub-cent costing precision. Demo E golden figures validate this end-to-end at M1.10.
**Resolved:** 2026-07-08 (M1.9 grill, Benjamin — "quantize at the total/display boundary")
**Affects:** M1.9 (Kalk→`calc_cost` wiring), M1.10 (roll-up + goldens), M1.11 (VAT/net-gross minor-unit boundary).

## [2026-07-08] M1.9 cost_formula snapshot-on-attach (config-freeze E4-d)

**Status:** RESOLVED
**Question:** `cost_formula` lands on `operation_def` at M1.9. Does a quote-level `operation` row reference the def's formula live, or copy it at attach time, given E4-d freezes pricing config for existing drafts?
**Decision:** **Snapshot-on-attach.** `operation.cost_formula` is copied from `operation_def.cost_formula` when the operation is added to a quote; editing the def never re-prices an existing draft. M1.10's "Refresh Pricing" re-copies deliberately. Evaluation always reads the operation row's snapshot.
**Resolved:** 2026-07-08 (M1.9 grill, Benjamin)
**Affects:** M1.9 schema + costing service, M1.10 (Refresh Pricing), M1.12 (seeded formulas).

## [2026-07-08] M1.9 Kalk variable overrides — jsonb on the operation row

**Status:** RESOLVED
**Question:** Where do UI overrides of Kalk-declared variables persist (per quote-operation; per quantity break for `quantity_specific=True`), preserving the calc-vs-override invariant?
**Decision:** `operation.variable_overrides jsonb` — `{var_name: value}` for plain vars, `{var_name: {"<qty>": value}}` for quantity-specific ones — passed as `overrides` into `evaluate()`; re-evaluation never touches it. The special `runtime`/`setup_time` names keep flowing through the existing `manual_runtime_mins`/`manual_setup_mins` columns (calc\_/manual\_ pairs from M1.7), not the jsonb; a formula's frozen `runtime`/`setup_time` outputs write `calc_runtime_mins`/`calc_setup_mins` (hours→minutes at the boundary).
**Resolved:** 2026-07-08 (M1.9 grill, Benjamin)
**Affects:** M1.9 schema + evaluation wiring, M1.10 (re-pricing keeps overrides).

## [2026-07-08] M1.9 custom-table column types + caps

**Status:** RESOLVED
**Question:** `DB-SCHEMA.sql` gives `custom_table.columns jsonb [{name,type}]` without a closed type set.
**Decision:** v1 column types = **boolean | numeric | string** (the KB filter-condition matrix's type set; no date/currency columns). Column names alphanumeric, no leading digit (dot-accessed in formulas). Caps kept as spec'd: `table_var` ≤200 rows, `table_lookup` ≤10,000, drop-down search ≤50. CSV import is in v1 scope (types validated against the declared columns on import).
**Resolved:** 2026-07-08 (M1.9 grill, Benjamin — recommendation approved)
**Affects:** M1.9 (custom-table entity/API/UI, `table_var`/`table_lookup` runtime).

## [2026-07-08] M1.8 Kalk sandbox isolation boundary — in-process restricted-AST evaluator (v1) behind an executor seam

**Status:** RESOLVED
**Question:** `#kalk-determinism` mandates an "AST allowlist of nodes + builtins; resource/time/recursion caps" but doesn't fix the isolation boundary. In-process CPython sandboxing is not a hard security boundary (an interpreter 0-day or an un-interruptible C-level op — e.g. a huge bigint `**` — runs inside the multi-tenant server process); subprocess isolation (rlimits, kill-able) is a hard boundary but costs a warm worker pool for the per-operation × per-quantity evaluation volume.
**Options considered:** (a) in-process restricted-AST evaluator — AST node/name/attribute allowlist, empty `__builtins__`, instrumented caps (op budget, loop-iteration ticks, wall-clock deadline, guarded binops with string/collection-size and `**`-operand limits) that make the un-interruptible cases unreachable; (b) subprocess/worker-pool isolation with OS rlimits.
**Decision:** **(a) for v1** — threat model is authenticated org estimators (tenant-scoped misuse + accidents, not anonymous code), and the operand/size guards close the known un-interruptible classes. **The evaluator sits behind an executor interface** so (b) can replace the execution step without any contract change, and the security escape matrix is a permanent pytest regression guard (`tests/test_kalk_m18_security.py`). Cap defaults (timeout 500 ms, ~1M-op budget, 100k iterations/loop, 64 KB strings, `**` exponent ≤ 512, numeric magnitude ≤ 1e300) are reversible constants noted in code, not spec.
**Resolved:** 2026-07-08 (M1.8 grill, Benjamin)
**Affects:** M1.8 (`app/services/kalk/`), M1.9+ (all five contexts run on this core), ops/security review before GA.

## [2026-07-08] M1.8 Kalk determinism contract — same-platform canonical bytes; goldens run in the canonical image

**Status:** RESOLVED
**Question:** M1.8 acceptance says "same inputs → identical bytes". Bit-for-bit across *machines* is stricter than it sounds: float `+ - * /` are IEEE-754-fixed, but float `**` goes through platform libm and may differ across OS/arch.
**Decision:** Determinism contract = **identical canonical bytes on the same platform/build** (the 1000-run test, plus fresh-interpreter runs under varying `PYTHONHASHSEED` to prove hash-seed independence); **cross-environment equality is delivered by running golden tests in the canonical container image**, not by software-emulating libm. Canonical serialization fixed now: JSON, sorted keys, compact separators, floats via `repr` (shortest round-trip), non-finite values rejected as errors. Non-determinism sources eliminated structurally: no time/random access (no imports, empty builtins), no `set` literals/comprehensions in the grammar (dicts are insertion-ordered and dict/set literals are banned anyway), `round()` keeps Python banker's rounding (P3L parity for golden figures). Kalk outputs stay floats; the float→integer-minor-units quantization rule is decided at M1.9 when Kalk becomes the `calc_cost` source (flagged, not blocking).
**Resolved:** 2026-07-08 (M1.8 grill, Benjamin)
**Affects:** M1.8 (serialization + tests), M1.9/M1.10 (quantization OPEN due then), golden fixtures CI.

## [2026-07-07] M1.7 material catalog content — hubs.com metal families + variants

**Status:** RESOLVED
**Question:** The `/block M1.7` note points the material list at `https://www.hubs.com/cnc-machining/metal/`. Which block owns that content (M1.7 entities vs M1.12 seed), how deep (families only vs variants), and in which naming language, given `SEED-AND-FIXTURES.md` §2 specifies a smaller exemplar list?
**Decision:** **(a) Scope:** M1.7 seeds the catalog so the nested picker is browsable — class **Metall** + the **11 hubs metal families** (Alloy steel, Aluminum, Brass, Bronze, Copper, Inconel, Invar 36, Mild steel, Stainless steel, Titanium, Tool steel); M1.12 inherits this as the canonical materials tree (supersedes the §2 exemplar list, which stays as examples of the keying convention). **(b) Depth:** variants (leaf materials) are pulled in too — hubs' subpage variant sets, keyed by standard DIN EN designations (Werkstoffnummer + EN name + AISI alias); the variants need not come from hubs.com verbatim (Benjamin 2026-07-07). Densities = standard published values; `cost_per_volume`/`cost_per_area` stay **NULL** (rates are shop-specific — the M1.14 missing-rates guard exists for exactly this). **(c) Naming:** German-first display names (Nichtrostender Stahl, Werkzeugstahl, Baustahl, …) with the English/AISI name kept as alias fields. Note: the build environment's network policy blocks hubs.com directly; the family list + variant sets were confirmed via web search and standard DIN/EN references — coverage is the well-known variants per family, not a verbatim page scrape.
**Resolved:** 2026-07-07 (M1.7 grill)
**Affects:** M1.7 (catalog seed), M1.12 (`SEED-AND-FIXTURES.md` Part 1 §2 — inherits this list).

## [2026-07-07] Operation model shape — spec `#oplibrary` wins; minutes persisted

**Status:** RESOLVED
**Question:** `#oplibrary` (tier 2, grilled 2026-06-14) defines the DACH operation model (`calculation_mode ENUM(machine_plus_operator|labour_only|outside_process)`, `run_rate`, `labour_rate`, `setup_cost` flat € XOR `setup_time_mins`, `surcharge_pct`, "all time inputs in minutes, never hours"), while the folded `DB-SCHEMA.sql` shows the older PP shape (`calc_mode text`, `cost_formula`, display units defaulting to hours). Which shape ships in M1.7, and in which unit are times persisted given `#kalk` says runtime/setup are *internally hours*?
**Decision:** Build the **`#oplibrary` shape** (spec outranks folded provenance). **Times are persisted in minutes** — the product-wide input/display unit; the M1.9 Kalk evaluation context converts to hours at the formula boundary (its internal convention stays hours per `#kalk`). The Kalk `cost_formula` column is added at M1.9, not now. Per-quote time inputs (Setup/Haupt-/Nebenzeit) live on the **operation row** (calc\_/manual\_ pairs), not per quantity cell — the spec's operations grid shows one Setup/Run per row with per-qty *price* columns; per-qty time variables arrive with `quantity_specific` Kalk vars (M1.9). `quote_cell` therefore carries only `(quantity, calc_cost, manual_cost)` + a composite FK onto `component_quantity(component_id, quantity)` so cells reshape with the break set — a deliberate, documented divergence from the folded `quote_cell(runtime, setup_time, days)` columns (`days` arrives with M1.11 lead times).
**Resolved:** 2026-07-07 (M1.7 grill)
**Affects:** M1.7 schema, M1.9 (Kalk context + `cost_formula`), M1.11 (`days`), M1.12 (54-op seed uses this shape).

## [2026-07-07] M1.7 "Calculated" source before Kalk = calculation-mode arithmetic

**Status:** RESOLVED
**Question:** The Calculated-vs-Override drawer needs a `calc_` value before Kalk exists (M1.9). Scope-out excludes *Kalk* formulas — but `#oplibrary`'s calculation-mode math is plain deterministic arithmetic.
**Decision:** M1.7 implements the mode arithmetic as the `calc_cost` source per quantity break: `machine_plus_operator` = `setup + (Hauptzeit/60 × run_rate + Nebenzeit/60 × labour_rate) × Losgröße`; `labour_only` = `setup + (Arbeitszeit/60 × run_rate) × Losgröße`; `outside_process` = no calc (manual cost only until the Vendor-RFQ path, M6). Losgröße = the break's **make quantity**. `surcharge_pct` applies on the computed op cost (`× (1 + pct/100)`), and the material line's `yield_factor` gross-up ships now (both deterministic, both `#oplibrary`). Material-category lines have **no calc source in M1.7** (real material calc needs geometry + stock pricing → M1.9/M4); their cells are manual, `yield_factor` is persisted and applied once a calc source exists. Kalk formulas take over/augment the calc source at M1.9.
**Resolved:** 2026-07-07 (M1.7 grill)
**Affects:** M1.7 costing service, M1.9 (Kalk replaces the calc source), M1.10 (roll-up consumes `COALESCE(manual_cost, calc_cost)`).

## [2026-07-07] Change Process semantics pre-router (M1.7)

**Status:** RESOLVED
**Question:** The spec's Update Process modal offers UPDATE (regenerate router — deletes existing operations) vs UPDATE AND KEEP EXISTING OPS, but router templates/auto-generation only arrive at M1.12/M4.
**Decision:** Ship **both commits now** with the specified destructive semantics: UPDATE deletes the component's operations (router *regeneration* is a no-op until M4 — the warning text stays honest), UPDATE AND KEEP EXISTING OPS changes the process and preserves operations. M4 slots router generation into the already-correct UPDATE path.
**Resolved:** 2026-07-07 (M1.7 grill)
**Affects:** M1.7 (change-process endpoint + modal), M4 (router generation).

## [2026-07-07] OPEN: rate used for time-based setup (Advanced toggle)

**Status:** OPEN
**Question:** `#oplibrary` says the Advanced toggle prices setup as "setup time in minutes × setup rate" but never defines *which* rate is the setup rate — the machine rate (`run_rate`/MSS), the operator rate (`labour_rate`), or a dedicated third rate.
**Options considered:** (a) `run_rate` — during setup the machine is occupied (and the operator is part of MSS-adjacent cost); (b) `labour_rate` — setup is operator work; (c) a dedicated `setup_rate` column.
**Recommended default (implemented in M1.7):** **(a)** `setup_cost = setup_time_mins/60 × run_rate` for both internal modes — the machine is blocked during Rüsten, and one fewer rate keeps the library simple. Reversible: no stored data depends on it (calc values recompute); flipping to (b)/(c) is a formula/column change. Confirm before M1.12 seeds rate guidance.
**Affects:** M1.7 costing service, M1.12 (seed/Quick-Setup docs), golden figures if any fixture uses time-based setup.

## [2026-07-07] Component quote inclusion — material-scoped quoting (Angebotsumfang)

**Status:** RESOLVED
**Question:** A customer sends one STEP of a whole construction in mixed materials (e.g. wood frame + stainless components) but the shop quotes **only the stainless parts**. The model has no child-component exclusion primitive: `qi_workflow_status='no_quote'` declines a whole *root* line item only, and `obtain_method` is just `MANUFACTURED|PURCHASED`. Where does per-component "not ours / not quoted" live? (Schema — expensive to reverse, block-and-log §6.)
**Options considered:** (a) extend `obtain_method` with a third value; (b) a new orthogonal per-component enum; (c) force each material group into its own root quote item and use `no_quote`.
**Decision:** **(b).** New **`component.quote_inclusion ENUM('quoted','excluded','customer_supplied') NOT NULL DEFAULT 'quoted'`**, orthogonal to `obtain_method` (a customer-supplied part can still carry assembly ops; no enum surgery on a shipped type). Named `quote_inclusion`, **not** `quote_scope` — PP terminology already uses "quote scope" for the component→quote link (`#assemblies-model`: *"tied to one part + one quote scope"*). Semantics: **`excluded`** = out of scope — contributes **zero to every cost category**, is skipped by interrogation-driven costing, and **vanishes entirely from all customer-facing outputs** (digital quote, quote PDF, portal DTOs — Benjamin 2026-07-07: "vanish entirely"); stays visible *internally*, greyed/ghosted in the BOM tree and 3D viewer. **`customer_supplied`** (*Beistellung*) = present in the build, zero material/purchase cost, may carry assembly/handling operations. **Filter granularity = material family** (e.g. "quote only 1.4xxx stainless", not "all metals" — Benjamin 2026-07-07). UX = one-click family filter **plus** per-component individual toggles (both, confirmed). An org-level **processed-material-families whitelist** lets Lens pre-suggest the whole scope so the estimator's job collapses to a single Accept — via AI-Governor, explicit accept, never auto-applied. **Migration timing:** M1.5/M1.6 have shipped, so the enum + column land as a **forward reversible migration in M4.10b** (the first consumer), per the stub-then-extend precedent — no reshaping.
**Resolved:** 2026-07-07 (feature-design session with Benjamin)
**Affects:** M4.9b/M4.10b (schema + detection + UX), M3 (Lens pipeline 5), M5 (customer-facing suppression), spec `#quote-inclusion` + `#db-schema`.

## [2026-07-07] Foreign materials — real Holz class + Sonstige catch-all

**Status:** RESOLVED
**Question:** Mixed constructions contain non-metal bodies, but `material_class` seeds only Metal/Polymer/Composite/Sand/Wax/Additive. Exclude-only, or priceable?
**Decision:** **Both a real class and a catch-all.** Seed a **Holz (Wood)** `material_class` — shops *do* quote wood parts (outsourced / externally processed, still on the customer quote — Benjamin 2026-07-07), priced via the outside-process / Buy-mode path (no internal wood machining rates are seeded). Additionally seed a **Sonstige (Fremdmaterial)** catch-all class so Lens material suggestions for detected-but-unclassifiable bodies always have a target without polluting the metals hierarchy.
**Resolved:** 2026-07-07
**Affects:** M1.12 seed / `SEED-AND-FIXTURES.md` §2, M4.10b, spec `#quote-inclusion`.

## [2026-07-07] thyssenkrupp live steel pricing — surface = materials4me (M6.7b)

**Status:** RESOLVED
**Question:** Which thyssenkrupp surface backs a live raw-material pricing feed? thyssenkrupp Steel Europe proper is contract-mill business with no public API.
**Decision:** **materials4me** (thyssenkrupp Materials Services' online shop — public prices, small/mid quantities) is the integration surface (Benjamin 2026-07-07). A **`ThyssenkruppMaterialPricingAdapter`** behind the same `SupplierAdapter` interface as Würth, **mock-first** against a documented fixture JSON (same posture as the 2026-06-14 Würth decision). It implements the spec's **`MaterialPricingFeed`** concept (the reference product's "Vendor RFQs [Beta]" nav = live material pricing from Online Metals + TK — see the note at `#integrations`). Request keyed on **Werkstoffnummer + product form (sheet/plate/bar/tube) + dimensions + quantity**; response feeds `material.cost_per_volume`/`cost_per_area` as **calc_** values with a "Pricing updated ⟨timestamp⟩" stamp. E4-d freeze + Refresh/Bulk-Refresh Pricing semantics unchanged — a live price never silently reprices an existing draft.
**Resolved:** 2026-07-07
**Affects:** M6.7b, spec `#material-pricing-feed` + `#dach-connectors-tbl`.

## [2026-07-07] materials4me API access channel

**Status:** OPEN
**Question:** materials4me has no documented public API. Channel options: (a) tk Materials Services partner/API agreement (procurement lead time); (b) OCI/electronic-catalog surface; (c) recurring price-list import (CSV) as interim.
**Recommended default:** start the tk partner/API conversation now; the adapter ships mock-first regardless (fixture JSON is the contract), with the price-list import (c) as the interim fallback if the pilot needs live numbers before an API lands. Do **not** block M6.7b on procurement.
**Affects:** M6.7b.

## [2026-07-07] CNC part quick-quote adapter (M6.7c) + mandatory external-send gate

**Status:** RESOLVED
**Question:** How do quick quotes for outsourced CNC-milled parts (instant supplier pricing, not the manual vendor-RFQ email loop) enter costing — and under what data-protection constraints, given customer CAD leaves the tenant?
**Decision:** A **`PartQuotingAdapter`** capability on the `SupplierAdapter` family: request = STEP + material + qty breaks + tolerance/finish class; response = price per break + lead time. Responses land in the **M6.6 Vendor Quotes panel** beside human vendor replies and use the **same Apply → Outside-Services cost / Buy-mode path** — an "automated vendor" inside the Vendor RFQ funnel, so there is exactly one price-application code path and one audit trail. Mock-first fixture JSON. **Hard gate (Benjamin 2026-07-07, confirmed):** sending customer CAD to any external quoting counterparty requires **explicit per-send confirmation**, offers the **redacted** file variant, and runs **export-control screening first** — a dual-use-flagged part is never auto-sent (same posture as the vendor-RFQ per-vendor file toggles; enforced in the adapter layer, audited under M6.9).
**Resolved:** 2026-07-07
**Affects:** M6.7c, spec `#part-quoting`, M6.6 (apply path), M6.9 (export-control audit covers the gate).

## [2026-07-07] CNC quick-quote first counterparty

**Status:** OPEN
**Question:** Who answers the instant-quote request first: (a) the shop's **own vendor network** behind a structured instant-quote API, or (b) a **marketplace** (Xometry/Fractory-style)? The adapter contract is counterparty-agnostic; the fixture can model both.
**Recommended default:** (a) own vendor network first — vendors are already under the shop's supplier agreements (no new data-sharing exposure), and it composes with the M6.2–M6.6 vendor entities; a marketplace adapter is post-pilot behind the same interface and raises the external-send gate stakes (GDPR + dual-use).
**Affects:** M6.7c.

---

## [2026-06-26] PartGeometry manual-dims storage model (M1.5)

**Status:** RESOLVED
**Question:** How are M1.5's **manual** geometry dims stored, given Kalk reads `part.size_x` etc. (M1.9/M1.10) and M4 interrogation must not clobber a human's manual value (the tier-1 calc-vs-override invariant)?
**Options considered:** (a) effective numeric columns + `overrides` jsonb + `raw` jsonb (null until M4); (b) numeric columns only now, add raw/overrides at M4; (c) pure `overrides` jsonb, no numeric columns.
**Decision:** **(a).** Follow `DB-SCHEMA.sql` as written: a 1:1 `part_geometry` table with numeric `size_x/y/z`, `max_dim/med_dim/min_dim`, `area`, `volume`, `weight` (the **effective** metric value Kalk reads), plus `raw jsonb` (NULL until M4 interrogation) and `overrides jsonb` (records which fields a human set). In M1.5 a manual dim writes the numeric column **and** the corresponding `overrides` key. Effective = `COALESCE(override, raw)`; the materialised numeric column is that result. Preserves the calc-vs-override invariant now so M4 only fills `raw` — no reshape, no backfill after Kalk/golden tests depend on the columns. `weight` and `geom_hash` are inert in M1.5 (no density until M1.7; no interrogation until M4). Storage is always metric (mm/mm²/mm³/g); the IN/MM toggle is **presentation-only** (DACH units invariant — never persists imperial).
**Resolved:** 2026-06-26 (/block M1.5 grill — Tier-2 schema + tier-1 calc-vs-override invariant)
**Affects:** M1.5 (schema), M1.9/M1.10 (Kalk part object), M4 (interrogation fills `raw`).

## [2026-06-26] PartGeometry storage units — grams + mm, not the general kg (M1.5)
**Status:** RESOLVED
**Question:** CLAUDE.md §5 states the metric convention as **mm / kg / deg**, but the `PartGeometry-Attribute-Catalog` (the geometry↔Kalk contract) specifies `part.weight` in **g** and `part.density` in **g/cm³**. Which unit does `part_geometry.weight` store? (Units/data-integrity — flagged in M1.5 ship review; block-and-log §6, never guess on units.)
**Decision:** **Store grams** (and density g/cm³, dims mm/mm²/mm³) per the **PartGeometry catalog** — the more-specific subsystem contract wins for its own internals (CLAUDE.md §2), and it *is* the Kalk `part` object surface (M1.9). Rationale: (1) internal consistency — `weight(g) = density(g/cm³) × volume(cm³)`, all gram/mm-based; storing weight in kg while density stays g/cm³ would inject a 1000× bridge into every Kalk/DFM formula; (2) PP `part.weight` parity — Kalk formulas ported from P3L expect grams, so kg would make them silently 1000× off. CLAUDE.md §5's "kg" is the **human-display** convention (a part weight shown to a user may render in kg); storage stays canonical-metric per the catalog, displayed per locale later — the same store-canonical / present-converted split as the mm/IN dimension toggle. Weight is inert in M1.5 (no density until M1.7, no Kalk until M1.9), so this is settled before any consumer depends on it.
**Resolved:** 2026-06-26 (/ship M1.5 — CodeRabbit raised the kg-vs-g conflict; resolved to the catalog with rationale)
**Affects:** M1.5 (`part_geometry.weight`), M1.7 (density g/cm³), M1.9 (Kalk `part.weight`/`part.density`), later UI (kg display).

## [2026-06-26] Safe evaluation of dimension math/unit inputs (M1.5)

**Status:** RESOLVED
**Question:** The spec requires dim fields to auto-evaluate math (`2.27 + .359`) and typed units (`1 meter`). This evaluates **user input** — how, safely, and where is it authoritative?
**Options considered:** (a) server-authoritative restricted-AST arithmetic + hand-rolled unit allow-list; (b) same but `pint` for units; (c) client-side preview, server stores a plain number only.
**Decision:** **(a).** A server-authoritative restricted-AST evaluator: numbers and `+ - * / ( )` only — **no** names, calls, attributes, subscripts, or dunders — plus a small unit allow-list (`mm/cm/m/in/ft` → mm) with hand-rolled factors. Reject anything outside the grammar with a clean 422. **Never `eval()`.** The client may mirror it for a live preview, but the server validates and stores; the acceptance criterion is met at the API layer (where golden/fixture tests live). Hand-rolled over `pint` because the unit surface is tiny (5 length units) and a small factor table is trivially auditable for a security-sensitive parser. This is deliberately **not** Kalk (M1.8) — strictly arithmetic, no variable/function references.
**Resolved:** 2026-06-26 (/block M1.5 grill — security-sensitive: no arbitrary code execution on dim input)
**Affects:** M1.5 (dimension input parser + tests), M1.8 (Kalk is the separate, sandboxed DSL).

## [2026-06-26] Export-controlled flag home (M1.5)

**Status:** RESOLVED
**Question:** Where does the export-controlled flag live? `quote_item.export_controlled` already exists (M1.4); DACH delta reframes ITAR → EU dual-use.
**Options considered:** (a) add `part.export_controlled`, keep `quote_item.export_controlled` as a line-level echo, defer org-level `export_regime` to M6; (b) part-level only; (c) add org-level `export_regime` enum now too.
**Decision:** **(a).** Add `part.export_controlled` as the primary home (the flag travels with the part across quotes); keep the existing `quote_item.export_controlled` as the line-level echo/override. Both are booleans, stored, **no runtime enforcement** in M1.5; UI checkbox labeled for DACH (EU dual-use, not ITAR). The org-level `export_regime` enum (`none|eu_dual_use|itar`) is deferred to **M6** (export-control connectors) — consistent with the 2026-06-24 "M0.5 seed scope" deferral. Both columns are already in the canonical `DB-SCHEMA.sql`, so this is not pulling scope forward.
**Resolved:** 2026-06-26 (/block M1.5 grill)
**Affects:** M1.5 (schema/UI), M6 (export-control connectors + org `export_regime`).

## [2026-06-26] Part identity uniqueness (M1.5)

**Status:** RESOLVED
**Question:** Should `part_number`/`revision` be uniquely constrained in M1.5?
**Decision:** **No.** `name`, `part_number`, `revision`, `description` are nullable free-text with **no** unique constraint in M1.5. Part-library matching/dedup is explicitly M1.5 scope-out (→ M2); RFQ intake (M3) also produces number-less parts. Adding uniqueness later is a clean forward migration; M2 owns identity/matching semantics.
**Resolved:** 2026-06-26 (/block M1.5 grill)
**Affects:** M1.5 (schema), M2 (part-library matching).

## [2026-06-26] Quote status enum — final value set (M1.4)

**Status:** RESOLVED
**Question:** The 2026-06-25 entry "7 folders vs 5 enum" deferred to M1.4 *which* of the spec `#quotelifecycle` statuses (Draft, On-Hold, Sent, Won, Lost, Expired, Cancelled, No-Quote, + Superseded/Trash) become real `quote_status` enum values vs. modelled otherwise. The tier-2 spec ("decided") outranks the folded 5-value `DB-SCHEMA.sql` enum (CLAUDE.md §2), so the enum must grow — but how far in M1.4?
**Decision:** Extend `quote_status` to **8 values**: add `cancelled`, `no_quote`, `on_hold` to the canonical `draft, sent, won, lost, expired`. **`no_quote`** is the *quote-level* decline of the whole RFQ (terminal) — distinct from the existing line-item `qi_workflow_status.no_quote`. **Trash = soft-delete** via a new `quote.deleted_at` (NOT an enum value) — the M1.1/M1.2 convention. **`superseded` is NOT added** in M1.4: it only arises from the revision flow, which is deferred to M5 (see below). Enum values are append-only (ADD VALUE), so M5 can add `superseded` with no rebuild. M1.3's dynamic `QuoteStatus(value)` filter parse picks the new values up for free.
**Resolved:** 2026-06-26 (/block M1.4 grill — supersedes the deferred 2026-06-25 ruling)
**Affects:** M1.4 (enum migration + state machine), M1.3 (filterable values, no change needed), M5 (`superseded` + revisions).

## [2026-06-26] Quote number generation — per-org atomic counter (M1.4)

**Status:** RESOLVED
**Question:** `quote.number` is `text` + `UNIQUE (org_id, number)` but nothing generates it. The spec requires sequential, backend-only, **configurable starting number**, **gaps allowed** ("even a trashed quote increments the counter"), revisions/Copy get new numbers. How to generate it safely under concurrency?
**Decision:** A dedicated org-scoped `quote_counter(org_id PK, last_number bigint NOT NULL DEFAULT 0)` table (RLS, app role gets SELECT/INSERT/UPDATE). Allocation is a single atomic upsert inside the create txn: `INSERT … VALUES (:org, 1) ON CONFLICT (org_id) DO UPDATE SET last_number = quote_counter.last_number + 1 RETURNING last_number` — row-locked, so concurrent creates serialise and never collide; the `UNIQUE (org_id, number)` constraint is the backstop. `last_number` = "last assigned"; **configurable start** = the seed pre-inserts the counter row with `last_number = start − 1` (else numbering begins at 1). **Format = bare integer string** (spec screenshots "15217", "1510") — no prefix/padding. A rolled-back create does **not** consume a number (no gaps from failures); a *committed-then-trashed* quote keeps its number (trash is post-commit) — satisfying "trashed still increments". Revision/Copy numbering arrives with those flows (M5).
**Resolved:** 2026-06-26 (/block M1.4 grill)
**Affects:** M1.4 (counter table + create flow), seed (per-org start), M5 (revision/copy numbering).

## [2026-06-26] QuoteItem anchoring — minimal `component` stub (M1.4)

**Status:** RESOLVED
**Question:** Canonical `quote_item.root_component_id → component(id) → part(id)`, but the full 4-layer Part→Node→Component model is M1.5's scope and `component` doesn't exist yet. How does M1.4 create a quote item without owning M1.5's model?
**Decision:** Follow the proven stub precedent (M1.2 `part`, M1.3 `quote`): M1.4 creates a **minimal `component` stub** — `{id, org_id, part_id → part(stub), is_root_component, created_at, updated_at}` + `UNIQUE (org_id, id)` (the composite-FK target for `quote_item`). The add-line-item flow creates `part(stub) → component(root) → quote_item`. **M1.5 extends `component`** (process, material, `obtain_method`, `is_assembly`, child nodes, BOM) by forward ALTER — no reshaping. Verified against the KB (`assemblies-data-types-and-terminology`: *"the root component is essentially equivalent to a quote item; a quote item simply links a root component to a quote with a position"*), the folded DOMAIN-MODEL, and DemoD/DemoE (line items are parts/components in the tree).
**Resolved:** 2026-06-26 (/block M1.4 grill — KB + domain-model + demo verification requested by Benjamin)
**Affects:** M1.4 (`component` stub + `quote_item`), M1.5 (extends `component`).

## [2026-06-26] On-Hold prior-status memory + status-transition audit (M1.4)

**Status:** RESOLVED
**Question:** Spec: On-Hold is reversible and "returns to the prior status" (Draft or Sent) — so it needs prior-status memory. And win/loss analysis + the optional Lost reason note + reopen imply a transition trail. How to model both?
**Decision:** (1) Add `quote.status_before_hold quote_status NULL`: on entering `on_hold` it records the current status; the un-hold transition's only legal target is that stored status, after which it is cleared. (2) Add an append-only **`quote_status_event(id, org_id, quote_id, from_status NULL, to_status, actor_id NULL, note, created_at)`** (RLS; app role gets SELECT/INSERT only — no UPDATE/DELETE) written on every transition *and* on create (`from_status = NULL → draft`); it carries the Lost reason note and is the audit trail for win/loss + reopen. The state machine is one `transition(session, quote, to, actor_id, note?)` service: validates server-side (rejects illegal transitions with `409 invalid_transition`), enforces the **Draft→Sent contact precondition** (`422 missing_contact` when `contact_id` is null), stamps timestamps (`sent_at`/`expired_at`), and writes the event.
**Resolved:** 2026-06-26 (/block M1.4 grill)
**Affects:** M1.4 (state machine, audit table), M5 (auto-expire sweep + reopen reuse the same service).

## [2026-06-26] M1.4 quote ALTER — composite-FK hardening + scope boundary (M1.4)

**Status:** RESOLVED
**Question:** The M1.3 stub's `account_id`/`salesperson_id`/`estimator_id` are *plain* global FKs (RLS scopes the row but not the FK target's org — a known cross-tenant leak, cf. the M1.1 salesperson ruling), and the stub lacks the canonical quote columns. What does M1.4 add, and where is the scope line vs. M5/M3?
**Decision:** **Harden** by ALTER (not reshape): drop the plain FKs and re-add **composite same-org FKs** — `(org_id, account_id) → account(org_id, id)`, `(org_id, contact_id) → contact(org_id, id)` (adding `uq_contact_org_id_id` first), `(salesperson_id, org_id)`/`(estimator_id, org_id) → user_org_membership(user_id, org_id)`; app layer additionally rejects a non-active member, a `vendor`-type or archived account. **Add** the canonical columns M1.4 needs: `contact_id`, `status_before_hold`, `revision int DEFAULT 0`, `currency char(3) DEFAULT 'EUR'`, `expiration_date`, `expired_at`, `rfq_received_date`, `started_at`, `sent_at`, `estimator_assigned_at`, `salesperson_assigned_at`, `config_frozen_at` (column only — freeze/Refresh-Pricing mechanics are pricing-engine work, E4-d), `private_notes`, `deleted_at` (Trash). **Deferred (not added speculatively):** `send_from_facility_id` (no facility table yet), `digital_last_viewed_at`/`lead_time_display_units`/`mark_sent_or_finalized`/`email_thread_id` → **M5** (send/digital quote); the **revision/reopen/superseded** flows → **M5**; the **`request_for_quote` table** → **M3** (its owner; quote keeps free-text `rfq_number` for direct-create); the **Celery auto-expire sweep** → **M5** (soft-expiry makes it non-urgent; the sweep will reuse the `transition()` service). 4-stage tracker timestamps: `rfq_received_date` set at create, `started_at` set when the first line item is added (the chosen "estimator begins work" heuristic — reversible), `sent_at` on →sent. Permissions: create/edit/ordinary transitions → `quote_edit`; →sent → `quote_finalize`; cancel + trash/restore → `quote_delete` (admin/manager only, per the M0.3 under-grant).
**Resolved:** 2026-06-26 (/block M1.4 grill — Tier-3 defaults accepted by Benjamin)
**Affects:** M1.4 (migration + endpoints), M3 (`request_for_quote`), M5 (send/revision/expire columns + flows), pricing blocks (`config_frozen_at` freeze logic).

---

## [2026-06-25] M1.3 build path — SavedView engine vs. quotes list (M1.4 not yet built)
**Status:** RESOLVED
**Question:** M1.3 ("Saved-view engine + quotes list") hard-depends on M1.4 (`Quote`/`QuoteItem`), which is not built. How to deliver M1.3 without owning M1.4's `quote` table?
**Options considered:** (a) reorder — build M1.4 first; (b) build M1.3 against a **stub** read-only quotes source in the **pinned canonical `quote` row shape** (DB-SCHEMA.sql), shipping the real `SavedView` engine + the list/filter/sort/saved-view UI now; (c) create a minimal real `quote` table here (rejected — double-ownership of M1.4's table + migration).
**Decision:** **(b), realized as a minimal real `quote` stub table** — the idiomatic form of "stub" in this codebase: M1.2 created a minimal `part` table that "M1.5 extends … does not reshape," and M1.3 does the same for `quote`. This gives **real RLS + real server-side SQL filtering** (durable — M1.4 keeps it) and lets the existing `Seeder` plant rows, instead of a low-fidelity in-memory stub that can't exercise the real RLS test harness. **Boundary:** M1.3 creates the minimal `quote` columns needed to **list/filter** (id, org_id, number, status, account_id, salesperson_id, estimator_id, rfq_number, due_date, created_at, updated_at — a subset of the canonical `quote` DDL) + `GET`-via-search list; it grants the app role **SELECT only** (no create endpoint). **M1.4 owns** quote creation, the lifecycle **state machine** (enforced transitions), `quote_item`, the Trash/soft-delete + `cancelled` decisions, and same-org composite-FK hardening — added by ALTER, not by reshaping. `SavedView` is a real org-scoped table (RLS) with `filters`/`sort` JSONB whose shape is **identical** to the `/quotes/search` request body, so applying a view = replaying its stored filters (one grammar, no translation layer).
**Resolved:** 2026-06-25 (/block M1.3 grill + codebase verification — matches the M1.2 `part`→M1.5 stub precedent)
**Affects:** M1.3 (this block), M1.4 (extends `quote` with lifecycle + `quote_item`; hardens FK rigor; grants INSERT/UPDATE).

## [2026-06-25] SavedView sharing / visibility scope
**Status:** OPEN
**Question:** Spec calls saved views "user-owned" (`owner_id`); M1.3 AC says "org/user-scoped." Are views private to the owner, or shareable org-wide? Are there org-default / admin-managed views?
**Options considered:** private-only; private + opt-in org-share; org-default views managed by admins.
**Decision (v1 default, pending review):** **private-only.** `saved_view` is org-scoped (RLS) + `owner_id`; a `visibility` enum column (`private | org`) is **reserved** in the schema but only `private` is honored in v1 (avoids a later migration). System/derived views (All Quotes, My Quotes, Drafts, Outstanding, Overdue) are **computed in code, not stored**. Org-sharing UI deferred (→ M6 candidate).
**Affects:** M1.3 (schema), M6.

## [2026-06-25] `saved_view` absent from canonical DB-SCHEMA.sql
**Status:** OPEN
**Question:** The 53-table canonical `DB-SCHEMA.sql` has no `saved_view` table; the definition exists only as the spec's inline tier-2 build-implication (`view_scope`, `filters` JSONB, `sort`, `owner_id`).
**Decision (proceeding):** Build `saved_view` per the spec build-implication (tier-2 > folded sub-spec). **Action:** fold the resulting DDL back into the canonical `DB-SCHEMA.sql` so the schema stays the single enumerated source.
**Affects:** M1.3, docs/spec/folded-subspecs/DB-SCHEMA.sql.

## [2026-06-25] Quote-level `priority` — home of the field
**Status:** OPEN
**Question:** The quotes grid shows a **Priority** column and the spec's "Highest Priority" saved view filters on it, but the canonical `quote` DDL has **no `priority` column** — the build-implication puts `priority` on `LineItem`. Where does quote-level priority live: on `quote`, derived/aggregated from line items, or both?
**Options considered:** quote-level enum column; derived MAX over line-item priorities; both (quote default + per-line override).
**Decision (revised — do not guess on a contested schema field):** M1.3's `quote` stub **does NOT add a `priority` column**, and **`priority` is dropped from the v1 filterable field set** (block-and-log: priority's home is genuinely open, and adding a column would commit schema to a contested field that may move to `line_item`). The quotes grid shows a Priority column rendered as a placeholder ("—") for now. The "Highest Priority" demo saved view is an *example*, not a hard M1.3 requirement, and is deferred. v1 filterable fields are therefore: `status`, `account_id`, `salesperson_id`, `estimator_id`, `created_at` (range), plus computed system views (My Quotes, Overdue via `due_date`). **M1.4/M1.6 decide priority's home**, then it can be added to the grammar with no breaking change (new allow-listed field).
**Affects:** M1.4, M1.6, M1.3 (filter grammar + grid placeholder).

## [2026-06-25] Quote status: 7 UI "folders" vs. 5-value canonical enum
**Status:** OPEN
**Question:** The spec narrative lists **7 status folders** (Drafts, Outstanding, Accepted, Expired, Lost, Cancelled, Trash); the canonical `quote_status` enum has **5 values** (`draft, sent, won, lost, expired`). Mapping: Drafts→draft, Outstanding→sent, Accepted→won, Expired→expired, Lost→lost; **Cancelled** and **Trash** are unmapped (Trash ≈ soft-delete; Cancelled ≈ ?).
**Decision (proceeding):** out of M1.3 scope — M1.3 filters/displays whatever `quote_status` exists. **Flagged for M1.4** (owns the enum + lifecycle): decide whether to add `cancelled` to the enum and treat Trash as soft-delete.
**Affects:** M1.4 (quote lifecycle enum).

---

## [2026-06-14] Product name and domain
**Status:** RESOLVED  
**Question:** "Bid Factory" is a working title only. The product needs a real name before domain registration, Mailgun EU domain verification, Clerk OAuth redirect URIs, email from-addresses, and PDF/UI branding can be finalised.  
**Decision:** **Tolera** — domain **tolera.eu**, app at **app.tolera.eu**, RFQ ingest at **rfq.tolera.eu**. `BRAND` config object must be parameterised from day one — no hardcoded product name strings in code.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M0 (branding config), Mailgun setup, Clerk setup, all customer-facing strings.

---

## [2026-06-14] Google OAuth security review timeline
**Status:** RESOLVED  
**Question:** Gmail OAuth `gmail.readonly` scope triggers a Google security review (2–3 weeks). Users see a security warning screen until approved.  
**Decision:** Ship Gmail connect behind the warning screen for the pilot. Submit the review on day one of infrastructure setup. Do not block M3 on review approval.  
**Affects:** M3 (email threading). Google app registration must be submitted before build starts.

---

## [2026-06-14] Spatial / HOOPS licensing timeline
**Status:** RESOLVED  
**Question:** Spatial licensing for native SLDPRT import and advanced feature recognition is in procurement.  
**Decision:** Build entirely on OCCT (pythonocc) for v1. Spatial swaps in post-pilot when licensing is confirmed. `GeometryService` abstraction must require zero changes above the service layer on swap.  
**Affects:** M4 (geometry). Document Spatial-upgradeable capabilities in `GEOMETRY.md`.

---

## [2026-06-14] Würth API access
**Status:** RESOLVED  
**Question:** `WürthMaterialPricingAdapter` requires API credentials not yet obtained.  
**Decision:** Build adapter against a fixture response (documented JSON schema). Real credentials slot in without code changes. Do not block M6 on Würth procurement.  
**Affects:** M6 (differentiators).

---

## [2026-06-14] Pilot customer org slug for RFQ ingest
**Status:** RESOLVED  
**Question:** The email ingest route is `{org-slug}@rfq.tolera.eu`. What is the pilot customer's org slug?  
**Decision:** Pilot org slug = **fechner**. Ingest address: **fechner@rfq.tolera.eu**. Seed their org with slug `fechner` in M0 fixtures.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M3 (email ingest), M0 (org seed).

---

## [2026-06-14] Margin math for mixed markup + margin pricing items
**Status:** RESOLVED  
**Question:** Margin contribution formula — verify `cost × pct/(1−pct)`.  
**Decision:** Confirmed. Formula is `cost × pct/(1−pct)` — verified against Paperless Parts pricing documentation (`Margin % = (Selling Price − Cost) / Selling Price × 100` rearranged to `Selling Price = Cost / (1−pct)`, profit = `cost × pct/(1−pct)`). Build M1 with this formula. Add a margin-type fixture case to the M1 golden-test suite once Benjamin supplies a test case with known cost + output price.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M1 (pricing engine). High priority — incorrect margin math breaks every quote.

---

## [2026-06-14] German translation strings
**Status:** RESOLVED  
**Question:** Who does native German review, and when?  
**Decision:** Use Claude-generated German strings throughout the build. Fechner (pilot customer, native German speakers) will review all UI strings and provide feedback before pilot go-live. Formal review happens between pilot start and first paying customer.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M5 (de-DE catalog). Non-blocking for pilot.

---

## [2026-06-14] SOLIDWORKS connector target surface
**Status:** RESOLVED  
**Question:** The CAD connector spec lists SOLIDWORKS as a fast-follow after Fusion. Target surface (PDM vs 3DEXPERIENCE vs desktop add-in) is still open.  
**Options considered:** Desktop add-in (most common for SME shops); PDM (larger shops); 3DEXPERIENCE (enterprise).  
**Decision:** **Deferred post-pilot, with the desktop add-in as the default target.** When built, target the SOLIDWORKS **desktop add-in** (most common for SME DACH shops like Fechner); revisit PDM/3DEXPERIENCE only if a real customer requires it. Do not build until confirmed by customer signal during/after the pilot.  
**Resolved:** 2026-06-21  
**Affects:** Post-v1.

---

## [2026-06-14] Belgian locale (nl-BE vs fr-BE)
**Status:** RESOLVED  
**Question:** When Belgian locale ships, primary language must be decided (Dutch / French / bilingual).  
**Decision:** **Dropped from the roadmap.** Tolera targets DACH (DE/AT/CH) only for the foreseeable future; Belgium (nl-BE/fr-BE) is out of scope and removed from the post-pilot backlog. Revisit only if clear, sustained demand appears — at which point default to bilingual nl-BE + fr-BE with a language picker.  
**Resolved:** 2026-06-21  
**Affects:** Out of scope (was Post-v1).

---

## [2026-06-14] CRM conflict resolution granularity
**Status:** RESOLVED  
**Question:** When HubSpot and Tolera have conflicting data for the same Account or Contact, what wins?  
**Decision:** Tolera-always-wins for v1 (simplest; avoids merge logic). Add field-level conflict resolution as a post-pilot HubSpot adapter upgrade.  
**Affects:** M6 (HubSpot adapter).

---

## [2026-06-14] Quote PDF visual design
**Status:** RESOLVED  
**Question:** WeasyPrint quote PDF template needs an approved layout before M5 implementation.  
**Decision:** **Design folded into the M5 build block** — no separate pre-M5 design session and no starter template up front. The M5 builder designs *and* implements the WeasyPrint quote-PDF template as part of M5, working from the digital-quote spec section. Fixed constraint (unchanged): the PDF is **fully white-label** (org logo, brand colours, no Tolera branding visible to the customer). Supersedes the earlier "design session at M4" note.  
**Resolved:** 2026-06-21 — white-label confirmed 2026-06-19; layout ownership moved into M5.  
**Affects:** M5 (quote PDF output) — now self-contained in the M5 block, no longer a separate pre-M5 blocker.

---

## [2026-06-19] AI assistant name
**Status:** RESOLVED  
**Question:** What is Tolera's name for the AI extraction/assistant layer (was "Wingman" in early spec)?  
**Decision:** **Lens**. Purple signal colour. AI Governor pattern (55% opacity until accepted). All spec references updated.  
**Affects:** All milestones. UI copy throughout.

---

## [2026-06-19] Pricing formula language name
**Status:** RESOLVED  
**Question:** What is Tolera's name for the formula DSL (was "P3L" / "Paperless Parts Pricing Language")?  
**Decision:** **Kalk**. Python-based, AST-sandboxed. Three contexts: pricing formulas, operation generation, operation cost formulas. All spec references updated.  
**Affects:** M1 (pricing engine), M2 (operation library), all Kalk editor UI.

---

## [2026-06-19] Partner integration names
**Status:** RESOLVED  
**Question:** What are Tolera's names for the partner integration slots (was TechMate / PEMConnect)?  
**Decision:** Advisory chat partner → **Tolera Advisor**. Fastener sourcing partner → **Tolera Source**. Both mocked in v1. All spec references updated.  
**Affects:** M6 (integrations), Part Viewer UI.

---

## [2026-06-19] Login type / auth flow
**Status:** RESOLVED  
**Question:** Is email login magic-link (passwordless) or password-first?  
**Decision:** **Password-primary, magic-link fallback.** Clerk also provides Google SSO and Microsoft SSO (via Clerk's OAuth providers). Passkey (WebAuthn/FIDO2) also available via Clerk. Spec updated on auth table.  
**Affects:** M0 (auth setup), Clerk configuration.

---

## [2026-06-19] Fixture packages
**Status:** RESOLVED (pending delivery)  
**Question:** When will 5–10 anonymised Fechner RFQ fixture packages be available for golden-test suite?  
**Decision:** Benjamin has access to the packages. Target delivery: Monday 2026-06-23. Build M1 golden-test suite structure now; slot fixtures in on delivery.  
**Affects:** M1 (golden tests), M3 (email ingest tests).

---

## [2026-06-19] Multi-organization users (E4-a)
**Status:** RESOLVED
**Question:** Should one user be able to belong to multiple orgs and switch between them (distinct from multi-tenancy)?
**Decision:** **In v1.** Build a `UserOrgMembership` (User⋈Org M:N, role per membership), active-org as session state (Clerk claim), an org switcher in the top-bar account menu, and cross-org notifications (labeled, switch-on-select). Membership model required from M0 so it isn't retrofitted into auth. Not exercised at the (single-org) Fechner pilot but must exist in the schema. See `E4-Behavioral-Gaps.md` §E4-a.
**Affects:** M0 (auth/session, data model), App Shell, Notifications.

## [2026-06-19] Pricing-config-change policy (E4-d)
**Status:** RESOLVED
**Question:** When pricing config (operations, Kalk, materials) changes, what happens to existing draft quotes / revisions?
**Decision:** **Freeze + manual refresh** (Paperless Parts model). Existing drafts/revisions keep pricing; only new quotes reflect config changes. Provide `Regenerate Operations` (no overrides), `Refresh Pricing` (single), `Bulk Refresh Pricing` (multi-select), with manual post-refresh cleanup. See `E4-Behavioral-Gaps.md` §E4-d.
**Affects:** M1 (pricing engine), Quote Detail (Process actions), quote lifecycle.

## [2026-06-19] Analytics scope (E4-k)
**Status:** RESOLVED
**Question:** Ship analytics as a stub, a fixed dashboard, or the full query-builder?
**Decision:** **Full query-builder** — a BI semantic layer of measures + dimensions across ~20 entities, time/filters, user dashboards + query editor, seeded with the 12-tile default dashboard. Replicate only the working fields (omit KB-flagged broken/deprecated ones); Segments are out (non-functional). Consider a semantic-layer lib over the Postgres warehouse. See `E4-Behavioral-Gaps.md` §E4-k. Replaces the prior "Analytics tab = stub" note.
**Affects:** New analytics milestone (sizeable build), data warehouse.

## [2026-06-19] E4 post-pilot deferrals (E4-e/f/g)
**Status:** RESOLVED
**Question:** Are MBD/PMI viewing, the on-prem managed connector, and MSSQL direct-DB import in v1?
**Decision:** **Post-pilot.** MBD/PMI needs Spatial-grade extraction (v1 OCCT can't); managed connector + MSSQL import are covered for v1 by adapters + SFTP. Keep viewer toggle / adapter interfaces as stubs; build later. See `E4-Behavioral-Gaps.md` post-pilot section.
**Affects:** Post-v1 (geometry/PMI, integrations).

## [2026-06-23] Local config / secrets loader — Infisical → `.env` + pydantic-settings
**Status:** RESOLVED
**Question:** The spec's seed CLAUDE.md (`#devworkflow`) says secrets load "from environment via **Infisical** (self-hosted on Hetzner)." The newer M0.0 runbook instead standardises on a gitignored **`.env`** (dev) + **GitHub Actions secrets** (CI) + **Kamal secrets** (prod). Which governs the build?
**Decision:** **Follow M0.0 — `.env` + `pydantic-settings` now; GitHub Actions + Kamal secrets for CI/prod; Infisical dropped for v1.** Real environment variables override `.env`, so Docker Compose / CI inject config without editing files. The committed `.env.example` is the env contract (names only). Revisit a dedicated secrets manager post-pilot only if operational need appears. Supersedes the spec's Infisical wording (this tier-1 entry wins per `CLAUDE.md` §2).
**Resolved:** 2026-06-23 (M0.1 grill)
**Affects:** M0.1 (config module), every later block's settings, CI, deploy.

## [2026-06-23] Python runtime version — 3.12
**Status:** RESOLVED
**Question:** The `uv init` scaffold pinned Python `>=3.10`; the spec (`#stack`, `#devworkflow`) specifies Python **3.12**.
**Decision:** **Pin 3.12** — `.python-version` = `3.12`, `requires-python = ">=3.12,<3.13"`, ruff/mypy target `py312`, Docker `python:3.12-slim` — so dev matches prod. Matches the spec; not a deviation, recorded for traceability.
**Resolved:** 2026-06-23 (M0.1 grill)
**Affects:** M0.1 (pyproject, Docker, CI).

## [2026-06-24] Membership role cardinality — multi-role per membership (M0.2)
**Status:** RESOLVED
**Question:** Does a `UserOrgMembership` carry exactly one role or many? Tier conflict: tier-1 E4-a says *"role per membership"* (reads singular) and the folded `DB-SCHEMA.sql` has `role membership_role NOT NULL`; tier-2 spec `#authz` says *"users may hold multiple roles; effective permissions = union"* and the `#auth` invite modal is a multi-select (`roles TEXT[]`). Schema-shape, expensive to migrate later (touches every permission check).
**Decision:** **Multi-role from the start.** `user_org_membership.roles membership_role[]` — `NOT NULL`, enforced non-empty (CHECK `cardinality(roles) > 0`). M0.3's `require()` computes effective permissions as the **union** across the array. Resolves the conflict in favour of the explicit spec model; "role per membership" (E4-a) is read as "a role set attached to each membership," not "exactly one." The single `role` column in the folded schema is superseded (folded schema is frozen provenance; tier-2 spec + this tier-1 entry win per `CLAUDE.md` §2).
**Resolved:** 2026-06-24 (M0.2 grill)
**Affects:** M0.2 (schema: membership table), M0.3 (permission matrix = union over roles), M5.12 (invite/role-edit UI).

## [2026-06-24] RLS enforcement mechanism + DB role split (M0.2)
**Status:** RESOLVED
**Question:** How is org-scoped Row-Level Security actually enforced *at the DB*? The folded `DB-SCHEMA.sql` only *notes* "enforce RLS by org_id" — no `CREATE POLICY` DDL, no session-variable mechanism, and M0.1 ships a single `tolera` DB role that owns the schema. Postgres RLS is **bypassed for a table's owner / superusers** unless forced, so naïve policies would be a silent no-op (and the cross-org test could pass for the wrong reason). M0.2 must *define* the pattern every later block inherits.
**Decision:** **Two-role split + forced RLS.** (1) Migrations/DDL run as the **owner/admin** role; (2) the **application connects as a dedicated restricted role** (`NOBYPASSRLS`, not the table owner). (3) Every tenant-scoped table gets `ENABLE` **and** `FORCE ROW LEVEL SECURITY`. (4) Org context is carried per-request as a transaction-local GUC: `SET LOCAL app.current_org_id = :org`, with policies keyed on `current_setting('app.current_org_id', true)::uuid` (`missing_ok = true` so an unset GUC yields zero rows rather than erroring). (5) The org-scoped DB session is transaction-scoped and the GUC is set after auth resolves the active org; connections are reset on pool check-in. This is the **inherited tenancy pattern** for all later blocks. Requires a docker-compose + connection-config change to provision the two roles.
**Resolved:** 2026-06-24 (M0.2 grill)
**Affects:** M0.2 (RLS policies, DB roles, docker-compose, db session), every later org-scoped table.

## [2026-06-24] Org identity model — Clerk native Organizations + webhook mirror (M0.2)
**Status:** RESOLVED
**Question:** DECISIONS (Login type / E4-a) says *"active-org as session state (Clerk claim)."* Do we use **Clerk's native Organizations** feature (Clerk orgs ↔ our `organization`, Clerk membership + active-org in the session) and mirror to our DB, or model orgs entirely in our DB and carry a self-managed `active_org_id` custom claim with Clerk doing identity only?
**Decision:** **Clerk native Organizations.** Clerk is the source of user identity, org membership existence, and the **active-org session claim**; memberships are **mirrored into our tables via Clerk webhooks** (`organizationMembership.created/updated/deleted`). The **app role is authored in our DB** (`user_org_membership.roles`) — our domain roles (estimator/salesperson/outside-service/…) are richer than Clerk's member/admin, so Clerk org roles are kept minimal and not the authority for app permissions. The active-org claim is verified server-side and drives the RLS GUC. Matches the spec `#auth` webhook-sync build notes.
**Resolved:** 2026-06-24 (M0.2 grill)
**Affects:** M0.2 (auth wiring, active-org claim, webhook endpoint stub), M0.4 (org switcher), M5.12 (invite → Clerk invitation).

## [2026-06-24] Authorization role set — adopt the 7 spec personas + retain `viewer` (M0.3)
**Status:** RESOLVED
**Question:** Three sources disagree on the canonical role enum. M0.2 shipped `membership_role = {admin, estimator, salesperson, viewer}` (a 4-value starter); the build-plan M0.3 example lists "Admin, Manager, Estimator, Salesperson, Viewer" (5, *"confirm against the spec"*); the authoritative spec `#authz`/`#personas` matrix defines **7** roles — Admin, Exec/Manager, Sales, Estimator, Engineer, Material/Purchasing, Outside-Service — and has **no Viewer**. The enum is schema (a Postgres type), expensive to reshape later and touched by every permission check.
**Decision:** **Adopt the 7 spec personas and keep `viewer` as an 8th, explicitly-non-spec read-only role.** Final `membership_role` = `{admin, manager, salesperson, estimator, engineer, material_purchasing, outside_service, viewer}`. Existing M0.2 spellings (`admin/estimator/salesperson/viewer`) are kept verbatim to avoid a PG enum *rename* (painful, breaks the M0.2 tenancy test); the migration only **adds** the four new values (`manager`, `engineer`, `material_purchasing`, `outside_service`). `viewer` is retained (not in the spec) because dropping a PG enum value requires a full type-rebuild and would break M0.2's `test_tenancy`; it is granted **`view_all` only**. The extension migration is **reversible** (CLAUDE.md §5 — reversible migrations only): `upgrade` adds the values online (`ALTER TYPE … ADD VALUE`, no table rewrite); `downgrade` rebuilds the type to the M0.2 set and re-casts the one dependent column (`user_org_membership.roles`) through `text[]`, raising by design if any membership still uses an M0.3 role (block the rollback rather than lose data). *(Tightened from an initial no-op-downgrade plan during M0.3 code review, to honor the reversible-migration convention.)*
**Resolved:** 2026-06-24 (M0.3 grill)
**Affects:** M0.3 (role enum, migration, permission matrix), M0.5 (seeded memberships use real roles), M5.12 (role-edit UI).

## [2026-06-24] Permission matrix — role-level only; owner/assigned/annotate refinements deferred (M0.3)
**Status:** RESOLVED
**Question:** The spec `#authz` matrix has cells that are **not** pure role→allow: Delete = *"owner"* for Sales/Estimator (only quotes they own); Create/edit = *"view + annotate"* for Engineer/Material/Outside (read + comment, not edit costing); review-step update is *per-assigned-stage*. M0.3 has no `QuoteItem`/ownership/`WorkflowStep` to evaluate object-level conditions against, and the build-plan defers "field-/object-level ABAC beyond role + org (post-pilot)." How permissive should M0.3 be in the meantime?
**Decision:** **Under-grant, never over-grant.** The matrix is **role → capability boolean** only. (1) `quote_delete` is granted to **admin + manager only** — Sales/Estimator get *no* delete in M0.3 (granting it role-wide would let them delete *any* quote, strictly more permissive than the spec's owner-only); owner-scoped delete is added when ownership exists (M1/M5). (2) "view + annotate" is modelled as a real `quote_annotate` capability (held by all 7 spec roles) distinct from `quote_edit` (admin/manager/sales/estimator), so Engineer/Material/Outside are correctly read-plus-annotate, not edit. (3) `review_step_update` enforcement is **deferred to M1** (no quote item/stage yet); granted coarsely to admin/manager, the granular per-stage/assigned mapping lands with `WorkflowStep`. Object-/field-level ABAC remains post-pilot.
**Resolved:** 2026-06-24 (M0.3 grill)
**Affects:** M0.3 (permission matrix), M1 (QuoteItem ownership + WorkflowStep → owner/stage refinement), post-pilot (ABAC).

## [2026-06-24] Manager may finalize/send/convert — intentional divergence from spec `#authz` (M0.3)
**Status:** RESOLVED
**Question:** The spec `#authz` matrix marks Finalize/Send/Convert as `—*` for Exec/Manager: an Exec gets it **only** if also granted a Sales or Estimator role (footnote: *"kept off the Exec preset to mirror the Sales + Estimators + Admin decision"*). Should Tolera keep that exclusion?
**Decision:** **Diverge from the spec — grant `quote_finalize` to `manager` directly** (Benjamin's call). A manager no longer needs a union'd sales/estimator role to send/convert/edit-orders. This is a deliberate override recorded here so it is not later read as a transcription error; per `CLAUDE.md` §2 a tier-1 `DECISIONS.md` entry overrides the spec. Net effect: `admin` and `manager` hold an identical permission set in M0.3 (the two diverge only if a later capability distinguishes them).
**Resolved:** 2026-06-24 (M0.3 grill)
**Affects:** M0.3 (permission matrix — manager row).

## [2026-06-24] Primary navigation pattern — sidebar wins over top-bar tabs (M0.4)
**Status:** RESOLVED
**Question:** The spec is internally inconsistent on the global nav surface. `#ui-system` (confirmed 2026-06-13, with `BidFactory-LiveMock.html` as the reference implementation) states the **dark sidebar** is "the primary navigation surface" (216/56 px, `[` collapse toggle, `localStorage` persistence). `#shell` instead describes a persistent **dark top bar with horizontal nav tabs**. Same spec tier — which is authoritative?
**Decision:** **Sidebar.** The collapsible dark sidebar is the primary nav surface (per the newer, explicitly *confirmed* `#ui-system` + its live reference mock); `#shell`'s top-bar-tabs layout is superseded. The **destinations** still come from `#shell` (Dashboard, Parts, Quotes, Orders, Contacts, Configure, Analytics). Global search lives in the sidebar top row; the account menu + org-switcher live in the sidebar's bottom account area (see next entry). Resolves a tier-2-internal conflict per CLAUDE.md §2 ("more specific / more recent confirmed wins").
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (app shell layout), and every screen rendered inside the shell thereafter.

## [2026-06-24] Org-switcher location — sidebar account area (amends E4-a) (M0.4)
**Status:** RESOLVED
**Question:** The "Multi-organization users (E4-a)" decision (2026-06-19) places the org-switcher in the **top-bar account menu**. M0.4 adopts a sidebar-primary layout with **no top bar** (previous entry). Where does the switcher live, and how functional is it in M0.4?
**Decision:** The org-switcher lives in the **sidebar bottom account area** (alongside the user/account menu) — a wording amendment to E4-a, consistent with the confirmed sidebar design system; the substance of E4-a (switcher exists in v1, active-org as session state, cross-org notifications labelled) is unchanged. **M0.4 ships a stub:** it lists the user's memberships (from `/api/me`) and highlights the active org resolved from the JWT claim; the actual *switch* action (token re-mint via Clerk's native Organizations) is **deferred to M5.12**, where the membership-table → session-token sync is built. This satisfies the M0.4 acceptance criterion ("switcher lists the user's memberships") without depending on un-built sync.
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (org-switcher stub), M5.12 (real switching + membership/token sync).

## [2026-06-24] Default colour mode — light, both token sets shipped (M0.4)
**Status:** RESOLVED
**Question:** `#ui-system` states *"Active defaults: `data-theme=claude` · `data-mode=light`"*, but the build-plan M0.4 scope line says *"dark theme per the design system."* Which is the v1 default colour mode? (A spec-vs-build-plan conflict; per CLAUDE.md §2 the spec outranks the build-plan execution map.)
**Decision:** **Default `data-mode="light"`** per the spec's explicit active default. Both the full light *and* dark token sets (CSS custom properties, the warm-dark palette `#ui-system` specifies) are shipped, with a persisted toggle (the build-plan's "dark theme" is honoured as *shipped & selectable*, not as the default). Reversible — it is a single default value, no schema impact.
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (theming / design tokens).

## [2026-06-24] `/api/me` session-bootstrap contract + permission-gated nav (M0.4)
**Status:** RESOLVED
**Question:** The app shell needs the current user, their active org (name/locale/currency/country), their cross-org memberships (for the switcher), and what nav/actions to show. No such endpoint exists. What is the contract, and does nav gate on roles or capabilities?
**Decision:** Add **`GET /api/me`** (authenticated) returning `{ user, active_org, memberships[], effective_permissions[], roles[] }` — `active_org` carries locale/currency/country/slug/name; `roles`/`effective_permissions` are derived from the **active membership row** (the DB, which `user_org_membership` makes authoritative) via `app.authz.permissions_for(...)` (the M0.3 single source of truth) — **not** the JWT `principal.roles` cache, so a briefly-stale claim can't make the payload overstate access or self-contradict `memberships[*].roles`. The frontend **gates nav/actions on capabilities** (e.g. *Configure* requires `config_edit`), never re-encoding the role→capability matrix client-side. (API-layer `require()` still keys on the claim in M0.3; M5.12 keeps claim↔membership in sync.)
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (`/api/me`, permission-gated nav), all later UI that conditions on permissions.

## [2026-06-24] `/api/me` cross-org identity read under RLS — SECURITY DEFINER function (M0.4)
**Status:** RESOLVED
**Question:** The M0.2 migration deliberately grants the restricted `tolera_app` role **no access to `app_user`** (global PII, no org scope) and applies **FORCE RLS** keyed to the active org on `organization`/`user_org_membership`. `/api/me` must read the caller's *own* identity (name/email) and *cross-org* memberships — neither reachable through the normal request path. The migration's own note defers this: *"a later block that must surface users will mediate via … a scoped view."* How does M0.4 read it safely? (DB-schema + security — block-and-log §6, never guessed.)
**Decision:** A **`SECURITY DEFINER` SQL function** `app_current_identity() → jsonb` (migration `0004`), owned by a dedicated **`BYPASSRLS`, `NOLOGIN`** role `tolera_identity` (a plain table-owner would still be subject to *FORCE* RLS), with a pinned `search_path`, returning `{user, memberships[]}` for the caller identified by the **transaction-local `app.current_user_id` GUC** (stamped by `app.deps.get_session` from the verified principal). The function takes **no argument** — binding to the GUC rather than a parameter means the *database* enforces "read only yourself"; there is no user-id argument to steer at another user. `tolera_app` gets `EXECUTE` only (revoked from `PUBLIC`). **RLS on every table is left untouched** (smallest blast radius); the one privileged path is a single audited function. The `tolera_identity` role follows the M0.2 `tolera_app` precedent (ensure-exists in-migration; attributes provisioned by infra in prod). Rejected: per-user GUC + RLS policy widening (broadens the visibility model app-wide) and a privileged BYPASSRLS connection in the request path (a code slip leaks everything; contradicts the fail-closed design).
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (`0004` migration, `/api/me`), any later user-surfacing read (reuses this function/pattern).

## [2026-06-24] Seed framework — Clerk provisioning scope (M0.5)
**Status:** RESOLVED
**Question:** Spec `#onboarding` says the seed script "calls `Clerk.organizations.createMembership()` for the admin user (Clerk fires the invite email)". But `SEED-AND-FIXTURES.md` reuses the *same* idempotent runner for tests (every test run seeds a clean org), where hitting the Clerk API is neither idempotent nor desirable. Should the M0.5 seed call the Clerk API, or only write DB rows?
**Options considered:** (A) DB-only seed — create `Organization`/`AppUser`/`UserOrgMembership` rows idempotently; `clerk_user_id`/`clerk_org_id` left nullable; "login works" proven in tests via the existing `authed()` Principal injection + RLS isolation; real Clerk linkage (createMembership/invite + claim metadata) deferred to the established Clerk→DB webhook mirror (M0.2 stub → M5.12) or a one-off `--with-clerk` side-effect run for the real pilot. (B) Call the Clerk API now (create org + invite admin + set `tolera_*` metadata), mocked/skipped in tests.
**Decision:** **(A) DB-only.** The seed is the DB source of truth; Clerk identity linkage is a separate, deferred side-effect handled by the already-decided *Clerk native Organizations + webhook mirror* path (2026-06-24, M0.2). The spec's "seed calls Clerk" remains the eventual provisioning behaviour for a *real* new org, layered on later — it does not belong in the idempotent, test-reused M0.5 runner. The M0 exit "login works" is satisfied at the test level (a seeded principal authenticates against the seeded pair + cross-org denial passes); real Clerk login is wired when the webhook/`--with-clerk` path lands.
**Resolved:** 2026-06-24 (M0.5 grill)
**Affects:** M0.5 (seed framework), M0.2/M5.12 (Clerk webhook + user-management). Spec-vs-practicality tension logged here per block-and-log (§6).

## [2026-06-24] M0.5 seed scope — §1 only, migration-free
**Status:** RESOLVED
**Question:** `seed.skeleton.json`'s `organization` block carries `default_tolerance_class`, `export_regime`, `brand`, and `rfq_ingest`, but none of these columns exist on the `Organization` model (M0.2). Does M0.5 add them?
**Decision:** **No — M0.5 ships zero new migration.** Scope is `SEED-AND-FIXTURES.md` Part 1 §1 only (org identity + users + `user_org_memberships`), seeding only columns that already exist (`slug`/`name`/`country`/`currency`/`locale`). `rfq_ingest` is **derived** from the slug (`{slug}@rfq.tolera.eu`) per the 2026-06-14 pilot-slug decision, not stored. `default_tolerance_class` (→ M1/geometry), `brand`/white-label (→ M0.4), and `export_regime` (→ M6 export control) are each deferred to their consuming block, which adds the column via its own reversible Alembic migration. The remaining `seed.skeleton.json` sections (materials, 54-op library, processes, interrogation profiles, pricing, rules, templates) are out of M0.5 → extend the framework in M1.12.
**Resolved:** 2026-06-24 (M0.5 grill)
**Affects:** M0.5 (seed scope), M0.4 (brand column), M1 (tolerance/catalog), M6 (export regime).

## [2026-06-24] Second seed org identity (M0.5)
**Status:** RESOLVED
**Question:** The build-plan seeds "two orgs (incl. `fechner`)" to drive the cross-org denial test, but only specifies fechner. What is org #2?
**Decision:** A minimal second org: **`currency=EUR`, `locale=en`** (English UI, to exercise the non-`de` path) — distinct from fechner's `de-DE`. `Organization.country` is a hard enum (`DE`/`AT`/`CH` only, no "EN"), so country is set to **`DE`** (a valid enum value; the org merely prefers English UI). Slug/name are demo data (reversible). One global `AppUser` may hold memberships in both orgs (E4-a) so the framework can later feed M0.4's org-switcher test.
**Resolved:** 2026-06-24 (M0.5 grill)
**Affects:** M0.5 (seed), M0.4 (org-switcher test fixture).

## [2026-06-25] Contact↔Account cardinality — `contact.account_id` nullable (M1.1)
**Status:** RESOLVED
**Question:** `DB-SCHEMA.sql` declares `contact.account_id` **nullable** (`REFERENCES account(id)`), but `DOMAIN-MODEL.md` §3 says a Contact "belongs to **exactly one** Account." Which governs the column M1.1 creates? (Schema/FK — expensive to reverse, block-and-log §6.)
**Decision:** **Nullable** — the canonical DDL wins on the column. The domain "exactly one account" is the *happy path* the CRUD UI always follows (a contact is created under an account), but the column stays nullable because RFQ intake (M3) will create account-less contacts before an account exists, and **loosening** a NOT NULL later would need a data backfill while **tightening** is cheap. The list/detail UI treats an account-less contact as an edge state, not the norm.
**Resolved:** 2026-06-25 (M1.1 grill)
**Affects:** M1.1 (contact model/migration), M3 (RFQ-origin contacts), any quote↔contact wiring (M1.4: "every quote requires a contact").

## [2026-06-25] Soft-delete × unique email — partial unique index on `contact` (M1.1)
**Status:** RESOLVED
**Question:** `DB-SCHEMA.sql` puts `UNIQUE (org_id, email)` on `contact`, but contacts are soft-deleted (`deleted_at`). A plain unique constraint would let an **archived** contact's email permanently block re-creating a contact with that address. Is that intended? (Schema/constraint — cheap now, painful after data lands.)
**Decision:** Replace the table-level unique with a **partial unique index** `UNIQUE (org_id, email) WHERE deleted_at IS NULL`, so email is unique only among *live* contacts and an archived email frees up for reuse. This is the general soft-delete + natural-key pattern; later org-scoped tables with a soft-deletable natural key reuse it. (Account name is intentionally **not** unique — multiple sites/legal entities may share a name — so it needs no such index.)
**Resolved:** 2026-06-25 (M1.1 grill)
**Affects:** M1.1 (contact migration), the soft-delete convention for later natural-key tables.

## [2026-06-25] Archive semantics + cascade for Account/Contact (M1.1)
**Status:** RESOLVED
**Question:** The M1.1 slice says "archive an Account and its Contacts." What does *archive* mean concretely, what happens to an archived account's contacts, and is hard delete in scope? (Data-lifecycle — defines what "archive" means for every downstream reader.)
**Decision:** **Archive = soft-delete** (set `deleted_at`); it is **reversible via Restore** (clear `deleted_at`). Default list endpoints exclude archived rows; a direct `GET /{id}` still returns an archived row (so the detail/restore UI works); `?include_archived=true` opts a list back in. **Archiving an account does *not* mutate its contacts' `deleted_at`** — instead the **cross-account** contact list (`GET /api/contacts`) excludes contacts **whose account is archived** (they disappear from general browsing with the account, but a Restore brings them back intact, and no child rows are silently rewritten). The **per-account** list (`GET /api/accounts/{id}/contacts`, the account-detail Contacts tab) still shows them even when the account is archived, since you've navigated into that specific account to review/restore it. **No hard delete in v1** (no `DELETE` route — and the restricted DB role is granted only `SELECT/INSERT/UPDATE`, not `DELETE`). Archive/restore are gated on `quote_delete` (the only role granted destructive-ish actions in the M0.3 matrix); create/edit on `quote_edit`.
**Resolved:** 2026-06-25 (M1.1 grill)
**Affects:** M1.1 (account/contact archive+restore endpoints, list filters), all later list/detail surfaces that read accounts/contacts, M6 CRM-sync (archive ≠ delete on the CRM side).

## [2026-06-25] Salesperson assignment must be an active member of the active org (M1.1)
**Status:** RESOLVED
**Question:** `account.salesperson_id` / `contact.salesperson_id` reference **`app_user`**, which is **global, not org-scoped** (no `org_id`, no RLS). So org RLS *cannot* stop assigning a salesperson who belongs to a different org (or to no org at all) — a cross-tenant identity leak. How is the assignment constrained? (Security/tenancy — never guessed, block-and-log §6.)
**Decision:** Guard at **two layers** (defense in depth):
1. **DB (schema):** the `salesperson_id` column carries **no direct `app_user` FK**; instead a **composite FK `(salesperson_id, org_id) → user_org_membership(user_id, org_id)`** makes "is a member of *this* org" a database invariant a cross-org reference physically cannot satisfy. (Likewise `contact.account_id` uses a composite FK to `account(org_id, id)` so a contact's account is same-org.) Identity to `app_user` is preserved transitively via the membership row.
2. **App (write path):** create/edit additionally validates that a non-null `salesperson_id` resolves to an **`active`** membership (the FK alone permits a `disabled` one) and returns the clean envelope **`422` code `invalid_salesperson`** rather than surfacing a DB error.

The check runs through the org-pinned session, so it reads only the active org's memberships. We deliberately **do not** require the assignee to hold the `salesperson` *role* — any active member is assignable (matches PP).

> Strengthened during the M1.1 CodeRabbit review (2026-06-25): the original plan kept a direct `app_user` FK + app-layer check only; the composite-FK approach makes the tenancy guarantee a DB invariant, not merely RLS/app-enforced.

**Resolved:** 2026-06-25 (M1.1 grill; FK approach strengthened in review)
**Affects:** M1.1 (account/contact schema + write validation + test), any later entity that references a `User`/account cross-row (reuse the composite-FK-to-membership pattern + active-member check).

## [2026-06-25] M1.2 file-owner model — files attach to `part`; minimal `part` stub created now (M1.2)
**Status:** RESOLVED
**Question:** What entity owns an uploaded file in M1.2? The canonical `DB-SCHEMA.sql` models `part_file.part_id → part(id)` + `part.primary_file_id`, and the spec/KB are explicit that files belong to a **Part** (PRIMARY = the part's geometry source of truth). But the M1.2 block text says "upload a file to a **quote**" / "file↔**line-item** association", and `quote`/`quote_item`/full `part` are M1.4/M1.5 — none of which M1.2 depends on (M1.2 is orthogonal, depends only on M0.2). Files can't honour "file↔part" while staying standalone unless the owner is resolved. (Schema/FK — expensive to reverse, block-and-log §6.)
**Options considered:** (a) create a **minimal `part` stub** now (only the columns `part_file` needs) and attach files to it, M1.5 extends `part`; (b) attach files to a generic/polymorphic owner and reconcile in M1.5; (c) pull `quote`/`quote_item` forward (breaks orthogonality, expands scope).
**Decision:** **(a) Minimal `part` stub.** KB + domain model confirm files are **part-level**, never line-item-level: the *Part Library* (`uploading-parts-to-your-part-library`) creates a Part by **file upload alone, no quote involved**, and the Quote-level "Quote Files" panel is a *UI aggregation* of all parts' files in a quote, not a storage layer. A Part therefore legitimately exists independently of any quote → a standalone stub is upstream-correct. M1.2 creates `part` with exactly `{id, org_id uuid NOT NULL → organization, primary_file_id uuid NULL (FK part_file, added after part_file exists), created_at, updated_at, deleted_at}` plus `part_file(part_id → part)`. The block's "upload to a quote" wording resolves to "upload to a part." M1.5 **extends** `part` (part_number, revision, is_assembly, obtain_method, BOM/Node tree, geom_hash, export_controlled…) via a forward reversible migration — no reshaping of what M1.2 lays down.
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (part stub + part_file schema), M1.5 (extends part; Component/Node/QuoteItem link the part to a quote).

## [2026-06-25] PRIMARY-per-part — `part.primary_file_id` authoritative + partial-unique enforcement (M1.2)
**Status:** RESOLVED
**Question:** The canonical schema represents the PRIMARY relationship **twice** — `part.primary_file_id` (FK) *and* `part_file.role ∈ {primary, supporting}`. Dual representation can drift; which is the source of truth, and how is "exactly one PRIMARY per part" enforced?
**Decision:** **`part.primary_file_id` is the authority**; `part_file.role` is a denormalized convenience kept in sync **within the same transaction**. One-PRIMARY-per-part is also enforced at the DB with a **partial unique index** `UNIQUE (part_id) WHERE role = 'primary'` (belt-and-braces alongside the single FK). Auto-PRIMARY on first upload uses a **file-type-tier rank** (B-Rep CAD > mesh > 2D/vector/print) matching the upstream "most geometric information wins" heuristic; ties → first uploaded. **Swap** = one transaction flipping the FK + both rows' `role`. Multi-quote/assembly swap guards (deep-copy / replace-referenced-part) are **deferred to M1.5+** (no Node/Component/multi-quote refs exist yet).
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (primary enforcement + swap), M1.5+ (multi-quote/assembly swap guards).

## [2026-06-25] Object-storage backend — S3 API via MinIO (dev/CI), tenant-scoped key scheme (M1.2)
**Status:** RESOLVED
**Question:** No object storage exists. What backend + abstraction + key layout does M1.2 build against, and how is tenant isolation enforced in storage?
**Decision:** Build against the **S3 API** (`aioboto3` / `boto3`) behind a thin storage-service seam so the provider is swappable. **Dev/CI:** add **MinIO** to docker-compose. Object keys are **tenant-scoped**: `org/<org_id>/part/<part_id>/<file_id>/<filename>` (the `org_id` prefix is defence-in-depth alongside RLS on `part_file`). Stored bytes are **raw / unmodified** (acceptance: byte-identical round-trip). **No** content-hash dedup/versioning in M1.2 (schema carries no hash column). Bucket name from config. The S3 access/secret keys live in `Settings` as plain strings, **consistent with the existing M0 pattern** (`clerk_secret_key`, the DB DSNs); they are never logged or dumped. Production provider is a separate OPEN (EU residency — below).

> **Follow-up (ship review, 2026-06-25, CodeRabbit):** secret-bearing `Settings` fields (S3 keys + the pre-existing `clerk_secret_key` / DB DSNs) should adopt Pydantic `SecretStr` **repo-wide** so an accidental `Settings` repr/`model_dump` can't expose them. Deferred from M1.2 as a cross-cutting hardening (doing it piecemeal for only the S3 fields would be inconsistent with the merged M0 convention) — track as a config-hardening task.
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (storage service, docker-compose MinIO, config), all later file-handling blocks (reuse the storage seam); a later config-hardening pass (SecretStr).

## [2026-06-25] File upload constraints + type validation — 200 MB, allow-list + magic-byte, proxy-stream (M1.2)
**Status:** RESOLVED
**Question:** What size cap, transport, and type-validation does M1.2 enforce on uploads? `MAX_UPLOAD_MB` is spec-sourced (`#viewer3d-limits` = 200) but was absent from DECISIONS.
**Decision:** **`MAX_UPLOAD_MB = 200`** (config constant) — reconciles the upstream conflict (3D viewer 250 / supported-file-types 150 / Lens ≤250) per spec `#viewer3d-limits`; recorded here as resolved. **Transport:** proxy-through-API with **streaming** to storage (never buffer 200 MB in memory); presigned direct-to-S3 is a later optimisation. **Type gate:** an **app-level allow-list constant/enum** (the `VIEWER-AND-FILE-TYPES.md` ~50-extension matrix, grouped B-Rep / mesh / 2D-vector / office-email / zip) **plus** a cheap **magic-byte sniff** for common containers (ZIP, PDF) to resist extension spoofing; full content validation belongs to interrogation (M4). Disallowed types are rejected at the edge (Pydantic v2 + the standard error envelope).
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (upload endpoint, validation, config), M4 (interrogation-grade content validation).

## [2026-06-25] File delete semantics — hard-delete blob; PRIMARY-delete blocked while supporting files remain (M1.2)
**Status:** RESOLVED
**Question:** `part_file`'s DDL has no `deleted_at` (implies hard delete) while M1.1/`part` use soft-delete; and deleting the current PRIMARY must not leave a dangling `part.primary_file_id`. What are the delete semantics?
**Decision:** **Hard-delete the blob from object storage always** (GDPR erasure), and **hard-delete the `part_file` row** (matches the DDL; cleanest erasure). **PRIMARY-delete guard:** deleting the current PRIMARY is **rejected while any supporting file remains** (force an explicit swap first); the FK is nulled only when the PRIMARY is the part's **last** file. (Rejected: auto-promote-next — it silently changes the part's geometry source of truth.) `part` itself keeps soft-delete (`deleted_at`), consistent with M1.1.

> **Implementation note (M1.2 ship review, 2026-06-25):** the blob is purged via a FastAPI `BackgroundTask` that runs *after* the DB commit (so a failed commit never deletes a referenced object). A single S3 `delete_object` is short + idempotent, so it isn't Celery-class "long work" — but a failed background delete has **no retry/dead-letter**, leaving an orphan blob. **Follow-up (post-pilot hardening):** move the orphan purge to a retried Celery task for GDPR-erasure durability; pairs naturally with the AV-scan/quarantine OPEN below.
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (delete endpoint + guard), later GDPR erasure flows + M6 hardening (Celery-backed blob purge).

## [2026-06-25] M1.2 surface scope — minimal Files panel + file-op permissions; ZIP/redaction/dedup/AV deferred (M1.2)
**Status:** RESOLVED
**Question:** How much of the rich `#partview` Files UI ships in M1.2, who may upload/delete, and which adjacent features are out?
**Decision:** **API + storage + a minimal React Files panel** in the existing shell (list, upload, set/swap PRIMARY, download, delete) — enough to demo the vertical slice; drag-drop reorder, "Download All", and explicit file ordering (no `sort_order` column) are deferred. **Permissions:** file *writes* (upload / set-primary / delete) gate on the **existing `quote_edit`** capability (admin / manager / salesperson / estimator) — managing a part's files is editing the quote's content, and reusing `quote_edit` keeps the M0.3 matrix untouched; reads need only an authenticated org session (`view_all`). The support roles (engineer / material-purchasing / outside-service) are therefore **read-only** on files — consistent with their spec "view + annotate" semantics (uploading changes the part's geometry source-of-truth, which is an edit, not an annotation). *(This refines the grill-time sketch "estimator/engineer/admin/manager" to the spec-consistent `quote_edit` set: drops engineer, adds salesperson; a dedicated `file_manage` capability for support roles can be added later if a real need appears.)* **Explicitly OUT of M1.2** (confirmed): ZIP pack-and-go *unpacking* (.zip is stored opaque, unpacked in M4); redaction logic (`is_redacted` column exists, unused — later GDPR feature); content-hash dedup/versioning; thumbnails / rendering / interrogation (M2/M4).
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (Files panel, file-op capabilities), M2/M4 (rendering, ZIP unpack, interrogation), later GDPR (redaction).

## [2026-06-25] OPEN: Production object-store provider — EU data residency (M1.2)
**Status:** OPEN
**Question:** Customer CAD/print files are personal-data-bearing under GDPR and must reside in the EU. M1.2 builds against the S3 API (MinIO locally) but the **production** provider is unchosen. Candidates: **Hetzner Object Storage** (matches the Hetzner infra anchor), **Cloudflare R2** (EU jurisdiction), **AWS S3 `eu-central-1`**, **Scaleway** — differ on cost, EU-residency guarantees, and S3-API compatibility.
**Options considered:** Hetzner (cheapest, in-region, S3-compatible, smaller ecosystem); R2 (no egress fees, EU-jurisdiction toggle); S3 eu-central-1 (most mature, dearer + egress).
**Recommended default:** Hetzner Object Storage (region-aligned, S3 API, cost) unless an existing AWS footprint argues otherwise. No code impact — deploy-time config behind the storage seam.
**Affects:** M1.2 (storage config / deploy), any block that stores blobs.

## [2026-06-25] OPEN: Antivirus / malware scanning of customer uploads (M1.2)
**Status:** OPEN
**Question:** Customers (and later, external vendors via email ingest) upload arbitrary files that staff download and forward to vendors. Should uploads be AV/malware-scanned, and where (sync at upload vs async Celery post-store vs at download/forward)?
**Options considered:** ClamAV sidecar scanned async on a Celery task after store (quarantine flag on `part_file`); a cloud scanning API; or accept-risk for the pilot.
**Recommended default:** **Defer to a later hardening block** (not M1.2) but logged now: async ClamAV scan on store with a quarantine flag, blocking download/forward until clean. Revisit before email-ingest (M3) opens an untrusted upload path.
**Affects:** M3 (email ingest = untrusted uploads), M6 (hardening), `part_file` (possible future `scan_status` column).

## [2026-06-27] Money representation — integer minor units vs `numeric(14,4)` (M1.6 grill; blocked M1.7)
**Status:** RESOLVED — option (b) confirmed at the M1.7 grill (Benjamin 2026-07-07): `numeric(14,4)` for unit-level/intermediate cost & price columns (per the folded schema); money rounds to **integer minor units + `currency`** at the quote/total boundary (display + any persisted total). This is the exact reading of the CLAUDE.md §5 money invariant from M1.7 onward.
**Question:** CLAUDE.md §5 mandates money as **integer minor units + explicit currency** ("never a float"). The folded `DB-SCHEMA.sql` models every `component_quantity` money column (`unit_cost`, `calc_unit_price`, `manual_unit_price`, the cost split, `total_profit`, …) — and `purchased_component.piece_price`, `quote_cell.*` — as **`numeric(14,4)`**. These conflict: integer **cents** (2dp) cannot hold the 4-decimal precision the schema/pricing relies on (unit/piece prices are 4dp; M1.10 must reproduce `$2,160.84`-class figures exactly without rounding drift). `numeric` is exact (not a float), so it satisfies "never a float" but **not** "integer minor units."
**Why it surfaced in M1.6 but does not block it:** M1.6 adds **no money columns** — `component_quantity` lands with only `quantity` / `make_quantity` / `deliver_quantity` (all `int`). The first money column arrives in **M1.7** (per-qty op-cost cells), so the representation must be settled before then.
**Options considered:** (a) **integer minor units everywhere** — uniform with §5, but loses the 4th decimal the unit-price math needs (rounding risk on the golden figures); (b) **`numeric(14,4)` for per-unit / intermediate calc columns, round to integer minor units only at the persisted/displayed quote-total boundary** — keeps calc precision, keeps stored/printed totals in §5's representation; (c) integer in a finer denomination (e.g. tenths-of-cent / micros) to stay integer while preserving 4dp.
**Recommended default:** **(b)** — `numeric(14,4)` for unit-level/intermediate cost & price columns (as the folded schema specifies), with money **rounded to integer minor units + `currency` at the quote/total boundary** (display + any persisted total). This honors the schema's precision where the math needs it and §5's representation where money is stored/shown. Confirm at the M1.7 grill before the first money column ships.
**Affects:** M1.7 (`component_quantity` cost cells, `quote_cell`), M1.10 (roll-up + pricing items + golden figures), M1.11 (VAT/add-ons), `purchased_component.piece_price`, and the §5 money invariant's exact reading.

## [2026-07-13] M2.4 redaction scope — text-selection deferred; raster fidelity; whiteout semantics (M2.4 grill)
**Status:** RESOLVED
**Question:** The spec's Redact bullet names "text / sections / pages" and "recolourable fill/stroke"; whiteout's specced targets (Lens callouts, Part-Setup sections) don't exist until M3+. What ships in M2.4?
**Decision:** (a) **Text-selection redaction is deferred** — rect-drag + whole-page cover the redact-text use functionally (the acceptance test redacts a title-block region); the pdf.js text-layer selection flow can follow without any API change. (b) Region-redacted pages rasterize at **renderScale 3** (≈216 DPI) — irrecoverability requires rasterization (a rect overlay leaves text extractable); the knob is one constant (`REDACTION_RENDER_SCALE`). (c) **Whiteout = user-drawn white rects over the drawing, session view-state only, never baked into the saved copy** (the persistent white case is the `weiss` *redaction* preset); global toggle + spotlight lifts exactly one section; M3 Lens callouts plug into the same state. (d) Fill recolour ships as the two spec-named **presets (schwarz/weiss)**, no free picker; `Redaction.stroke` is modelled but not yet rendered (follows with text-selection). (e) Duplicate saves stay allowed server-side; the client **confirms** when a `<stem>-redacted.pdf` already exists.
**Resolved:** 2026-07-13 (M2.4 grill, Benjamin)
**Affects:** M2.4 (viewer redact UI + renderer), M3 (Lens whiteout targets), M6 (share the redacted file).

## [2026-07-13] OPEN: `part_file.redacted_from` FK + persisted redaction regions (M2.4 → M6)
**Status:** OPEN
**Question:** The spec's model section lists `PartFile — redaction is_primary (bool) redacted_from (FK source file) + redaction regions`. M2.4 stores only `is_redacted=TRUE` on the copy — no FK to the source file, no region payload. M6's external-share scoping ("share the redacted file *instead of* the original") may need the provenance link; regions would also enable re-editing a redaction instead of redoing it.
**Options considered:** (1) add `redacted_from` + a regions JSONB now (migration in M2.4, unused until M6); (2) add both in the M6 Vendor-RFQ block when share-scoping actually consumes them; (3) FK only, regions never (a saved copy is final; re-redact from the original).
**Recommended default:** **(2)** — schema changes ride with the block that consumes them; nothing in M2.4/M2.5 reads the link, and the filename convention (`<stem>-redacted.pdf`) plus `is_redacted` carries the demo until then. Decide at the M6 grill.
**Affects:** `part_file` schema (future migration), M6 external-share scoping, GDPR provenance reporting.

---

## [2026-07-13] M2.5 Split-PDF policy — async Celery split, provenance column, edge bundle, naming

**Status:** RESOLVED (Benjamin, M2.5 grill)
**Question:** Four expensive-to-reverse choices for the server-side Split PDF: (1) synchronous request vs Celery job (no job-status API pattern existed yet); (2) whether derived files carry a DB provenance link; (3) rejection policy for unsplittable PDFs; (4) page-file naming + re-run behaviour.
**Decision:** (1) **Celery + status polling** — `POST …/files/{id}/split` validates at the edge and returns 202 + task id (CLAUDE.md §5: long work never blocks a request); a *feature-scoped* `GET …/split/{task_id}` maps task state/progress for the viewer. (2) **`part_file.source_file_id`** (nullable self-FK, composite same-org, `SET NULL (source_file_id)` on source delete — migration 0017); M2.4 redacted copies and M2.12 merges reuse it. (3) 1-page → 422 `nothing_to_split`; non-PDF/corrupt → 422 `invalid_pdf`; encrypted → 422 `encrypted_pdf`; **200-page ceiling** → 422 `too_many_pages`; **all-or-nothing** persistence (any failure discards written blobs, commits no rows). (4) **`<stem>-p<N>.pdf`**, language-neutral; re-running a split is allowed and adds another set (the user acted twice; deterministic task *retries* are guarded separately). *Note:* the viewer has no toast component — the AC's "progress + success toasts" surface through the repo's existing `aria-live`/`role="status"` pattern (a status line in the pages panel); a real toast system, if one arrives, adopts these strings unchanged.
**Resolved:** 2026-07-13 (M2.5 grill; Benjamin picked the recommended option on all four).
**Affects:** M2.5; M2.4 + M2.12 (source_file_id reuse); M3/M4 (the async-task + status-polling pattern).

---

## [2026-07-13] OPEN: Generic job-status API vs per-feature scoped polling endpoints
**Status:** OPEN
**Question:** M2.5's split status lives at `GET /api/parts/{part_id}/files/{file_id}/split/{task_id}` — deliberately feature-scoped, tenancy-checked through the org-scoped file lookup plus task-meta binding. M3 (Lens extraction) and M4 (GeometryService interrogation) also run long Celery jobs the UI must poll: do they each get a scoped endpoint, or does a generic `/api/jobs/{id}` contract (with its own org-binding story) replace them?
**Options considered:** keep per-feature scoped endpoints (simple tenancy story, some duplication); introduce a generic jobs resource once a second consumer exists (one polling client, but needs a durable org-scoped job table rather than Celery result meta).
**Recommended default:** keep the scoped pattern until M3 lands, then decide with the second consumer's real shape on the table; if a generic resource wins, back it with a durable `job` table (org-scoped, RLS) instead of raw Celery meta.
**Affects:** M2.5 (unchanged either way), M3, M4, frontend polling helpers.

---

## [2026-07-14] OPEN: Viewer-mesh provenance & face-ID correlation (M2.6 → M4)
**Status:** OPEN
**Question:** M2.6 renders a **client-side** occt-import-js tessellation (browser WASM parse of the stored STEP), while DECISIONS [2026-06] fixes GeometryService on **server-side** OCCT (pythonocc) and the spec (`#viewer3d-tools`) says the viewer "renders what GeometryService tessellates". M2.7 exposes a stable face/entity id that M2.11 **persists** with chat annotations, and M4 must paint interrogation features onto whatever mesh the viewer displays. If display mesh ≠ interrogation mesh, persisted face ids and feature→face maps don't correlate.
**Options considered:** (a) keep the client-side display mesh permanently and define a correlation contract between the two tessellations (stable face ordering or geometric matching — both OCCT-kernel-based, which helps but is uncontractual in occt-import-js); (b) switch the viewer to fetch GeometryService's server tessellation in M4 and delete the client parse path.
**Recommended default:** **(b)** — the sub-spec's "renders what GeometryService tessellates" already points there. M2.6 therefore keeps the mesh source behind an async `MeshProvider` seam (worker-based occt-import-js today, swappable without touching scene/UI code), and nothing occt-import-js-specific is persisted. **Until this is resolved, face/entity ids from the client tessellation are opaque and transient — valid only within one loaded viewer session; M2.7 must present them as such and M2.11 must NOT persist them** (or must gate persistence on this decision landing first). Decide at the M4 grill, before M2.11 face-bound annotations ship if M2.11 lands first.
**Affects:** M2.6 (seam only), M2.7 (face/entity id shape), M2.11 (persisted annotation binding), M4 (tessellation endpoint + feature→face map).

---

*Add new entries above this line as ambiguities arise during the build.*
