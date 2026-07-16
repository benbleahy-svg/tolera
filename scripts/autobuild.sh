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
#
# Milestone boundaries are NON-BLOCKING: each finished milestone is logged to
# REVIEW-QUEUE.md and the run continues. Review one on demand, any time, with
# scripts/checkpoint.sh <M>.
#
# "Is this block done?" is answered by the LEDGER (.autobuild.completed): one
# block id per line, appended automatically after each confirmed merge. Name-
# based PR matching is only a fallback — early PRs don't carry block ids in
# their titles, which made pure name-matching produce false negatives.
#
# Usage:
#   scripts/autobuild.sh                 # next block = first not in the ledger; confirm, run
#   scripts/autobuild.sh --start M2.10   # start from a specific block
#   scripts/autobuild.sh --continue      # resume after a checkpoint or a fix
#   scripts/autobuild.sh --dry-run       # print the queue + model routing, run nothing
#   scripts/autobuild.sh --headless      # unattended mode (invisible sessions; overnight runs)
#   scripts/autobuild.sh --stop-before M3     # stop when the next block is in M3 (a milestone)
#   scripts/autobuild.sh --stop-before M3.2   # stop when the next block is M3.2 (a single block)
#
# --stop-before takes a block id (M3.2) or a milestone id (M3) and parks the run
# just BEFORE that point: the named block is never started, nothing is left half-
# built, and the driver exits 0. Resume with a plain scripts/autobuild.sh.
#
# DEFAULT MODE: each block opens in the full Claude Code CLI in this Terminal —
# you watch it work and can interrupt/type at any time. When /ship finishes and
# the session says it's done, type /exit — that hands control back to this
# driver, which verifies the merge and opens the next block. With --headless,
# sessions run invisibly instead (auto-sleeps through usage limits; logs to
# .autobuild-logs/) — use for overnight runs.
set -euo pipefail
cd "$(dirname "$0")/.."

# ── Config ────────────────────────────────────────────────────────────────
# Model IDs confirmed from the CLI's /model list (2026-07-14):
#   opus            = Opus 4.8 ("best for everyday, complex tasks")
#   claude-fable-5  = Fable 5  ("most capable for your hardest and longest-running tasks")
#
# The two tiers MUST name different models. Point them at the same one and the
# routing machinery below still runs but can no longer decide anything: the
# frontier/default split, build-plan/model-overrides.txt and the CI-fix
# escalation all go silently inert while the --dry-run table still claims to be
# routing. Keep them distinct (2026-07-16).
#
# Reasoning effort is a CLI session flag, not a model-id suffix: `--effort <level>`
# (low|medium|high|xhigh|max), confirmed from `claude --help` (2026-07-15). It applies
# to interactive and headless (-p) sessions alike, so run_session passes it on every
# claude invocation.
DEFAULT_MODEL="opus"                 # routine S/M blocks
FRONTIER_MODEL="claude-fable-5"      # L blocks, spikes, money/schema/geometry, all of M4
EFFORT="high"                        # reasoning effort for every session (--effort)
REVIEW_NOTE="cross-model review runs in CI (claude-code-review.yml)"
MAX_FIX_ATTEMPTS=2                   # CI-fix rounds on the default model
LIMIT_SLEEP_MIN=30                   # poll interval while a usage window is exhausted
STATE_FILE=".autobuild.state"        # last completed block + checkpoint flag
LEDGER=".autobuild.completed"        # one block id per line = done (gitignored, local)

notify() {  # macOS notification + log line; the build never fails just because notify does
  printf '\n\033[1m[autobuild] %s\033[0m\n' "$1"
  osascript -e "display notification \"$1\" with title \"Tolera autobuild\" sound name \"Glass\"" 2>/dev/null || true
}

halt() { notify "$1"; echo "$1" > .autobuild.halted; exit 1; }

