#!/usr/bin/env bash
# Notification / Stop hook — push a phone alert when the autonomous loop needs you or finishes.
#
# Fires on:
#   - Notification events (Claude is waiting on input / a permission / an escalation question)
#   - Stop events (a block finished, or the loop paused)
#
# This is the plan-agnostic fallback to Claude Code's native Remote Control push: it routes the
# event to ntfy.sh so you get it on your phone even if Remote Control is off. If you ALSO have
# Remote Control + "/config -> Push when actions required" on, you'll get the native push too —
# harmless to have both. Set NTFY_TOPIC to enable; leave it unset to no-op.
#
# Setup: install the ntfy app (iOS/Android), subscribe to a private topic, then:
#   export NTFY_TOPIC="tolera-<something-random>"     # in your shell profile / launchd env
# Optional self-hosted server: export NTFY_SERVER="https://ntfy.example.com"
set -uo pipefail

TOPIC="${NTFY_TOPIC:-}"
[ -z "$TOPIC" ] && exit 0          # not configured -> do nothing
SERVER="${NTFY_SERVER:-https://ntfy.sh}"

# Hook payload arrives as JSON on stdin; pull a human message if jq is available.
payload="$(cat 2>/dev/null || true)"
msg=""
if command -v jq >/dev/null 2>&1 && [ -n "$payload" ]; then
  msg="$(printf '%s' "$payload" | jq -r '.message // .notification // empty' 2>/dev/null)"
fi
[ -z "$msg" ] && msg="Tolera autobuild needs you (or a block finished)."

repo="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || echo Tolera)")"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"

curl -fsS \
  -H "Title: ${repo} · ${branch}" \
  -H "Priority: high" \
  -H "Tags: robot" \
  -d "$msg" \
  "${SERVER}/${TOPIC}" >/dev/null 2>&1 || true

exit 0
