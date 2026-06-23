# Tolera E2E — the demo-test harness

The 14 acceptance demos ([build-plan/DEMOS-TRACEABILITY.md](../build-plan/DEMOS-TRACEABILITY.md)) are the product's **definition of done**. This harness turns each one into an automated Playwright click-through, so the "a human clicks the demo" gate becomes a **regression test**. For a team whose human code review is light, this is the real safety net.

> The matrix lists 15 rows (A–O); the spec calls them "14" because Demo **H** is *progressive* (a grab-bag, no single fixture). It's in the registry, tagged `progressive`.

## The model: fixme → promote

Every demo starts as a `test.fixme` placeholder in `demos/demos.spec.ts` (driven by `demos/demo-registry.ts`). The suite is **green from day one** — fixme tests don't fail. As you build the milestone that makes a demo replayable, you **promote** it:

1. Remove `.fixme`.
2. `resetToSeed(request, '<scenario>')` for a deterministic start.
3. Drive the flow following `docs/reference/screenshots/Demo<ID>/` (the UI ground truth).
4. Assert against the fixture in `docs/fixtures/` (see DEMOS-TRACEABILITY → that demo).

`demos/demo-e-markups.spec.ts` is the **worked template** (Demo E, the M1 exit — the `2.160,84 €` golden). Copy its shape. The Playwright HTML report becomes a live **N / 14 scoreboard**; **M6.10 = all green** is the pilot's definition of done.

Demos light up in dependency order: **E → M1**, **C → M3**, **{A,D,G,I,J,M,N,O} → M4**, **{B,K} → M5**, **{F,L} → M6**.

## Run it

```bash
cd e2e
npm install                       # first time — commit the resulting package-lock.json
npm run install:browsers          # one-time: chromium + OS deps
cp .env.example .env              # fill from the vault (dev Clerk keys + a seeded pilot user)
npm test                          # all fixme until you promote a demo → exits green
npm run test:ui                   # interactive runner while writing a demo
npm run test:demo "Demo E"        # run one demo by title
```

Auth uses [`@clerk/testing`](https://clerk.com/docs/guides/development/testing/playwright/overview): `clerkSetup()` runs once in `global.setup.ts`, and `signInAsPilot()` (`support/auth.ts`) signs in via `clerk.signIn` with the seeded Fechner user. The browser runs **de-DE / Europe-Berlin** to match the German-first UI.

## Wiring to the app

`playwright.config.ts` has a commented `webServer` block — uncomment it once M0.1/M1 can serve the frontend + API, and point it at the real run scripts. Promoted demos also need a **test-only seed endpoint** (`/__test__/seed`, build block M0.5) that resets the demo tenant — it must be disabled in production.

## CI

`.github/workflows/e2e.yml` runs the suite on PRs touching `e2e/**` or `frontend/**`. While demos are fixme it passes without needing the app or Clerk secrets. Make it a **required check** (and add the Clerk + base-URL secrets) once the first demo is promoted.
