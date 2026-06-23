---
description: Start a build-plan block — load only its sources, branch, then grill before coding
argument-hint: "[block id, e.g. M1.7]"
allowed-tools: Bash(git switch *), Bash(git pull *), Read, Grep, Glob
---
We are starting build block **$1**.

1. Open its GitHub issue and the `build-plan/` entry for $1. Load ONLY: its `Implements (spec)` anchors (navigate via `docs/spec/SPEC-INDEX.md`), its one folded sub-spec under `docs/spec/folded-subspecs/`, and skim its `KB:` links. Do **not** load the whole spec — context is the scarce resource.
2. Confirm its `Depends on` blocks are merged. If any aren't, stop and tell me.
3. Branch: `git switch develop && git pull && git switch -c feature/<m>-<slug>`.
4. Then **grill me** on scope and edge cases before writing any code. Surface anything ambiguous and expensive-to-reverse (schema, money, tax, security) as a candidate `OPEN:` for `docs/decisions/DECISIONS.md` — never guess.

Stop after grilling and wait for my go-ahead to build test-first.
