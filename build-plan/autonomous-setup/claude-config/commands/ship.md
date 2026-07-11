---
description: Pre-merge gate — run the full local check + review, then open the PR with auto-merge on
argument-hint: "[optional PR title]"
allowed-tools: Bash(uv *), Bash(ruff *), Bash(mypy *), Bash(pytest *), Bash(coderabbit *), Bash(git *), Bash(gh pr *), Bash(gh run view *)
---
Get this block ready to auto-merge (FULL BOT-ONLY — no human approval gate):

1. Run `uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest --cov`. Fix anything red.
2. Run the block's fixture test AND the golden-thread fixture. For money/tax/schema/auth changes, the **golden + tax/rounding + property + RLS fixtures are the gate** and must be green — these are required status checks, so a red fixture blocks the merge automatically. Both green or we are not done.
3. Run `coderabbit review` locally and `/code-review` + `/security-review` on the diff; address the findings.
4. Write a short PR body: what changed, the **self-grill Q&A + any auto-accepted assumptions**, and how to verify by clicking. Not a description of the code.
5. Open the PR into `develop` and enable auto-merge:
   `gh pr create --base develop --fill` then `gh pr merge --auto --squash`.
   Greptile + CodeRabbit review on the PR; the `@claude` action (Sonnet) addresses findings and pushes fixes. When CI + Greptile go green, GitHub auto-merges. Nothing red ever merges.
6. **Fix-step resilience (if the `@claude` action is unavailable).** If the action errors, or findings remain unresolved after a bounded wait (e.g. ~10 min / 2 checks), do NOT stall: **resolve the review findings yourself** — read them with `gh pr view <n> --comments`, push the fixes from this local session (off-API, subscription-billed), and re-run checks. Retry at most twice with backoff. If still red, mark the PR `needs-human`, fire a notification, **park this block and move to the next independent one** — never merge red. (Note: a full Anthropic outage disables this local fallback too, since it shares the backend; in that case just wait and retry, and let the notify hook alert me.)
7. After merge, continue to the next block whose deps are merged.

Never mark anything done if a check is red or a fixture fails. Escalate to the human only for an unresolved irreversible question (see /block step 5).
