# Bid Factory Build Spec — Gap Audit
**Audited:** Bid-Factory-Build-Spec.html (v2.14) + 4 supporting docs (PP workflow technical spec, PP build spec, PP technical review, PP 2025 features analysis)
**Goal tested against:** "Hand Claude Code the docs and it builds the entire product."
**Date:** 2026-06-12

---

## Verdict

The spec is exceptionally strong on **what the product does** — screens, fields, workflows, state machines, and the costing math are documented to a level most teams never reach (the verified additive markup model and quote lifecycle are genuinely buildable as written). It is **not yet sufficient for an autonomous Claude Code build**. The gaps cluster in five areas: (1) unresolved foundational decisions, (2) the two AI/geometry subsystems are specified by *outputs* but not by *implementation*, (3) no test fixtures or seed assets to verify against, (4) missing infrastructure specs (email, payments/VAT, API), and (5) the supporting docs contain load-bearing detail the master spec doesn't reference.

Severity legend: 🔴 blocks the build · 🟡 Claude Code will guess (wrongly or inconsistently) · 🟢 minor, fix opportunistically

---

## 1 · Foundational decisions still open 🔴

These change the schema and architecture on day one. Claude Code cannot pick them for you:

| Gap | Why it blocks |
|---|---|
| **Multi-tenancy** (listed as open question) | Affects every table (org_id), email-ingest address scheme, Configure scoping, auth, file storage layout. Single-tenant vs multi-org SaaS must be decided before line 1 of schema. |
| **Backend stack** — spec says "Node (NestJS) **or** Python (FastAPI/Django)" | Pick one. Same for "Tailwind **or** CSS modules", and the auth provider ("e.g. Auth0/Clerk/WorkOS or Keycloak"). Every "or" in the tech stack section becomes a coin-flip. |
| **Deployment target** | "Self-hosted / EU-region" is stated for the geometry engine, but nothing on hosting (Hetzner? AWS eu-central-1?), containerization, CI/CD, environments. Needed for the email/file/queue infrastructure choices. |
| **Geometry engine v1 path** (see §3) | Spatial is "decided" but not licensed. Claude Code cannot sign a license. Without a concrete decision the largest subsystem is unbuildable. |

---

## 2 · Empty screenshot folders 🔴

The spec's own framing is "every screen, field, and behavior is traced to a specific screenshot" — **all 14 `Screenshots/Demo*` folders are empty (0 files)**. The doc explicitly says the figures render as placeholders until files are dropped in.

~36 images exist in the Claude project knowledge, but they are not in the folder Claude Code would receive, and they don't cover the ~150 filenames in the Screenshot Index. Without them, Claude Code has prose only — layout, visual hierarchy, density, and the dark theme are all guesswork.

**Fix:** populate the folders per the index (it doubles as a save-to manifest), or explicitly state which screenshots are unavailable so the spec text is treated as sole authority for those screens.

---

## 3 · Geometry engine: decided on paper, unbuildable in practice 🔴

The spec correctly calls this "the single largest technical risk," but for an autonomous build:

- **No license in hand.** Spatial (lead) and HOOPS (alt) are commercial SDKs requiring procurement, NDAs, and on-prem licensing confirmation (flagged as unresolved in the spec itself). Claude Code can't acquire them.
- **No GeometryService API contract.** No method signatures, job payload schemas, or feature-output JSON shape. Every consumer (viewer, DFM, costing formulas, nesting, part-library hashing) depends on this contract.
- **The OCCT fallback is described but not chosen**, and the spec admits open-source has *no production-grade feature recognition* — meaning hole/pocket/bend/EDM recognition algorithms would need to be designed from scratch. That design doesn't exist anywhere in the docs.
- **DFM warning definitions are names, not formulas.** The master spec lists warning types (Tipped Hole, Wire Conflict, Flushing Issue, W-Bending…) without trigger logic. The supporting PP build spec has *some* (short flange < 2× thickness, close bends 3–4×, deep hole 8–10:1, thin wall < 0.040", internal radius < 0.020") but it's not consolidated, not per-family-complete, and not referenced by the master spec.
- **Geometry signature/hash algorithm** (powers Part Library matching + purchased-component memory) is named but never specified.

