---
description: End-of-session handoff — capture state on the branch so a fresh session resumes without re-deriving
argument-hint: "[optional: why the session is ending, e.g. 'context full', 'end of day']"
allowed-tools: Bash(git *), Read, Grep, Glob, Write, Edit
---
This session is ending ($ARGUMENTS). Write a handoff so a **fresh session** (or a teammate) resumes this block with zero re-derivation. Context lives in the repo, never only in chat.

1. Write `HANDOFF.md` at the repo root (overwrite any existing one) with exactly these sections:
   - **Block & branch:** block id, branch name, linked issue/PR.
   - **State:** what is done and proven (which tests/fixtures are green), what is in progress, what is untouched.
   - **Next step:** the single next concrete action, specific enough to start cold.
   - **Sources loaded:** the spec anchors + folded sub-spec + KB slugs this block uses (so the next session loads only these).
   - **Gotchas:** anything non-obvious discovered this session (flaky test, naming trap, decision made inline).
   - **OPEN candidates:** anything ambiguous and expensive to reverse → also add it to `docs/decisions/DECISIONS.md` as `OPEN:` now.
2. Commit everything on the branch: work-in-progress code (marked WIP if red) + `HANDOFF.md`. Never leave state only in the working tree or the chat.
3. Tell me it's committed, then remind me: **start the next session fresh** — `/block <id>` will pick up `HANDOFF.md` if present.
