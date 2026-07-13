---
description: Start a build-plan block — fresh session only; sweep stale worktrees, load its sources, branch, then grill before coding
argument-hint: "[block id, e.g. M1.7]"
allowed-tools: Bash(git switch *), Bash(git pull *), Bash(git worktree *), Bash(git branch *), Bash(git merge-base *), Bash(git status *), Read, Grep, Glob
---
We are starting build block **$1**.

0. **Fresh-session check + housekeeping.** One block = one session. If this session has already executed another block (or its context is substantially used), STOP and tell me to run `/block $1` in a fresh session instead — a degraded context is how blocks fail. If `HANDOFF.md` (or `HANDOFF.autogen.md` — the mechanical net a dying session leaves behind) exists at the repo root, read it first: it is the previous session's state for this block. For the autogen variant, trust the tests over the note — run the suite to establish ground truth. Delete the file(s) once absorbed. Then **sweep stale worktrees:** for each entry in `git worktree list` (skip the main checkout), if its branch is merged into `develop` (`git merge-base --is-ancestor <branch> develop`, or its squash-merge PR is closed) AND its tree is clean (`git -C <path> status --porcelain` empty), run `git worktree remove <path>` and delete the merged branch. If a worktree is dirty or its branch unmerged, leave it and tell me — never force-remove.
1. Open its GitHub issue and the `build-plan/` entry for $1. Load ONLY: its `Implements (spec)` anchors (navigate via `docs/spec/SPEC-INDEX.md`), its one folded sub-spec under `docs/spec/folded-subspecs/`, and skim its `KB:` links. Do **not** load the whole spec — context is the scarce resource.
2. Confirm its `Depends on` blocks are merged. If any aren't, stop and tell me.
3. Branch: `git switch develop && git pull && git switch -c feature/<m>-<slug>` (or resume the existing branch per `HANDOFF.md`).
4. Then **grill me** on scope and edge cases before writing any code (`/grill-with-docs`). Surface anything ambiguous and expensive-to-reverse (schema, money, tax, security) as a candidate `OPEN:` for `docs/decisions/DECISIONS.md` — never guess.

Stop after grilling and wait for my go-ahead to build test-first.
