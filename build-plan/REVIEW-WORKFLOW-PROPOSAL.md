# Cheaper code-review workflow — proposal

**Status:** proposal (not yet adopted). Recommendation only — no repo files changed yet.
**Date:** 2026-06-26 · **Author:** drafted for review
**Decision needed:** approve the target stack, then I wire it into the playbook + config.

---

## The problem

One layer in the current four-layer review stack is the cost driver: **Anthropic hosted Code Review** (`GITHUB-SETUP.md §7`), at **~$15–25 per review**, gated to a Team/Enterprise plan. It was set to *"After every push,"* so a single PR that takes three pushes is three billed reviews. At our cadence that compounds fast:

| Volume assumption | Reviews/mo | Anthropic Code Review cost |
|---|---|---|
| ~60 PRs, 1 review each | 60 | ~$900–1,500 |
| ~60 PRs, ~2.5 pushes each ("after every push") | ~150 | **~$2,250–3,750** |

Everything *else* in the stack is already cheap or free — CodeRabbit CLI (free), in-session `/code-review` (your existing Claude usage), `@claude` triage (metered API). So the fix is surgical: **replace that one PR-bot layer**, keep the rest.

---

## Recommendation: split the two tools by layer (don't double-pay)

You now have **both Greptile and CodeRabbit**. The temptation is to run both as full PR reviewers — but that doubles cost *and* produces duplicate, conflicting comments that `@claude` then has to reconcile. The cheaper, less noisy design gives each tool the lane where it's strongest and either free or flat-rate:

| Layer | Tool | When | Cost |
|---|---|---|---|
| 1. Local gut-check (pre-commit) | **CodeRabbit CLI** | In the Claude Code loop, before a PR exists | **Free** |
| 2. In-session diff review | **Claude `/code-review`** | Block looks done, before PR | Existing Claude usage |
| 3. **PR deep review (the replacement)** | **Greptile** | On PR open / push | **$30/seat/mo, 50 reviews incl., then $1** |
| 4. PR summary (optional, free) | **CodeRabbit free** | On PR open | **Free** (summaries only) |
| 5. Auto-fix findings | `@claude address findings` | After bots comment | Metered API (use sparingly) |
| 6. Human gate ✋ | Teammate + Code Owner | Every block | — |

**Why Greptile for layer 3:** it indexes the *whole repo*, so it catches the cross-file issues that matter most here — a query missing `org_id` / RLS, a money value typed as float, an AI value leaking into Kalk costing — not just within-diff style. Pricing is flat and predictable ($30/seat including 50 reviews ≈ ~42 PRs/dev/mo, comfortably above our one-block-one-PR rate), with **$1/review** overage and **50% off for pre-Series-A startups under $2M revenue**.

**Why keep CodeRabbit as CLI + free summaries, not a second paid PR bot:** the CLI is free, runs inside the Claude Code loop, and catches issues *before* the PR — the cheapest place to catch them. CodeRabbit's free tier also posts a PR summary, which is a useful free complement to Greptile's deep review. Paying for CodeRabbit Pro's inline PR bot *on top of* Greptile is redundant for a team this size.

So the answer to "maybe both?" is **yes — both, but each in its free/flat lane:** CodeRabbit local + free summaries, Greptile as the single deep PR reviewer.

---

## Cost comparison (2–3 devs)

| Stack | Monthly cost | Notes |
|---|---|---|
| **Current** (Anthropic Code Review on PRs) | **~$900–3,750** | Scales with pushes; unpredictable |
| **Recommended** (Greptile PR + CodeRabbit free + CLI) | **~$45–90** | $30/seat × 2–3, or ~$15/seat with startup discount; 50 reviews/seat included |
| Fully-free fallback (see below) | **~$0 + tokens** | No dedicated PR bot; `@claude` Action reviews via API |

That's roughly a **10–40× reduction** with no loss of the whole-codebase review you were paying Anthropic for.

---

## Alternative if you want to spend even less

Drop dedicated PR bots entirely and let the **existing `@claude` GitHub Action** (`.github/workflows/claude.yml`) run the PR review, driven by `REVIEW.md`. It already has the credentials and reads your tier-1 rules. Cost becomes ordinary metered API tokens (cents-to-low-dollars per review) instead of a per-review surcharge. Trade-off: it reviews mostly the diff with less persistent whole-repo indexing than Greptile, and you'd be tuning a prompt rather than using a purpose-built reviewer. **Good as a stopgap; Greptile is the better fit given the team can't review by eye and the codebase is tenancy/money-critical.**

