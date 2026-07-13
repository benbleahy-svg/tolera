# CLAUDE.md — Build Guide & Document Index

**Read this first.** This is the orientation file for any agent (Claude Code or otherwise) working in the Bid Factory project. It tells you *what we're building*, *which document is authoritative for what*, the *precedence order* when documents disagree, the *repo conventions*, and the *block-and-log rule* for handling ambiguity. It is intentionally short; the detail lives in the documents it points to.

> **2026-06-21 — Single-source fold-in.** The thirteen engine/contract sub-specs (Kalk, pricing, geometry/interrogation, DFM, PartGeometry, rules, Lens, domain model, DB schema, integration API, viewer/file-types, user-stories/workflows, DACH delta) were **enriched with the Paperless Parts KB and folded inline into `Bid-Factory-Build-Spec.html`**, which is now the **single self-contained build source** for Claude Code — KB-cited (89 articles, green `KB:` chips), ~620 KB, with new sub-anchors (`#kalk-*`, `#geometryservice`, `#dfm-catalogue`, `#rules-*`, `#lens-*`, `#db-schema`, `#api-*`, `#dach-delta`, …). The folded sub-specs are frozen under `docs/spec/folded-subspecs/` as provenance — **do not edit them; edit the spec.** `DECISIONS.md` still overrides everything; `SEED-AND-FIXTURES.md` (fixtures harness) + `E4-Behavioral-Gaps.md` remain standalone.

---

## 0. Repository layout

All planning docs live under `docs/`, organized so **folder = precedence tier** (see §2). Application code (added during the build) lives at the repo root alongside `CLAUDE.md`.

```
<repo root>
├── CLAUDE.md                      ← this file (orientation; auto-loaded)
├── README.md                      ← human quickstart
├── docs/
│   ├── decisions/                 ← TIER 1  DECISIONS.md
│   ├── spec/                      ← TIER 2  Bid-Factory-Build-Spec.html + SPEC-INDEX.md + folded-subspecs/ (frozen provenance)
│   ├── subsystems/                ← E4-Behavioral-Gaps.md + DOMAIN-MODEL.mermaid (engine sub-specs FOLDED into the spec → docs/spec/folded-subspecs/)
│   ├── fixtures/                  ← TIER 3  SEED-AND-FIXTURES.md + seed.skeleton.json
│   ├── analysis/  (+ ui/)         ← TIER 4  gap audits, research, UI mock
│   └── reference/                 ← TIER 5  screenshots/ + Screenshot-Mapping.* (kb/ = signpost; PP KB parked in archive/)
├── ui-prototype/                  ← throwaway UI prototype (separate session)
├── build-plan/                    ← execution map: README + M0–M6 + DEMOS-TRACEABILITY.md (the build blocks; see §8)
└── archive/                       ← backups + parked PP KB (kb-reference/) — ignored (folded sub-specs now tracked at docs/spec/folded-subspecs/)
```

**Reference convention:** docs cite each other by **bare filename** (e.g. `DB-SCHEMA.sql`). Resolve by filename — every name maps to exactly one file under `docs/<tier>/`. Use `docs/spec/SPEC-INDEX.md` to jump into the master HTML spec by section anchor instead of loading the whole (~620 KB) file. The spec is now **self-contained** — engine internals are folded in at the anchors listed in §3.

---

## 1. What we're building

**Tolera** (working title "Bid Factory") is a **DACH-region clone — and intended better version — of Paperless Parts**: an instant-quoting / RFQ platform for custom manufacturers (CNC machining, sheet metal, tube laser, turning, assembly). It ingests RFQs and CAD/print files, analyzes geometry and requirements, and produces priced quotes fast.

Three hard subsystems carry the product (each has its own sub-spec):
- **GeometryService** (v1 on **OCCT**, Spatial swap-in later) — 3D solid interrogation → manufacturability features + DFM feedback.
- **Lens** (= PP "Wingman/PartBot") — the AI layer: print/PDF/email extraction, BOM detection. Surfaced via the **AI-Governor** UI pattern (purple, 55% opacity, explicit Accept).
- **Kalk** (= PP "P3L") — the Python-AST-sandboxed pricing DSL.