# ── Queue: block ids in build order, with milestone + risk routing ────────
# Parses `### M{n}.{k} — Title [S|M|L] {SPIKE}` headings from build-plan/M*.md.
#
# ROUTING (Benjamin's decision, 2026-07-16): every block runs on the DEFAULT tier
# (Opus 4.8 high) unless build-plan/model-overrides.txt opts it into `frontier`.
# Fable 5 is opt-in per block, never automatic.
#
# The risk heuristic below no longer routes — it only ANNOTATES, as the third
# `--dry-run` column, so you can see which blocks are worth opting in. It fires on:
#   1. sized [L] or marked SPIKE in its heading   (the build plan's own risk labels)
#   2. it lives in M4                             (the plan marks all of M4 high-drift)
#   3. its section text touches a tier-1 domain   (kalk/pricing/money/tax/schema/
#      migration/auth/tenancy/rls — the "expensive to reverse" list from CLAUDE.md §6)
# It is deliberately broad — it matched 68 of 82 blocks, which is why it advises
# rather than decides. Opt a block in with `M4.1 frontier` in model-overrides.txt;
# inspect the live table any time with:  scripts/autobuild.sh --dry-run
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
        # Opus for everything; `frontier` (Fable 5) is opt-in via model-overrides.txt.
        # `risky` only annotates — see the routing note above.
        tier = overrides.get(block, 'default')
        print(f"{block}\t{tier}\t{'risky' if risky else '-'}")
PY
}

completed() {  # the ledger is the source of truth for "done"
  [ -f "$LEDGER" ] && grep -qx "$1" "$LEDGER"
}

merged_by_name() {  # FALLBACK only: match the id in PR titles and branch names
  local pat="${1//./\\.}"
  gh pr list --state merged --limit 300 --json title,headRefName \
    --template '{{range .}}{{.title}} {{.headRefName}}{{"\n"}}{{end}}' 2>/dev/null \
    | grep -qiE "(^|[^0-9a-z])${pat}([^0-9a-z]|\$)"
}

pr_state() { gh pr view "$1" --json state --jq .state 2>/dev/null; }  # OPEN | MERGED | CLOSED

milestone_of() { echo "${1%%.*}"; }  # M2.10 -> M2

# ── Args ──────────────────────────────────────────────────────────────────
START=""; DRY=0; CONT=0; HEADLESS=0; STOP_BEFORE=""
while [ $# -gt 0 ]; do case "$1" in
  --start) START="$2"; shift 2;; --dry-run) DRY=1; shift;; --continue) CONT=1; rm -f .autobuild.halted "$STATE_FILE.checkpoint" 2>/dev/null; shift;;
  --headless) HEADLESS=1; shift;;
  --stop-before) STOP_BEFORE="$2"; shift 2;;
  *) echo "unknown arg $1"; exit 1;; esac; done

[ -f .autobuild.halted ] && [ "$CONT" -eq 0 ] && halt "Halted earlier: $(cat .autobuild.halted). Fix, then rerun with --continue."

QUEUE="$(build_queue)"
[ "$DRY" -eq 1 ] && { echo "$QUEUE" | column -t; exit 0; }