---

## What changes if you approve (the wiring, for later)

Small, contained edits — nothing structural:

- **`GITHUB-SETUP.md §7`** — replace the "enable Anthropic hosted Code Review" step with "install the Greptile GitHub App on `tolera`; set review on PR open + push." Add Greptile config (`greptile.json` / dashboard rules) pointing at `REVIEW.md`.
- **`WORKFLOW-PLAYBOOK.html §6`** — swap the "Code Review bot · ~$15–25/review" row for "Greptile · $30/seat flat"; update the stack diagram/legend copy.
- **`REVIEW.md`** — change "injected into every AI reviewer (Anthropic Code Review + CodeRabbit)" to "(Greptile + CodeRabbit)"; the rules themselves carry over unchanged.
- **`CONTRIBUTING.md §3`** — replace the "Anthropic Code Review" table row with Greptile.
- **`.coderabbit.yaml`** — decide CodeRabbit's PR role: keep `auto_review` on for free summaries, or set it CLI-only. Path-instruction rules stay.
- **`@claude` triage** — unchanged; it now reads Greptile's + CodeRabbit's comments.

Human gate, CODEOWNERS, CI, and Playwright demo tests are all untouched — they remain the real acceptance oracle.

---

---

# Part 2 — Unattended "travel mode": automate the review → merge → next-block loop

Goal: keep the project building while you're on the go — bots verify, auto-fix, and merge; a fresh session picks up the next block automatically; you only step in for the things that genuinely need you, and you can do that from your phone.

## Gate line: full bot-only merge (chosen) — with a machine-truth safety net

**Decision:** no human approval gate anywhere. Every block auto-merges on green checks, including money/tax/schema/auth.

This overrides the original tier-1 rule (`CLAUDE.md §9`/§5: *"the Code Owner signs off money/tax/schema/auth — never bot-only"*) — note it in `DECISIONS.md` as a dated entry so the change of policy is recorded. The residual risk is real and specific: the failures bots miss are the *"plausible but wrong for your domain"* ones (a misread tax rule, a subtly wrong rounding), and the independent verifier reads the **same docs** the builder did, so the two can share a blind spot. So we don't rely on AI judgment to protect the financial core — we make the gate **machine truth** and keep the human informed *after*, not in the way:

- **Tests are the real gate on money/tax/schema/auth.** Require the golden fixtures + a dedicated **tax/rounding fixture** + **Hypothesis property tests** (and a `testcontainers` RLS test for tenancy) to pass. The AI cannot verify itself past a red fixture — correctness is proven by execution, not opinion.
- **Reversibility.** Migrations are reversible by rule and everything lands on `develop`, not production; a bad merge is revertable. Customer-facing gates still come at deploy (M5/M6).
- **Notify-after, not approve-before.** A **morning digest** push lists what auto-merged overnight, flagging any money/tax/schema/auth diffs, so you can revert async without ever being a blocker.

## How each piece actually works (grounded in current behaviour)

**1. Session-limit answer — keep it on the subscription, notify + resume from your phone (no API key).**
The build loop runs as a **long-running local Claude Code session** on your always-on Mac (auto-accept mode), billed to your Pro/Max **subscription**. When it hits a limit it pauses; you get told and you resume from your phone:

