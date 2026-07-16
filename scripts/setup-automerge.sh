#!/usr/bin/env bash
# setup-automerge.sh — ONE-TIME GitHub configuration for the autonomous pipeline.
#
# Enables repo auto-merge and sets the required status checks that gate every
# auto-merged PR: backend · frontend · semgrep (+ e2e, added automatically once
# that workflow has produced a check run — rerun this script at that point).
# Fully-automatic mode: no human approval requirement (the milestone checkpoint
# in scripts/checkpoint.sh is the human gate).
#
# Prereq: `gh auth login` done. Safe to rerun any time.
set -euo pipefail
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
echo "Configuring $REPO…"

gh repo edit --enable-auto-merge --enable-squash-merge

CHECKS='{ "context": "backend" }, { "context": "frontend" }, { "context": "semgrep" }'
if gh api "repos/$REPO/commits/develop/check-runs" --jq '.check_runs[].name' 2>/dev/null | grep -qx 'e2e'; then
  CHECKS="$CHECKS, { \"context\": \"e2e\" }"
  echo "✓ e2e check has run — adding it as required."
else
  echo "! e2e has not produced a check run on develop yet."
  echo "  Rerun this script after the first e2e workflow run to make the demo tests merge-blocking."
fi

for BR in develop main; do
  gh api -X PUT "repos/$REPO/branches/$BR/protection" --input - <<JSON
{
  "required_status_checks": { "strict": true, "checks": [ $CHECKS ] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "restrictions": null
}
JSON
  echo "✓ $BR protected (required checks: $(echo "$CHECKS" | grep -o '"context"' | wc -l | tr -d ' '))"
done

echo "Done. PRs opened by /ship with 'gh pr merge --auto --squash' now merge themselves on green."
