# M0 — Foundations (Scaffold + Tenancy + Auth + Seed)

**Spec:** [#milestones](../docs/spec/Bid-Factory-Build-Spec.html#milestones) (M0 row) · **Exit criteria (authoritative):** two seeded orgs; login works; role-gated API smoke tests pass.

**Goal.** Stand up the monorepo and prove the one property the whole product is built on — **org-scoped data isolation, authenticated, end-to-end** — before any feature exists. This is the architectural tracer bullet. Everything in M0 either *connects a layer* or *proves the spine*; no domain features yet.

**Golden thread:** M0 builds the rails the thread later runs on; it does not yet carry the thread (that closes in M1).

**Read first:** [#stack](../docs/spec/Bid-Factory-Build-Spec.html#stack), [#devworkflow](../docs/spec/Bid-Factory-Build-Spec.html#devworkflow), `CLAUDE.md` §5 (conventions) — and obey them from the first commit.

**Prerequisite:** [M0.0 — Provisioning & Accounts](M0.0-prerequisites.md) must be complete (accounts, secrets, DNS) before M0.1 — it consumes the Clerk keys + `DATABASE_URL`/`REDIS_URL` on first run. The long-lead items there (Anthropic DPA, Google OAuth verification) should be *started* even earlier since they gate M3.

**Sequence:** M0.1 → M0.2 → M0.3 → (M0.4 ⟂ M0.5). M0.3 defines the permission model the rest of the app enforces; M0.4 and M0.5 can run in parallel branches once the spine (M0.2) is green.

---

### M0.1 — Walking skeleton   `[M]`
- **Vertical slice:** a request travels React → FastAPI → Postgres and back, in Docker, with CI green — the layers are connected and deployable before anything is built on them.
- **Scope (in):** monorepo (FastAPI backend + React/TypeScript/Vite frontend); Docker Compose (app, Postgres, Redis); Alembic baseline migration; one health endpoint that round-trips a DB read; one e2e smoke test; GitHub Actions CI running `pytest` + `mypy` + `ruff`; the seed `CLAUDE.md` run-commands wired (`docker compose up`, `pytest`).
- **Scope (out):** auth, any domain table, any UI beyond a mounted shell placeholder (→ M0.2/M0.4).
- **Depends on:** — (first block)
- **Implements (spec):** [#stack](../docs/spec/Bid-Factory-Build-Spec.html#stack), [#devworkflow](../docs/spec/Bid-Factory-Build-Spec.html#devworkflow)
- **Internals (provenance):** ../docs/spec/folded-subspecs/DB-SCHEMA.sql (DB conventions: UUID PKs, snake_case, ISO-8601 UTC, JSONB)
- **Acceptance criteria:** `docker compose up` brings the stack up clean; `GET /healthz` returns a value read from Postgres; CI is green on the PR (pytest + mypy + ruff all pass).
- **Test plan (fixtures):** e2e smoke test hits `/healthz` through the running stack and asserts the DB-sourced payload; CI runs it on every PR thereafter.
- **Golden-thread role:** none yet — establishes the harness the thread's CI test will live in.

### M0.2 — Tenancy + auth spine (the tracer bullet)   `[L]`
- **Vertical slice:** an authenticated user in org A reads an org-scoped endpoint and **provably cannot see org B's data** — RLS-enforced, with a wrong-role request rejected.
- **Scope (in):** Clerk session auth wired (password-primary + magic-link fallback + Google/Microsoft SSO available, per DECISIONS); `Org`, `User`, and **`UserOrgMembership`** (M:N, role-per-membership) tables; active-org as a session claim; Postgres **RLS** policies keyed on `org_id`; one trivial org-scoped entity + one authed `GET` endpoint; RBAC enforced at the API layer; the **cross-org denial test** and a role-gated smoke test. Two orgs seeded *inline in the test fixture* (minimal) to run the denial check.
- **Scope (out):** the reusable seed framework (→ M0.5); org-switcher UI (→ M0.4); real domain entities (→ M1).
- **Depends on:** M0.1
- **Implements (spec):** [#auth](../docs/spec/Bid-Factory-Build-Spec.html#auth), [#authz](../docs/spec/Bid-Factory-Build-Spec.html#authz), [#db-schema](../docs/spec/Bid-Factory-Build-Spec.html#db-schema)
- **Internals (provenance):** ../docs/spec/folded-subspecs/DB-SCHEMA.sql (RLS + org-scoping), ../docs/spec/folded-subspecs/DOMAIN-MODEL.md
- **KB:** [KB: setting-up-your-organization](https://help.paperlessparts.com/s/article/setting-up-your-organization)
- **Decisions:** ../docs/decisions/DECISIONS.md → *Multi-organization users (E4-a)* (membership model + active-org claim required from M0, not retrofitted); *Login type / auth flow* (password-primary, magic-link fallback, SSO via Clerk)
- **Acceptance criteria:** a user authenticated into org A receives **zero** rows of org B's data on the org-scoped endpoint; an unauthenticated request is rejected; a user lacking the required role is rejected at the API layer; RLS is enforced at the DB (not just the app).
- **Test plan (fixtures):** automated cross-org denial test (seed org A + org B, assert isolation both directions) + a role-gated smoke test; both run in CI. This pair is the M0 exit gate.
- **Golden-thread role:** none yet — but every later block inherits this block's pattern (`org_id` + RLS + authed route + isolation test).

### M0.3 — Authorization policy module (roles + permission matrix)   `[M]`
- **Vertical slice:** one policy module declares the canonical **roles + permission matrix**, and a single `require(permission)` guard enforces it on an endpoint — proven by a matrix test (role × action → allow/deny) and an endpoint that denies an unauthorized role.
- **Scope (in):** the canonical **role set** as an enum (from `#personas` — e.g. Admin, Manager, Estimator, Salesperson, Viewer; confirm against the spec); the **permission matrix** (role → allowed actions across quote / part / pricing / order / settings) as **one declarative module — the single source of truth**; a `require(permission, resource?)` API dependency every endpoint calls; the **5 review stages** (Sales / Engineering / Material-Pricing / Outside-Service / Executive Review) modeled as **workflow-assignee states on the quote item, NOT roles**; every check evaluated within the **active-org** membership role (M0.2).
- **Scope (out):** the User-Management *screen* (invite / assign / deactivate UI) → **M5.12**; per-feature enforcement points — they accrete as features land and *call* this module (e.g. M3.8's rule-edit/quote-edit gating); field-/object-level ABAC beyond role + org (post-pilot).
- **Depends on:** M0.2
- **Implements (spec):** [#authz](../docs/spec/Bid-Factory-Build-Spec.html#authz), [#personas](../docs/spec/Bid-Factory-Build-Spec.html#personas)
- **Internals (provenance):** ../docs/spec/folded-subspecs/USER-STORIES-AND-WORKFLOWS.md (#states-roles — role choreography + the review stages as states)
- **Decisions:** ../docs/decisions/DECISIONS.md → *Multi-organization users (E4-a)* (a permission is always evaluated against the **active-org** membership's role)
- **Acceptance criteria:** the permission matrix lives in **one module** (no scattered role-string checks); `require(...)` **denies** an unauthorized role and **allows** an authorized one at the API layer; review stages are quote-item states, not roles; changing the matrix in one place changes enforcement everywhere; every check is org-scoped.
- **Test plan (fixtures):** a declarative **role × action matrix test** asserted against the module + an endpoint test proving `require()` enforces it; roles drawn from the M0.5 seed.
- **Golden-thread role:** none directly — it is the **single definition every later block's permission checks consume** (orthogonality: one policy, many call-sites; the M6.9 GDPR/dual-use audit verifies *this* module, not 70 scattered checks).

### M0.4 — App shell + navigation + i18n + BRAND   `[M]`  ⟂
- **Vertical slice:** an authenticated user sees the app shell with working nav, can toggle language (en/de), and every product string comes from the parameterised `BRAND` config — no hardcoded "Tolera".
- **Scope (in):** React app shell + primary nav (per `#shell`); en/de i18n plumbing (catalog loader, locale switch, de-DE default for the pilot); the `BRAND` config object (product name, domains, logo, colours) consumed everywhere customer-facing; an **org-switcher stub** in the account menu (wired to the active-org claim from M0.2); dark theme per the design system.
- **Scope (out):** populated dashboard (→ M6 redesign), settings detail screens (→ M5), real notifications (→ M3).
- **Depends on:** M0.2
- **Implements (spec):** [#shell](../docs/spec/Bid-Factory-Build-Spec.html#shell), [#ui-system](../docs/spec/Bid-Factory-Build-Spec.html#ui-system)
- **Internals (provenance):** ../docs/spec/folded-subspecs/USER-STORIES-AND-WORKFLOWS.md (#states-roles — role-aware nav)
- **KB:** [KB: company-settings](https://help.paperlessparts.com/s/article/company-settings)
- **Decisions:** ../docs/decisions/DECISIONS.md → *Product name and domain* (Tolera; `BRAND` parameterised from day one, no hardcoded product strings); *Multi-organization users (E4-a)* (org switcher + cross-org notifications labelled)
- **Acceptance criteria:** shell renders only when authed; nav reflects the user's role; language toggle re-renders strings; changing `BRAND` config changes all product-name/logo/colour usages with zero code edits; org switcher lists the user's memberships.
- **Test plan (fixtures):** component/integration test asserts a `BRAND`-config change propagates and the locale toggle swaps catalogs; seeded multi-membership user shows >1 org in the switcher.
- **Golden-thread role:** none — UI frame the thread is later viewed through.

### M0.5 — Seed framework + two orgs   `[M]`  ⟂
- **Vertical slice:** one idempotent command provisions a clean org (incl. the pilot `fechner`) with users and role-per-membership, re-runnable without duplication — the foundation every test and first-run relies on.
- **Scope (in):** the idempotent `seed.json` runner (upsert keyed on org + natural key); **Part 1 §1 only** — org + identity + users + `user_org_memberships`; two orgs seeded (incl. `fechner`, `slug=fechner`, `country=DE`, `currency=EUR`, `locale=de-DE`, ingest `fechner@rfq.tolera.eu`); the `docker compose exec app python -m scripts.seed_demo` command from `CLAUDE.md`.
- **Scope (out):** catalog content — materials, the 54-op library, processes, interrogation profiles, pricing defaults, rules, email templates (→ M1.12, which extends this framework); the golden-fixtures *harness* (→ M1.13).
- **Depends on:** M0.2, M0.3 (role enum — so seeded memberships use real roles)
- **Implements (spec):** [#onboarding](../docs/spec/Bid-Factory-Build-Spec.html#onboarding), [#quick-setup](../docs/spec/Bid-Factory-Build-Spec.html#quick-setup)
- **Internals (provenance):** ../docs/fixtures/SEED-AND-FIXTURES.md (Part 1 §1), ../docs/fixtures/seed.skeleton.json
- **KB:** [KB: setting-up-your-organization](https://help.paperlessparts.com/s/article/setting-up-your-organization)
- **Decisions:** ../docs/decisions/DECISIONS.md → *Pilot customer org slug for RFQ ingest* (`fechner` / `fechner@rfq.tolera.eu`)
- **Acceptance criteria:** running the seed twice yields the same state (idempotent); two orgs exist; a seeded user can log in (satisfies the M0 exit "login" + "two seeded orgs"); roles are per-membership.
- **Test plan (fixtures):** test seeds, re-seeds, asserts no duplication and that both orgs + their memberships exist; a seeded user authenticates and the cross-org denial test (M0.2) passes against the seeded pair.
- **Golden-thread role:** none yet — provides the clean org the golden-thread fixture is seeded into from M1.13 on.

---

**M0 done when:** the cross-org denial + role-gated smoke tests pass (M0.2), the **authz policy matrix lives in one module** (M0.3), the seed yields two orgs and login works (M0.5), the shell renders branded + localized (M0.4), and CI is green (M0.1). That is the spec's M0 exit criteria, met.
