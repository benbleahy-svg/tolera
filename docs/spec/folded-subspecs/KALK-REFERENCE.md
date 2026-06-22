# Kalk — Pricing Language Reference (v1)

**Status:** Spec appendix for Tolera (Bid Factory). **Provenance:** reverse-engineered from the Paperless Parts P3L documentation (9 cheat-sheet articles in `paperless-parts-kb-reference/articles/05-pricing-costing-p3l/`). Per `DECISIONS.md`, **Kalk** is the Tolera name for this DSL — Python-based, **AST-sandboxed**, three execution contexts. This document is the consolidated builtin/object/variable reference that `{kalk}` in the build spec references but does not yet contain (closes Gap-Audit §8).

> **Naming:** source product calls it "P3L"; we call it **Kalk**. Function/object names below are the *semantics to implement*; rename surface strings as desired but keep the contracts.

---

## 1. Execution model

Kalk is a restricted Python 3 dialect (extra globals/functions added; some Python removed for security/performance/determinism). It runs **per operation × per quantity break** — a formula executes once for each quantity on each operation/item, and outputs sum up the component → quote-item → quote tree.

**Five documented formula contexts** (the spec groups these into 3 Kalk execution contexts — map as noted):

| Context | Output variable(s) | Purpose | Spec mapping |
|---|---|---|---|
| **Operation cost** | `COST` (number), `DAYS` (int business days) | Cost + lead-time for one operation/quantity | "operation cost formulas" |
| **Operation/process generation** | (mutates routing; sets custom attrs) | Generate operations on a part from a process template | "operation generation" — see `custom-operation-generation` |
| **Pricing item** | `PERCENTAGE` (markup/margin %); custom items also `set_custom_cost()` | Apply markup/margin to a cost category | "pricing formulas" |
| **Add-on** | `PRICE` (number) | Line-item-level fee (NRE, tooling, cert), required or optional | "pricing formulas" |
| **Discount** | `PERCENTAGE` (positive number) | Deduct % from calculated price | "pricing formulas" |

> ⚠️ **COST vs PRICE inconsistency in source:** the operation cheat sheet uses `COST`; some PP examples use `PRICE` for operations. **Decision for Tolera:** standardize operation output on `COST` + `DAYS`; treat `PRICE` as operation alias only if you choose to. Add-ons use `PRICE`; pricing/discount use `PERCENTAGE`.

**Units:** part data is **metric by default** (mm, mm², mm³, g, g/cm³). Call `units_in()` as the **first** statement to switch the whole formula to imperial; `units_mm()` to be explicit about metric. Calling either after the first statement is an error. (For DACH, metric-default is the natural path — see Gap-Analysis.)

**Pricing theory baseline:** most operations reduce to
`COST = setup_time * rate + runtime * make_quantity * rate` — `setup_time` is one-time per op; `runtime` is per-unit.

---

## 2. Shared Python subset

**Operators:** `* / + -`, augmented `+= -= *= /=`, exponent `**`, comparisons `< <= > >=` (and `== !=`), boolean `and` / `or`, membership `in`. Standard `if/elif/else` and `for` loops.

**Built-in functions** (Python 3.6 semantics):
`min()`, `max()`, `mean()`, `median()` — take an iterable or varargs · `round(number[, ndigits])` · `abs(number)` · `sum(iterable[, start])` · `floor(x)` · `ceil(x)` · `str(x)` · `'{}'.format(args)` (dynamic strings for names/lookups) · `split(x)` / `string.split(sep)` (e.g. `part.material.split(' ')`).

**Removed/Restricted:** no imports, file/network/system access, no arbitrary attribute access — enforce via the AST sandbox (per `DECISIONS.md`). Resource/recursion limits and deterministic evaluation are implementation requirements (Gap-Audit §8).

---

## 3. Variable system

Variables create overridable inputs in the live quoting UI. **All declaration functions (`var`, `table_var`, `table_lookup`, `variable_group`, `drop_down_var`) must NOT be called inside `if/elif/else` or loops.**

### `var(name, default, description, value_type, default_visible=True, frozen=True, quantity_specific=False)`
Declares an operation/formula variable, overridable on the Processes page and per quote item.
- `value_type` ∈ `number` | `currency` | `string` (type-enforced).
- `default` is computed **once at save time** and cannot depend on `part` or other variables (unless `frozen=False`).
- `default_visible=False` hides it from the Processes page by default.
- `frozen=False` → **dynamic variable** (see below).
- `quantity_specific=True` → value is displayed/overridable per quantity break.
- Returns the value after overrides.

