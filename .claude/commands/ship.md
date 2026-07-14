---
description: Pre-PR gate — full local checks + fresh-eyes review, open the PR with auto-merge armed, then end the session
argument-hint: "[optional PR title]"
allowed-tools: Bash(uv *), Bash(ruff *), Bash(mypy *), Bash(pytest *), Bash(semgrep *), Bash(coderabbit *), Bash(git *), Bash(gh pr *), Task
---
Get this block merged without a human in the loop:

1. **Full local gate:** `uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest --cov`. Fix anything red.
2. **Fixtures:** run the block's fixture test AND the golden-thread fixture. Both green or we are not done.
3. **Tier-1 mechanical rules:** `semgrep --config .semgrep/tier1.yml --error .` — money-as-float, non-determinism in pricing, missing org scoping, raw DDL. Fix every finding; these are never nits.
4. **Fresh-eyes review:** spawn a subagent (Task tool) with **clean context** and this prompt: "Review `git diff develop...HEAD` strictly against REVIEW.md and CLAUDE.md §5. You did not write this code. Hunt for tier-1 violations and plausible-but-wrong domain logic (tax rates, rounding, tenancy, Lens→Kalk boundary). Cite file:line for every finding." Address every 🔴 it returns. Then run `coderabbit review` locally and address those findings too.
5. **PR body:** what/why, milestone, **how to test it by clicking** (for the checkpoint reviewer), the self-grill **verification table** from `/grill-with-docs`, any `ASSUMED:` items, and the tier-1 self-check filled honestly.
6. **Open + arm auto-merge:** `git push -u origin HEAD`, `gh pr create` into `develop` with our template, then `gh pr merge --auto --squash`. The PR merges itself when CI (backend · frontend · semgrep · e2e demos) is green. Do **not** sit waiting for CI — CI failures come back to the driver, not this session.
7. **Clean up:** delete `HANDOFF.md` if present (its content lives in the PR body now). If this block ran in a worktree, note it for removal after merge.
8. **End of session.** One block = one session. The driver starts the next block in a fresh session.

**Never arm auto-merge if any local check is red, any fixture fails, or an `OPEN:`/`BLOCKED.md` exists for this block.** Red local state → fix it or write `BLOCKED.md` and halt.
