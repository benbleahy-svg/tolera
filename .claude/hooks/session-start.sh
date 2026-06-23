#!/usr/bin/env bash
# SessionStart hook — print the per-block loop so it's salient every session.
# stdout from a SessionStart hook is added to Claude's context.
cat <<'EOF'
[Tolera operating procedure — follow for every build block]
1. /block <id> — load only the block's sources, branch off develop, then GRILL me before coding.
2. Build test-first (TDD); the fixture is the target. Pricing/geometry math: tests are mandatory.
3. When something breaks, run the diagnosis loop — do not guess-patch.
4. Invariants: money = integer minor units + currency; every table org-scoped (RLS); Lens never auto-fed into Kalk; reversible migrations only.
5. /ship — ruff + mypy + pytest + coderabbit + /code-review, then open the PR. Green or it's not done.
6. A human verifies the demo and approves the PR. Never self-merge money/tax/schema/auth changes.
EOF
exit 0
