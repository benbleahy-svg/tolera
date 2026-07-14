---
description: Self-grill — interrogate the block's scope and edge cases, then answer every question from the sources with citations; no human in the loop
argument-hint: "[optional focus, e.g. 'tax rounding', 'schema']"
allowed-tools: Read, Grep, Glob
---
With the current block's sources loaded (its spec anchors, folded sub-spec, demo screenshots, KB links — load them first if not already), run the grill **against the documents, not the human**. $ARGUMENTS

**Phase 1 — ask the hard questions** (write them all down before answering any):
- Prioritise what is **expensive to reverse**: schema, money/tax math, tenancy/authz, API contracts, state machines.
- Probe edge cases the block text is silent on: empty/zero/negative quantities, currency + rounding (Rappen vs Cent), cross-org access, concurrent edits, retries/idempotency, German vs English strings, unit boundaries (mm/kg/deg).
- Challenge scope: what is explicitly OUT of this block? Where exactly is the line to the next block?

**Phase 2 — answer each question yourself**, strictly up the precedence ladder:
`DECISIONS.md` > spec anchors (`Bid-Factory-Build-Spec.html` via `SPEC-INDEX.md`) > the folded sub-spec > demo narrative + `DemoX/` screenshots (UI ground truth) > KB articles. The DACH delta overrides any US/imperial/ITAR/QuickBooks behaviour a lower source shows.

Rules of evidence:
- **Every answer cites its source** — file + anchor/section (e.g. `spec#kalk-golden`, `DECISIONS.md 2026-06-30`, `Demo3/frame-04.png`). An answer you cannot cite is a **guess**.
- Where the block has a demo, **verify the answer against the screenshots** — layout, controls, copy. A pixel never outranks the spec, but a spec-silent UI question is answered by the demo.
- A guess that is *cheap to reverse* (internal naming, layout, comments): pick a sensible default, mark it `ASSUMED:` in the table, note it inline in code.
- A guess that is *expensive to reverse*: → `OPEN:` in `docs/decisions/DECISIONS.md` + halt per `/block` step 5. **Never build on an uncited answer to a schema/money/tax/security question.**

**Phase 3 — output the verification table** (this is the audit trail; it goes verbatim into the PR body):

| # | Question | Answer | Source | Status |
|---|----------|--------|--------|--------|
| 1 | … | … | spec#… / DECISIONS.md / DemoX | CITED / ASSUMED / OPEN |

Finish with: (1) the agreed scope in ≤5 bullets, (2) the acceptance check restated, (3) any `OPEN:`/`ASSUMED:` items. If there are no `OPEN:` items, **continue directly to test-first build — do not stop and wait.**