- **Notify:** Claude Code's **`rate_limit` hook** fires the moment a usage limit is hit — route it to a phone push (native Claude mobile push, or ntfy/Slack) so a silent lockout becomes an alert with the reset time. Native **mobile push** (Claude Code v2.1.110+, Apr 2026) also pings you when the loop finishes a block or needs a decision; enable in `/config` → *"Push when Claude decides"* + *"Push when actions required."*
- **Resume:** open the session in the Claude mobile app via **Remote Control** and send "continue."
- **Two hard limits to accept:** (a) a notification/phone tap **cannot grant usage** — you can only resume *after* the window resets. The rolling **5-hour** window clears on its own (fine); the **weekly cap is a wall** — when you hit it the loop sleeps until the weekly reset and no phone action helps. So expect the loop to **stall periodically**; that's the price of staying off the API. (b) The loop **shares one pool** with your personal Claude chats while travelling — they consume each other.
- **Lowest-babysitting upgrade:** a small **launchd/cron wrapper** on the Mac re-runs `claude --continue` shortly after each 5-hour reset so the loop **self-resumes** without a manual tap. Then notifications are just FYI and Remote Control is reserved for answering grills.
- **Prereqs (Team plan):** Remote Control **is available on Team** (research preview) but is **off by default — your Team admin enables the "Remote Control" toggle in Claude Code admin settings**. Native push needs an active Remote Control session. The **Mac must stay awake** (`caffeinate`) and reachable.
- **Plan-agnostic fallback (works without Remote Control):** `tmux` + Tailscale SSH + **ntfy**. Route the `rate_limit`/Stop/Notification hooks to the **ntfy phone app** for alerts, and attach the live `tmux` session from a phone SSH app (Blink/Termius) to answer a grill or resume directly. This gives you full phone control even if Remote Control is disabled or drops.
- **Hybrid config (chosen): subscription build + cheap metered `@claude` fix.** Keep the local subscription session for build / self-grill / verify, but keep the **`@claude` action ON for fix-findings**, pinned to **Sonnet 4.6**. This is cheap — **~$0.20–0.40 per PR** on Sonnet (≈ **under $5 for 50 PRs**), and it is **not** the $15–25 hosted Code Review bot we dropped (that was a flat per-review service; this is per-token). The win: fix-work runs on a **separate metered budget**, so it no longer eats your subscription pool — **fewer stalls, more unattended throughput** while travelling. Guardrails: pin **Sonnet not Opus** (Opus ≈ $0.90–1.80/run), enable **prompt caching** (90% off repeated context), set a **monthly API spend cap** (~$50), fire **only on findings**.
  - *Fully off-API alternative:* delete `claude.yml` and have the local session read PR comments (`gh pr view --comments`) and push fixes itself — $0 API, but build + review + fix then share the same subscription caps, so the loop **stalls more often**. Use this only if you want literally zero metered spend.

