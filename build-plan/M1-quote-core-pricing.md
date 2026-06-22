# M1 — Quote Core + Pricing Engine

**Spec:** [#milestones](../docs/spec/Bid-Factory-Build-Spec.html#milestones) (M1 row) · **Exit criteria (authoritative):** golden tests reproduce **every verified Demo E figure** (Difficult-Material **$2,160.84** + the other five) exactly; quote lifecycle transitions are enforced.

**Goal.** Build the heart of the product — quote/account/part data model and the full costing & pricing engine — and **close the golden thread thin**: a fixture quote goes from create → line item → manual material/op → costing → pricing and reproduces the verified figures. Intake is a direct create (real email is M3); geometry is manual dims (real interrogation is M4); "send" is a status flag (real output is M5).

**This file is the worked example.** M2–M6 follow its block template and citation density exactly.

**Sequence:** `M1.1 ⟂ M1.2 ⟂ M1.3` (orthogonal CRUD, any order after M0) → `M1.4 → M1.5 → M1.6 → M1.7 → M1.8 (spike) → M1.9 → M1.10 → M1.11 → M1.12 → M1.13`. The spine is sequential because each layer renders into the one below; the chain ends at the golden-thread close. `M1.14 ⟂` (config-completeness guard) is orthogonal — it can land any time after M1.7 + M1.12, off the spine.

---

### M1.1 — Accounts & Contacts CRUD   `[M]`  ⟂
- **Vertical slice:** create/list/edit/archive an Account and its Contacts, org-scoped, with Tolera as the system of record.
- **Scope (in):** native `Account` + `Contact` models + CRUD API/UI; soft-delete; salesperson links; org-scoping via the M0.2 RLS pattern. (CRM two-way sync layers on top later — M6.)
- **Scope (out):** HubSpot sync (→ M6); export controls/ITAR flags on parts (→ M1.5).
- **Depends on:** M0.2 (tenancy/auth), M0.4 (shell)
- **Implements (spec):** [#contacts](../docs/spec/Bid-Factory-Build-Spec.html#contacts)
- **Internals (provenance):** ../docs/spec/folded-subspecs/DOMAIN-MODEL.md, ../docs/spec/folded-subspecs/DB-SCHEMA.sql
- **KB:** [KB: accounts-and-contacts](https://help.paperlessparts.com/s/article/accounts-and-contacts)
- **Acceptance criteria:** CRUD round-trips; soft-deleted records hide but persist; all reads org-scoped (cross-org denial holds).
- **Test plan (fixtures):** API tests for CRUD + soft-delete + org isolation; seed a Fechner account/contact used by the golden thread.
- **Golden-thread role:** supplies the account/contact the golden-thread quote is attached to.

### M1.2 — File upload & storage   `[M]`  ⟂
- **Vertical slice:** upload a file to a quote, tag one PRIMARY, download it back — stored in object storage, org-scoped.
- **Scope (in):** S3-compatible object storage; upload/download/delete; file↔line-item association; PRIMARY tagging; the supported-file-type allow-list (ingest only — no rendering/interrogation yet).
- **Scope (out):** PDF/3D rendering + viewers (→ M2); Split PDF (→ M2); extraction (→ M3); interrogation (→ M4).
- **Depends on:** M0.2
- **Implements (spec):** [#partview](../docs/spec/Bid-Factory-Build-Spec.html#partview) (Files section), [#supported-file-types](../docs/spec/Bid-Factory-Build-Spec.html#supported-file-types)
- **Internals (provenance):** ../docs/spec/folded-subspecs/VIEWER-AND-FILE-TYPES.md (file-type matrix), ../docs/spec/folded-subspecs/DB-SCHEMA.sql
- **KB:** [KB: swap-primary-and-supporting-files](https://help.paperlessparts.com/s/article/swap-primary-and-supporting-files), [KB: supported-file-types](https://help.paperlessparts.com/s/article/supported-file-types)
- **Acceptance criteria:** upload→download round-trips byte-identical; PRIMARY swap works; disallowed types rejected; files org-scoped.
- **Test plan (fixtures):** upload a `/fixtures/cad` STEP + a `/fixtures/drawings` PDF, assert storage + association + PRIMARY tag.
- **Golden-thread role:** the thread's part can carry its fixture file (rendered/interrogated only from M2/M4).

### M1.3 — Saved-view engine + quotes list   `[M]`  ⟂
- **Vertical slice:** the quotes list renders, can be filtered, and a filter set saved as a named view that survives reload.
- **Scope (in):** TanStack Table quotes list; column/filter/sort; saved-view persistence (per user/org); the default "Workflows" view.
- **Scope (out):** dashboard work-queue redesign (→ M6); analytics query-builder (→ separate analytics milestone).
- **Depends on:** M1.4 (needs quotes to list) — *may branch in parallel against a stub list, integrate after M1.4.*
- **Implements (spec):** [#quoteslist](../docs/spec/Bid-Factory-Build-Spec.html#quoteslist)
- **Internals (provenance):** ../docs/spec/folded-subspecs/USER-STORIES-AND-WORKFLOWS.md
- **KB:** [KB: tracking-outstanding-quotes](https://help.paperlessparts.com/s/article/tracking-outstanding-quotes), [KB: workflows](https://help.paperlessparts.com/s/article/workflows)
- **Acceptance criteria:** filter narrows rows; a saved view reloads with its filters; views are org/user-scoped.
- **Test plan (fixtures):** seed N quotes, save a filtered view, reload, assert the filter persists and rows match.
- **Golden-thread role:** the thread's quote appears in the list once created.

### M1.4 — Quote + Quote Item + lifecycle state machine   `[M]`
- **Vertical slice:** create a quote against an account, add a root quote item, and move it through enforced lifecycle states (illegal transitions rejected).
- **Scope (in):** `Quote` + `QuoteItem` (root component); the quote lifecycle state machine with **enforced** transitions; quote detail skeleton + the workflow tracker; the RFQ entity exists in schema but is populated by direct-create (ingestion → M3).
- **Scope (out):** email ingest/auto-quote (→ M3); bulk create (→ M3); send/PDF (→ M5).
- **Depends on:** M1.1
- **Implements (spec):** [#quotedetail](../docs/spec/Bid-Factory-Build-Spec.html#quotedetail), [#quotelifecycle](../docs/spec/Bid-Factory-Build-Spec.html#quotelifecycle), [#states-machines](../docs/spec/Bid-Factory-Build-Spec.html#states-machines)
- **Internals (provenance):** ../docs/spec/folded-subspecs/USER-STORIES-AND-WORKFLOWS.md (state machines), ../docs/spec/folded-subspecs/DOMAIN-MODEL.md, ../docs/spec/folded-subspecs/DB-SCHEMA.sql
- **KB:** [KB: creating-a-new-quote](https://help.paperlessparts.com/s/article/creating-a-new-quote), [KB: setting-up-quote-items](https://help.paperlessparts.com/s/article/setting-up-quote-items)
- **Decisions:** ../docs/decisions/DECISIONS.md → *Pricing-config-change policy (E4-d)* (existing drafts freeze pricing; only new quotes reflect config changes)
- **Acceptance criteria:** a legal transition succeeds and an illegal one is rejected (server-side); the tracker reflects state; org-scoped.
- **Test plan (fixtures):** state-machine test enumerates legal/illegal transitions; create the golden-thread quote here.
- **Golden-thread role:** **opens the thread** — the quote + root item the rest of M1 prices.

### M1.5 — Part / Node / Component model + BOM tree   `[M]`
- **Vertical slice:** a quote item resolves to the 4-layer Part→Node→Component model and a BOM tree can be queried, with manual geometry dims and an attached file.
- **Scope (in):** the 4-layer model (`Part`, `Node`, `Component`, `QuoteItem`=root component); `PartFile`; `PartGeometry` with **manual** dims (L/W/H, volume, area, IN/MM toggle, math/unit inputs); ITAR/export-controlled flag; BOM tree querying; identity fields (part number/rev/description/name).
- **Scope (out):** geometry auto-population (→ M4); assembly BOM Builder + child BOMs (→ M4); part-library matching (→ M2).
- **Depends on:** M1.4
- **Implements (spec):** [#partview](../docs/spec/Bid-Factory-Build-Spec.html#partview), [#model-4layer](../docs/spec/Bid-Factory-Build-Spec.html#model-4layer), [#assemblies-model](../docs/spec/Bid-Factory-Build-Spec.html#assemblies-model)
- **Internals (provenance):** ../docs/spec/folded-subspecs/DOMAIN-MODEL.md (the 4-layer contract), ../docs/spec/folded-subspecs/DB-SCHEMA.sql, ../docs/spec/folded-subspecs/PartGeometry-Attribute-Catalog.md (`part.*` names/units; manual subset)
- **KB:** [KB: setting-up-quote-items](https://help.paperlessparts.com/s/article/setting-up-quote-items), [KB: assemblies-data-types-and-terminology](https://help.paperlessparts.com/s/article/assemblies-data-types-and-terminology)
- **Acceptance criteria:** a quote item maps to root component; BOM tree query returns the hierarchy; manual dims persist with units; math expressions (`2.27 + .359`) and typed units (`1 meter`) auto-evaluate; ITAR flag persists.
- **Test plan (fixtures):** model + tree-query tests; assert `PartGeometry` stores metric, presents per IN/MM toggle (the geometry↔Kalk contract).
- **Golden-thread role:** the thread's line item gets its part + manual dims (replaced by real interrogation at M4).

### M1.6 — Quantity breaks + ComponentQuantity cells   `[M]`
- **Vertical slice:** a line item carries N quantity breaks and the per-break cell grid every downstream cost/price renders into.
- **Scope (in):** quantity breaks; `ComponentQuantity` per-break cells; make-qty vs deliver-qty (`part.qty` / `bom_qty` / `innate_quantity`); the per-quantity column layout; "Change quantities".
- **Scope (out):** per-qty operation cost values (→ M1.7); per-qty pricing (→ M1.10); per-qty lead times (→ M1.11).
- **Depends on:** M1.5
- **Implements (spec):** [#partview](../docs/spec/Bid-Factory-Build-Spec.html#partview) (Pricing & Quantities), [#line-item-management](../docs/spec/Bid-Factory-Build-Spec.html#line-item-management)
- **Internals (provenance):** ../docs/spec/folded-subspecs/DOMAIN-MODEL.md (`ComponentQuantity`), ../docs/spec/folded-subspecs/DB-SCHEMA.sql
- **KB:** [KB: setting-up-quote-items](https://help.paperlessparts.com/s/article/setting-up-quote-items), [KB: quantity-specific-variables](https://help.paperlessparts.com/s/article/quantity-specific-variables)
- **Acceptance criteria:** adding/removing breaks reshapes the per-qty grid; make-qty vs deliver-qty distinct and index-aligned across lists.
- **Test plan (fixtures):** assert `get_quantities()`/`get_make_quantities()`/`get_bom_quantities()` align for a multi-break fixture (1/5/20).
- **Golden-thread role:** the thread's quantity-break columns — the grid the golden figures land in.

### M1.7 — Manual Materials & Operations + Calculated/Override drawers   `[M]`
- **Vertical slice:** add a material and operations to a line item, with per-qty cost cells, and override any calculated value without losing the calc.
- **Scope (in):** `Material` + `Operation` entities + the nested material picker + Edit Material Properties; operation rows + Change Process; per-qty op-cost cells with **manual** values; the **Calculated-vs-Override** persistence pattern (`COALESCE(manual_*, calc_*)` — persist both, recalculation never destroys human input).
- **Scope (out):** Kalk-driven cost formulas (→ M1.9); auto-routing/operation-generation (→ M4); the seeded 54-op library content (→ M1.12).
- **Depends on:** M1.6
- **Implements (spec):** [#partview](../docs/spec/Bid-Factory-Build-Spec.html#partview) (Materials · Operations), [#costing](../docs/spec/Bid-Factory-Build-Spec.html#costing), [#oplibrary](../docs/spec/Bid-Factory-Build-Spec.html#oplibrary)
- **Internals (provenance):** ../docs/spec/folded-subspecs/PRICING-ENGINE-SPEC.md, ../docs/spec/folded-subspecs/DB-SCHEMA.sql (calc-vs-override columns)
- **KB:** [KB: managing-materials](https://help.paperlessparts.com/s/article/managing-materials), [KB: setting-up-operations](https://help.paperlessparts.com/s/article/setting-up-operations), [KB: costing-a-part](https://help.paperlessparts.com/s/article/costing-a-part)
- **Acceptance criteria:** material + ops attach; per-qty manual cost cells compute the cost roll-up inputs; an override persists and survives a recalculation (calc value retained underneath).
- **Test plan (fixtures):** test that `COALESCE(manual, calc)` resolves correctly and re-costing preserves overrides.
- **Golden-thread role:** the thread's operations + material (manual costs now; formula-driven from M1.9).

### M1.8 — Kalk sandbox core   `[M]`  · SPIKE-FIRST
- **Vertical slice:** a Kalk formula evaluates inside a Python-AST sandbox — provably *secure* and *bit-for-bit deterministic* — on a toy operation-cost formula.
- **Scope (in):** **Spike**: prove the AST sandbox blocks imports/dunder/file/network access and that evaluation is deterministic (same inputs → identical bytes), incl. `frozen=True/False` semantics; declarations-not-in-loops constraint. Then harden into the reusable evaluator.
- **Scope (out):** the full variable system, the five contexts, the editor UI (→ M1.9); operation-generation context (→ M4).
- **Depends on:** M1.7
- **Implements (spec):** [#kalk](../docs/spec/Bid-Factory-Build-Spec.html#kalk), [#kalk-exec](../docs/spec/Bid-Factory-Build-Spec.html#kalk-exec)
- **Internals (provenance):** ../docs/spec/folded-subspecs/KALK-REFERENCE.md (sandbox, determinism, freeze)
- **KB:** [KB: what-is-paperless-parts-pricing-language-p3l](https://help.paperlessparts.com/s/article/what-is-paperless-parts-pricing-language-p3l), [KB: operation-p3l-cheat-sheet](https://help.paperlessparts.com/s/article/operation-p3l-cheat-sheet)
- **Acceptance criteria:** sandbox rejects every escape attempt in the security test matrix; a formula evaluates identically across 1000 runs; non-determinism sources (time, hash seed, set ordering) are eliminated.
- **Test plan (fixtures):** security test matrix (import/exec/open/`__builtins__` attempts all blocked) + a determinism test; these become permanent regression guards.
- **Golden-thread role:** prerequisite for formula-driven costs the golden figures depend on.

### M1.9 — Kalk variable system + operation-cost & pricing contexts + editor + Custom Tables   `[L]`
- **Vertical slice:** an estimator writes a Kalk formula in the editor using variables and a custom table, and it drives a real per-qty operation/pricing value.
- **Scope (in):** the variable system (`var`, `table_var`, `drop_down_var`, dynamic variables); the **operation-cost** and **pricing-item** contexts with their globals/functions (`get_components`, `set_custom_cost`, geometry/workpiece reads); Custom Tables (used by `table_var`); the Kalk editor UI with validation.
- **Scope (out):** operation-generation/auto-routing context (→ M4); add-on/discount contexts (→ M1.10/M1.11 use the evaluator but their items are defined there).
- **Depends on:** M1.8
- **Implements (spec):** [#kalk-vars](../docs/spec/Bid-Factory-Build-Spec.html#kalk-vars), [#kalk-tables](../docs/spec/Bid-Factory-Build-Spec.html#kalk-tables), [#kalk-contexts](../docs/spec/Bid-Factory-Build-Spec.html#kalk-contexts), [#customcat](../docs/spec/Bid-Factory-Build-Spec.html#customcat)
- **Internals (provenance):** ../docs/spec/folded-subspecs/KALK-REFERENCE.md (variable system + contexts + custom tables)
- **KB:** [KB: operation-p3l-cheat-sheet](https://help.paperlessparts.com/s/article/operation-p3l-cheat-sheet), [KB: pricing-items-p3l](https://help.paperlessparts.com/s/article/pricing-items-p3l), [KB: custom-table-p3l](https://help.paperlessparts.com/s/article/custom-table-p3l), [KB: custom-tables](https://help.paperlessparts.com/s/article/custom-tables), [KB: drop-down-variables](https://help.paperlessparts.com/s/article/drop-down-variables), [KB: p3l-lists](https://help.paperlessparts.com/s/article/p3l-lists)
- **Acceptance criteria:** a formula reading a `table_var` + part attribute produces the expected per-qty value; editor rejects invalid Kalk with a clear error; custom tables resolve by key.
- **Test plan (fixtures):** unit tests per context against `KALK-REFERENCE` examples; a custom-table lookup test.
- **Golden-thread role:** makes the thread's operation/material costs formula-driven (the Difficult-Material custom category uses this).

### M1.10 — Costing roll-up + pricing (markup / margin / target-margin) + discounts   `[L]`
- **Vertical slice:** the line item rolls operation+material+component costs into the five categories and prices them with markup, margin, **and target-margin**, plus a discounts layer — reproducing a verified Demo E figure.
- **Scope (in):** cost roll-up (operation → component → root); the 5 cost categories (Material/Inside/Outside/Purchased/General) + **custom categories** (e.g. Difficult Material via a Kalk category formula); pricing items — Markup, Margin (`Sell = Cost/(1−pct)`), and the **Target-Margin back-solve** (v1 differentiator: solve the required markup amount so Total Profit/Total = target, holding other items fixed; "unreachable" state); Discounts layer (applied after markup, before add-ons); per-qty Total/Unit/Markup%/Margin%.
- **Scope (out):** add-ons/lead-times/VAT (→ M1.11); margin coach (→ M5).
- **Depends on:** M1.9
- **Implements (spec):** [#costing](../docs/spec/Bid-Factory-Build-Spec.html#costing), [#newscope](../docs/spec/Bid-Factory-Build-Spec.html#newscope) (Margin-target mode), [#kalk-rollup](../docs/spec/Bid-Factory-Build-Spec.html#kalk-rollup)
- **Internals (provenance):** ../docs/spec/folded-subspecs/PRICING-ENGINE-SPEC.md (roll-up + margin/markup + target-margin), ../docs/spec/folded-subspecs/KALK-REFERENCE.md
- **KB:** [KB: pricing-a-part](https://help.paperlessparts.com/s/article/pricing-a-part), [KB: costing-table](https://help.paperlessparts.com/s/article/costing-table), [KB: pricing-table](https://help.paperlessparts.com/s/article/pricing-table), [KB: discounts](https://help.paperlessparts.com/s/article/discounts), [KB: pricing-items-p3l-cheat-sheet](https://help.paperlessparts.com/s/article/pricing-items-p3l-cheat-sheet)
- **Decisions:** ../docs/decisions/DECISIONS.md → *Margin math for mixed markup + margin pricing items* (`cost × pct/(1−pct)` confirmed); *Pricing-config-change policy (E4-d)* (freeze + manual refresh; `Refresh Pricing` / `Bulk Refresh`)
- **Acceptance criteria:** reproduces the **Difficult-Material $2,160.84** case exactly; a markup on a custom category applies to only that category's cost (e.g. 10% on $539.36, not all $674.20); target-margin back-solves to the correct markup and shows "unreachable" when other items exceed the target.
- **Test plan (fixtures):** golden pricing tests for **all six Demo E examples** (difficult-material, single work center, labour-vs-overhead, piece-price-vs-tooling, outside-finishes, complexity-driven) — exact assertions.
- **Golden-thread role:** **prices the thread** — the segment that produces the verified figure.

### M1.11 — Add-Ons / Lead Times / Expedite + VAT lines   `[M]`
- **Vertical slice:** add an add-on and per-qty lead times with expedite, then compute net + MwSt/USt lines for a DACH quote.
- **Scope (in):** Add-Ons (NRE/tooling/minimum-order, Kalk-priced); per-qty Lead Times + Expedite (days_faster + markup); VAT lines (DE 19%/7%, AT 20%, CH 8.1%) computed at quote level (not in Kalk); net/gross display in German locale.
- **Scope (out):** reverse-charge §13b + VIES validation (→ M5 checkout); e-invoice export (post-v1).
- **Depends on:** M1.10
- **Implements (spec):** [#addons](../docs/spec/Bid-Factory-Build-Spec.html#addons), [#dach-costing](../docs/spec/Bid-Factory-Build-Spec.html#dach-costing), [#dach-tax](../docs/spec/Bid-Factory-Build-Spec.html#dach-tax)
- **Internals (provenance):** ../docs/spec/folded-subspecs/PRICING-ENGINE-SPEC.md (add-ons/lead-times), ../docs/spec/folded-subspecs/DACH-DELTA-LAYER.md (VAT)
- **KB:** [KB: add-ons-p3l-cheat-sheet](https://help.paperlessparts.com/s/article/add-ons-p3l-cheat-sheet), [KB: final-touches-add-ons-discounts-and-dynamic-lead-times](https://help.paperlessparts.com/s/article/final-touches-add-ons-discounts-and-dynamic-lead-times), [KB: dynamic-lead-times-guide](https://help.paperlessparts.com/s/article/dynamic-lead-times-guide)
- **Acceptance criteria:** add-on applies after discounts; expedite shortens lead time and adjusts price per its rule; VAT line is correct for DE/AT/CH; money is integer minor units + explicit currency, displayed `1.234,56 €`.
- **Test plan (fixtures):** VAT test across DE/AT/CH (incl. the CH/CHF fixture); add-on + expedite price test.
- **Golden-thread role:** completes the thread's priced quote (net + tax).

### M1.12 — Seed catalog (materials · operations · processes · pricing defaults)   `[M]`
- **Vertical slice:** provisioning an org now fills the Configure data the engine needs — materials tree, 54-op library, Core-4 processes, pricing defaults — extending the M0.5 framework.
- **Scope (in):** `SEED-AND-FIXTURES` Part 1 §2 (materials tree, Werkstoffnummer-keyed), §3 (54-op German library), §4 (Core-4 process templates + routers, *minus* interrogation), §6 (pricing defaults + Zuschlagskalkulation), §7 partial (workflow steps, custom tables, email templates).
- **Scope (out):** §5 interrogation profiles (→ M4, needs DFM); §7 starter rule library (→ M3, needs rules engine).
- **Depends on:** M1.7 (material/op entities), M1.9 (Kalk for rate/pricing formulas), M1.10 (pricing items)
- **Implements (spec):** [#oplibrary](../docs/spec/Bid-Factory-Build-Spec.html#oplibrary), [#zuschlagskalkulation](../docs/spec/Bid-Factory-Build-Spec.html#zuschlagskalkulation)
- **Internals (provenance):** ../docs/fixtures/SEED-AND-FIXTURES.md (Part 1 §2–§7), ../docs/fixtures/seed.skeleton.json
- **KB:** [KB: managing-materials](https://help.paperlessparts.com/s/article/managing-materials), [KB: setting-up-operations](https://help.paperlessparts.com/s/article/setting-up-operations)
- **Decisions:** ../docs/decisions/DECISIONS.md → log `OPEN:` for the exact 54-op rates (shop-specific) if not supplied — do not invent rates.
- **Acceptance criteria:** seeding yields the materials tree, 54 ops, Core-4 processes, and pricing defaults; idempotent re-seed; a quote can pick a seeded op/material end-to-end.
- **Test plan (fixtures):** seed → assert catalog counts + a Werkstoffnummer lookup (`1.4301`→304); the golden thread now uses seeded ops/materials.
- **Golden-thread role:** supplies the real catalog the golden-thread quote prices against.

### M1.13 — Golden-thread close + golden-test harness   `[M]`
- **Vertical slice:** the end-to-end thread runs in CI — seed org → create quote → line → material/ops → costing → pricing → reproduces all six Demo E figures — and stays green forever after.
- **Scope (in):** `SEED-AND-FIXTURES` Part 2 harness (`/fixtures` layout, golden schemas, the runner that seeds a clean org, ingests a fixture, runs pricing, diffs `/golden`); the **golden-thread integration test** wired into CI; 1–2 synthetic STEP+PDF samples until the Fechner packages land.
- **Scope (out):** interrogation/extraction goldens (→ M4/M3 wire into the same harness); buyer-facing send (→ M5).
- **Depends on:** M1.11, M1.12
- **Implements (spec):** [#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance) (Demo E), [#milestones](../docs/spec/Bid-Factory-Build-Spec.html#milestones) (M1 exit)
- **Internals (provenance):** ../docs/fixtures/SEED-AND-FIXTURES.md (Part 2 harness + golden schemas)
- **Decisions:** ../docs/decisions/DECISIONS.md → *Fixture packages* (Benjamin's anonymised Fechner packages, target 2026-06-23 — build the harness now, slot fixtures on delivery)
- **Acceptance criteria:** the harness reproduces **all six Demo E figures exactly** (incl. $2,160.84); the golden-thread integration test passes in CI; re-running is deterministic.
- **Test plan (fixtures):** the harness *is* the test; pricing assertions exact, future geometry assertions within tolerance (per Part 2).
- **Golden-thread role:** **closes the thread (thin)** and pins it green in CI — the contract M3/M4/M5 each make progressively more real.

### M1.14 — Config-completeness guard (operation-rates banner + missing-rates warning)   `[S]`  ⟂
- **Vertical slice:** an operation with no rate raises a **missing-rates warning** on any quote that uses it, and Configure → Operations shows an **operation-rates banner** ("N operations need rates") — so the pilot can't quote on a €0/placeholder rate unnoticed.
- **Scope (in):** the **operation-rates banner** in the Configure → Operations/Pricing surface (count of ops/materials with no rate + link to fix); the **missing-rates warning** on the part-estimating/costing view when a used op/material resolves to no rate (flags the line item; surfaces in "Outstanding Work"); deterministic, non-AI.
- **Scope (out):** the full **Quick-Setup wizard + advanced-setup** self-serve onboarding (→ deferred post-pilot, see M6); auto-filling rates (shop-specific — a `DECISIONS.md` OPEN item).
- **Depends on:** M1.7 (operations), M1.12 (seed catalog supplies the rates being checked)
- **Implements (spec):** [#operation-rates-banner](../docs/spec/Bid-Factory-Build-Spec.html#operation-rates-banner), [#missing-rates-warning](../docs/spec/Bid-Factory-Build-Spec.html#missing-rates-warning)
- **Internals (provenance):** ../docs/fixtures/SEED-AND-FIXTURES.md (the 54-op rates — the OPEN shop-specific values this guards)
- **KB:** [KB: setting-up-operations](https://help.paperlessparts.com/s/article/setting-up-operations)
- **Decisions:** ../docs/decisions/DECISIONS.md → the **54-op rates `OPEN:` item** (shop-specific; this guard is the safety net while they're unconfirmed)
- **Acceptance criteria:** seeding an op with no rate → the Configure banner shows the count **and** the quote-side warning fires on a line item using it; a fully-rated catalog shows neither; deterministic; org-scoped.
- **Test plan (fixtures):** seed one op with a null rate → assert banner count = 1 and a quote using it flags the line; set the rate → both clear. Bind to `/fixtures`.
- **Golden-thread role:** none — orthogonal safety guard; the golden thread uses fully-rated fixtures, so it is unaffected.

---

**M1 done when:** the golden-test harness reproduces every Demo E figure exactly and lifecycle transitions are enforced (the spec's M1 exit), and the golden-thread integration test is green in CI. From here, M3/M4/M5 replace the thread's mock segments one milestone at a time.
