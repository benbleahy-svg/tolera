---
description: Pre-PR gate — run the full local check + review, open the PR, then end the session
argument-hint: "[optional PR title]"
allowed-tools: Bash(uv *), Bash(ruff *), Bash(mypy *), Bash(pytest *), Bash(coderabbit *), Bash(git *), Bash(gh pr *)
---
Get this block ready to merge:

1. Run `uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest --cov`. Fix anything red.
2. Run the block's fixture test AND the golden-thread fixture. Both must be green or we are not done.
3. Run `coderabbit review` locally and `/code-review` on the diff; address the findings.
4. Write a short summary of what changed and **how to test it by clicking** (for the PR body and the reviewer) — not a description of the code.
5. Open the PR into `develop` with `gh pr create` using our template; fill the tier-1 self-check honestly.
6. **Clean up:** delete `HANDOFF.md` if present (its content belongs in the PR body now). If this block ran in a worktree, remind me to `git worktree remove` it after the merge — stale worktree copies pollute searches.
7. **End of session.** This session is done — one block = one session. Tell me to start the next block with `/block <id>` in a **fresh session** (or after `/clear`). Do not start new work here.

Never mark anything done if a check is red or a fixture fails.
