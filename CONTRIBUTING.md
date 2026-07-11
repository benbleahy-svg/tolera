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

Then run the loop (full detail in the playbook): **grill → TDD build → diagnose → local review → fixtures + golden thread green → PR**.

- Start every block by getting Claude to **grill you** (`/grill-with-docs`) — align before code. Highest-leverage habit on the team.
- Build test-first (`/tdd`). Mandatory for pricing/geometry math.
- Before the PR, run the **local review** (`coderabbit` in the terminal + `/code-review` in-session) and fix what they find.

## 3. Open the PR — full bot-only merge, machines carry the review

We run a **full bot-only auto-merge with no human approval gate** (decided 2026-06, recorded in `DECISIONS.md`; this overrides the old `CLAUDE.md §9` human-gate rule). The machines are the safety net and **correctness is proven by fixtures, not by an eyeball**:

| Layer | Who | Gate |
|---|---|---|
| CI | ruff · mypy · pytest · eval-suite | required — must be green |
| Greptile | whole-codebase PR review | **required check** — resolve 🔴 |
| CodeRabbit | advisory PR review + summaries (see `.coderabbit.yaml`) | feeds the fixer |
| `@claude` (Sonnet) | reads Greptile + CodeRabbit comments and pushes fixes (cheap metered API) | findings cleared |
| Money/tax/schema/auth | golden + tax/rounding + property + RLS fixtures | **required checks** — red blocks merge |
| Merge | GitHub auto-merge on green | automatic, no approval |

> The bots can't sign off the things that are *plausible but wrong* in our domain — a money rule, a tax rate, a tenancy boundary. We protect those with **required machine fixtures** (not a human tap): a wrong tax rounding fails its fixture and the PR cannot merge. Migrations are reversible and everything lands on `develop` (not production), and a **morning digest** (`.github/workflows/digest.yml`) reports overnight merges so anything off can be reverted async.

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
