# Build Plan — Tolera (Bid Factory)

**What this is.** The execution map that turns `docs/spec/Bid-Factory-Build-Spec.html` into code. The spec says *what* to build; this plan says *in what order, in what size, and how each piece is proven done*. It is decomposed into **build blocks** — vertical slices each sized to one focused Claude Code session and one pull request.

**What this is not.** It is not a restatement of the spec. Every block is a **thin pointer** into the invested work — the spec section, the folded sub-spec that carries the internals, and the Paperless Parts KB article behind the behaviour — plus the one thing that proves the block done. Read the block to know *what to load and what "done" means*; read the linked sources for the genuine logic and UI. Nothing in the spec is summarised away here; it is referenced so it is never lost.

> Precedence (from `CLAUDE.md` §2, unchanged): `DECISIONS.md` **>** the spec **>** folded sub-specs **>** analysis **>** PP KB. `DACH-DELTA-LAYER` overrides any US/imperial/ITAR/QuickBooks behaviour. When in doubt, resolve *up* the ladder — never silently pick the lower source.

---

## 1. How to run one session (the per-block protocol)

A Claude Code session executes **exactly one block**. The protocol:

1. **Pick the block.** Take the lowest-numbered block in the current milestone whose `Depends on` are all merged. Orthogonal blocks (marked ⟂) may be taken in parallel branches.
2. **Load only its sources.** Open the block's `Implements (spec)` anchors, its one `Internals (provenance)` sub-spec, and skim the linked `KB:` articles. Do **not** load the whole 640 KB spec — that is what `docs/spec/SPEC-INDEX.md` and these anchors are for. Conserving context *is* the sizing constraint (see §3). If the block names a demo, open its row in [DEMOS-TRACEABILITY.md](DEMOS-TRACEABILITY.md) → the demo narrative + the `DemoX/` screenshots (the UI ground truth).
3. **Branch.** `feature/{m}-{slug}` off `develop` (per the spec's Development Workflow, `#devworkflow`).
4. **Build to the acceptance criteria**, test-first where it pays (the `tdd` skill; mandatory for pricing/geometry math).
5. **Prove it against the fixtures.** Every block names a test bound to `/fixtures` (`docs/fixtures/SEED-AND-FIXTURES.md`). Green or it is not done.
6. **Keep the golden thread green** (see §4). If your block touches the thread, the end-to-end fixture test must still pass.
7. **PR** with the spec's template (what/why, milestone, how-to-test, follow-ups). CI (pytest + mypy + eval suite) gates the merge.
8. **Block, don't guess.** Hit an ambiguity the precedence ladder doesn't resolve? Add an `OPEN:` to `DECISIONS.md` and proceed on work that doesn't depend on it (`CLAUDE.md` §6). Never invent schema, money/tax math, an API contract, or a security rule.

If a block won't fit one session, it was mis-sized — **split it, don't push through a degraded context.**

---

## 2. First principles — why the plan has this shape

The plan is derived from four hard constraints, not from habit:

- **The builder is one person + Claude Code.** So blocks are *independently grabbable* and *self-describing*: each carries its own scope, sources, and definition of done. No block assumes another's author is in the room.
- **Context is the scarce resource, not time.** A session fails by *context exhaustion* — too many files held at once, too much spec loaded, or a long failing-test loop that re-reads everything. So we size by context surface (§3) and front-load the *risky* loops as spikes so they don't blow a feature session.
- **The spec is exhaustively designed and must not be lost.** Schemas, formulas, contracts, and golden figures are pinned to an unusual degree. So the plan *references* rather than *reproduces*, and detail tapers by **uncertainty, not recency**: fully detail what's knowable now, gate what's only knowable after code runs.
- **Irreversible mistakes are the expensive ones.** Tenancy, money, tax, schema, API contracts, security. So those are proven *first and explicitly* (the M0 tracer bullet) and held human-gated (block-and-log).

Everything below — the tracer bullet, the golden thread, the spike register — falls out of these four.

---

## 3. The block, and how it's sized

A **block** is one vertical slice that satisfies **all** of:

- **One PR / one branch.** Never "per file"; never a multi-PR epic.
- **One acceptance check.** A single fixture-bound assertion (or a tight cluster) proves it done. Two unrelated assertions → two blocks.
- **Bounded surface.** Rule of thumb ≤ ~8–10 files touched, ≤ ~600 net new lines incl. tests.
- **Loadable context.** ≤ 2 spec anchors + 1 folded sub-spec needed in head at once.
- **Bounded uncertainty.** If the *approach* is unknown (sandbox security, OCCT capability), a throwaway **spike** comes first; the real block builds on its findings.

Each block carries a **T-shirt size** — the currency is context, not hours:

| Size | Meaning |
|---|---|
| **S** | One concern, one file-area, trivial test. A warm-up. |
| **M** | The default. A few files, one clear slice, one fixture check. |
| **L** | The ceiling. Approaching the limits above. **Anything bigger must be split.** |
| **SPIKE** | Throwaway proof of an unknown approach. Output is *knowledge* (and maybe a thin scaffold), not production code. De-risks the block(s) that follow. |

### Block template (every block uses these fields)

```
### M{n}.{k} — {Title}   `[S|M|L]`  {· SPIKE-FIRST}
- **Vertical slice:** the one thread this proves, in a sentence.
- **Scope (in):** what ships.
- **Scope (out):** what is explicitly deferred (and to which block/milestone).
- **Depends on:** {block ids}   ·   ⟂ if orthogonal/parallelizable
- **Implements (spec):** [#anchor](../docs/spec/Bid-Factory-Build-Spec.html#anchor), …
- **Internals (provenance):** ../docs/spec/folded-subspecs/{FILE}
- **KB:** [KB: {slug}](https://help.paperlessparts.com/s/article/{slug}), …
- **Decisions:** ../docs/decisions/DECISIONS.md → {entry}   (only if one applies)
- **Acceptance criteria:** the checks that define done.
- **Test plan (fixtures):** the golden fixture/test that proves it, bound to /fixtures.
- **Golden-thread role:** how it advances or must preserve the end-to-end thread (if at all).
```

---

### Testing the two kinds of block

Most blocks are **deterministic** — schema, pricing math, rules evaluation, state machines, parsing. They get **exact fixture-bound assertions that gate every PR** (a wrong number fails the build — that's the point, e.g. M1.13's $2,160.84).

The **Lens / AI blocks (M3) are probabilistic** — an LLM/vision model produces them, so exact-match tests would be flaky and a benign phrasing difference would fail CI for nothing. They are tested on a **second track**:

- **Split the work.** The **deterministic core** around the model — the `ExtractionFinding` schema, the never-hallucinate *guard logic*, the rules AST, review-item lifecycle, email parsing — gets exact unit tests and **mocks the model**. Only the **extraction quality itself** is probabilistic.
- **Score, don't match.** That quality is measured by the **extraction eval suite (M3.11)**: a labelled fixture set scored on **precision / recall / F1 per field category** against the spec targets (classification ≈95%, recall ≈65%, precision ≈85%), run at **temperature 0 + pinned model + versioned prompts**.
- **Gate on thresholds, not output.** CI gates the eval suite on **thresholds + regression-vs-baseline** — benign variance passes, a real quality drop or a bad prompt change fails. Prompt/model changes are validated by re-running the suite and diffing the metrics.

So: deterministic blocks → exact, PR-gating; probabilistic blocks → eval-suite, threshold-gating. **Never write an exact-match test against raw model output.**

---

## 4. The golden thread (end-to-end discipline)

Beyond the M0 architectural tracer bullet, one **golden-thread fixture** stays runnable and green from the end of **M1** onward — the spine a real RFQ travels: *intake → quote → line item → part → costing/pricing → send*. Each later milestone **replaces a mock segment with the real subsystem**; the thread's integration test runs in CI every milestone and can only get *more real*, never break.

| Milestone | Thread state | Mock replaced this milestone |
|---|---|---|
| **M1** | quote → line → **manual** material/op → costing → pricing → reproduces golden € | — (thread first closed, thin) |
| **M3** | …intake becomes a real ingested RFQ email + Lens prefill | direct-create intake → **email ingest** |
| **M4** | …part dims come from real interrogation | manual dims → **GeometryService** |
| **M5** | …"sent" becomes a real PDF + email + buyer portal | sent-flag → **PDF/email/portal** |

The mocks are deliberately tiny (a create shortcut, manual dims, a status flag), so throwaway cost is near zero and each milestone inherits a crisp definition of done: *"make segment X real, thread still green."*

---

## 5. Milestone map & dependency graph

Seven milestones (`#milestones` is authoritative for contents + exit criteria). Detail **tapers by uncertainty**: M0/M1 are execution-ready; M2/M3/M5/M6 are fully blocked out; **M4 is scoped and sequenced but its high-uncertainty internals stay thin behind an OCCT spike**.

```
M0 Foundations ──┬─> M1 Quote core + Pricing ──┬─> M2 Files & Viewers ──┐
 (tenancy spine) │   (golden thread closes)     │                        ├─> M3 Intelligence ─┐
                 │                               └─> ─────────────────────┘  (thread: real      │
                 │                                                            intake)            │
                 └──────────────────────────────────────────> M4 Geometry & Mfg <───────────────┘
                                                               (spike-gated; thread: real dims)
                                                                      │
                                                                      v
                                                          M5 Outputs & Orders
                                                          (thread: real send/PDF)
                                                                      │
                                                                      v
                                                  M6 Differentiators + Pilot hardening
```

- **Hard gates:** don't start a milestone until the prior one's fixture exit-criteria pass (`#milestones`). M2 and the start of M3 can overlap once M1 is green (viewers vs. extraction are orthogonal).
- **M4 sits off the critical UI path** but **feeds M3 rules** (interrogation signals) and **M2 viewers** (feature highlight). Its spike (M4.0) may be pulled forward opportunistically once fixtures land, but per decision it heads M4.
- **Orthogonal (⟂) blocks** — file storage, saved views, settings sub-trees — can be built in parallel branches whenever their data deps exist.

| File | Milestone | Blocks | Detail | Drift |
|---|---|---|---|---|
| [M0.0-prerequisites.md](M0.0-prerequisites.md) | **Provisioning gate** — accounts · secrets · DNS (human-gated; do before coding) | — | Runbook | — |
| [M0-foundations.md](M0-foundations.md) | Scaffold + tenancy + auth + seed | 5 | Full | Low |
| [M1-quote-core-pricing.md](M1-quote-core-pricing.md) | Quote core + full pricing engine | 14 | Full | Low–Med |
| [M2-files-viewers.md](M2-files-viewers.md) | PDF/3D viewers, Part Library | 12 | Full | Med |
| [M3-intelligence.md](M3-intelligence.md) | Lens, Rules, email ingest/threading | 11 | Full | Med |
| [M4-geometry-manufacturing.md](M4-geometry-manufacturing.md) | GeometryService, sheet metal, nesting, BOM | 14 | Spike-gated | **High** |
| [M5-outputs-orders.md](M5-outputs-orders.md) | Digital quote, checkout, PDF, orders | 12 | Full | Med |
| [M6-differentiators-hardening.md](M6-differentiators-hardening.md) | Dashboard, Vendor RFQ, adapters, pilot | 10 | Full | Med |
| ↳ M7 (appendix in M6 file) | **Analytics query-builder** — deferred, post-pilot | ~6 | Outline | — |

≈ **78 blocks** (+ deferred post-pilot work: a self-serve onboarding wizard and the M7 analytics milestone). At one block per focused session, that is the order of the pilot effort the spec scopes at 3–6 months solo + Claude Code. **M7 (Analytics)** is a resolved-scope but sizeable build (`DECISIONS.md` E4-k) that the spec's M0–M6 table doesn't slot; it is **not on the pilot critical path** and shares no golden-thread segment — sequence it during or after the pilot at your discretion.

The 14 demos that define *done* are mapped to their implementing blocks, screenshots, and replay fixtures in **[DEMOS-TRACEABILITY.md](DEMOS-TRACEABILITY.md)** — the acceptance oracle.

---

## 6. Spike register (the explicit unknowns)

Two places where the design is only knowable once code runs. Both are isolated so they never blow a feature session:

- **M1.8 — Kalk sandbox core.** A Python-AST sandbox that must be both *secure* (no imports, no escapes) and *bit-for-bit deterministic* — the golden pricing figures depend on it. Spike proves security + determinism on a toy formula before the variable system/contexts/editor build on top.
- **M4.0 — OCCT capability probe.** Per-family, *what does OCCT/pythonocc actually return vs. what the spec promises* (milling setup detection, sheet-metal unfold, tube cross-section classification, geometry signature)? The probe greenlights M4 as written **or** triggers the Spatial-license conversation (which has procurement lead time). Until it resolves, M4's downstream block internals stay thin.

---

## 7. Citation conventions

- **Spec anchors** → `[#anchor](../docs/spec/Bid-Factory-Build-Spec.html#anchor)`; jump via `docs/spec/SPEC-INDEX.md`.
- **Internals (provenance)** → the one folded sub-spec under `../docs/spec/folded-subspecs/` whose schema/math/contract the block implements. *Edit the spec, never the folded provenance* — it is frozen.
- **KB** → `[KB: {slug}](https://help.paperlessparts.com/s/article/{slug})`. The KB is the upstream Paperless Parts behaviour the spec was distilled from (tier-5, descriptive); link it so the genuine logic/UI behind a feature is one click away. Superseded by the spec and always by the DACH delta where they speak.
- **Demos & screenshots** → via [DEMOS-TRACEABILITY.md](DEMOS-TRACEABILITY.md): the demo is the **acceptance oracle** — its narrative ([#demos](../docs/spec/Bid-Factory-Build-Spec.html#demos) / [#acceptance](../docs/spec/Bid-Factory-Build-Spec.html#acceptance)) plus the `../docs/reference/screenshots/DemoX/` frames are the **UI ground truth** (build to them), and the fixture is the machine-checkable form (verify against it). Never inline demo text (DRY); the **DACH delta overrides** any US/imperial behaviour a screenshot shows.
- **Decisions** → `../docs/decisions/DECISIONS.md` (tier-1). Cited per block where a resolved decision constrains it; the next session reads this file first.

---

## 8. Decisions locked while planning (2026-06-22)

Resolved this session; recorded here so the slicing rationale isn't lost (substantive product decisions live in `DECISIONS.md`):

- **Sizing rubric** = §3 (multi-dimensional; S/M/L; L is the ceiling; spike the unknowns).
- **Coverage** = everything fully detailed, **taper by uncertainty not recency**; M4 internals spike-gated.
- **M0 tracer bullet** = the **tenancy + auth spine**, proven by a cross-org denial test (the riskiest, least-reversible property first).
- **Golden-thread discipline** adopted (§4).
- **M0 cut** = 5 blocks (skeleton / tenancy spine / **authz policy** / shell+i18n+BRAND / seed framework); skeleton split from tenancy; the authz policy module + a User Management screen (M5) added in the 2026-06-22 grill.
- **M1 Kalk** = a spike + two blocks (sandbox core; then variable system + contexts + editor).
- **OCCT spike** heads **M4** (not pulled early).
- Three spec-implied decisions **folded into their owning blocks** rather than reopened: PDF rendering = PDF.js (M2 owns annotate/redact on top); LLM provider = Anthropic/Claude, configurable (M3); Lens correction-storage = per-tenant default, global on opt-in (M3).

`DECISIONS.md` itself has **zero open items** as of commit `23d7ebe` (SOLIDWORKS → post-pilot desktop add-in; Belgium → dropped, DACH-only; quote-PDF design → folded into the M5 block).
