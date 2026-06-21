# Requirements Review — Rules Engine Sub-Spec

**Status:** Build-readiness appendix for Tolera (Bid Factory). Specifies the **rules engine** that turns print/model/text/quote data into actionable, assignable **review items** — the connective tissue between the geometry engine (DFM warnings), the Lens engine (extractions), and the human estimator workflow. **Provenance:** `building-review-rules` (full signal/resolution model + the canonical rule JSON), `requirements-review` (why + lifecycle). Companions: `INTERROGATION-ENGINE-SPEC.md` (produces interrogation-result signals), `AI-LENS-ENGINE-SPEC.md` (produces GD&T/text/feature signals — "each finding can seed a rule"), `DFM-WARNINGS.md` (the feedback signals), `PartGeometry-Attribute-Catalog.md` (part-property signals), `SEED-AND-FIXTURES.md` (starter rule library), `DECISIONS.md`.

> **Why it exists.** Quoting from prints is the bottleneck: hundreds of requirements buried across many pages, *hours* of a senior estimator's time just to answer "should we even make this?". Rules let a shop encode that judgment **once** so the requirement is flagged **every** subsequent time it appears — capturing tribal knowledge, training juniors, and producing an audit trail. This is Tolera's equivalent of PP **Requirements Review**.

---

## 1. Core model: signals → resolutions

A **rule** connects **signals** (conditions over data from prints, models, document text, and high-level line-item/quote data) to **resolutions** (the decisions/actions a user takes in response). When a rule's signals match a component, a **review item** is created and (optionally) auto-assigned.

Worked example: *a tight true-position tolerance on a print* → **Signal:** ≥1 tight true-position tolerance present → **Resolution:** No-quote **or** send for outside processing.

---

## 2. Signal catalog (what you can test)

Signals are built from file, line-item, part, and quote data. Top-level categories (each maps to one or more `document_path` keys in §4):

- **GD&T & callouts** — holes, sinks, bores, control frames, dimensions, tolerances. (Source: Lens GD&T extractions + geometry.)
- **Document text** — raw text from any `.pdf .tiff .doc .docx`; simple **keywords** (with case matching) **or** complex **regex** patterns.
- **Interrogation results** — high-level properties, **features**, and **feedback (DFM warnings)** for **sheet metal, tube laser, milling, turning**. *⚠ Only evaluated after the relevant interrogation has run* (manually, or by setting a process / adding operations). Source: `INTERROGATION-ENGINE-SPEC.md` + `DFM-WARNINGS.md`.
- **Presence of files by type** — whether the part has a **model** and/or a **print** (`has_model`, `has_print`).
- **Part properties** — high-level geometric attributes (auto-filled from models; manually enterable from prints), **is_assembly** (T/F), **is_root** (T/F). Source: `PartGeometry-Attribute-Catalog.md`.
- **Line-item information** — minimum / maximum requested quantity.
- **Quote information** — the **account** being quoted.

The signal picker shows a description for each option. Units are switchable per signal (in ↔ mm); **Tolera default = mm** (see §7).

---

## 3. Resolution catalog (what you can do)

A resolution is one selectable outcome presented to the user on the review item:

| Resolution | Effect | Params |
|---|---|---|
| **No-quote** | Set that component's line-item status to *no-quote*. | — |
| **Assign line-item estimator** | Assign that component's line item to a specified estimator. | estimator id |
| **Set process** | Set the component's process. | `process_id` |
| **Add operation** | Append the specified operation(s) to the bottom of the router. | `op_def_ids[]` |
| **Resolve (custom label)** | Resolve with no other change; the label captures a real-world task/decision the system can't model (e.g. "Outsource", "Contacted customer", "We have the spec doc"). | `custom_label` |

A rule offers **one or more** resolutions; the user picks the one that applies, which both records the decision and (for No-quote/Set process/Add operation) mutates the quote/router.

---

## 4. Canonical rule schema (build to this)

PP rules import/export as a **single JSON string** (paste-in on the rules config page). Tolera adopts the same serialized shape so rule sets are portable and diffable. Structure (reverse-engineered from the `building-review-rules` inspiration pack):

```jsonc
Rule {
  "uuid": "…",
  "name": "All tight dimension tolerances",
  "description": "…",
  "logical_operator": "OR" | "AND",      // how the top-level signals combine
  "signals": [ Signal, … ],
  "resolutions": [ Resolution, … ],
  "default_assignee_id": null | "<user_id>"
}

Signal {                                  // one "case"
  "logical_operator": "AND" | "OR",
  "groups": [ Group, … ]
}

Group {
  "document_path": "length_tolerances",   // WHAT collection to test (see catalog below)
  "logical_operator": "AND" | "OR",
  "queries": [ Query, … ],                // field-level predicates
  "count_query": null | { "value": 7, "operator": "greaterThanOrEqual" }  // test the COUNT of items
}

Query {
  "field_name": ["smallest_delta"],       // field within the document_path item
  "operator": "lessThanOrEqual" | "greaterThanOrEqual" | "equals"
            | "includesCaseInsensitive" | "regex",
  "value": 0.005,                         // scalar, array (keyword list), or regex string
  "value_type": "distance" | "angle" | "number" | "string" | "boolean",
  "filter_type": "numeric" | "string" | "boolean",
  "units": "in" | "mm" | "deg" | null
}

Resolution {
  "type": "NO_QUOTE" | "RESOLVE" | "ADD_OPERATION" | "SET_PROCESS" | "ASSIGN_ESTIMATOR",
  "parameters": [ { "name": "op_def_ids", "value": [14936] }, … ],
  "custom_label": null | "Outsource"
}
```

