## What & why
<!-- One or two sentences. -->
Block: <!-- e.g. M1.7 -->
Closes #

## Milestone / golden thread
- Milestone:
- [ ] Golden-thread test still green (or N/A this block)

## How to test — so a reviewer can *click*, not *read*
<!-- Exact steps + the fixture/command that proves it. A teammate should be able to verify the BEHAVIOUR
     without reading the diff line by line. This is our main safety net. -->
1.
Fixture / command that proves done:

## Tier-1 self-check (author ticks before requesting review)
- [ ] Money = integer minor units + explicit currency (no floats)
- [ ] New tables/queries are org-scoped (RLS); no cross-org reads
- [ ] Schema change has a reversible Alembic migration (no manual DDL)
- [ ] No secrets / customer PII / CAD contents in logs or errors
- [ ] Lens/AI output is suggestion-only (never auto-fed into Kalk)
- [ ] Metric units only (mm / kg / deg)

## Review status
- [ ] CI green (ruff · mypy · pytest · eval-suite)
- [ ] CodeRabbit + Claude review findings addressed (🔴 resolved)
- [ ] A human teammate approved (required — bots don't approve)

## Follow-ups / OPEN items
<!-- Anything deferred → add an OPEN: entry to DECISIONS.md and link it here. Never guess on irreversible things. -->
