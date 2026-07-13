#!/usr/bin/env bash
# SessionEnd hook — mechanical handoff net. If the session dies with uncommitted work
# and no proper HANDOFF.md, write HANDOFF.autogen.md (branch, status, diff, commits)
# so the next session's /block step 0 can reconstruct state. Pure script — the session
# is already over, so no model involvement. Never blocks, never fails the exit.
set -uo pipefail
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
cd "$(git rev-parse --show-toplevel)" || exit 0
[ -f HANDOFF.md ] && exit 0                                   # proper handoff exists
dirty="$(git status --porcelain 2>/dev/null)"
[ -n "$dirty" ] || exit 0                                     # clean tree — nothing to save

input="$(cat)"
reason="$(printf '%s' "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('reason',''))" 2>/dev/null || true)"
branch="$(git branch --show-current 2>/dev/null || echo unknown)"
block="$(printf '%s' "$branch" | grep -oiE 'm[0-9]+[._-][0-9]+[a-z]?' | head -1 || true)"

{
  echo "# HANDOFF (auto-generated — mechanical only, no narrative)"
  echo
  echo "> Session ended (${reason:-unknown}) with uncommitted work and no /handoff."
  echo "> Next session: read this, run the tests to establish ground truth, then delete it."
  echo
  echo "- **Generated:** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- **Branch:** ${branch}   **Block (guessed):** ${block:-?}"
  echo
  echo "## Uncommitted changes"
  echo '```'
  git status --porcelain
  echo '```'
  echo
  echo "## Diff stat (unstaged + staged)"
  echo '```'
  git diff --stat; git diff --cached --stat
  echo '```'
  echo
  echo "## Last commits on this branch (vs develop)"
  echo '```'
  git log --oneline develop..HEAD 2>/dev/null | head -10
  echo '```'
  echo
  echo "## Missing (only an in-session /handoff captures these)"
  echo "- Intent behind the in-progress edits · approaches already rejected · next step."
  echo "- Trust the TESTS, not assumptions: run \`uv run pytest -q -x\` first."
} > HANDOFF.autogen.md
exit 0
