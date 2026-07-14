#!/usr/bin/env bash
# checkpoint.sh <milestone> — the clickable milestone gate for non-technical reviewers.
#
# Boots the full local app with seeded demo data, writes CHECKPOINT.md (a plain-
# language click-script generated from DEMOS-TRACEABILITY + the demo narratives),
# optionally replays the milestone's promoted Playwright demos in headed mode so
# you can WATCH the flows run, and opens the app + the guide.
#
# Called automatically by scripts/autobuild.sh at each milestone boundary.
# Manual use:  scripts/checkpoint.sh M2
set -euo pipefail
cd "$(dirname "$0")/.."
MS="${1:?usage: scripts/checkpoint.sh <milestone, e.g. M2>}"

echo "▶ Booting the app stack (db · redis · minio · api · worker)…"
docker compose up -d --build
echo "▶ Seeding demo data…"
docker compose exec -T app python -m scripts.seed_demo \
  || echo "  (seed script not available yet — continuing with existing data)"

echo "▶ Starting the frontend…"
if ! curl -fsS http://localhost:5173 >/dev/null 2>&1; then
  ( cd frontend && nohup npm run dev >/tmp/tolera-frontend.log 2>&1 & echo $! > /tmp/tolera-frontend.pid )
  for _ in $(seq 1 30); do curl -fsS http://localhost:5173 >/dev/null 2>&1 && break; sleep 2; done
fi

echo "▶ Writing your click-through guide (CHECKPOINT.md)…"
claude -p "Milestone $MS of the build just completed and a NON-TECHNICAL reviewer will now click through the product at http://localhost:5173. Write CHECKPOINT.md at the repo root. Using build-plan/DEMOS-TRACEABILITY.md, the demo narratives (spec #demos/#acceptance), and docs/fixtures: (1) list every demo that $MS (and earlier milestones) lights up; (2) for each, give numbered plain-language click steps — what to click, what to type/upload (name the exact fixture file), and EXACTLY what they should see, including exact figures from the fixtures (e.g. '2.160,84 €'); (3) end with a section titled 'Notes — anything that looked wrong' left blank for the reviewer. No jargon. Two pages max." \
  --model opus --permission-mode acceptEdits || echo "  (could not generate the guide — open build-plan/DEMOS-TRACEABILITY.md instead)"

echo "▶ Replaying promoted demos in a visible browser (watch them run; Ctrl-C to skip)…"
( cd e2e && npm run test:headed ) || true

command -v open >/dev/null && { open http://localhost:5173; [ -f CHECKPOINT.md ] && open CHECKPOINT.md; }

cat <<'EOT'

──────────────────────────────────────────────────────────────────────
 CHECKPOINT: click through CHECKPOINT.md in the app.

 All good?           scripts/autobuild.sh --continue
 Something wrong?    Write what you saw under 'Notes' in CHECKPOINT.md, then:
                     claude -p "Read the reviewer notes in CHECKPOINT.md and fix them, test-first, on a fix branch; then /ship"
                     …and rerun scripts/autobuild.sh --continue afterwards.
──────────────────────────────────────────────────────────────────────
EOT
