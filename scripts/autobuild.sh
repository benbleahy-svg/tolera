#!/usr/bin/env bash
# autobuild.sh — the block-queue driver.
#
# Runs the tolera build plan block after block, each in a FRESH headless
# Claude Code session (perfect context hygiene: one block = one process).
# Routes cheap blocks to the default model and risky blocks to the frontier
# model, arms auto-merge via /ship, waits for the merge, and only stops for:
#   * BLOCKED.md            — an OPEN: decision or missing credential needs YOU
#   * red CI after retries  — 2 fix attempts, then 1 frontier-model attempt
#   * a usage-limit window  — sleeps and resumes automatically (no action needed)
#   * a milestone boundary  — the clickable checkpoint (scripts/checkpoint.sh)
#
# Usage:
#   scripts/autobuild.sh                 # auto-detect next block from GitHub, confirm, run
#   scripts/autobuild.sh --start M2.10   # start from a specific block
#   scripts/autobuild.sh --continue      # resume after a checkpoint or a fix
#   scripts/autobuild.sh --dry-run       # print the queue + model routing, run nothing
set -euo pipefail
cd "$(dirname "$0")/.."

# ── Config ────────────────────────────────────────────────────────────────
# Model IDs confirmed from the CLI's /model list (2026-07-14):
#   opus            = Opus 4.8 ("best for everyday, complex tasks")
#   claude-fable-5  = Fable 5  ("most capable for your hardest and longest-running tasks")
DEFAULT_MODEL="opus"                 # routine S/M blocks
FRONTIER_MODEL="claude-fable-5"      # L blocks, spikes, money/schema/geometry, all of M4
REVIEW_NOTE="cross-model review runs in CI (claude-code-review.yml)"
MAX_FIX_ATTEMPTS=2                   # CI-fix rounds on the default model
LIMIT_SLEEP_MIN=30                   # poll interval while a usage window is exhausted
STATE_FILE=".autobuild.state"        # last completed block + checkpoint flag

notify() {  # macOS notification + log line; the build never fails just because notify does
  printf '\n\033[1m[autobuild] %s\033[0m\n' "$1"
  osascript -e "display notification \"$1\" with title \"Tolera autobuild\" sound name \"Glass\"" 2>/dev/null || true
}

halt() { notify "$1"; echo "$1" > .autobuild.halted; exit 1; }

# ── Queue: block ids in build order, with milestone + risk routing ────────
# Parses `### M{n}.{k} — Title [S|M|L] {SPIKE}` headings from build-plan/M*.md.
# Risky → frontier model when ANY of these fires (the block's own metadata decides):
#   1. sized [L] or marked SPIKE in its heading   (the build plan's own risk labels)
#   2. it lives in M4                             (the plan marks all of M4 high-drift)
#   3. its section text touches a tier-1 domain   (kalk/pricing/money/tax/schema/
#      migration/auth/tenancy/rls — the "expensive to reverse" list from CLAUDE.md §6)
# Manual override: build-plan/model-overrides.txt, one `M2.10 frontier` or
# `M5.3 default` per line — it beats the automatic routing. Inspect the full
# routing table any time with:  scripts/autobuild.sh --dry-run
build_queue() {
  python3 - <<'PY'
import re, glob, os
overrides = {}
if os.path.exists('build-plan/model-overrides.txt'):
    for line in open('build-plan/model-overrides.txt', encoding='utf-8'):
        parts = line.split()
        if len(parts) == 2 and parts[1] in ('frontier', 'default'):
            overrides[parts[0]] = parts[1]
for path in sorted(glob.glob('build-plan/M[0-9]*.md')):
    text = open(path, encoding='utf-8').read()
    for m in re.finditer(r'^### (M\d+\.\d+[a-z]?)\s*[—-]\s*(.*)$', text, re.M):
        block, rest = m.group(1), m.group(2)
        section = text[m.start(): text.find('### M', m.end()) if text.find('### M', m.end()) != -1 else len(text)]
        risky = bool(re.search(r'\[L\]|SPIKE', rest)) or block.startswith('M4') or \
                bool(re.search(r'\b(kalk|pricing|money|tax|mwst|ust|schema|migrations?|auth\w*|tenanc\w*|rls)\b', section, re.I))
        tier = overrides.get(block, 'frontier' if risky else 'default')
        print(f"{block}\t{tier}")
PY
}

merged() {  # has this block's PR merged? (PR titles carry the block id per template)
  gh pr list --state merged --search "\"$1\" in:title" --json number --jq 'length' | grep -qv '^0$'
}

milestone_of() { echo "${1%%.*}"; }  # M2.10 -> M2

# ── Args ──────────────────────────────────────────────────────────────────
START=""; DRY=0; CONT=0
while [ $# -gt 0 ]; do case "$1" in
  --start) START="$2"; shift 2;; --dry-run) DRY=1; shift;; --continue) CONT=1; rm -f .autobuild.halted "$STATE_FILE.checkpoint" 2>/dev/null; shift;;
  *) echo "unknown arg $1"; exit 1;; esac; done