**2. Auto-merge is GitHub's job, not the bot's.**
The Claude action **cannot self-approve/merge** a PR (Anthropic's deliberate safety boundary). But GitHub **native auto-merge** merges a PR the moment its **required status checks** go green — no human approval needed if branch protection requires **0 approvals**. So the merge is done by GitHub automation: the `@claude` action (Sonnet) pushes review fixes → CI + Greptile go green → auto-merge fires. To enable: branch protection on `develop` with required checks = `backend` (CI: ruff/mypy/pytest) + Greptile, approvals = 0, then `gh pr merge --auto --squash` on each PR. (`/security-review` runs inside the local loop before the PR, not as an API-billed GitHub check.)

**3. Each CI run is a fresh context with "auto mode" built in.**
You don't need to manage `/clear` — every Action run starts at context 0 by definition and runs headless (non-interactive = auto-accept). An **orchestrator workflow** picks the next block: on merge to `develop`, select the lowest-numbered open block issue whose `Depends on` are all merged, then dispatch a build run for it. This is the documented "issue-to-merge loop" / continuous-Claude pattern.

**4. Two footguns to wire around (both well-documented):**
- **Infinite re-trigger:** the build commits trigger the workflow that triggers another build… Guard with an `if` that excludes Claude's own branches (e.g. `!startsWith(head_branch, 'claude/')`).
- **API rate-limit self-DOS:** Claude tends to write tight `gh run view` polling loops that burn the 5,000 req/hr GitHub limit in under an hour. Use `workflow_run` triggers (event-driven) or a `sleep` between polls — never a bare `until … done`.

**5. Keep the grill — but self-answered and auto-accepted (non-blocking).**
The grill stays, because it forces scope and edge-cases into the open and leaves a written record. It's just made non-blocking: at the start of each block the agent runs the grill **on itself**, and for each question proposes a **recommended answer grounded in the docs** (spec anchor / KB slug / demo / `DECISIONS.md`) with a confidence, then **auto-accepts** and proceeds. The full Q&A is committed to the branch/PR so you can audit every assumption async.
- **Auto-accept only when** the answer is doc-backed, or the choice is reversible / low-stakes (§6 rule 3 — note the assumption inline and move on).
- **When unsure, reverify before deciding (§6 rule 4 — verify before you ask).** Don't guess, don't ping yet: do **one deeper pass** down the precedence ladder (DECISIONS → spec → folded sub-spec → analysis → KB → demo/fixture), ideally via a read-only fan-out sub-agent across the whole doc/KB set. If it resolves → auto-accept + log. If still unresolved, split by reversibility (next two bullets). Bound it to **one** reverify pass so it can't loop on your budget.
- **Escalate (notify you) when** — after reverify — the question is still unsettled **and** expensive to reverse: schema, money, tax, auth, the domain model (§6 rule 1). That's a block-and-log `OPEN:` → **Remote Control** push to your phone (Team admin enables the toggle; tmux+SSH+ntfy is the fallback). Auto-accepting a *guessed* tax or schema answer is the one move that can quietly cost real money.
- **Proceed with a noted assumption when** — after reverify — it's still unsettled but reversible / low-stakes; log the assumption to the PR and move on.
  - The notification is **answerable in one tap**: it carries the question, the agent's *recommended* answer, the options, and the doc citation it's stuck on.
  - The loop **doesn't stall** — it parks that block as `needs-answer` and continues building the next independent block; the parked one resumes when you reply.
- **After build, an independent verifier sub-agent** (fresh context; sees only the docs + the diff, not the builder's reasoning) confirms the implementation matches plan + KB behaviour + demo/fixture. Grill aligns before; verify confirms after — and independence stops the builder's own misreading from passing its own check.

> Where this is weakest: blocks **without** a promoted demo/fixture verify against prose spec only, so those are the likeliest to escalate. Blocks **with** a demo + fixture are machine-checkable and run fully unattended.

**6. Stop-on-red, never merge-on-red.** If checks stay red after N self-fix attempts (say 2), the loop **stops that block**, opens an issue tagged `needs-human`, and moves to the next independent block. Nothing red ever merges. Cap blocks-per-night so a bad night can't churn the whole backlog.

## Target unattended pipeline (recommended shape)

| Stage | Mechanism | Runs on | Your involvement |
|---|---|---|---|
| Pick next block | Local loop picks lowest-numbered block whose deps are merged | Local session (subscription) | none |
| Self-grill (auto-accept) | Agent grills itself; doc-grounded answers auto-accepted + logged to PR | Local session (subscription) | none (unsure → reverify; still unsettled + irreversible → escalate) |
| Build (TDD) | Local Claude Code session, auto-accept, fresh context per block; fixture is the target | Local session (subscription) | none |
| Verify vs docs | **Independent** sub-agent checks the diff against spec + KB + demo/fixture (fresh context) | Local session (subscription) | none |
| Limit hit | `rate_limit` hook → phone push; cron `--continue` after reset (or you resume) | Phone / cron | ~10 sec or auto |
| Review | Greptile + CodeRabbit on PR + CI; `/code-review` + `/security-review` run in the local session | GitHub + local (subscription) | none |
| Fix findings | `@claude` action (Sonnet, ~$0.30/PR) reads CodeRabbit/Greptile comments + pushes fixes | GitHub (metered API) | none |
| Merge | GitHub **auto-merge** on green checks — all paths, no approval | GitHub | none |
| Money/tax/schema/auth | Same auto-merge, gated on **machine tests** (golden + tax/rounding + property + RLS fixtures); **after-merge digest** | GitHub | none (notify only) |
| Escalate (rare) | block-and-log `OPEN:` (docs can't resolve) → Remote Control push | Phone | only when docs can't resolve |
| Next block | Local loop continues after merge | Local session (subscription) | none |

## Tool-status notes for this plan

- **Greptile is on a 14-day trial** — perfect to pilot the autonomous gate now; budget a paid seat (~$30, or ~$15 with the startup discount) before it lapses or the loop loses its deep reviewer.
- **Reviewers vs fixer are different roles.** *Review* (the required-check gate) = **Greptile + CodeRabbit** (their own SaaS, not Anthropic API), plus local `/code-review` + `/security-review`. *Fixing* the findings = the **`@claude` action**, pinned to **Sonnet** (~$0.20–0.40/PR metered — cheap, and not the $15–25 hosted bot). No hosted Claude *review* bot. Note CodeRabbit's free tier is summaries + CLI only — full inline PR review needs Pro; decide one-bot vs A/B per the earlier section.
- The loop runs on your **Team subscription** (no API key), so throughput is capped by the 5-hour/weekly limits and stalls until reset — the `rate_limit` hook + ntfy/Remote Control keep you informed and let you resume. Remote Control works on Team once an **admin enables the toggle**; otherwise the tmux+SSH+ntfy stack covers you.

## Concrete next actions to stand this up

1. **Gate line = full bot-only merge (decided).** No approval gate on any path. Record the policy change in `DECISIONS.md`; the money/tax/schema/auth safety net is machine tests + reversibility + after-merge digest (not a human tap).
2. In `GITHUB-SETUP.md`: set `develop` branch protection to **0 approvals + required checks** (CI + Greptile); enable repo-level **"Allow auto-merge."** Keep the `@claude` action (`claude.yml`) for fix-findings, **pinned to Sonnet**, with a monthly API **spend cap** (~$50) + prompt caching.
3. Stand up the **local autonomous loop**: a long-running Claude Code session on the always-on Mac in auto-accept mode that runs the per-block loop and continues to the next block on merge. Keep the Mac awake (`caffeinate`). Per-block: **self-grill with doc-grounded auto-accept** (escalate only irreversible + ambiguous), build, then an **independent verifier sub-agent** (fresh context; docs + diff only) against spec + KB + demo/fixture before review.
4. Wire **notifications + resume**: ask your **Team admin to enable the Remote Control toggle** (then enable push in `/config`), and/or set up the **tmux + Tailscale SSH + ntfy** stack; add a **`rate_limit` hook** routing to phone push; add a **launchd/cron wrapper** that runs `claude --continue` ~15 min after each 5-hour reset so the loop self-resumes.
5. Extend `ship.md` / the build command to finish with `gh pr merge --auto --squash`; add the `needs-human` stop path (red after N tries) and make the **golden + tax/rounding + property + RLS fixtures required checks** so money/tax/schema/auth can't merge without passing them. Add the **morning digest** of overnight merges.
6. Confirm the **hybrid config**: subscription build/grill/verify + cheap metered `@claude` (Sonnet) for fix-findings; Greptile (flat) + CodeRabbit (free) for review. (Fully off-API remains a fallback if you ever want zero metered spend.)

> Reality check: this is essentially bringing forward the playbook's own **loop ⑥ ("autonomous, M6+, optional")** to now. It's very doable, but it was deliberately scheduled late because it wants a mature test suite under it. Piloting it on the safe (non-CODEOWNERS) blocks first is the prudent on-ramp.

---

## Open questions for you

1. **Gate line** — full bot-only merge of everything, or auto-merge everything *except* the money/tax/schema/auth paths (recommended)? This is the load-bearing decision.
2. **Remote Control** — can your **Team admin enable the Remote Control toggle** (Claude Code admin settings)? If not, we use the tmux + Tailscale SSH + ntfy stack for phone notify/control instead.
3. **Greptile discount** — are you eligible for the pre-Series-A startup 50% off (<$2M revenue)? Worth claiming before the trial converts.

---

### Sources

- [Greptile pricing 2026 (costbench)](https://costbench.com/software/ai-code-review/greptile/)
- [Greptile per-review pricing change (Agent Wars)](https://www.agent-wars.com/news/2026-05-01-greptile-per-review-pricing)
- [Greptile 2026 review — $30/mo, 82% bug catch (DEV)](https://dev.to/jovan_chan_9500711396d4e6/greptile-review-2026-82-bug-catch-rate-the-1review-trap-and-who-should-pay-30month-4jao)
- [CodeRabbit pricing 2026 (CheckThat.ai)](https://checkthat.ai/brands/coderabbit/pricing)
- [CodeRabbit plans — free CLI/IDE + summaries (docs)](https://docs.coderabbit.ai/management/plans)
- [Claude Code GitHub Actions (docs)](https://code.claude.com/docs/en/github-actions) · [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action)
- [Issue-to-merge loop; bot can't self-merge (Saulius)](https://saulius.io/blog/claude-code-github-native-agent-issue-to-merge-loop)
- [continuous-claude — autonomous PR/merge loop](https://github.com/AnandChowdhary/continuous-claude)
- [Claude Code usage limits — 5-hour/weekly, API vs subscription (support)](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work)
- [GitHub auto-merge (docs)](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/automatically-merging-a-pull-request)
- [Claude Code Remote Control — Max-only research preview (docs)](https://code.claude.com/docs/en/remote-control)
- [Claude Code hooks incl. `rate_limit` (docs)](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code mobile push notifications v2.1.110+ (claudcod)](https://claudcod.com/blog/claude-code-push-notifications/)
- [claude-push — ntfy.sh phone notifications for Claude Code](https://github.com/coa00/claude-push)
- [Control Claude Code from your phone — native, Tailscale, tmux (explainx)](https://www.explainx.ai/blog/claude-code-mobile-remote-control-phone-guide-2026)
- [Claude Code from the beach — mosh + tmux + ntfy (rogs)](https://rogs.me/2026/02/claude-code-from-the-beach-my-remote-coding-setup-with-mosh-tmux-and-ntfy/)
- [tap-to-tmux — phone notifications when an agent needs attention](https://github.com/flavio87/tap-to-tmux)
