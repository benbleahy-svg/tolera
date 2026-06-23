---
description: Pre-PR gate — run the full local check + review, then open the PR
argument-hint: "[optional PR title]"
allowed-tools: Bash(uv *), Bash(ruff *), Bash(mypy *), Bash(pytest *), Bash(coderabbit *), Bash(git *), Bash(gh pr *)
---
Get this block ready to merge:

1. Run `uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest --cov`. Fix anything red.
2. Run the block's fixture test AND the golden-thread fixture. Both must be green or we are not done.
3. Run `coderabbit review` locally and `/code-review` on the diff; address the findings.
4. Write a short summary of what changed and **how to test it by clicking** (for the PR body and the reviewer) — not a description of the code.
5. Open the PR into `develop` with `gh pr create` using our template; fill the tier-1 self-check honestly.

Never mark anything done if a check is red or a fixture fails.