**Combination semantics** (the part everyone gets wrong — call it out in the UI):
- Top-level `logical_operator: "OR"` across signals → match if **any** case matches (the usual choice for "flag any of these").
- `"AND"` → **all** cases must match.
- Same recursion applies within a Signal's groups and a Group's queries.

**`document_path` catalog** (the addressable collections; from the inspiration pack):

| Group | `document_path` values | Typical `field_name` | Source |
|---|---|---|---|
| Length/size tolerances | `length_tolerances`, `diameter_tolerances`, `radius_tolerances`, `angular_tolerances` | `smallest_delta` (tightest of upper/lower) | Lens |
| Control frames (per characteristic) | `flatness_…`, `parallelism_…`, `perpendicularity_…`, `position_…`, `cylindricity_…`, `straightness_…`, `concentricity_…`, `profile_of_line_…`, `profile_of_surface_…`, `runout_…`, `total_runout_…`, `symmetry_…`, `circularity_control_frames` | `value`, `datum_count` | Lens |
| Frame/datum **counts** | `control_frames`, `datums`, `position_control_frames` | `count_query`, `datum_count` | Lens |
| Dimensions | `greatest_distance_dimension`, `least_distance_dimension` | `value` | Lens |
| Part | `part` | `max_dim` (and the broader part-attribute set) | Geometry |
| Files | `files` | `has_model`, `has_print` (boolean) | File pipeline |
| Document text | `text` | `raw_text` (`includesCaseInsensitive` keyword[] or `regex`) | Lens/OCR |
| Interrogation | `three_axis_mill.machine_direction` (count), sheet-metal / tube-laser / lathe property paths | per family (see interrogation spec) | Geometry |

> **Build note.** This is effectively a small, serializable **query AST** over the part's analyzed data. Implement an evaluator that, given a component's `{extractions, interrogation_result, part_attributes, files, line_item, quote}`, evaluates each Rule and emits review items. Keep `value_type`/`units` so numeric comparisons normalize correctly (distance in mm, angle in deg).

---

## 5. Worked rules (from PP's inspiration pack — keep as test cases)