**Fix:** decide the v1 path explicitly. Pragmatic recommendation: define `GeometryService` interface + JSON schemas now; build v1 on OCCT/occt-import-js + three.js + ezdxf + trimesh with a *reduced, explicitly listed* feature set per family; treat Spatial as a swap-in once licensed. Add a seed table of every DFM warning → formula → default threshold → per-material/machine overrides.

---

## 4 · AI extraction ("Wingman"): outputs specified, system unspecified 🔴

Email parsing, GD&T/callout extraction with bounding boxes, BOM-table detection, title-block matching, plain-language descriptions — the spec defines what comes out, never how:

- No model/provider decision (Claude API vision? self-hosted? — note the self-hosted "files never leave" stance conflicts with cloud LLM APIs for CUI/ITAR tenants; this needs an explicit policy).
- No prompt specs, no confidence thresholds, no per-extraction-category accuracy expectations, no behavior on low confidence.
- "Build vs buy" is still an open question in the spec's own list.
- The training feedback loop (mark-inaccurate / add-missing) says "persist for retraining" — stored where, used how, per-tenant or global? Undefined.
- The supporting PP build spec has a far richer extraction taxonomy (12 categories, ~100 fields, threads v2, surface finish v2, weld symbols, print regions, 10k+ linked specs) that the master spec doesn't include or reference.

**Fix:** write an extraction-service spec: provider + model per task (email parse / table detect / GD&T OCR), input/output JSON schemas (reuse ExtractionFinding), confidence handling, CUI/ITAR routing policy, and v1 accuracy targets. State plainly that v1 = LLM-with-vision pipeline, not a trained custom model.

---

## 5 · No test fixtures or seed assets 🔴

Acceptance = replaying 14 demo narratives with specific parts, thicknesses, and dollar figures. But there are:

- **No CAD files** (STEP/SLDPRT/STL/DXF) for any demo part
- **No drawing PDFs** with the GD&T callouts the extraction tests need
- **No RFQ .eml file** for the email-ingest flow
- **No seed-data manifest** (tenants, accounts, materials tree, operations library, machine rates, processes, rules) in loadable form — it's scattered through prose
- **No expected-output goldens** (e.g. "this STEP → 3 bends, 0.029in thickness, flat area 29.563")

Claude Code can build the machinery but cannot *verify* any of it end-to-end. This is the difference between "code complete" and "works."

**Fix:** create a `/fixtures` folder: 5–10 representative CAD models + drawings (free STEP samples or your own), one realistic RFQ .eml with attachments, a `seed.json`/SQL for the full Configure catalog, and per-fixture expected-extraction/geometry JSON. Rewrite acceptance criteria to bind to these fixtures instead of unavailable demo parts.

---

## 6 · Infrastructure specs missing 🟡