[ -f .autobuild.halted ] && [ "$CONT" -eq 0 ] && halt "Halted earlier: $(cat .autobuild.halted). Fix, then rerun with --continue."

QUEUE="$(build_queue)"
[ "$DRY" -eq 1 ] && { echo "$QUEUE" | column -t; exit 0; }

# ── Main loop ─────────────────────────────────────────────────────────────
STARTED=0
PREV_MILESTONE=""
while IFS=$'\t' read -r BLOCK TIER; do
  # skip until the start point / already-merged blocks
  if [ -n "$START" ] && [ "$STARTED" -eq 0 ]; then [ "$BLOCK" = "$START" ] && STARTED=1 || continue; fi
  if [ -z "$START" ] && merged "$BLOCK"; then PREV_MILESTONE="$(milestone_of "$BLOCK")"; continue; fi

  # milestone boundary → clickable checkpoint, then stop until --continue
  MS="$(milestone_of "$BLOCK")"
  if [ -n "$PREV_MILESTONE" ] && [ "$MS" != "$PREV_MILESTONE" ] && [ "$CONT" -eq 0 ]; then
    notify "Milestone $PREV_MILESTONE complete — starting your clickable checkpoint."
    scripts/checkpoint.sh "$PREV_MILESTONE"   # boots the app + seed data, writes CHECKPOINT.md, opens browser
    touch "$STATE_FILE.checkpoint"
    halt "Checkpoint for $PREV_MILESTONE is open in your browser. Click through CHECKPOINT.md, then rerun: scripts/autobuild.sh --continue"
  fi
  CONT=0  # a checkpoint pass only skips one boundary

  # confirm first pick when auto-detecting
  if [ -z "$START" ] && [ "$STARTED" -eq 0 ]; then
    STARTED=1
    notify "Auto-detected next block: $BLOCK ($TIER model). Starting in 60s — Ctrl-C to abort."
    sleep 60
  fi

  MODEL="$DEFAULT_MODEL"; [ "$TIER" = "frontier" ] && MODEL="$FRONTIER_MODEL"
  notify "Building $BLOCK on $MODEL ($REVIEW_NOTE)"

  # one FRESH session per block; retry the launch itself while usage-limited
  run_session() {  # $1 = prompt, $2 = model
    while :; do
      OUT="$(claude -p "$1" --model "$2" --permission-mode acceptEdits 2>&1)" && { echo "$OUT"; return 0; }
      if echo "$OUT" | grep -qiE 'usage limit|rate limit|limit (reached|exceeded)'; then
        notify "Usage window exhausted — sleeping ${LIMIT_SLEEP_MIN}m, will resume automatically."
        sleep "$((LIMIT_SLEEP_MIN * 60))"
      else echo "$OUT"; return 1; fi
    done
  }

  run_session "/block $BLOCK" "$MODEL" || true
  [ -f BLOCKED.md ] && halt "$BLOCK is blocked and needs you: $(head -c 400 BLOCKED.md)"

  # wait for the PR, watch its checks, fix on red (2x default, then 1x frontier)
  PR="$(gh pr list --state open --search "\"$BLOCK\" in:title" --json number --jq '.[0].number' || true)"
  [ -z "$PR" ] || [ "$PR" = "null" ] && halt "$BLOCK finished without an open PR — inspect the branch manually."
  ATTEMPT=0
  until gh pr checks "$PR" --watch --fail-fast >/dev/null 2>&1; do
    if merged "$BLOCK"; then break; fi
    ATTEMPT=$((ATTEMPT+1))
    if   [ "$ATTEMPT" -le "$MAX_FIX_ATTEMPTS" ]; then FIX_MODEL="$MODEL"
    elif [ "$ATTEMPT" -eq $((MAX_FIX_ATTEMPTS+1)) ]; then FIX_MODEL="$FRONTIER_MODEL"; notify "Escalating $BLOCK CI fix to $FRONTIER_MODEL"
    else halt "$BLOCK: CI still red after $ATTEMPT fix rounds — needs you (PR #$PR)."; fi
    run_session "CI is red on PR #$PR (block $BLOCK). Get the failing logs with 'gh pr checks $PR' and 'gh run view', fix the root cause test-first, push. Never weaken a test or a tier-1 rule to go green." "$FIX_MODEL" || true
    [ -f BLOCKED.md ] && halt "$BLOCK fix session blocked: $(head -c 400 BLOCKED.md)"
  done

  # auto-merge is armed by /ship; give it a moment, then verify
  for _ in $(seq 1 60); do merged "$BLOCK" && break; sleep 30; done
  merged "$BLOCK" || halt "$BLOCK: checks green but PR #$PR not merged — check branch protection / auto-merge settings."

  echo "$BLOCK" > "$STATE_FILE"
  notify "$BLOCK merged ✅"
  PREV_MILESTONE="$MS"
done <<< "$QUEUE"

notify "Queue complete — every block in the build plan is merged. 🎉"
