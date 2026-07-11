# Autonomous build — setup runbook (your step-by-step)

This is everything **you** do to switch on the hands-off loop. Claude has already made the repo-side changes (listed at the bottom). Work top to bottom; each step says where it happens. Budget ~45–60 min.

> What you're turning on: one local Claude Code session builds block-by-block on your **Team subscription**, self-grills against the docs, an independent sub-agent verifies, **Greptile + CodeRabbit** review the PR, the **`@claude` action (Sonnet)** fixes findings, and **GitHub auto-merges on green** — no human approval. You're pinged on your phone only when an *irreversible* question can't be answered from the docs. Money/tax/schema/auth are protected by **required fixtures**, not by you.

---

## 0. One decision already recorded
Add a dated entry to `docs/decisions/DECISIONS.md` noting: *"2026-06 — adopted full bot-only auto-merge; overrides CLAUDE.md §9 human-gate. Money/tax/schema/auth protected by required fixtures + reversibility + morning digest."* (Claude can do this on request.)

## 1. Copy the staged `.claude` config into place  *(Terminal, on the Mac)*
Claude can't edit `.claude/` from a session, so the new versions are staged under `build-plan/autonomous-setup/claude-config/`. From the repo root:
```bash
cp build-plan/autonomous-setup/claude-config/settings.json        .claude/settings.json
cp build-plan/autonomous-setup/claude-config/hooks/notify.sh      .claude/hooks/notify.sh
cp build-plan/autonomous-setup/claude-config/hooks/session-start.sh .claude/hooks/session-start.sh
cp build-plan/autonomous-setup/claude-config/commands/block.md     .claude/commands/block.md
cp build-plan/autonomous-setup/claude-config/commands/ship.md      .claude/commands/ship.md
chmod +x .claude/hooks/*.sh
```
This fixes a JSON syntax error in your old `settings.json` (missing comma), adds the notification hook, and switches `session-start`/`block`/`ship` to the autonomous loop.

## 2. Enable Remote Control  *(Claude Code admin settings — admin)*
Team plan: an admin must turn it on. In Claude Code **admin settings → enable the Remote Control toggle**. Then on the build Mac, in a Claude session run `/config` and enable **"Push when Claude decides"** and **"Push when actions required."** Install the **Claude mobile app**, sign in with the same account, allow notifications.

## 3. Phone notifications fallback (ntfy)  *(phone + Terminal)*
Works on any plan, and powers the digest + the `notify.sh` hook.
1. Install the **ntfy** app (iOS/Android), pick a private topic name, e.g. `tolera-7h3k9q`.
2. On the Mac, add to your shell profile: `export NTFY_TOPIC="tolera-7h3k9q"`.
3. Store it for GitHub: `gh secret set NTFY_TOPIC` → paste the same topic.

## 4. Install the review bots  *(web)*
- **Greptile** — greptile.com → connect the GitHub app to `tolera` → set review on **PR open + push**. **Claim the pre-Series-A startup discount (50% off, <$2M revenue) before the 14-day trial converts.**
- **CodeRabbit** — already configured by `.coderabbit.yaml` (advisory + summaries). Free tier is fine to start; Pro only if you later decide to A/B it against Greptile.

## 5. `@claude` fix action  *(Terminal)*
```bash
claude /install-github-app          # installs app + stores ANTHROPIC_API_KEY
```
Keep the committed `.github/workflows/claude.yml` — it's **pinned to Sonnet** (`model: claude-sonnet-4-6`). Don't let the installer drop that line.

## 6. API spend cap (backstop)  *(Anthropic console)*
console.anthropic.com → Billing → **set a monthly spend limit** (e.g. $50). The loop builds on your subscription, so the only metered spend is the Sonnet fix action (~$0.20–0.40/PR) — the cap is just insurance.

## 7. Branch protection + auto-merge  *(Terminal, run once)*
Follow `build-plan/GITHUB-SETUP.md §3`, then:
```bash
gh repo edit OWNER/tolera --enable-auto-merge
```
Required checks = **0 approvals** + CI (`backend`) + `greptile` + the `golden`/`tax`/`property`/`rls` fixture jobs. **Add each check only after it has run once** (they don't exist until M0.1+ wires real code) — otherwise PRs block on a check that never reports.

## 8. Turn on the self-resuming loop  *(Terminal — do this LAST, after M0.1 exists)*
The loop script ships with a **SAFETY STOP** so it can't run before you've read it.
1. Open `scripts/autobuild-loop.sh`, read it, and **delete the SAFETY STOP block** when ready.
2. Edit `scripts/com.tolera.autobuild.plist`: set the real repo path and your `NTFY_TOPIC` (and `AUTOBUILD_MODEL` — `opus` default, `sonnet` for mechanical milestones).
3. Install the launchd agent:
   ```bash
   cp scripts/com.tolera.autobuild.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.tolera.autobuild.plist
   ```
   It re-runs every 5h15m, self-resuming after each 5-hour usage reset; the lockfile prevents overlap.
   Stop anytime: `launchctl unload ~/Library/LaunchAgents/com.tolera.autobuild.plist`.

> **Don't do step 8 until there's a real Python project (post-M0.1) and a few green fixtures.** Run the loop *manually* for one or two blocks first (`bash scripts/autobuild-loop.sh` after removing the SAFETY STOP) to watch it behave before handing it the keys on a schedule.

---

## How you'll experience it while travelling
- **Normal:** blocks build and auto-merge silently. A **morning digest** push lists what merged overnight and flags any money/tax/schema/auth diffs.
- **Needs you:** a phone push with the question, the recommended answer, and the doc citation. Reply via Remote Control (or SSH/tmux). The loop parked that one block and kept going on others; it resumes when you answer.
- **Limit hit:** the `rate_limit`/notify hook pings you; the 5-hour window self-resumes via launchd. A **weekly-cap** stall waits for the weekly reset (no action helps) — consider a **Premium seat** (6.25× usage) on the build account if this bites.
- **`@claude` fixer unavailable** (API spend cap / rate limit / key error): the loop automatically falls back to the **local subscription session** to resolve review findings, retries twice, then `needs-human` + notify + park. The one case nothing helps is a **full Anthropic outage** (it disables the local fallback too, same backend) — the loop just waits and retries and the notify hook tells you it's stalled.

## Two caps worth knowing
- **Weekly usage cap** is a hard wall on the subscription — the loop sleeps until it resets.
- **API spend cap** only throttles the Sonnet fix action; the build keeps going on the subscription.

---

## What Claude already changed in the repo
- `.github/workflows/claude.yml` — `@claude` action pinned to **Sonnet**.
- `.github/workflows/digest.yml` — **new** morning digest (needs `NTFY_TOPIC` secret).
- `scripts/autobuild-loop.sh`, `scripts/resume-after-reset.sh`, `scripts/com.tolera.autobuild.plist` — **new** loop + self-resume (loop has a SAFETY STOP).
- `REVIEW.md`, `.coderabbit.yaml`, `CONTRIBUTING.md §3`, `build-plan/GITHUB-SETUP.md §3/§6/§7`, `build-plan/WORKFLOW-PLAYBOOK.html §3/§6` — review stack → **Greptile + CodeRabbit + full bot-only merge**.
- `build-plan/autonomous-setup/claude-config/*` — **staged** `.claude` files for step 1.
- `build-plan/REVIEW-WORKFLOW-PROPOSAL.md` — the design rationale behind all of this.