The rules engine (**Requirements Review**) ties geometry + Lens findings to assignable review items. Region: **DE/AT/CH**, metric-native, EUR/CHF, German-first UI, DATEV/EU integrations, GDPR + EU dual-use export control. Stack anchors: **Clerk** auth, **Mailgun EU** ingest, **Paddle** billing, **PostgreSQL**. Pilot org slug **`fechner`** (`fechner@rfq.tolera.eu`); golden fixtures due **2026-06-23**.

Working-name glossary: **Tolera** = product · **Kalk** = pricing DSL (P3L) · **Lens** = AI extraction (Wingman) · **GeometryService** = interrogation engine · **AI-Governor** = the purple suggestion UI · **Werkstoffnummer** = DIN/EN material number (e.g. `1.4301` = X5CrNi18-10 = 304).

---

## 2. Document precedence (authority ladder)

When two documents conflict, **higher tier wins**. Resolve conflicts *up* the ladder; never silently pick the lower source.

1. **`DECISIONS.md` — the living decision log.** Any explicit decision here **overrides everything**, including the master spec. This is where conflicts get resolved and where new decisions are recorded. *Always check it before acting on a contested point.*
2. **`Bid-Factory-Build-Spec.html` — the master product spec.** Authoritative for product scope, feature set, and UI/UX intent (≈418 sections; anchors like `{kalk}`, `{interrogations-config}`, `{dach-costing}`, `{geometry-engine}`, `{integration-manager}`, `{auth}`, `{authz}`, `{billing-decided}`, `{ai-settings}`). The backups in `archive/` (`*.v2.14.backup.html`, `*.html.bak2`) are **history — ignore**. **As of 2026-06-21 this file is the single self-contained build source: the engine sub-specs below are folded into it (see §3 anchors); on any conflict the spec wins and the archived sub-spec is mere provenance.**
3. **Subsystem sub-specs — FOLDED into the spec (2026-06-21); now archived provenance in `docs/spec/folded-subspecs/`.** Their internals (schema, math, contracts) now live inline in `Bid-Factory-Build-Spec.html` at the §3 anchors and are the build target there. The originals are kept for traceability only. The set: `DOMAIN-MODEL.md`/`.mermaid`, `DB-SCHEMA.sql`, `INTERROGATION-ENGINE-SPEC.md`, `PRICING-ENGINE-SPEC.md` + `KALK-REFERENCE.md`, `AI-LENS-ENGINE-SPEC.md`, `RULES-ENGINE-SPEC.md`, `INTEGRATION-API-CONTRACT.md`, `VIEWER-AND-FILE-TYPES.md`, `DACH-DELTA-LAYER.md`, `DFM-WARNINGS.md`, `PartGeometry-Attribute-Catalog.md`, `SEED-AND-FIXTURES.md` + `seed.skeleton.json`, `USER-STORIES-AND-WORKFLOWS.md`, `E4-Behavioral-Gaps.md`.
   - **`DACH-DELTA-LAYER.md` is a cross-cutting override:** wherever any document (or the PP KB) describes US/imperial/ITAR/QuickBooks behavior, the DACH delta **wins** (metric, EUR/CHF + MwSt/USt, DIN/EN, GDPR + EU dual-use, DATEV).
   - **Within a subsystem, the more specific spec wins for its own internals** (e.g. Lens-vs-Geometry boundary is fixed in the Lens spec §0/§9).
4. **Analysis & rationale (non-normative):** `Build-Spec-Gap-Audit.md`, `KB-Coverage-Gap-Analysis.md`, `Screenshot-Mapping.md`, `Onboarding-Research-and-Design.md`, the `UI-*Research/Recommendations*.html`, `Infrastructure-Audit.html`, `BidFactory-LiveMock.html`. Use for *why* and for design options — not as a source of binding requirements.
5. **`paperless-parts-kb-reference/` (186 articles) — upstream PP behavior.** Descriptive "how PP does it," the raw material the sub-specs were distilled from. **Not** a Tolera spec; superseded by tiers 1–3 wherever they speak, and always by the DACH delta.

---

## 3. Document index (what each file is authoritative for)

