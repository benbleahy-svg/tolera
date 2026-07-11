# Review instructions — Tolera / Bid Factory

These rules are injected at highest priority into every AI reviewer (**Greptile + CodeRabbit**). **We run a full bot-only merge with no human approval gate, so be thorough on correctness and on the tier-1 rules below — do not soften or skip findings.** Behaviour is verified by machine fixtures (golden + tax/rounding + property + RLS), not a human eyeball; you are the line-by-line safety net and the `@claude` action (Sonnet) fixes what you flag.

## What 🔴 Important (must-fix-before-merge) means here

Reserve 🔴 for anything that breaks behaviour, corrupts/leaks data, or violates a tier-1 rule from `CLAUDE.md` §5:

- **Money mistyped.** Any monetary value as a float, or missing an explicit `currency` (EUR/CHF). Money is **integer minor units + currency**, always.
- **Tenancy leak.** A query, route, or table not scoped to the caller's `org_id` / missing RLS. No cross-org reads. Every new domain table must be org-scoped.
- **AI boundary crossed.** Lens/AI output auto-fed into Kalk costing, persisted as a *calculated* value, or a value invented that wasn't on the source document (hallucination). Lens output is **suggestion-only, explicit-accept**.
- **Irreversible schema.** A schema change without a **reversible Alembic migration**, or manual DDL.
- **Secret / PII exposure.** Secrets, customer PII, or CAD/print contents in logs, errors, or anything sent to an external LLM. **Export-control / dual-use-flagged files must never reach any external LLM.**
- **Tax wrong.** MwSt/USt rate or rounding incorrect (DE 19 % / 7 %, AT 20 %, CH 8.1 %).
- **Determinism break in Kalk.** Any non-deterministic op (time, randomness, network, unordered iteration) in the pricing sandbox — the golden figures depend on bit-for-bit determinism.

Style, naming, and refactor suggestions are 🟡 Nit at most.

## Always check

- A new API route is org-scoped **and** has an integration test.
- A new table/column has a migration and appears in the domain model.
- A new money field stores integer minor units + currency.
- Units are metric only (mm / kg / deg); no imperial defaults (the DACH delta wins).

## Cap the noise

- At most **5** 🟡 Nits per review; summarise the rest as a count.
- Do **not** report: generated files, `*.lock`, `docs/reference/**`, `archive/**`, migration version files (review the model + the up/down only), and anything CI already enforces (ruff/mypy/formatting).

## Verification bar

- Behaviour claims need a `file:line` citation in the source, not an inference from naming.
- After the first review of a PR, post only 🔴 Important findings unless asked for more (don't re-litigate nits on every push).
