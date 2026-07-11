#!/usr/bin/env bash
# SessionStart hook — print the AUTONOMOUS per-block loop so it's salient every session.
# stdout from a SessionStart hook is added to Claude's context.
cat <<'EOF'
[Tolera operating procedure — AUTONOMOUS build loop. Follow for every build block.]
1. /block <id> — load ONLY the block's sources (spec anchors via SPEC-INDEX, its one folded sub-spec, KB links), confirm deps merged, branch off develop.
2. SELF-GRILL with doc-grounded auto-accept: interrogate yourself on scope + edge cases; answer each from the docs (DECISIONS > spec > sub-spec > analysis > KB > demo/fixture) with a confidence; AUTO-ACCEPT doc-backed or reversible answers and log the Q&A to the PR. Do NOT wait for a human.
3. WHEN UNSURE, REVERIFY before deciding (§6 rule 4): one deeper pass over the precedence ladder (a read-only fan-out sub-agent across the docs/KB). If it resolves -> auto-accept. If still unresolved: irreversible (schema/money/tax/auth/domain) -> ESCALATE (block-and-log OPEN: + notify the human, park the block, move to the next independent block); reversible -> proceed with the assumption logged. Never guess on anything expensive to reverse.
4. Build test-first (TDD); the fixture is the target. Pricing/geometry/tax math: tests are mandatory and are the real gate.
5. INDEPENDENT VERIFY: spawn a fresh-context sub-agent that sees only the docs + the diff (not your build reasoning) and confirms the implementation matches plan + KB behaviour + demo/fixture.
6. Invariants (hard): money = integer minor units + currency; every table org-scoped (RLS); Lens never auto-fed into Kalk; reversible migrations only.
7. /ship — ruff + mypy + pytest + the block's fixture + golden thread + coderabbit + /code-review + /security-review, then open the PR with `gh pr merge --auto --squash`. Greptile + CodeRabbit review on the PR; the @claude action (Sonnet) addresses findings. GitHub auto-merges on green. Green or it's not done; nothing red ever merges.
   FIX-STEP BACKUP: if the @claude action is unavailable (spend cap, rate limit, key error) or findings remain after a bounded wait, resolve them YOURSELF from this local session (gh pr view --comments + push, off-API), retry twice with backoff, else mark needs-human + notify + park the block. (A full Anthropic outage disables the local fallback too — then just wait and retry.)
8. FULL BOT-ONLY MERGE (decided 2026-06; recorded in DECISIONS.md, overrides old CLAUDE.md §9). No human approval gate. Money/tax/schema/auth are protected by REQUIRED machine fixtures (golden + tax/rounding + property + RLS), reversibility, and an after-merge digest — not by a human tap.
9. After merge, continue to the next block whose deps are merged. Escalate to the human only when the docs genuinely cannot resolve an irreversible question.
EOF
exit 0
