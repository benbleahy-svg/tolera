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

Branch protection is what enforces *one-PR-per-block*. **Solo for now:** GitHub won't let you approve your own PRs, so we require **0 human approvals** and lean on CI + CodeRabbit + Claude review as the gate — while still forcing every change through a PR. When a second teammate joins, bump approvals to **1** and turn on **Code Owner reviews** (`.github/CODEOWNERS` is already wired).

> Note: the `backend` status check is the job in `.github/workflows/ci.yml`. Add it to protection **after** CI has passed once (the CI file is a scaffold until M0.1 wires it to real code) — otherwise PRs will block on a check that never runs.

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
- `required_approving_review_count`: **0** while solo (you can't approve your own PRs). Set to **1** when a teammate joins.
- `require_code_owner_reviews`: **false** while solo; flip to **true** with a teammate to make `.github/CODEOWNERS` binding (schema/auth/pricing then need the owner's approval).
- `enforce_admins: false` keeps you from being *locked out*; the PR + green-CI requirement still gates normal merges.

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

This installs the app, stores `ANTHROPIC_API_KEY`, and writes the workflow (we've committed a reference at `.github/workflows/claude.yml` — let the installer reconcile it). After this, mention **`@claude`** in any PR/issue comment to have it act (e.g. *"@claude address CodeRabbit's findings and push a fix"*).

## 7. (If you adopt it) enable Anthropic hosted Code Review

Admin → [claude.ai/admin-settings/claude-code](https://claude.ai/admin-settings/claude-code) → Code Review → install the app on `tolera` → set **Review behavior = After every push** (catches issues as the PR evolves). It reads `REVIEW.md` + `CLAUDE.md` automatically. Requires a Team/Enterprise Claude plan; ~$15–25/review.

## Done when
- [ ] `tolera` private repo exists; `main` + `develop` pushed; default = `develop`.
- [ ] Both branches protected (1 approval + Code Owners + CI check).
- [ ] `block` label created; secrets stored.
- [ ] `@claude` app installed; CodeRabbit + (optional) hosted Code Review enabled.
