---
description: Resolve merge conflicts safely — understand both sides before touching a line
argument-hint: "[branch being merged]"
allowed-tools: Bash(git *), Bash(uv *), Bash(pytest *), Read, Grep, Glob, Edit
---
We have merge conflicts ($ARGUMENTS). Resolve them deliberately — a bad resolution is a silent regression.

1. `git status` + `git diff` — list every conflicted file. For each, show me both sides' *intent* (`git log --oneline -3 <ours>` / `<theirs>` on the file) before proposing a resolution.
2. Resolve file by file. Never mechanically take ours/theirs on: `app/models.py`, `alembic/`, anything under pricing/costing, authz, or money/tax logic — walk me through those explicitly.
3. **Alembic:** two branches adding migrations = revision conflict. Re-parent so history is linear (`alembic heads` must show exactly one head); never merge heads blindly.
4. After resolving: `uv run pytest -q -x` + the golden-thread fixture must be green before the merge commit is made.
5. If a conflict reveals a genuine design disagreement between branches, stop — that's a human call, not a merge call.