These are real PP rules; retain them (re-unit'd to metric) as engine regression fixtures:

1. **All-in-one tight tolerances** — every tolerance/control-frame `document_path`, each `smallest_delta`/`value ≤ 5 thou (→ 0.13 mm)`, combined with top-level **OR**; resolutions: No-quote / "Outsource" / "Feasible in-house".
2. **Machine-envelope check** — `greatest_distance_dimension.value ≥ 12"` **OR** `part.max_dim ≥ 12"` (→ machine-bed limit in mm); No-quote / Outsource / Feasible.
3. **Missing model or print** — text includes "MODEL" **AND** `files.has_model == false`, **OR** `files.has_print == false`; Resolve: "Contacted customer" / "Quote without the file".
4. **Part complexity (Level 3)** — composite of `control_frames.count ≥ 7`, `datum_count ≥ 2`, position frames with `datum_count ≥ 3`, `datums.count ≥ 5`, 3-axis machine-direction count ≥ 5, tight least-distance dimension — routes to programming for a runtime estimate.
5. **Finish keyword → add operation** — text `includesCaseInsensitive ["anodiz" | "passiv" | "grind"|"debur"|"REMOVE ALL BURRS"]` → `ADD_OPERATION(op_def_ids=[…])` (ties directly to the seeded Operation Library ids).
6. **Spec/standard detection** — large `regex` over the shop's accepted spec list → Resolve.
7. **OEM-specific spec** — `regex ^SPX-[A-Za-z0-9-]+$` style → Resolve "We have / need the spec doc".
8. **Vendor picking (material spec)** — text matches a material standard → Resolve with vendor options.
9. **Bulk-assign process** — text includes "bracket"/"plate" → `SET_PROCESS(process_id=…)` (sheet metal).

---

## 6. Review-item lifecycle & collaboration

1. **Trigger:** after AI/interrogation finishes (spinner in viewer / Found-in-Files), matching rules create **review items** in the **Review Items panel** (the burn-down list).
2. **Assign:** `default_assignee_id` auto-assigns + notifies; items can be reassigned.
3. **Collaborate:** each item carries a **chat thread**; discussion/decisions are permanently stored (audit trail).
4. **Context for consistency:** show up to **5 past parts** the rule flagged + the decision taken there, so juniors act consistently.
5. **Resolve:** user selects one configured resolution → mutates quote/router as applicable → item closes. **Summary view + bulk actions** to mass-resolve across the quote.
6. **Audit:** resolutions, assignee, thread, and timestamps are retained for production handoff and future quoting insight.

**Permissions:** building/editing rules requires the **edit permission on "processes"** (PP). Map to Tolera's RBAC (`AUTHZ`). Resolving items needs quote-edit.

**Build/test loop (PP guidance worth shipping):** create rule → upload a print with the target condition → wait for AI → confirm the item appears; if not, check Found-in-Files + the default units, and that the dimension was actually extracted (label it manually if missed).

---

## 7. DACH adaptations (vs PP defaults)

- **Metric-native.** Default signal units = **mm** / **deg**; seed thresholds in mm (PP's 5-thou tight-tolerance → **0.13 mm**; 12″ envelope → the org's actual bed size in mm). Keep the in↔mm unit toggle but never default to inches. (Consistent with `DACH-DELTA-LAYER.md` "drop the imperial path".)
- **ISO GPS GD&T.** Control-frame signals interpret **ISO GPS** symbology (not just ASME Y14.5); datum/material-condition semantics per ISO. (Lens emits ISO-GPS-aware findings.)
- **DIN/EN material & spec detection.** The "your shop's specs" / OEM-spec regex pattern stays, but the seeded list is **DIN/EN / Werkstoffnummer** and **EU OEM** specs (e.g. Airbus/automotive), not the US MIL/BAC/BMS aerospace dump.
- **Export-control as dual-use.** Replace the ITAR/US-export framing with an **EU dual-use** rule: *Lens `export_controlled`/dual-use finding → require manager review / confirm classification* (seed rule in `SEED-AND-FIXTURES.md`). Pairs with the EU-routing guarantee in the Lens spec.
- **German keywords.** Finish/process keyword rules include German terms (e.g. `eloxier` for anodize, `entgraten` for deburr, `passivier`, `schleifen` for grind), mapped to the seeded German Operation Library ids.
- **Starter rule library** ships seeded (per `SEED-AND-FIXTURES.md §7`): export-control review; no-material-specified → block send; tight-tolerance → senior estimator; missing model/print; finish-keyword → add op.

---

## 8. How the three engines feed signals (integration map)

| Signal source | Produced by | Feeds `document_path` |
|---|---|---|
| GD&T, dims, tolerances, control frames, holes/threads/c'sinks, material/spec text | **Lens** (`ExtractionFinding`, `AI-LENS-ENGINE-SPEC §8`) | `*_tolerances`, `*_control_frames`, `text`, dimension paths |
| Interrogation properties, features, **DFM warnings/feedback** | **GeometryService** (`AnalysisResult`, `INTERROGATION-ENGINE-SPEC §2`; thresholds in `DFM-WARNINGS.md`) | family interrogation paths |
| Part geometric attributes, is_assembly, is_root | **Geometry / part record** (`PartGeometry-Attribute-Catalog.md`) | `part` |
| has_model / has_print | **File pipeline** | `files` |
| min/max requested qty | **Line item** | line-item signal |
| account | **Quote/CRM** | quote signal |

A Lens or DFM finding surfaced in Found-in-Files offers **"build a Review rule from this finding"** — the one-click path from observation → reusable rule.

---

## 9. Acceptance criteria

- **Schema round-trip:** export a rule set to the JSON string and re-import it byte-equivalently; the nine §5 rules import and evaluate.
- **AST evaluation:** given a fixture component's analyzed data, the evaluator produces the expected review items (and *none* for non-matching) — wire to `/fixtures` goldens.
- **Interrogation gating:** interrogation-result signals do **not** fire before the relevant interrogation has run; they do after.
- **AND/OR semantics:** a multi-case OR rule fires on any single case; an AND group requires all queries.
- **Resolution effects:** No-quote sets line-item status; Set process / Add operation mutate the router; Resolve(label) closes with no mutation; assignee notified.
- **Lifecycle:** item appears post-AI, threads, shows ≤5 prior decisions, supports bulk resolve, retains audit trail.
- **DACH:** thresholds evaluate in mm; ISO-GPS control frames; German finish keywords map to seeded ops; the dual-use export rule fires on a flagged fixture and blocks send pending review.
- **Permissions:** rule editing gated on process-edit; resolving gated on quote-edit.

**Sources:** `building-review-rules`, `requirements-review` (in `paperless-parts-kb-reference/`); cross-refs `INTERROGATION-ENGINE-SPEC.md`, `AI-LENS-ENGINE-SPEC.md`, `DFM-WARNINGS.md`, `PartGeometry-Attribute-Catalog.md`, `SEED-AND-FIXTURES.md`, `DOMAIN-MODEL.md`, `DECISIONS.md`.