> Paths are under `docs/` per §0. **The tier-3 sub-specs are now folded into `Bid-Factory-Build-Spec.html`** at the anchors shown — read them there; the source files are frozen in `docs/spec/folded-subspecs/`. Fold-in anchors: DOMAIN-MODEL+DB-SCHEMA→`#model`/`#model-4layer`/`#db-schema`; INTERROGATION+DFM→`#geometryservice`/`#dfm-catalogue`; PartGeometry→`#partgeometry`; PRICING+KALK→`#kalk`…`#kalk-golden`; AI-LENS→`#lens-engine`…`#lens-accept`; RULES→`#rules-engine`…`#rules-accept`; INTEGRATION-API→`#api-contract`…; VIEWER→`#viewer3d-tools`/`#pdf-capabilities`; USER-STORIES→`#states-roles`/`#states-stories`; DACH-DELTA→`#dach-delta`.

| Document | Authoritative for | Tier |
|---|---|---|
| `DECISIONS.md` | All resolved decisions + open questions (the override log) | 1 |
| `Bid-Factory-Build-Spec.html` | Product scope, features, UI/UX | 2 |
| `DOMAIN-MODEL.md` / `.mermaid` | Entity model: Part→Node→Component→QuoteItem, ComponentQuantity, Material hierarchy, RFQ | 3 |
| `DB-SCHEMA.sql` | Canonical PostgreSQL DDL (53 tables, 16 enums), RLS/org-scoping, calc-vs-override, DACH fields | 3 |
| `INTERROGATION-ENGINE-SPEC.md` | GeometryService interface, per-family `AnalysisResult` scalars, OCCT v1 ceilings | 3 |
| `PRICING-ENGINE-SPEC.md` + `KALK-REFERENCE.md` | Cost roll-up math; Kalk DSL contexts/vars/tables | 3 |
| `AI-LENS-ENGINE-SPEC.md` | 4 AI pipelines, `ExtractionFinding` schema, EU/GDPR routing, never-hallucinate | 3 |
| `RULES-ENGINE-SPEC.md` | Rule JSON schema, signal/resolution catalog, review-item lifecycle | 3 |
| `INTEGRATION-API-CONTRACT.md` | REST + Streaming/webhook contract, Managed-Integrations, event catalog, DACH connectors | 3 |
| `VIEWER-AND-FILE-TYPES.md` | 3D/PDF viewer UX, render limits, supported-file/interrogation matrix | 3 |
| `DACH-DELTA-LAYER.md` | Region overrides (tax, e-invoicing, materials, export control) — **cross-cutting** | 3* |
| `DFM-WARNINGS.md` | Per-family DFM warning catalogue + default thresholds | 3 |
| `PartGeometry-Attribute-Catalog.md` | `part.*` attributes + units + v1 feasibility flags | 3 |
| `SEED-AND-FIXTURES.md` + `seed.skeleton.json` | Org-provisioning seed + golden-fixtures harness | 3 |
| `USER-STORIES-AND-WORKFLOWS.md` | Roles, choreography, state diagrams, 23 stories w/ ACs | 3 |
| `E4-Behavioral-Gaps.md` | Resolved behavioral-gap decisions (multi-org, config-freeze, analytics…) | 3 |
| `KB-Coverage-Gap-Analysis.md` | 186-article coverage matrix vs spec (provenance/rationale) | 4 |
| `Build-Spec-Gap-Audit.md` | The original gap audit (§4 AI, §5 seed, …) | 4 |
| `Screenshot-Mapping.md`, `Onboarding-*`, `UI-*`, `Infrastructure-Audit.html`, `*LiveMock.html` | UI research, onboarding, infra options, mock | 4 |
| `archive/kb-reference/` (PP KB, 186 articles; **parked** during build) | Upstream PP behavior (descriptive) | 5 |

\* DACH delta is tier-3 but **overrides** any region-specific behavior elsewhere.

---

## 4. The KB source

The Paperless Parts knowledge base (186 articles, Markdown) is the upstream reference the sub-specs were built from. It has already been distilled into the tier-1–3 specs, so during the build it is **parked in `archive/kb-reference/`** (out of the tracked tree to keep things focused) — `INDEX.md` (grouped index), `articles/01-…`–`14-…/` (one file per article, cited by **slug**), and `index.html`. It stays **on disk and greppable** (grep ignores `.gitignore`); to bring it back into the active tree run `mv archive/kb-reference docs/reference/kb/paperless-parts-kb-reference`. Treat it as tier-5 (descriptive); when it conflicts with a sub-spec or the DACH delta, the sub-spec wins. Cite articles by slug (e.g. `building-review-rules`); coverage vs the spec is mapped in `KB-Coverage-Gap-Analysis.md`.

