# Pricing Engine (Kalk) — Sub-Spec

**Status:** Engine sub-spec for Tolera (Bid Factory). **Provenance:** the P3L cheat sheets + pricing/costing articles. Implements Gap-Analysis rec #3 and closes Gap-Audit §8 (Kalk execution model). Kalk = Python-based, **AST-sandboxed**, three execution contexts (`DECISIONS.md`).

**Companion docs:** the full builtin/object/variable catalog → `KALK-REFERENCE.md` (don't duplicate — this doc is the *engine* spec: execution, roll-up math, contract, acceptance). Input contract → `PartGeometry-Attribute-Catalog.md` + `INTERROGATION-ENGINE-SPEC.md`. Entities → `DOMAIN-MODEL.md`.

> **Role:** the deterministic pricing/costing evaluator. It consumes the interrogation engine's output (via `part` + `analyze_*()`) and produces cost, lead time, and price per operation × quantity, then **rolls them up** the BOM tree to the quote. Everything user-facing is CRUD around this engine + the interrogation engine.

---

## 1. Execution model

- A restricted **Python 3** dialect run in an **AST sandbox** (no imports / IO / arbitrary attribute access; deterministic; resource + recursion limits; errors surfaced inline in the formula editor).
- **Runs per (operation × quantity break)** — and per pricing-context formula. Outputs sum up the tree (§3).
- **Five formula contexts** (spec groups into 3 Kalk contexts):

| Context | Output | When |
|---|---|---|
| Operation cost | `COST` (number) + `DAYS` (int business days) | per operation per quantity |
| Operation/process generation | mutates routing / sets custom attrs | when a Process is applied to a part |
| Pricing item | `PERCENTAGE` (+`set_custom_cost` for custom) | per cost-category per quantity (root component) |
| Add-on | `PRICE` | per add-on per quantity (root component) |
| Discount | `PERCENTAGE` (positive) | per discount per quantity (root component) |

> Source uses `COST` (operation cheat sheet) and `PRICE` (some examples) interchangeably for operations — **standardize on `COST`+`DAYS`** for operation context; `PRICE` for add-ons; `PERCENTAGE` for pricing/discount. (See `KALK-REFERENCE.md` §1.)
- **Units:** part data metric by default; `units_in()` as first statement to switch the whole formula to imperial.

**Evaluator interface**
```
Kalk.evaluate(
  formula, context_type, eval_context, quantity
) -> { output (COST/DAYS | PRICE | PERCENTAGE),
       declared_variables[], applied_overrides[], notes, operation_name, errors[] }
```
- `eval_context` exposes: `part` (PartGeometry contract), `analyze_*()` (→ interrogation engine), `quote`/`contact`, `workpiece` + cost/price dicts, `op_def`/`line_item`, custom tables, custom attributes.
- **Variable resolution:** `var(...)` defaults compute **once at save** without `part`; dynamic (`frozen=False`) vars may read `part`/others via `.update()`; **the freeze point is where a UI override applies**. `var`/`table_var`/`drop_down_var`/`variable_group` cannot be declared inside conditionals/loops.

---

## 2. The input contract (interrogation → pricing)

Kalk's inputs are exactly the interrogation engine's outputs:
- **`part.*`** — the geometry/material/identity/BOM attribute catalog (`PartGeometry-Attribute-Catalog.md`). Also `part.mat_cost_per_volume` / `part.mat_cost_per_area` for material pricing.
- **`analyze_<family>()`** — returns the family `AnalysisResult` (`INTERROGATION-ENGINE-SPEC.md` §2): `family_scalars` (e.g. `thickness`, `pierce_count`, `total_cut_length`, `stock_radius`, milling `setups[].runtime/confidence`), `.features` (filter/iterate via P3LList), `.feedback` (DFM warnings).
- **Custom attributes** — manual inputs for non-geometric files (`set/get_custom_attribute`), so one formula prices CAD and PDF parts.
- This attribute list is the **single contract** between the two engines — change it in one place (`PartGeometry-Attribute-Catalog.md`).

---

## 3. Cost roll-up math (the load-bearing part)

For a customer-requested quantity Q on a quote item:

1. **Make quantity** per component is computed from BOM tree position × Q (a child appearing 6× in the tree at Q=1 has make_qty 6). Operation formulas multiply runtime by `part.qty` (= make quantity for that component/break). Deliver qty ≠ make qty (scrap).
2. **Operation cost** (per component, per quantity) = Kalk `COST`; lead-time contribution = `DAYS`. Material ops, inside ops, outside ops, and purchased-component cost are tagged by category.
3. **Component cost** (per quantity) = Σ its operations' `COST`. Cost categories accumulate: `MATERIAL_COST`, `INSIDE_COST`, `OUTSIDE_COST`, `PURCHASED_COMPONENT_COST`, `TOTAL_COST` (Kalk exposes these + `get_cost_value('--material--' | '--outside--' | '--inside--' | '--total--')`).
4. **Roll-up:** child-component costs **roll up the tree to the root component** (= quote item) per quantity. Pricing items, add-ons, expedites apply **only at the root component**.
5. **Price** (root component, per quantity break):
   - **Pricing items** apply markup/margin `PERCENTAGE` to a cost category. **Markup:** `Sell = Cost × (1 + pct)`. **Margin:** `Sell = Cost / (1 − pct)`; profit = `Cost × pct/(1−pct)` (matches `DECISIONS.md`).
   - → **calculated unit price** (rounded).
   - **Discounts** apply after markups/margins: `discounted_unit = rounded_unit × (1 − Σdiscount% / 100)` (discount `PERCENTAGE` is positive).
   - **Add-ons** apply **after** discounts (line-item one-time fees; required or optional; `PRICE`).
   - **Expedite / dynamic lead times**: each option = relative days-faster + `%` markup on price (E4-c).
   - **Invariants:** `unit_price × quantity = total_price`; total rounded to 2 dp; both pre- and post-discount unit prices shown to buyer.
6. **Quote total** = Σ selected quote items (at chosen quantity/lead-time options).

Persist per-break results as **ComponentQuantity** + per-quantity **cells** (operation cells, pricing-item cells, discount cells, add-on cells) with **calculated vs manual(override)** values separated (`DOMAIN-MODEL.md`).

---

## 4. Custom tables, lists, workpiece, BOM iteration

Reference `KALK-REFERENCE.md` for full APIs; engine requirements:
- **Custom tables:** `table_var` (≤200 rows, override-able) / `table_lookup` (≤10,000 rows) with `create_filter/filter/exclude/create_order_by/create_range`; `TableRow`/`TableVariable` selection. Enforce row caps.
- **Lists:** `P3LList` (filter/map/reduce/sort/unique/create_multi_sort) — used heavily to process `.features`.
- **Workpiece** dict + **cost/price** dicts flow operation→operation **along each quantity line**.
- **BOM iteration:** `get_children(obtain_method, is_assembly, recursive)` (operation context); `get_components/get_operations/get_material_operations` (pricing-item context) for assembly-aware pricing.
- **drop_down_var** dynamic forms (often populated from custom tables).

---

## 5. Config-change semantics (E4-d — FREEZE)

Config edits (operations, Kalk, materials, pricing items) **do not** re-price existing drafts/revisions — only new quotes. Opt-in actions (re-run the engine):
- **Regenerate Operations** — items without overrides: delete ops/overrides/manual ops, repopulate from latest Process.
- **Refresh Pricing** (single) / **Bulk Refresh Pricing** (multi-select): re-run while **preserving overrides**; then manual cleanup of stale/added ops & pricing items.
The engine must support a re-evaluate-with-preserved-overrides mode and a clean regenerate mode.

---

## 6. Determinism, security, performance

- Deterministic evaluation (same inputs → same outputs) — prerequisite for golden tests.
- Sandbox: no imports/IO/system; AST allowlist of nodes/builtins (`min/max/mean/median/round/abs/sum/floor/ceil/str/format/split` + operators); resource/time/recursion caps; safe error surfacing (`CHECK`/editor errors).
- Performance: cache `analyze_*()` results; target >100-component BOMs (spec NFR); evaluate per-quantity efficiently; interrogations are async jobs the engine awaits.

## 7. Acceptance / golden tests

- **Golden costing:** the verified demo numbers + Fechner fixtures → assert exact `COST/DAYS/PRICE/PERCENTAGE` and final unit/total prices for known inputs (`DECISIONS.md` margin case + fixtures).
- **Margin/markup**: unit tests for `Sell=Cost/(1−pct)` and `Sell=Cost×(1+pct)`, mixed pricing items by category.
- **Roll-up**: assembly with a repeated child → make-qty and child→root roll-up correct; discounts after markup; add-ons after discount; `unit×qty=total`.
- **Per-context**: each of the 5 contexts evaluates with correct globals/outputs; declaration-in-loop rejected; freeze-point override applied.
- **DACH:** `currency` formats EUR / de-DE; **tax (MwSt/USt) is applied at quote/order level, not inside Kalk**; metric default.

**Sources:** `what-is-paperless-parts-pricing-language-p3l`, `operation-/pricing-items-/add-ons-/discounts-/custom-table-p3l`, `p3l-lists`, `pricing-a-part`, `costing-a-part`, `discounts`, `working-with-existing-quotes-after-an-update-to-pricing-configuration`, the `*-process` articles (all in `paperless-parts-kb-reference/`).