# ── Main loop ─────────────────────────────────────────────────────────────
STARTED=0
PREV_MILESTONE=""
while IFS=$'\t' read -r BLOCK TIER RISK; do
  # skip completed blocks (ledger first; name-match fallback backfills the ledger)
  if [ -n "$START" ] && [ "$STARTED" -eq 0 ]; then [ "$BLOCK" = "$START" ] && STARTED=1 || continue; fi
  if [ -z "$START" ]; then
    if completed "$BLOCK"; then PREV_MILESTONE="$(milestone_of "$BLOCK")"; continue; fi
    if merged_by_name "$BLOCK"; then
      echo "$BLOCK" >> "$LEDGER"; PREV_MILESTONE="$(milestone_of "$BLOCK")"; continue
    fi
  fi

  # milestone boundary → log to the review queue and keep going (non-blocking)
  MS="$(milestone_of "$BLOCK")"
  if [ -n "$PREV_MILESTONE" ] && [ "$MS" != "$PREV_MILESTONE" ]; then
    echo "$PREV_MILESTONE — completed $(date '+%Y-%m-%d %H:%M'), unreviewed. Review: scripts/checkpoint.sh $PREV_MILESTONE" >> REVIEW-QUEUE.md
    notify "Milestone $PREV_MILESTONE complete — continuing into $MS. Review any time: scripts/checkpoint.sh $PREV_MILESTONE"
  fi

  # --stop-before: park just before the named block/milestone, having started nothing
  if [ -n "$STOP_BEFORE" ] && { [ "$BLOCK" = "$STOP_BEFORE" ] || [ "$MS" = "$STOP_BEFORE" ]; }; then
    notify "Reached $STOP_BEFORE — stopping here as requested. Resume: scripts/autobuild.sh"
    exit 0
  fi

  # confirm first pick when auto-detecting
  if [ -z "$START" ] && [ "$STARTED" -eq 0 ]; then
    STARTED=1
    if [ "$HEADLESS" -eq 1 ]; then
      notify "Auto-detected next block: $BLOCK ($TIER model). Starting in 60s — Ctrl-C to abort."
      sleep 60
    else
      notify "Next block: $BLOCK ($TIER model$([ "$RISK" = "risky" ] && echo "; flagged risky — 'echo \"$BLOCK frontier\" >> build-plan/model-overrides.txt' to run it on $FRONTIER_MODEL"))."
      read -r -p "Press Enter to open the Claude Code session for $BLOCK (Ctrl-C to abort)… "
    fi
  fi

  MODEL="$DEFAULT_MODEL"; [ "$TIER" = "frontier" ] && MODEL="$FRONTIER_MODEL"
  notify "Building $BLOCK on $MODEL ($REVIEW_NOTE)"

  # one FRESH session per block.
  # Default: the full Claude Code CLI takes over this Terminal — watch, interrupt,
  # or type as you like; /exit when /ship says the session is done. Headless:
  # invisible session streaming to .autobuild-logs/, auto-sleeping through limits.
  run_session() {  # $1 = prompt, $2 = model
    if [ "$HEADLESS" -eq 0 ]; then
      claude --model "$2" --effort "$EFFORT" --permission-mode acceptEdits "$1" || true
      return 0
    fi
    mkdir -p .autobuild-logs
    local log=".autobuild-logs/${BLOCK}.log"
    while :; do
      claude -p "$1" --model "$2" --effort "$EFFORT" --permission-mode acceptEdits --verbose 2>&1 | tee -a "$log"
      local status="${PIPESTATUS[0]}"
      [ "$status" -eq 0 ] && return 0
      if tail -c 4000 "$log" | grep -qiE 'usage limit|rate limit|limit (reached|exceeded)'; then
        notify "Usage window exhausted — sleeping ${LIMIT_SLEEP_MIN}m, will resume automatically."
        sleep "$((LIMIT_SLEEP_MIN * 60))"
      else return 1; fi
    done
  }

  run_session "/block $BLOCK" "$MODEL" || true
  [ -f BLOCKED.md ] && halt "$BLOCK is blocked and needs you: $(head -c 400 BLOCKED.md)"

  # find the PR by the branch the session worked on (robust), title search as fallback
  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  PR=""
  if [ -n "$BRANCH" ] && [ "$BRANCH" != "develop" ] && [ "$BRANCH" != "main" ]; then
    PR="$(gh pr list --state all --head "$BRANCH" --json number --jq '.[0].number' 2>/dev/null || true)"
  fi
  [ -z "$PR" ] || [ "$PR" = "null" ] && PR="$(gh pr list --state open --search "\"$BLOCK\" in:title" --json number --jq '.[0].number' 2>/dev/null || true)"
  [ -z "$PR" ] || [ "$PR" = "null" ] && halt "$BLOCK ended without a PR. If you exited the session before /ship finished, just rerun: scripts/autobuild.sh --continue (the block resumes on branch '$BRANCH')."

  # watch checks by PR NUMBER; fix on red (2x same model, then 1x frontier); verify merge by number.
  # SELF-HEALS the two known overnight stalls: branch behind develop (strict
  # up-to-date protection) → gh pr update-branch; merge conflicts → a resolution
  # session per /resolving-merge-conflicts (max 2 rounds, then wake the human).
  ATTEMPT=0; CONFLICT_ROUNDS=0; GREEN_WAITS=0
  while :; do
    STATE="$(pr_state "$PR")"
    [ "$STATE" = "MERGED" ] && break
    [ "$STATE" = "CLOSED" ] && halt "$BLOCK: PR #$PR was closed without merging — needs you."

    MSTATE="$(gh pr view "$PR" --json mergeStateStatus --jq .mergeStateStatus 2>/dev/null || true)"
    if [ "$MSTATE" = "BEHIND" ]; then
      notify "$BLOCK: PR #$PR is behind develop — updating the branch."
      gh pr update-branch "$PR" >/dev/null 2>&1 || true
      sleep 30; continue
    fi
    if [ "$MSTATE" = "DIRTY" ]; then
      CONFLICT_ROUNDS=$((CONFLICT_ROUNDS+1))
      [ "$CONFLICT_ROUNDS" -gt 2 ] && halt "$BLOCK: PR #$PR still has merge conflicts after 2 autonomous resolution rounds — needs you (gh pr view $PR --web)."
      notify "$BLOCK: PR #$PR has merge conflicts — resolving autonomously (round $CONFLICT_ROUNDS/2)."
      run_session "PR #$PR (block $BLOCK) has merge conflicts with develop. Switch to its branch, git fetch origin && git merge origin/develop, resolve per /resolving-merge-conflicts (autonomously — fixtures and tier-1 rules decide, never weaken either), rerun the full local gate, push." "$MODEL" || true
      [ -f BLOCKED.md ] && halt "$BLOCK conflict session blocked: $(head -c 400 BLOCKED.md)"
      continue
    fi

    if gh pr checks "$PR" --watch --fail-fast >/dev/null 2>&1; then
      # checks green → auto-merge should land it; poll up to 10 minutes
      MERGED_OK=0
      for _ in $(seq 1 40); do
        [ "$(pr_state "$PR")" = "MERGED" ] && { MERGED_OK=1; break; }
        sleep 15
      done
      [ "$MERGED_OK" = "1" ] && break
      # not merged despite green — re-enter the loop so BEHIND/DIRTY healing can
      # kick in (a develop merge during our wait flips the state); 3 strikes → human
      GREEN_WAITS=$((GREEN_WAITS+1))
      [ "$GREEN_WAITS" -ge 3 ] && halt "$BLOCK: checks green but PR #$PR not merged — check auto-merge/branch protection, or run scripts/setup-automerge.sh once (gh pr view $PR --web)."
      continue
    fi
    ATTEMPT=$((ATTEMPT+1))
    if   [ "$ATTEMPT" -le "$MAX_FIX_ATTEMPTS" ]; then FIX_MODEL="$MODEL"
    elif [ "$ATTEMPT" -eq $((MAX_FIX_ATTEMPTS+1)) ]; then FIX_MODEL="$FRONTIER_MODEL"; notify "Escalating $BLOCK CI fix to $FRONTIER_MODEL"
    else halt "$BLOCK: CI still red after $ATTEMPT fix rounds — needs you (PR #$PR)."; fi
    run_session "CI is red on PR #$PR (block $BLOCK). Get the failing logs with 'gh pr checks $PR' and 'gh run view', fix the root cause test-first, push. Never weaken a test or a tier-1 rule to go green." "$FIX_MODEL" || true
    [ -f BLOCKED.md ] && halt "$BLOCK fix session blocked: $(head -c 400 BLOCKED.md)"
  done

  echo "$BLOCK" >> "$LEDGER"
  echo "$BLOCK" > "$STATE_FILE"
  git switch develop >/dev/null 2>&1 && git pull --ff-only >/dev/null 2>&1 || true
  notify "$BLOCK merged ✅ (PR #$PR)"
  PREV_MILESTONE="$MS"
done <<< "$QUEUE"

notify "Queue complete — every block in the build plan is merged. 🎉"
