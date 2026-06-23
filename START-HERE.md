# START HERE — everything to do before writing code

The detail is spread across runbooks; this is the single ordered spine. Pointers to detail:
`build-plan/M0.0-prerequisites.md` (accounts/secrets/DNS) · `build-plan/GITHUB-SETUP.md` (repo + protection) ·
`CONTRIBUTING.md` (daily flow) · `build-plan/WORKFLOW-PLAYBOOK.html` (the visual workflow).

**Two rules that cut the overwhelm:**
1. **Start the slow approvals first** — the Anthropic DPA and Google verification take days-to-weeks; kick them off before anything else so they finish in the background.
2. **You can start coding M0.1 once GitHub + Clerk + a local database exist.** A pending Google review or unfinished Mailgun setup does **not** block M0.1 — those are needed later (M3 / deploy).

---

## 0 · Finish the commit  (2 min — in your own Terminal, not here)
```
cd "/Users/benjaminleahy/Documents/Claude/Projects/Bid Factory"
rm -f .git/HEAD.lock .git/index.lock
git add -A
git commit -m "chore: Claude Code workflow scaffold"
git gc --prune=now
```

## 1 · Install the tools on your Mac  (~30 min — INSTALL)
```
# Homebrew (if you don't have it)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install gh uv node            # GitHub CLI · Python toolchain · Node (for skills + e2e)
brew install --cask docker         # Docker Desktop — runs local Postgres + Redis
curl -fsSL https://cli.coderabbit.ai/install.sh | sh   # CodeRabbit CLI (free local reviews)
```
Then, inside a Claude Code session in the repo:
```
npx skills@latest add mattpocock/skills
/setup-matt-pocock-skills          # pick GitHub as the tracker
```

## 2 · Kick off the SLOW approvals TODAY  (CREATE ACCOUNT — runs in background, days-weeks)
- [ ] **Anthropic Console** account → request + sign the **DPA** (powers Lens/AI; needed for GDPR). *(M0.0 §6)*
- [ ] **Google Cloud** → configure OAuth consent screen → **submit for verification** (Gmail scope review takes weeks). *(M0.0 §7)*
- [ ] Register **`tolera.eu`** and point DNS (needed by Mailgun + Clerk). *(M0.0 §1)*

## 3 · Create the core accounts  (CREATE ACCOUNT — one focused sitting; exact order in M0.0)
- [ ] **Password vault** (1Password) first — turn on 2FA everywhere, store recovery codes.
- [ ] **GitHub** (private repo) · **Hetzner** (EU host + object storage) · **Microsoft/Entra** (Outlook OAuth) · **Clerk** (auth, EU residency) · **Mailgun** (EU region, inbound RFQ email).
- [ ] Capture **every key** into the vault as you go. *(Full step-by-step: `build-plan/M0.0-prerequisites.md`)*

## 4 · Put the repo on GitHub + connect the bots  (CONNECT — follow GITHUB-SETUP.md)
- [ ] Create the private repo, push `main` + `develop`, set branch protection (solo settings already baked in).
- [ ] Store CI secrets · `claude /install-github-app` (the `@claude` bot) · install CodeRabbit on the repo.
- [ ] *(Optional)* enable Anthropic hosted Code Review. *(All commands: `build-plan/GITHUB-SETUP.md`)*

## 5 · Wire your machine to the services  (LINK UP)
- [ ] `cp .env.example .env` → fill the keys from your vault.
- [ ] Start local **Postgres + Redis** via Docker (M0.1 needs `DATABASE_URL` + `REDIS_URL`).
- [ ] `cd e2e && npm install && npm run install:browsers` (Playwright demo tests).

## 6 · You're ready → start coding
- [ ] Open one Claude Code session and run **`/block M0.1`** — the walking skeleton (tenancy + auth spine).

---

### The absolute minimum to write your first line of M0.1 code
Tools installed (step 1) · GitHub repo created (step 4) · Clerk dev keys + local Postgres/Redis (step 5). Everything else can finish in the background.
