#!/usr/bin/env bash
# Resume the autonomous loop after a usage-limit window resets.
#
# The Team subscription's 5-hour window clears on its own; this wrapper re-launches the loop shortly
# after, so you don't have to tap "continue" from your phone every time. Driven by launchd (see
# com.tolera.autobuild.plist) on a fixed cadence. The weekly cap is a hard wall — when that is hit,
# this will simply no-op each run until the weekly reset (and the notify hook will have alerted you).
#
# It is safe to run on a schedule: if the loop is already running, the lockfile makes this a no-op.
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || exit 1)" || exit 1

LOCK="/tmp/tolera-autobuild.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "autobuild already running ($LOCK exists) — skipping." >&2
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# Keep the Mac awake for the duration of a cycle so the session isn't suspended mid-build.
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i scripts/autobuild-loop.sh
else
  exec scripts/autobuild-loop.sh
fi
