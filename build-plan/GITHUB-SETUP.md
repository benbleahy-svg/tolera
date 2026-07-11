# GitHub one-time setup (admin runbook)

Run this **once**, by one person, after the [M0.0 accounts gate](M0.0-prerequisites.md) §2. It turns the local repo into a protected, team-ready GitHub repo. Prereq: install the GitHub CLI (`brew install gh`) and `gh auth login`.

> All commands assume you're in the repo root. Replace `OWNER` with your GitHub user/org. The repo is private.

## 1. Create the private repo and push `main`

```bash
# from the repo root (already a git repo on branch main)
gh repo create tolera --private --source=. --remote=origin --push
```

## 2. Create and push `develop` (the integration branch)

```bash
git switch -c develop
git push -u origin develop
gh repo edit --default-branch develop   # PRs target develop by default
```

## 3. Protect both branches

Branch protection is what enforces *one-PR-per-block* and gates the **full bot-only auto-merge** (decided 2026-06; recorded in `DECISIONS.md`). We require **0 human approvals** permanently and lean on the **required status checks** as the gate — CI + Greptile, plus the money/tax/schema/auth fixtures — while still forcing every change through a PR. No human approval is needed or used.

> Note: status checks (`backend` from `.github/workflows/ci.yml`, `greptile`, and the fixture jobs) must be added to protection **after** each has run once (CI is a scaffold until M0.1) — otherwise PRs block on a check that never runs. Add Greptile + the `golden`/`tax`/`property`/`rls` fixture checks as they come online.

> Also enable repo-level auto-merge: `gh repo edit OWNER/tolera --enable-auto-merge`. Then `/ship` runs `gh pr merge --auto --squash` and GitHub merges each PR the moment its required checks pass.

```bash
for BR in develop main; do
  gh api -X PUT "repos/OWNER/tolera/branches/$BR/protection" --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "backend" } ] },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "require_code_owner_reviews": false,
    "dismiss_stale_reviews": true
  },
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "restrictions": null
}
JSON
done
```

Knobs to know:
- `required_approving_review_count`: **0** — full bot-only merge; we never require a human approval. (Leave at 0 even with teammates; the gate is the required checks, not approvals.)
- `require_code_owner_reviews`: **false** — money/tax/schema/auth are gated by **required fixtures**, not Code-Owner approval. (`.github/CODEOWNERS` stays as documentation of ownership.)
- `required_status_checks.checks`: add `greptile` and the `golden`/`tax`/`property`/`rls` fixture jobs alongside `backend` as they come online — these are the real gate.
- `enforce_admins: false` keeps you from being *locked out*; the PR + green-checks requirement still gates every merge.

## 4. Create the `block` label and seed issues

```bash
gh label create block --description "One build-plan block" --color 1D76DB
gh label create spike --description "Throwaway proof of an unknown" --color FBCA04
gh label create golden-thread --description "Touches the end-to-end thread" --color 0E8A16
```

(Optional) turn each build-plan block into a claimable issue with the `/to-issues` skill, or open them by hand from `.github/ISSUE_TEMPLATE/build-block.md`.

## 5. Store the CI/deploy secrets (from the M0.0 vault)

```bash
gh secret set ANTHROPIC_API_KEY          # used by the @claude action + Lens
gh secret set KAMAL_REGISTRY_PASSWORD
gh secret set SSH_DEPLOY_KEY < ~/path/to/deploy_key
# ...plus the rest of the M0.0 secrets inventory as deploy work begins
```

## 6. Install the `@claude` GitHub App

```bash
claude /install-github-app
```

This installs the app, stores `ANTHROPIC_API_KEY`, and writes the workflow (we've committed a reference at `.github/workflows/claude.yml`, **pinned to Sonnet 4.6** for cheap fix-findings — let the installer reconcile it but keep the `model:` line). The autonomous loop comments *"@claude address the review findings and push a fix"* on each PR; it reads Greptile + CodeRabbit comments and commits. Cost is ~$0.20–0.40/PR on Sonnet — set a monthly API spend cap in the Anthropic console as a backstop.

## 7. Enable the PR reviewers — Greptile (required) + CodeRabbit

We **do not** use Anthropic's hosted Code Review service (flat ~$15–25/review). The PR-review gate is **Greptile** (its own flat SaaS — $30/seat incl. 50 reviews, then $1; pre-Series-A startups under $2M get 50% off), with **CodeRabbit** as the advisory layer.

1. **Greptile** — install the Greptile GitHub App on `tolera` (greptile.com → Connect GitHub), set review on **PR open + push**. It reads `REVIEW.md` + `CLAUDE.md`. Add its `greptile` status check to branch protection (§3) once it's posted once. Claim the startup discount before the 14-day trial converts.
2. **CodeRabbit** — already configured via `.coderabbit.yaml` (advisory + summaries). Free tier = summaries + CLI; full inline PR review needs Pro — decide one-bot-vs-A/B per `build-plan/REVIEW-WORKFLOW-PROPOSAL.md`.
3. **NTFY_TOPIC secret** (for the morning digest): `gh secret set NTFY_TOPIC` → your private ntfy topic.

## Done when
- [ ] `tolera` private repo exists; `main` + `develop` pushed; default = `develop`.
- [ ] Both branches protected (**0 approvals** + required checks: CI + Greptile + fixtures); **auto-merge enabled**.
- [ ] `block` label created; secrets stored (incl. `NTFY_TOPIC`).
- [ ] `@claude` app installed (Sonnet-pinned); Greptile app installed; CodeRabbit configured.