**Dynamic variables** (`frozen=False`): initialise to `default`, then `.update(expr)` (may reference `part`, other vars) as many times as needed; call `.freeze()` before using the value for cost — UI overrides apply *at the freeze point*.
```
my_var = var('My Variable', 0, '', number, frozen=False)
my_var.update(max(part.size_x, part.size_y, part.size_z))
my_var.freeze()
```

**Special names `runtime` and `setup_time`:** surface directly on the operations list (not behind the modal). Internally in **hours**; UI display unit configurable (s/min/hr) and overrides are entered in display units.

### `drop_down_var(name, default_value, default_options, description, value_type, frozen=True, quantity_specific=False)`
Discrete-option variable (logic switches / dynamic forms). Methods: `.clear_options()`, `.update_options(P3LList)`, `.select_option(value)`, `.select_default()`. Options can be populated dynamically from custom tables. Search returns ≤50 results. See `drop-down-variables`.

### `variable_group(name, default_collapsed=False)`
Groups `var`/`table_var` into ordered collapsible sections in the quoting UI. Add with `.add_by_name('Var A', 'Var B')`. Declaration order = UI order. Default groups are **primary** (runtime/setup_time) and **declared**. Special `runtime`/`setup_time` cannot be added to groups.

---

## 4. Lists (`P3LList`)

`create_list(*args)` → P3LList (args = values or another P3LList to copy).
**Methods** (mutate-in-place return self for chaining unless noted): `append(item)`, `extend(other)`, `reverse()`, `copy()` (new), `clear()`, `remove(item)` (errors if absent — guard with `in`), `pop(index=0)`, `sort(lambda)`, `filter(lambda)`, `map(lambda)` (new), `reduce(lambda, initial=None)`, `unique(lambda)` (new — first of each unique extracted value), `join(delimiter="\n")` → str.
**Helpers:** `create_multi_sort(*args)` (multi-key sort inside a lambda; prefix `-` for descending), `iterate(list_object)` (loop helper). `min/max/mean/median/sum` work on numeric lists.
```
sm = analyze_sheet_metal()
long_bends = sm.features.filter(
  lambda x: x.name in create_list('bend','curl','open_hem') and x.properties.length > 10
).sort(lambda x: create_multi_sort(-x.properties.length, -x.properties.radius))
```

---

## 5. Custom tables

### `table_var(name, description, table_name, filters, order_by, display_column_name, frozen=True, quantity_specific=False)`
Look up a custom table; overridable in the live UI. `filters` = `create_filter(...)`, `order_by` = `create_order_by(...)`. `display_column_name` = column shown in UI.
- `frozen=True` (default) → returns the **first** matching `TableRow` (or `None`). Returns ≤**200** rows' worth (first match).
- `frozen=False` → returns a `TableVariable` (see below).

### `table_lookup(table_name, filters, order_by, quantity_specific=False) -> P3LList[TableRow]`
Returns **all** matching rows (≤**10,000**); does **not** create an overridable UI variable. Use for bulk data / tooling sets / ERP-derived routing.

### Filtering
- `create_filter(*[filter|exclude])`
- `filter(column, condition, value)` — inclusive · `exclude(column, condition, value)` — exclusive
- `create_order_by(*columns)` — ascending; prefix `-` for descending; multi-column supported
- `create_range(a, b)` — for the `range` condition

| Condition | Types | Example |
|---|---|---|
| `=` | bool, numeric, string | `filter('material','=','Aluminum 6061-T6')` |
| `>` `>=` `<` `<=` | numeric, string | `exclude('length','>',10)` |
| `range` | numeric | `filter('diameter','range',create_range(5,6))` |
| `contains` | string | `filter('material','contains','Aluminum')` |

### `TableRow`
Dot access to columns (alphanumeric, no spaces/leading digits) + built-in `row.row_number`. Helpers: `.to_keys_list()`, `.to_values_list()`, `.to_list()` (→ P3LList of `{key,value}`).

### `TableVariable` (from `frozen=False`)
Properties: `.value` (selected `TableRow` or `None`), `.rows` (P3LList copy). Selection methods (freeze on call; one selection only): `select_first()`, `select_last()`, `select_by_row(row)`, `select_by_row_number(n)`. Overrides apply at the selection point.

---

## 6. Geometry analyzers

Run interrogation and return an analysis object with computed attributes + a `.features` P3LList. **v1 note:** these map to `GeometryService` (OCCT per `DECISIONS.md`); flag which return reduced data until Spatial is licensed.

