---
description: Resolve merge conflicts autonomously and safely — understand both sides before touching a line
argument-hint: "[branch being merged]"
allowed-tools: Bash(git *), Bash(uv *), Bash(pytest *), Read, Grep, Glob, Edit
---
We have merge conflicts ($ARGUMENTS). Resolve them deliberately and **autonomously** — do not wait for a human unless a halt condition in step 5 fires. A bad resolution is a silent regression, so the fixtures are the referee, not your judgement alone.

1. `git status` + `git diff` — list every conflicted file. For each, establish both sides' *intent* first (`git log --oneline -3 <ref> -- <file>` for ours and theirs) — never resolve a hunk you haven't understood.
2. Resolve file by file. Never mechanically take ours/theirs on: `app/models.py`, `alembic/`, anything under pricing/costing, authz, or money/tax logic. For those, derive the resolution from the sources (`DECISIONS.md` > spec > folded sub-spec) and record one line per file in the PR body: *what conflicted, which side won, why, with the citation*. That audit line replaces the old "walk the human through it".
3. **Alembic:** two branches adding migrations = revision conflict. Re-parent so history is linear (`alembic heads` must show exactly one head); never merge heads blindly.
4. After resolving: the full gate — `uv run pytest -q -x`, the block's fixture AND the golden-thread fixture — must be green before the merge commit is pushed.
5. **HALT** (write `BLOCKED.md` and end, per `/block` step 5) only if: the two sides implement genuinely contradictory *decisions* that the precedence ladder cannot rank, or the resolution would change money/tax/schema/authz behaviour that **no fixture covers**. Everything else: resolve, verify, continue — asking a human about an ordinary conflict is a stall, not a safety measure.
