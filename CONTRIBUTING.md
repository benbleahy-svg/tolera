# Contributing — how our team builds Tolera with Claude Code

The visual companion to this file is **[build-plan/WORKFLOW-PLAYBOOK.html](build-plan/WORKFLOW-PLAYBOOK.html)** — open it first. This file is the text rules for a **2–3 person team + Claude Code**. One-time repo setup lives in [build-plan/GITHUB-SETUP.md](build-plan/GITHUB-SETUP.md).

## The golden rule

**One block = one Claude Code session = one branch = one PR.** Blocks are defined in `build-plan/`. Don't widen scope mid-session; if a block won't fit one focused session, it was mis-sized — split it.

## 1. Claim a block (so two people never grab the same one)

1. Open (or pick) the block's GitHub issue — template: `.github/ISSUE_TEMPLATE/build-block.md`.
2. **Assign it to yourself.** Assignment is the lock. If it's assigned, it's taken.
3. Take the lowest-numbered block in the current milestone whose `Depends on` are all merged.

## 2. Branch and build (the per-block loop)

```bash
git switch develop && git pull
git switch -c feature/m1-quote-costing      # feature/{m}-{slug}
```

Then run the loop (full detail in the playbook): **self-grill → TDD build → diagnose → local review → fixtures + golden thread green → PR (auto-merge armed)**.

- Normally the **driver runs this for you**: `scripts/autobuild.sh` executes the queue block-by-block, one fresh session each, and only stops for `BLOCKED.md` halts and milestone checkpoints. Manual sessions still work the same way (`/block <id>`).
- Every block starts with the **self-grill** (`/grill-with-docs`): Claude asks the hard questions and answers them *from the sources with citations* (precedence ladder; uncited + irreversible = `OPEN:` + halt). The verification table lands in the PR body — audit it at checkpoints.
- Build test-first (`/tdd`). Mandatory for pricing/geometry math.
- `/ship` runs the local gate — ruff/mypy/pytest, **semgrep tier-1** (`.semgrep/tier1.yml`), a **fresh-context subagent review**, `coderabbit` — then opens the PR and arms `gh pr merge --auto --squash`.

## 3. The PR merges itself — the machines carry the review

PRs are opened by `/ship` with **auto-merge armed**; no human approval per PR. The safety net is layered, and **the human verifies behaviour at milestone checkpoints, not lines per PR**:

| Layer | Who | Gate |
|---|---|---|
| CI | ruff · mypy · pytest · **semgrep tier-1** · eval-suite | must be green (merge-blocking) |
| e2e demos | promoted Playwright demos — "a human clicks the demo," executable | must be green (merge-blocking) |
| Fresh-context review | a clean-memory subagent reviews the diff vs. `REVIEW.md` inside `/ship` | 🔴 fixed before the PR opens |
| CodeRabbit | auto-reviews every PR (assertive, see `.coderabbit.yaml`) | advisory post-merge; swept at checkpoints |
| Claude Code Review | cross-model: **Fable 5** on money/pricing/schema/auth/tax diffs, Opus 4.8 otherwise | advisory post-merge; swept at checkpoints |
| **Human** | clicks through `CHECKPOINT.md` at each **milestone boundary** (`scripts/checkpoint.sh`) | required ✋ before the next milestone |

> The *plausible but wrong* domain mistakes — a money rule, a tax rate, a tenancy boundary — are covered mechanically: semgrep tier-1 rules + golden-fixture tests gate every merge, and the frontier model reviews every tier-1 diff. Anything the ladder can't decide is an `OPEN:` halt, never a guess.

### Demo tests are how "done" is proven
The 14 acceptance demos live as Playwright tests in [`e2e/`](e2e/). Each is a `fixme` placeholder until its milestone lands; when you build that milestone you **promote** the demo (remove `.fixme`, drive the flow per the `DemoX/` screenshots, assert the fixture). A promoted demo then gates every PR — so "the demo still works" is checked by a machine, not your memory. Template: `e2e/demos/demo-e-markups.spec.ts`; full guide: `e2e/README.md`.

## 4. Handoffs (the team multiplier)

Context is our scarce resource, and so is each other's time. Hand work off cleanly:

- **Session → session (same person, or to a fresh Claude):** when context fills, run `/handoff`. Commit the handoff note to the branch (or paste into the PR/issue) so the next session resumes without re-deriving everything.
- **Person → person:** the PR description + the `/handoff` note + `CLAUDE.md` (the shared brain) are enough for a teammate to pick up. Never leave state only in your local chat.
- **Decisions:** anything ambiguous and expensive to reverse → add an `OPEN:` entry to `docs/decisions/DECISIONS.md` and keep moving on independent work. When resolved, move it to a dated entry. `DECISIONS.md` is the team's source of truth for *what we decided and why*.

## 5. Working in parallel (only on ⟂ blocks)

Two people (or two Claudes) can run at once **only when their blocks don't touch the same files** — the build plan marks these ⟂. The first real window is **M2 viewers ∥ M3 extraction** once M1 is green.

- Use a worktree per parallel track: `claude --worktree m2-viewer` (creates `.claude/worktrees/m2-viewer/` on branch `worktree-m2-viewer`). Tell terminals apart with `/rename` + `/colour`.
- **One person owns schema/migrations at a time.** Two branches both adding Alembic migrations = revision conflicts. Serialise anything under `models/`, `migrations/`, `pricing/`.
- Before opening a second track, list the files each block touches. Overlap → sequential. Disjoint → parallel.
- **Merge one branch at a time**, run the suite between merges. Conflicts → `/resolving-merge-conflicts`.

## 6. Onboarding a new teammate (15 minutes)

```bash
gh repo clone OWNER/tolera && cd tolera
cp .env.example .env            # fill from the shared vault (see M0.0)
uv sync --all-extras --dev      # backend deps
pre-commit install              # local lint/type/format gate
npx skills@latest add mattpocock/skills   # then run /setup-matt-pocock-skills
curl -fsSL https://cli.coderabbit.ai/install.sh | sh && coderabbit auth login
cd e2e && npm install && npm run install:browsers && cd ..   # Playwright demo harness
```

Then read, in order: `CLAUDE.md` → `build-plan/WORKFLOW-PLAYBOOK.html` → this file → the milestone file you'll work in. The shared `.claude/settings.json` (permissions + safe-command allowlist) is already in the repo; your personal overrides go in `.claude/settings.local.json` (gitignored).

## Conventions (quick reference)

- Branches: `feature/{m}-{slug}` off `develop`. Commits: imperative, scoped (`feat(pricing): ...`).
- Money: integer minor units + currency. Units: metric. Tenancy: org-scoped + RLS. (Full rules: `CLAUDE.md` §5.)
- Never commit secrets; `.env` is gitignored, `.env.example` is the committed contract.
- Precedence when docs disagree: `DECISIONS.md` > spec > folded sub-specs > analysis > KB; DACH delta overrides US/imperial behaviour.