`analyze_mill3()` · `analyze_lathe()` · `analyze_sheet_metal()` · `analyze_tube_laser()` · `analyze_wire_edm()` · `analyze_casting()` · `analyze_additive()` · `manual_nest()` (gathers nesting-module results).
`get_features(analysis, name=...)` → P3LList of features; each feature has `.name` and `.properties.*` (e.g. `length`, `radius`, `volume`, `area`, `side_length`, `side_width`). Sheet-metal exposes `.thickness`, `.pierce_count`, `.total_cut_length`; lathe exposes `.stock_radius`, `.stock_length`. (Per-family attribute/feature lists → see `DFM-WARNINGS.md` + the `*-process` / `*-interrogation` articles.)

---

## 7. Workpiece & cost/price dictionaries

**Workpiece** — a dict that flows operation→operation along each quantity line:
`set_workpiece_value(key, value)` · `get_workpiece_value(key, default)`. (e.g. pass tapped-hole count from a Tapping op to a downstream Anodize op.)

**Cost dictionary** — `get_cost_value(key)` returns the summed cost of cells whose operation name **or** op-def name matches `key` for the current quantity. Special keys: `--material--`, `--outside--`, `--inside--`, `--total--`.

**Price dictionary (add-ons)** — `get_price_value(key)`; special keys `--required_add_on--`, `--non_required_add_on--`.

---

## 8. Custom part attributes

Top-level part properties usable in Kalk; set manually at quote time or from code. Useful for inputs not extractable from files (e.g. critical tolerances), and to bridge geometric vs non-geometric files.
`set_custom_attribute(key, value)` (value = number/bool/string; type-stable) · `get_custom_attribute(key, default)`. Defaults configurable in settings and copied to every new part.

---

## 9. BOM / assembly iteration

- `get_quantities()` / `get_bom_quantities()` / `get_make_quantities()` → P3LList iterators (index-aligned).
- `get_children(obtain_method=None, is_assembly=None, recursive=False)` → P3LList of `child` objects. `recursive=True` = flat BOM (all descendants × counts to base of tree); `False` = direct children only.
  `child`: `.obtain_method` (`PURCHASED`|`MANUFACTURED`), `.is_assembly`, `.part_number`, `.revision`, `.count`, `.purchased_component`.
- **Pricing-item only:** `get_components(order='leaf_to_root'|'root_to_leaf')`, `get_children(component)`, `get_operations(component|uuid)`, `get_material_operations(component|uuid)` — see §11.3.

---

## 10. Object model

### `part` (operation/add-on context; see §11 for availability)
Geometry/spec attributes — **see `PartGeometry-Attribute-Catalog.md` for the full table with units** (31 attributes incl. `size_x/y/z`, `max/med/min_dim`, `area`, `volume`, `weight`, `density`, `mat_cost_per_volume`, `material`/`_family`/`_class`, `qty`, `bom_qty`, `innate_quantity`, `quantities`/`make_quantities`/`bom_quantities`, `is_root_component`, `is_assembly`, `obtain_method`, `part_number`, `revision`, `count_manufactured_children`, `count_purchased_children`, `purchased_component`).

### `part.purchased_component` (or `None`)
`.oem_part_number`, `.internal_part_number`, `.piece_price` ($, 4 dp), `.description`, plus **custom columns** configured on the Purchased Components tab (e.g. `.insertion_time`, `.bag_price`).

### `op_def`
`.name` (+ `.erp_code` in pricing-item op access).

### `line_item`
`.is_export_controlled` (bool). *(DACH: reframe export-control semantics per Gap-Analysis §B.)*

### `quote` / `contact`
Empty-safe (guard before use; does not auto-refresh on field change — user must refresh pricing).
- `quote.account`: `.name`, `.erp_code`, `.UUID`
- `quote.contact`: `.email`, `.first_name`, `.last_name`, `.full_name`, `.uuid`
- `quote.estimator` / `quote.salesperson`: `.email`, `.first_name`, `.last_name`, `.full_name`, `.erp_code`, `.uuid`
- `quote.facility`: `.name`, `.uuid`
- In **pricing/discount** contexts the object is exposed as `contact` (with `contact.account.name`, etc.).

---

## 11. Context-specific reference

### 11.1 Operation cost context
Output `COST` + `DAYS`. Special: `no_quote()` (blank-cost this op/qty; irreversible), `set_operation_name(name)`, `set_notes(notes)` / `set_notes_from_list(...)`, `is_close(n1, n2, tol=0.001)`, `is_a_in_b(a, b)`. Full access to `part`, analyzers, custom attributes, workpiece, cost dict, BOM iteration. (Purchased-component & assembly costing patterns: see operation cheat sheet §"Purchased Component Costing" / §"Assembly Costing".)

