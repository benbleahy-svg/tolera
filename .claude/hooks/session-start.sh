#!/usr/bin/env bash
# SessionStart hook — print the per-block loop so it's salient every session.
# stdout from a SessionStart hook is added to Claude's context.
cat <<'INNER'
[Tolera operating procedure — follow for every build block]
0. ONE BLOCK = ONE SESSION. Start each block in a fresh session via /block <id>; after /ship, the session ends. Never run a second block in a used context. If HANDOFF.md exists at the repo root, read it first. Ending mid-block? Run /handoff.
1. /block <id> — load only the block's sources, branch off develop, then GRILL me before coding.
2. Build test-first (/tdd); the fixture is the target. Pricing/geometry math: tests are mandatory.
3. When something breaks, run the diagnosis loop — do not guess-patch.
4. Invariants: money = integer minor units + currency; every table org-scoped (RLS); Lens never auto-fed into Kalk; reversible migrations only.
5. /ship — ruff + mypy + pytest + coderabbit + /code-review, then open the PR. Green or it's not done.
6. A human verifies the demo and approves the PR. Never self-merge money/tax/schema/auth changes.
INNER
exit 0
