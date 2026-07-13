#!/usr/bin/env bash
# PreCompact hook — the mid-block safety net. Auto-compaction is exactly the moment
# state silently degrades, so: (a) tell the summarizer what it MUST preserve, and
# (b) tell Claude to write HANDOFF.md immediately after compaction completes.
set -uo pipefail
input="$(cat)"
trigger="$(printf '%s' "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trigger',''))" 2>/dev/null || true)"

branch="$(git branch --show-current 2>/dev/null || echo unknown)"
ctx="COMPACTION (${trigger:-unknown}) on branch ${branch}.
PRESERVE VERBATIM in the summary: the current block id; the spec anchors + folded sub-spec in use; the exact next step; any red test and why; tier-1 invariants (integer minor units + currency, org-scoped RLS, Lens never auto-fed into Kalk, reversible migrations).
AFTER compaction: immediately run /handoff to write HANDOFF.md and commit it — a compacted session is a degraded session; prefer finishing the current red->green loop, handing off, and resuming the block in a FRESH session via /block."

python3 - "$ctx" <<'PY'
import json,sys
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreCompact","additionalContext":sys.argv[1]}}))
PY
exit 0