---

## 5. Repo conventions

- **Tenancy:** every domain table is **org-scoped**; enforce via RLS (`DB-SCHEMA.sql`). Machine integrations use per-integration API **tokens** (org-scoped), users use Clerk sessions. No cross-org reads.
- **Money:** integer **minor units + explicit `currency`** (EUR/CHF), never a bare float. Display with German locale formatting (`1.234,56 €`; CH `CHF 1'234.56`). Tax = MwSt/USt (DE 19%/7%, AT 20%, CH 8.1%).
- **Units:** **metric-native** — mm / kg / deg. The imperial path PP carries is **dropped** (toggle may exist, default never imperial).
- **Identifiers:** UUID PKs; `snake_case` columns + JSON fields; ISO-8601 UTC timestamps.
- **Calculated vs override:** persist both; resolve with `COALESCE(manual_*, calc_*)` (see schema) so recalculation never destroys human input.
- **AI output:** Lens results are **suggestions** (AI-Governor, explicit accept); **never** auto-fed into Kalk costing; **never hallucinated** (a value not on the print must not be invented).
- **Language/i18n:** German-first UI + email templates; ISO GPS for GD&T.
- **Naming:** sub-spec files `UPPER-KEBAB.md`; keep cross-references by filename so the index stays navigable.

**Engineering (cross-cutting — scaffolded in `build-plan/M0.1`, inherited by every block):**
- **Logging:** structured **JSON** logs carrying a request-id + `org_id` + user; **never** log secrets or customer PII / print contents; one logging config shared by API + workers.
- **Errors & validation:** one API **error envelope** (`{code, message, details}`); validate input at the edge with **Pydantic v2**; never leak a stack trace to a client or external recipient.
- **Async jobs:** all long work (extraction, geometry, nesting, email sync) runs on **Celery** — tasks **idempotent** (safe to re-run), **retried with backoff**, **timeout-bounded**, **dead-lettered** on final failure; never block a request on it.
- **Observability:** a health/readiness endpoint + baseline metrics (request latency, job success/failure, queue depth); instrument the usage funnels the spec calls out (e.g. Vendor-RFQ open/submit/apply) from day one.
- **Migrations:** every schema change is a **reversible Alembic migration** (autogenerate + human review); **no manual DDL**; migrations run in CI and on deploy.

---

## 6. The block-and-log rule (how to handle ambiguity)

When you hit a question the precedence ladder (§2) does **not** resolve:

1. **Do not guess on anything expensive to reverse** — DB schema, pricing/tax math, the domain model, money handling, external API contracts, security/permissions, or anything touching customer data. For these, **stop and log**.
2. **Log it in `DECISIONS.md`** as an `OPEN:` entry — state the question, the options, the trade-offs, and a **recommended default** — then continue on work that does **not** depend on the answer.
3. **Proceed without blocking only** on low-stakes, reversible choices (internal naming, layout, comments); note the assumption inline.
4. **Never** invent a fact, a regulatory rule, or a PP behavior. If the KB and the DACH delta are both silent, it's an `OPEN:` item — verify (web/official source) or ask.
5. When a decision is made, **move it from `OPEN:` to a dated resolved entry** in `DECISIONS.md`. That file is the single source of truth for "what did we decide and why."

This keeps irreversible choices human-gated while letting reversible work flow. Open items already flagged across the sub-specs (e.g. the 150-vs-250 MB upload limit in `VIEWER-AND-FILE-TYPES.md`, the 54-op rates and starter rule set in `SEED-AND-FIXTURES.md`, Lens correction-storage scope) belong in `DECISIONS.md` under `OPEN:`.

---

## 7. Suggested build order

Foundations first, then the engines, then the workflow:

1. **Schema + tenancy + auth** (`DB-SCHEMA.sql`, RLS, Clerk) → **seed** a clean org (`SEED-AND-FIXTURES.md`).
2. **GeometryService** (`INTERROGATION-ENGINE-SPEC.md`) + **3D/PDF viewer** (`VIEWER-AND-FILE-TYPES.md`).
3. **Lens** (`AI-LENS-ENGINE-SPEC.md`) + **Found-in-Files**, feeding the **rules engine** (`RULES-ENGINE-SPEC.md`).
4. **Kalk** + cost roll-up (`PRICING-ENGINE-SPEC.md`, `KALK-REFERENCE.md`).
5. **Quote/RFQ workflow** (`USER-STORIES-AND-WORKFLOWS.md`) + **email ingest** + **integrations/e-invoicing** (`INTEGRATION-API-CONTRACT.md`).
6. Apply **`DACH-DELTA-LAYER.md`** throughout (not a final step — a constraint on every layer).