### 11.2 Operation/process-generation context
Runs at the **process** level to generate operations on a part and set custom attributes. Similar surface to operation context. See `custom-operation-generation` (not yet fully captured — read that article when building the process-template engine).

### 11.3 Pricing-item context
Output `PERCENTAGE`. **Markup** `% = (Sell−Cost)/Cost×100`; **Margin** `% = (Sell−Cost)/Sell×100` → `Sell = Cost/(1−pct)` (matches your `DECISIONS.md` margin formula).
- **Standard** items: apply to one of `total | material | inside | outside | purchased_component`.
- **Custom** items: arbitrary cost aggregation; must call `set_custom_cost(number)` (per quantity break) and typically use `get_components()`.
- Globals: `PURCHASED_COMPONENT_COST`, `MATERIAL_COST`, `OUTSIDE_COST`, `INSIDE_COST`, `TOTAL_COST`, `CALCULATION_TYPE` (`MARKUP`|`MARGIN`), `COST_CATEGORY` (`general`|`purchased_component`|`material`|`inside`|`outside`), `CATEGORY_COST`, `contact`, `REQUESTED_QUANTITY`.
- Functions: `set_profit_item_name(name)`, `get_components(order=)`, `get_children(component)`, `get_operations(component)`, `get_material_operations(component)`, `set_custom_cost(cost)`.
- Component object: `.uuid`, `.part_uuid`, `.self_cost`, `.lead_time`, `.process` (`.name`, `.lead_time`), `.part` (full part object), `.get_custom_attribute(k, default)`.
- Operation object (from `get_operations`): `.cost`, `.lead_time`, `.runtime`, `.setup_time`, `.name`, `.category`, `.is_outside_service`, `.is_finish`, `.get_variable(name, default)`, `.op_def` (`.name`, `.erp_code`).
- **Not available:** `part` (top-level), `set/get_custom_attribute`, analyzers (`analyze_*`), `get_child_info()`.

### 11.4 Add-on context
Output `PRICE`. Has full `part` + all operation functions **except** `no_quote()`, all `analyze_*()`, `set_operation_name()`. Extra: `set_add_on_name(name)`, `set_is_required(bool)`, `get_price_value(key)` (`--required_add_on--`, `--non_required_add_on--`). Add-ons are templatable on processes; apply *after* discounts.

### 11.5 Discount context
Output `PERCENTAGE` (positive). `Discounted unit price = rounded unit price × (1 − total discount %/100)`; applied after markups/margins, before add-ons. Globals: `contact`, `REQUESTED_QUANTITY`. Function: `set_discount_name(name)`. Full variable/list/table/workpiece suite. **Not available:** `part`, custom attributes, analyzers, `get_child_info()`.

---

## 12. Implementation notes for Tolera (Kalk)

1. **Three interpreters, shared core:** implement one sandboxed evaluator + per-context globals/output validation. Reject declaration calls inside conditionals/loops (matches source constraint).
2. **Default-at-save semantics:** `var` defaults compute once at save without `part`; only dynamic (`frozen=False`) vars touch `part`. The "freeze point = override point" rule is load-bearing for UI overrides.
3. **Row limits:** `table_var` ≤200 rows, `table_lookup` ≤10,000, drop-down search ≤50 — keep or document deliberate changes.
4. **Geometry coupling:** `analyze_*()` returns are the `GeometryService` output surface (`PartGeometry-Attribute-Catalog.md`). v1 OCCT will populate a reduced feature set per family — Kalk authors need to know which `.properties.*` are guaranteed.
5. **Determinism & golden tests:** Kalk + the verified margin/markup math are ideal golden-test material (Gap-Audit §5/§8). Bind to the Fechner fixtures when delivered.
6. **DACH:** metric-default aligns; ensure `currency` type formats as EUR and number formatting is de-DE (1.234,56 €).

**Source articles (for any detail beyond this summary):** `operation-p3l-cheat-sheet`, `pricing-items-p3l-cheat-sheet`, `add-ons-p3l-cheat-sheet`, `discounts-p3l-cheat-sheet`, `custom-table-p3l`, `p3l-lists`, `drop-down-variables`, `quantity-specific-variables`, `what-is-paperless-parts-pricing-language-p3l` (all in `paperless-parts-kb-reference/articles/05-pricing-costing-p3l/`).
