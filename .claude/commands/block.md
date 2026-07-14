---
description: Start a build-plan block AUTONOMOUSLY — fresh session only; load sources, branch, self-grill against the docs, then build without waiting
argument-hint: "[block id, e.g. M2.10]"
allowed-tools: Bash(git switch *), Bash(git pull *), Read, Grep, Glob
---
We are starting build block **$1** in **autonomous mode**: after the self-grill you proceed straight to test-first building. Do **not** stop to ask for a go-ahead. The only reasons to halt are the ones in step 5.

0. **Fresh-session check.** One block = one session. If this session has already executed another block (or its context is substantially used), STOP — the driver must relaunch `/block $1` in a fresh session. If `HANDOFF.md` (or `HANDOFF.autogen.md`) exists at the repo root, read it first: it is the previous session's state for this block. For the autogen variant, trust the tests over the note — run the suite to establish ground truth. Delete the file(s) once absorbed.

1. **Load only this block's sources.** Its GitHub issue, its `build-plan/` entry, its `Implements (spec)` anchors (navigate via `docs/spec/SPEC-INDEX.md`), its one folded sub-spec under `docs/spec/folded-subspecs/`, and skim its `KB:` links. If the block names a demo, open its row in `build-plan/DEMOS-TRACEABILITY.md` and the `DemoX/` screenshots — they are the UI ground truth. Do **not** load the whole spec; context is the scarce resource.

2. **Dependency check.** Confirm every `Depends on` block is merged (`gh pr list --state merged`). If one isn't → HALT (step 5), do not build around it.

3. **Branch.** `git switch develop && git pull && git switch -c feature/<m>-<slug>` (or resume the existing branch per `HANDOFF.md`).

4. **Self-grill** (`/grill-with-docs`). Generate the hard questions, then answer them **yourself from the sources** — the human is not in this loop. Produce the verification table; it goes in the PR body later.

5. **Halt conditions — the ONLY reasons to stop and wait for a human:**
   - An `OPEN:` item: a question that is *expensive to reverse* (schema, money/tax math, tenancy/authz, API contracts, security, customer data) and that the precedence ladder does not answer. Log it in `docs/decisions/DECISIONS.md` as `OPEN:` with options + a recommended default, write `BLOCKED.md` at the repo root stating exactly what decision is needed, and end the session.
   - A **missing credential** — API key, login, secret, DNS, or third-party account the block needs. Write `BLOCKED.md` naming exactly what is missing and where it goes (`.env` key name), and end the session.
   - An **unmerged dependency** (step 2). Write `BLOCKED.md` and end the session.

   Everything else — including cheap-to-reverse choices (naming, layout, copy) — you decide yourself, note the assumption inline, and keep building.

6. **Build test-first** — red → green → refactor; the fixture is the target. Mandatory for pricing/geometry math. When the block's acceptance criteria and the golden thread are green, run `/ship` without being asked.

Tier-1 invariants hold throughout (CLAUDE.md §5): money = integer minor units + currency; every table org-scoped (RLS); Lens output suggestion-only, never auto-fed into Kalk; reversible migrations only; metric-native; German-first UI.