| Area | What's missing |
|---|---|
| **Email** | Inbound: provider (SES/Postmark/Mailgun), per-org address scheme (blocked on multi-tenancy), .eml parse + attachment/ZIP extraction pipeline, size limits, spam. Outbound: sending domain/DKIM, and the **digital-quote secure link token design** (auth-less buyer access — scope, expiry, revocation). |
| **Payments & tax** 🔴 for DACH | "Credit Card" checkout has no PSP (Stripe/Mollie/Adyen). Bigger: spec is EUR/DACH but tax = a single "Default Tax Rate" (US-style). **German VAT (19/7%), reverse-charge for intra-EU B2B, VAT-ID validation (VIES), and invoice content rules (§14 UStG) are unaddressed.** GoBD retention and ZUGFeRD/XRechnung e-invoicing at least need a deliberate "out of v1" statement. GDPR is flagged "still to scope" — DPA, data residency, erasure/export need a one-page decision before storing customer data. |
| **API layer** | "Open API" is claimed; zero endpoints, auth scheme, or pagination/webhook conventions specified. Either spec it or descope it from v1. |
| **DB schema** | Entity sketch is good but "field types are suggestions." Decide and state: Claude Code derives the canonical schema (recommended), incl. how per-quantity-break values and Calculated-vs-Override pairs are stored (JSONB pattern hinted, not defined). |
| **Files** | Thumbnail generation (2D and 3D — server-side render?), virus scanning, max sizes, storage layout, .eml/ZIP handling. |
| **Search** | "Postgres FTS **or** OpenSearch" — pick (FTS is fine for v1); PDF text indexing pipeline tied to extraction service. |
| **Non-functionals** | Only one perf target exists (>100-component BOM). Add: concurrent users, max file size, browser matrix, backup/restore, audit-log scope (CUI audit is mentioned; general audit isn't), session policy. |
| **Testing strategy** | Acceptance scripts exist; nothing on unit/integration expectations, the costing-engine golden tests (the verified demo numbers are perfect golden-test material — say so explicitly). |

---

## 7 · Third-party adapters: real partners don't exist for you 🟡

PEMConnect/DB Roberts live pricing, TechMate/MSC chat, Online Metals, JobBOSS/Global Shop ERP, HubSpot/Salesforce/SAP CRM — the spec defines adapter interfaces (good) but acceptance criteria demand *live behavior* (inventory dots, dynamic re-query) that requires partnerships you don't have.

**Fix:** state explicitly per adapter: **v1 = interface + mock implementation with seeded data** (deterministic fake distributor inventory/pricing so the green/amber logic is testable), real adapters post-launch. Same for CRM: interface + one mock; HubSpot first real target. ERP: define the push payload schema even for the stub. Without this, Claude Code will either stall or fake it inconsistently.

---

## 8 · P3L: three formula contexts, no language spec 🟡

The object model and helpers are sketched well, but Claude Code will be *designing a programming language* — that needs a definitive reference:

- Full builtin list per context (pricing / operation-generation / operation-formula) — the supporting docs add `table_var()`, `set_notes_from_list()`, `is_close()`, drop-down variables, workpiece dict; master spec has only a subset
- Execution model: sandbox approach (e.g. embedded interpreter vs RestrictedPython), resource limits, determinism, error surfacing in the editor
- Evaluation context: per-quantity-break semantics, variable scoping, what CHECK validates
- Custom Tables: lookup syntax, CSV schema, the quote-time override semantics (only in supporting docs)

**Fix:** one consolidated "P3L Language Reference" appendix merging all functions from all docs, plus a sandbox decision.

---

## 9 · Spec-internal open items Claude Code can't resolve 🟡

The spec's own open-questions list still contains items that surface in UI it must build:

- **Likelihood (win-probability) column** — no formula at all. Decide: manual entry v1 (recommended) or omit.
- Margin-math when mixed with markups — documented but unverified; bless the `cost × pct/(1−pct)` formula as authoritative.
- On-Hold mechanics, revision labels (Rev A/B/C), send preconditions — marked "confirm"; confirm them.
- Rule auto-apply vs suggestion-only — pick suggestion-only v1 (matches demos), state it.
- Canonical default workflow-step set per new org — pick one of the three observed sets as the shipped default.
- Customer portal scope in v1 (digital quote + checkout = yes per demos; EXTERNAL vendor login = ?).
- Belgian locale (nl-BE vs fr-BE) — trivial, but listed.
- Analytics tab: "stub only" — define what a stub renders.

---

## 10 · Supporting docs: valuable, unintegrated, occasionally conflicting 🟡

The four PP docs contain material Claude Code needs but the master spec never points to them, and the user-facing instruction ("hand it the doc/files") leaves precedence undefined:

**Only in supporting docs (would be missed):**
- The 41-step four-role workflow choreography (salesperson → estimator → purchasing → shop floor → manager → send) — the master spec has the *objects*, this has the *sequence*
- Task vs @mention distinction (email + due date vs in-app only) and which roles get which
- Two-layer status convention (overall line-item status manually held "In Progress" until manager approval)
- Purple-suggestion accept-pattern as the universal auto-fill interaction
- Chat history carry-forward on re-quote ("quoting journal")
- DFM threshold numbers and the 62-attribute sheet-metal taxonomy, 52 CNC checks, Swiss-specific variables
- Honest capability ceilings that should shape v1 claims: 5-axis runtime can't be auto-costed (manual override is the designed path), ~50% feature recognition on complex parts, GD&T flagged-not-costed, nesting is estimation-grade (master spec does say this one)

**Conflicts to adjudicate (state which doc wins):**
- Rule signals: master = AND/OR grouping; PP build spec = AND-only
- Quote workflow tracker: master = 4-stage; workflow spec describes different status conventions
- The 2025 features doc proposes *FactoryBid improvements beyond PP* (drag-drop PDF layout builder, urgency scoring, margin-target mode, vendor RFQ portal, two-way email threading) — are these in scope or roadmap? If Claude Code reads them as spec, scope balloons.

**Fix:** add a "Document precedence" section to the master spec (master wins; supporting docs are reference for X, Y, Z; the 2025 improvements doc is roadmap, NOT v1 scope), and pull the DFM thresholds + P3L functions + workflow choreography *into* the master spec or dedicated appendices.

---

## 11 · Build-orchestration gaps for Claude Code specifically 🟡

Even with perfect content, a ~2,700-line monolith describing a multi-year product needs scaffolding for an agentic build:

- **No epic/milestone breakdown with per-milestone acceptance.** Six phases exist, but "done" = all 14 demos = everything. Each phase needs its own verifiable checkpoint (ideally bound to the fixtures from §5) so progress is testable incrementally.
- **No CLAUDE.md / repo conventions**: directory layout, module boundaries (the adapter interfaces are a great start), code style, how to run tests, what to do when the spec is ambiguous (recommended rule: "choose the simplest interpretation consistent with the demos, log the decision in DECISIONS.md").
- **Recommended doc restructure:** split into (1) CLAUDE.md + architecture decisions, (2) data model + API contracts, (3) per-module screen specs, (4) P3L reference, (5) DFM/extraction taxonomies + thresholds, (6) seed data + fixtures + acceptance tests, (7) roadmap/non-goals. Claude Code performs far better with scoped per-module files than one 270KB HTML.

---

## 12 · Minor notes 🟢

- i18n: state that machine-translated German is acceptable for v1 strings, and lock number formatting (1.234,56 €).
- The product is a functional clone of a competitor: replace all reference branding/screenshots in anything customer-facing (spec already mandates renaming — extend to "no PP screenshots ship in the product or marketing").
- "Demo A–E" vs "DemoA–DemoN" inconsistency in the Screenshot Index intro ("one subfolder per demo (DemoA–DemoE)" — there are 14).
- Per-account "1000 unique parts" cap: confirm it's a real billing construct or drop it.
- Spec says both "Two formula contexts" and "Three formula contexts to build" within a page of each other — delete the stale paragraph.

---

## Priority fix list (ordered)

1. Decide: multi-tenancy, backend stack (one), auth provider, deployment target. *(1 day of decisions)*
2. Decide geometry v1 path (recommend: OCCT-based with defined reduced scope, GeometryService contract + JSON schemas, Spatial as swap-in) and write the DFM threshold seed table.
3. Write the Wingman extraction-service spec (provider, prompts/IO schemas, confidence, CUI policy).
4. Build the fixtures pack (CAD + PDFs + .eml + seed.json + goldens) and rebind acceptance criteria to it.
5. Populate the Screenshots folders.
6. Add: VAT/payments decision, email infrastructure spec, digital-quote token design.
7. Consolidate P3L reference + adapter mock policy + document-precedence rules.
8. Resolve the §9 open items (mostly one-line decisions).
9. Restructure into per-module docs + CLAUDE.md + milestone plan.

With items 1–5 done, Claude Code can credibly build and verify Phases 1–3 (foundations, quote builder, viewers minus advanced geometry). Items 6–9 unlock the rest.
