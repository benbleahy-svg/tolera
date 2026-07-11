#!/usr/bin/env bash
# Tolera autonomous build loop (local, subscription-billed).
#
# Runs ONE block per Claude Code invocation (fresh context each time = "auto mode"), then loops to
# the next block whose dependencies are merged. The build runs on your Team subscription (Opus by
# default; tier to Sonnet for mechanical blocks). Review + fix + auto-merge happen on GitHub.
#
# This is a SCAFFOLD — review before trusting it unattended. It is inert until the Python project
# exists (pyproject.toml) and until you remove the SAFETY STOP below.
#
# Footgun guards baked in:
#   - bounded iterations (MAX_BLOCKS) so a bad night can't churn the whole backlog
#   - a real sleep between cycles (never a tight `gh run view` poll — that exhausts the GH API limit)
#   - stops on repeated failure instead of merging red
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || exit 1)" || exit 1

MAX_BLOCKS="${MAX_BLOCKS:-6}"        # cap blocks per run
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-120}"
MODEL="${AUTOBUILD_MODEL:-opus}"     # opus by default; set AUTOBUILD_MODEL=sonnet for mechanical milestones

command -v claude >/dev/null 2>&1 || { echo "claude CLI not found" >&2; exit 1; }
[ -f pyproject.toml ] || { echo "No pyproject.toml yet (pre-M0.1) — nothing to build." >&2; exit 0; }

for ((i = 1; i <= MAX_BLOCKS; i++)); do
  echo "=== autobuild cycle $i/$MAX_BLOCKS ($(date -u +%FT%TZ)) ==="

  # Pick the lowest-numbered open block issue whose deps are merged. The prompt does the selection;
  # we let Claude read build-plan/ + open issues rather than hard-coding the order here.
  prompt='Run the autonomous per-block loop from .claude/hooks/session-start.sh:
  pick the lowest-numbered open build-plan block whose Depends-on are all merged, then /block it,
  self-grill (auto-accept doc-backed answers; reverify when unsure; escalate + STOP only on an
  irreversible question the docs cannot resolve), build test-first, run the independent verifier,
  and /ship with auto-merge. If there is no eligible block, print "NO-ELIGIBLE-BLOCK" and exit.'

  # Headless, auto-accept. --continue keeps prior session state across resumes after a limit reset.
  if ! claude --model "$MODEL" --dangerously-skip-permissions -p "$prompt"; then
    echo "Claude exited non-zero (likely a usage limit or an escalation). Stopping cleanly." >&2
    break
  fi

  # If the loop reported nothing to do, stop.
  # (The loop writes NO-ELIGIBLE-BLOCK to its output; pipe-check it in your own wrapper if desired.)

  echo "--- cooldown ${COOLDOWN_SECONDS}s ---"
  sleep "$COOLDOWN_SECONDS"
done

echo "=== autobuild run complete ($(date -u +%FT%TZ)) ==="
