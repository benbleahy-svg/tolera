---
description: Start a build-plan block — load its sources, branch, self-grill (auto-accept), then build autonomously
argument-hint: "[block id, e.g. M1.7]"
allowed-tools: Bash(git switch *), Bash(git pull *), Bash(git branch *), Read, Grep, Glob, Task
---
We are starting build block **$1** in AUTONOMOUS mode (no human in the loop unless escalated).

1. Open its GitHub issue and the `build-plan/` entry for $1. Load ONLY: its `Implements (spec)` anchors (navigate via `docs/spec/SPEC-INDEX.md`), its one folded sub-spec under `docs/spec/folded-subspecs/`, and skim its `KB:` links. Do **not** load the whole spec — context is the scarce resource.
2. Confirm its `Depends on` blocks are merged. If any aren't, skip to the next independent block.
3. Branch: `git switch develop && git pull && git switch -c feature/<m>-<slug>`.
4. **Self-grill (auto-accept):** interrogate yourself on scope and edge cases. For each question, propose a recommended answer grounded in the docs (precedence: DECISIONS > spec > folded sub-spec > analysis > KB > demo/fixture) with a confidence. **Auto-accept** doc-backed or reversible answers and write the Q&A into the PR body. Do not wait for a human.
5. **When unsure, reverify** (one deeper pass, ideally a read-only fan-out sub-agent across the docs/KB) before deciding. If still unresolved: irreversible (schema/money/tax/auth/domain model) → log an `OPEN:` in `docs/decisions/DECISIONS.md`, **notify the human, park this block, and move to the next independent block**; reversible/low-stakes → proceed with the assumption logged. **Never guess on anything expensive to reverse.**
6. Then build test-first, run the independent verifier sub-agent, and `/ship`. Proceed without stopping unless you hit an escalation in step 5.