Verify each milestone against the **golden fixtures** (`SEED-AND-FIXTURES.md` Part 2); slot in the Fechner packages on **2026-06-23**.

---

## 8. Build-time source protocol — demos, screenshots, KB

The execution map is in `build-plan/`: `README.md` (the spine — sizing rubric, golden-thread, dependency graph, per-session protocol), one file per milestone `M0`–`M6`, and `DEMOS-TRACEABILITY.md` (the demo → block → screenshot → fixture map). When executing a build block:

- **Load only the block's cited sources** — its spec anchors, the one folded sub-spec, its `KB:` links. Navigate via `docs/spec/SPEC-INDEX.md`; don't load the whole spec. Conserving context is the sizing constraint.
- **Demos are the acceptance oracle.** Via `DEMOS-TRACEABILITY.md`, a block's demo points to the narrative (`Bid-Factory-Build-Spec.html#demos` / `#acceptance`) and the `docs/reference/screenshots/Demo<X>/` frames. The **screenshots are the UI ground truth** (layout, controls, copy) — build to them; the **fixture is the machine-checkable form** — verify against it.
- **KB** (`[KB: slug]` → `https://help.paperlessparts.com/s/article/{slug}`, or grep `archive/kb-reference/` by slug) is the upstream behavioural detail behind a feature (tier-5, descriptive).
- **Reference, never copy.** Demo / spec / KB text is not duplicated into code or the plan — it would drift from its source (DRY).
- **Precedence holds:** `DECISIONS.md` > spec > folded sub-spec > analysis/screenshots > KB; the **DACH delta overrides** any US/imperial/ITAR/QuickBooks behaviour a screenshot or KB article shows. A pixel never outranks the spec. Don't guess — **block-and-log** (§6).

---

## 9. Operating procedure — the per-block loop (hook-enforced)

Every build block runs this loop **in a fresh session — one block = one session, no exceptions**. A session that has finished a block does not start the next one: end it (or `/clear`) and open the next block fresh. Rationale: context is the scarce resource — compaction silently drops spec anchors and invariants, and the previous block's assumptions bleed into the next. All durable state lives in git + `DECISIONS.md` + the PR (+ `HANDOFF.md` via `/handoff` when a session must end mid-block; a dying session leaves a mechanical `HANDOFF.autogen.md` net), so a fresh session loses nothing. **Commit workflow/config changes immediately** — uncommitted work does not survive branch switches. The **start and end are human-gated** (per the build plan); the **middle is automated**. Local hooks in `.claude/hooks/` make parts fire on their own — they stay inert until the Python project exists (M0.1), and the test gate is bypassable with `CLAUDE_SKIP_TEST_GATE=1`.

1. **`/block <id>`** — refuses a used session, sweeps stale (merged, clean) worktrees, loads only the block's sources (+ any `HANDOFF*.md`), branches off `develop`, then **grills** you before any code. *(human: you answer the grill.)*
2. **Build test-first** — red → green → refactor; the fixture is the target. Mandatory for pricing/geometry math.
3. **Diagnose, don't guess** — when something breaks, run the diagnosis loop.
4. After each edit the **PostToolUse hook** lints the changed file (ruff); fix what it reports.
5. **`/ship`** — checks CodeRabbit auth first, runs ruff + mypy + pytest + CodeRabbit + `/code-review`, opens the PR, cleans up (`HANDOFF.md`), then **ends the session**. The **Stop hook** won't let a turn end with red lint/tests when Python changed (scoped to the changed files' tests for speed; the full suite gates `/ship` + CI).
6. **Human gate:** a teammate clicks the demo and approves the PR; the Code Owner signs off money/tax/schema/auth — never self-merged, never bot-only.

Tier-1 invariants (§5) hold throughout: money = integer minor units + currency; every table org-scoped (RLS); Lens never auto-fed into Kalk; reversible migrations only. Full workflow: `build-plan/WORKFLOW-PLAYBOOK.html` + `CONTRIBUTING.md`.
