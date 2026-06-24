# DECISIONS.md
# Tolera — Ambiguity Log

**Purpose:** When Claude Code (or any developer) encounters a genuine ambiguity not resolved by `Bid-Factory-Build-Spec.html`, add an entry here. Do not guess — block and add an entry. Benjamin reviews and resolves entries before the next build session.

**Format:**
```
## [YYYY-MM-DD] Short description
**Status:** OPEN | RESOLVED
**Question:** What exactly is unclear?
**Options considered:** ...
**Decision:** (fill in when resolved)
**Affects:** Which milestone / module
```

---

## Pre-seeded open items (resolve before or during build)

---

## [2026-06-14] Product name and domain
**Status:** RESOLVED  
**Question:** "Bid Factory" is a working title only. The product needs a real name before domain registration, Mailgun EU domain verification, Clerk OAuth redirect URIs, email from-addresses, and PDF/UI branding can be finalised.  
**Decision:** **Tolera** — domain **tolera.eu**, app at **app.tolera.eu**, RFQ ingest at **rfq.tolera.eu**. `BRAND` config object must be parameterised from day one — no hardcoded product name strings in code.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M0 (branding config), Mailgun setup, Clerk setup, all customer-facing strings.

---

## [2026-06-14] Google OAuth security review timeline
**Status:** RESOLVED  
**Question:** Gmail OAuth `gmail.readonly` scope triggers a Google security review (2–3 weeks). Users see a security warning screen until approved.  
**Decision:** Ship Gmail connect behind the warning screen for the pilot. Submit the review on day one of infrastructure setup. Do not block M3 on review approval.  
**Affects:** M3 (email threading). Google app registration must be submitted before build starts.

---

## [2026-06-14] Spatial / HOOPS licensing timeline
**Status:** RESOLVED  
**Question:** Spatial licensing for native SLDPRT import and advanced feature recognition is in procurement.  
**Decision:** Build entirely on OCCT (pythonocc) for v1. Spatial swaps in post-pilot when licensing is confirmed. `GeometryService` abstraction must require zero changes above the service layer on swap.  
**Affects:** M4 (geometry). Document Spatial-upgradeable capabilities in `GEOMETRY.md`.

---

## [2026-06-14] Würth API access
**Status:** RESOLVED  
**Question:** `WürthMaterialPricingAdapter` requires API credentials not yet obtained.  
**Decision:** Build adapter against a fixture response (documented JSON schema). Real credentials slot in without code changes. Do not block M6 on Würth procurement.  
**Affects:** M6 (differentiators).

---

## [2026-06-14] Pilot customer org slug for RFQ ingest
**Status:** RESOLVED  
**Question:** The email ingest route is `{org-slug}@rfq.tolera.eu`. What is the pilot customer's org slug?  
**Decision:** Pilot org slug = **fechner**. Ingest address: **fechner@rfq.tolera.eu**. Seed their org with slug `fechner` in M0 fixtures.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M3 (email ingest), M0 (org seed).

---

## [2026-06-14] Margin math for mixed markup + margin pricing items
**Status:** RESOLVED  
**Question:** Margin contribution formula — verify `cost × pct/(1−pct)`.  
**Decision:** Confirmed. Formula is `cost × pct/(1−pct)` — verified against Paperless Parts pricing documentation (`Margin % = (Selling Price − Cost) / Selling Price × 100` rearranged to `Selling Price = Cost / (1−pct)`, profit = `cost × pct/(1−pct)`). Build M1 with this formula. Add a margin-type fixture case to the M1 golden-test suite once Benjamin supplies a test case with known cost + output price.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M1 (pricing engine). High priority — incorrect margin math breaks every quote.

---

## [2026-06-14] German translation strings
**Status:** RESOLVED  
**Question:** Who does native German review, and when?  
**Decision:** Use Claude-generated German strings throughout the build. Fechner (pilot customer, native German speakers) will review all UI strings and provide feedback before pilot go-live. Formal review happens between pilot start and first paying customer.  
**Resolved:** 2026-06-19 (grill-me session)  
**Affects:** M5 (de-DE catalog). Non-blocking for pilot.

---

## [2026-06-14] SOLIDWORKS connector target surface
**Status:** RESOLVED  
**Question:** The CAD connector spec lists SOLIDWORKS as a fast-follow after Fusion. Target surface (PDM vs 3DEXPERIENCE vs desktop add-in) is still open.  
**Options considered:** Desktop add-in (most common for SME shops); PDM (larger shops); 3DEXPERIENCE (enterprise).  
**Decision:** **Deferred post-pilot, with the desktop add-in as the default target.** When built, target the SOLIDWORKS **desktop add-in** (most common for SME DACH shops like Fechner); revisit PDM/3DEXPERIENCE only if a real customer requires it. Do not build until confirmed by customer signal during/after the pilot.  
**Resolved:** 2026-06-21  
**Affects:** Post-v1.

---

## [2026-06-14] Belgian locale (nl-BE vs fr-BE)
**Status:** RESOLVED  
**Question:** When Belgian locale ships, primary language must be decided (Dutch / French / bilingual).  
**Decision:** **Dropped from the roadmap.** Tolera targets DACH (DE/AT/CH) only for the foreseeable future; Belgium (nl-BE/fr-BE) is out of scope and removed from the post-pilot backlog. Revisit only if clear, sustained demand appears — at which point default to bilingual nl-BE + fr-BE with a language picker.  
**Resolved:** 2026-06-21  
**Affects:** Out of scope (was Post-v1).

---

## [2026-06-14] CRM conflict resolution granularity
**Status:** RESOLVED  
**Question:** When HubSpot and Tolera have conflicting data for the same Account or Contact, what wins?  
**Decision:** Tolera-always-wins for v1 (simplest; avoids merge logic). Add field-level conflict resolution as a post-pilot HubSpot adapter upgrade.  
**Affects:** M6 (HubSpot adapter).

---

## [2026-06-14] Quote PDF visual design
**Status:** RESOLVED  
**Question:** WeasyPrint quote PDF template needs an approved layout before M5 implementation.  
**Decision:** **Design folded into the M5 build block** — no separate pre-M5 design session and no starter template up front. The M5 builder designs *and* implements the WeasyPrint quote-PDF template as part of M5, working from the digital-quote spec section. Fixed constraint (unchanged): the PDF is **fully white-label** (org logo, brand colours, no Tolera branding visible to the customer). Supersedes the earlier "design session at M4" note.  
**Resolved:** 2026-06-21 — white-label confirmed 2026-06-19; layout ownership moved into M5.  
**Affects:** M5 (quote PDF output) — now self-contained in the M5 block, no longer a separate pre-M5 blocker.

---

## [2026-06-19] AI assistant name
**Status:** RESOLVED  
**Question:** What is Tolera's name for the AI extraction/assistant layer (was "Wingman" in early spec)?  
**Decision:** **Lens**. Purple signal colour. AI Governor pattern (55% opacity until accepted). All spec references updated.  
**Affects:** All milestones. UI copy throughout.

---

## [2026-06-19] Pricing formula language name
**Status:** RESOLVED  
**Question:** What is Tolera's name for the formula DSL (was "P3L" / "Paperless Parts Pricing Language")?  
**Decision:** **Kalk**. Python-based, AST-sandboxed. Three contexts: pricing formulas, operation generation, operation cost formulas. All spec references updated.  
**Affects:** M1 (pricing engine), M2 (operation library), all Kalk editor UI.

---

## [2026-06-19] Partner integration names
**Status:** RESOLVED  
**Question:** What are Tolera's names for the partner integration slots (was TechMate / PEMConnect)?  
**Decision:** Advisory chat partner → **Tolera Advisor**. Fastener sourcing partner → **Tolera Source**. Both mocked in v1. All spec references updated.  
**Affects:** M6 (integrations), Part Viewer UI.

---

## [2026-06-19] Login type / auth flow
**Status:** RESOLVED  
**Question:** Is email login magic-link (passwordless) or password-first?  
**Decision:** **Password-primary, magic-link fallback.** Clerk also provides Google SSO and Microsoft SSO (via Clerk's OAuth providers). Passkey (WebAuthn/FIDO2) also available via Clerk. Spec updated on auth table.  
**Affects:** M0 (auth setup), Clerk configuration.

---

## [2026-06-19] Fixture packages
**Status:** RESOLVED (pending delivery)  
**Question:** When will 5–10 anonymised Fechner RFQ fixture packages be available for golden-test suite?  
**Decision:** Benjamin has access to the packages. Target delivery: Monday 2026-06-23. Build M1 golden-test suite structure now; slot fixtures in on delivery.  
**Affects:** M1 (golden tests), M3 (email ingest tests).

---

## [2026-06-19] Multi-organization users (E4-a)
**Status:** RESOLVED
**Question:** Should one user be able to belong to multiple orgs and switch between them (distinct from multi-tenancy)?
**Decision:** **In v1.** Build a `UserOrgMembership` (User⋈Org M:N, role per membership), active-org as session state (Clerk claim), an org switcher in the top-bar account menu, and cross-org notifications (labeled, switch-on-select). Membership model required from M0 so it isn't retrofitted into auth. Not exercised at the (single-org) Fechner pilot but must exist in the schema. See `E4-Behavioral-Gaps.md` §E4-a.
**Affects:** M0 (auth/session, data model), App Shell, Notifications.

## [2026-06-19] Pricing-config-change policy (E4-d)
**Status:** RESOLVED
**Question:** When pricing config (operations, Kalk, materials) changes, what happens to existing draft quotes / revisions?
**Decision:** **Freeze + manual refresh** (Paperless Parts model). Existing drafts/revisions keep pricing; only new quotes reflect config changes. Provide `Regenerate Operations` (no overrides), `Refresh Pricing` (single), `Bulk Refresh Pricing` (multi-select), with manual post-refresh cleanup. See `E4-Behavioral-Gaps.md` §E4-d.
**Affects:** M1 (pricing engine), Quote Detail (Process actions), quote lifecycle.

## [2026-06-19] Analytics scope (E4-k)
**Status:** RESOLVED
**Question:** Ship analytics as a stub, a fixed dashboard, or the full query-builder?
**Decision:** **Full query-builder** — a BI semantic layer of measures + dimensions across ~20 entities, time/filters, user dashboards + query editor, seeded with the 12-tile default dashboard. Replicate only the working fields (omit KB-flagged broken/deprecated ones); Segments are out (non-functional). Consider a semantic-layer lib over the Postgres warehouse. See `E4-Behavioral-Gaps.md` §E4-k. Replaces the prior "Analytics tab = stub" note.
**Affects:** New analytics milestone (sizeable build), data warehouse.

## [2026-06-19] E4 post-pilot deferrals (E4-e/f/g)
**Status:** RESOLVED
**Question:** Are MBD/PMI viewing, the on-prem managed connector, and MSSQL direct-DB import in v1?
**Decision:** **Post-pilot.** MBD/PMI needs Spatial-grade extraction (v1 OCCT can't); managed connector + MSSQL import are covered for v1 by adapters + SFTP. Keep viewer toggle / adapter interfaces as stubs; build later. See `E4-Behavioral-Gaps.md` post-pilot section.
**Affects:** Post-v1 (geometry/PMI, integrations).

## [2026-06-23] Local config / secrets loader — Infisical → `.env` + pydantic-settings
**Status:** RESOLVED
**Question:** The spec's seed CLAUDE.md (`#devworkflow`) says secrets load "from environment via **Infisical** (self-hosted on Hetzner)." The newer M0.0 runbook instead standardises on a gitignored **`.env`** (dev) + **GitHub Actions secrets** (CI) + **Kamal secrets** (prod). Which governs the build?
**Decision:** **Follow M0.0 — `.env` + `pydantic-settings` now; GitHub Actions + Kamal secrets for CI/prod; Infisical dropped for v1.** Real environment variables override `.env`, so Docker Compose / CI inject config without editing files. The committed `.env.example` is the env contract (names only). Revisit a dedicated secrets manager post-pilot only if operational need appears. Supersedes the spec's Infisical wording (this tier-1 entry wins per `CLAUDE.md` §2).
**Resolved:** 2026-06-23 (M0.1 grill)
**Affects:** M0.1 (config module), every later block's settings, CI, deploy.

## [2026-06-23] Python runtime version — 3.12
**Status:** RESOLVED
**Question:** The `uv init` scaffold pinned Python `>=3.10`; the spec (`#stack`, `#devworkflow`) specifies Python **3.12**.
**Decision:** **Pin 3.12** — `.python-version` = `3.12`, `requires-python = ">=3.12,<3.13"`, ruff/mypy target `py312`, Docker `python:3.12-slim` — so dev matches prod. Matches the spec; not a deviation, recorded for traceability.
**Resolved:** 2026-06-23 (M0.1 grill)
**Affects:** M0.1 (pyproject, Docker, CI).

## [2026-06-24] Membership role cardinality — multi-role per membership (M0.2)
**Status:** RESOLVED
**Question:** Does a `UserOrgMembership` carry exactly one role or many? Tier conflict: tier-1 E4-a says *"role per membership"* (reads singular) and the folded `DB-SCHEMA.sql` has `role membership_role NOT NULL`; tier-2 spec `#authz` says *"users may hold multiple roles; effective permissions = union"* and the `#auth` invite modal is a multi-select (`roles TEXT[]`). Schema-shape, expensive to migrate later (touches every permission check).
**Decision:** **Multi-role from the start.** `user_org_membership.roles membership_role[]` — `NOT NULL`, enforced non-empty (CHECK `cardinality(roles) > 0`). M0.3's `require()` computes effective permissions as the **union** across the array. Resolves the conflict in favour of the explicit spec model; "role per membership" (E4-a) is read as "a role set attached to each membership," not "exactly one." The single `role` column in the folded schema is superseded (folded schema is frozen provenance; tier-2 spec + this tier-1 entry win per `CLAUDE.md` §2).
**Resolved:** 2026-06-24 (M0.2 grill)
**Affects:** M0.2 (schema: membership table), M0.3 (permission matrix = union over roles), M5.12 (invite/role-edit UI).

## [2026-06-24] RLS enforcement mechanism + DB role split (M0.2)
**Status:** RESOLVED
**Question:** How is org-scoped Row-Level Security actually enforced *at the DB*? The folded `DB-SCHEMA.sql` only *notes* "enforce RLS by org_id" — no `CREATE POLICY` DDL, no session-variable mechanism, and M0.1 ships a single `tolera` DB role that owns the schema. Postgres RLS is **bypassed for a table's owner / superusers** unless forced, so naïve policies would be a silent no-op (and the cross-org test could pass for the wrong reason). M0.2 must *define* the pattern every later block inherits.
**Decision:** **Two-role split + forced RLS.** (1) Migrations/DDL run as the **owner/admin** role; (2) the **application connects as a dedicated restricted role** (`NOBYPASSRLS`, not the table owner). (3) Every tenant-scoped table gets `ENABLE` **and** `FORCE ROW LEVEL SECURITY`. (4) Org context is carried per-request as a transaction-local GUC: `SET LOCAL app.current_org_id = :org`, with policies keyed on `current_setting('app.current_org_id', true)::uuid` (`missing_ok = true` so an unset GUC yields zero rows rather than erroring). (5) The org-scoped DB session is transaction-scoped and the GUC is set after auth resolves the active org; connections are reset on pool check-in. This is the **inherited tenancy pattern** for all later blocks. Requires a docker-compose + connection-config change to provision the two roles.
**Resolved:** 2026-06-24 (M0.2 grill)
**Affects:** M0.2 (RLS policies, DB roles, docker-compose, db session), every later org-scoped table.

## [2026-06-24] Org identity model — Clerk native Organizations + webhook mirror (M0.2)
**Status:** RESOLVED
**Question:** DECISIONS (Login type / E4-a) says *"active-org as session state (Clerk claim)."* Do we use **Clerk's native Organizations** feature (Clerk orgs ↔ our `organization`, Clerk membership + active-org in the session) and mirror to our DB, or model orgs entirely in our DB and carry a self-managed `active_org_id` custom claim with Clerk doing identity only?
**Decision:** **Clerk native Organizations.** Clerk is the source of user identity, org membership existence, and the **active-org session claim**; memberships are **mirrored into our tables via Clerk webhooks** (`organizationMembership.created/updated/deleted`). The **app role is authored in our DB** (`user_org_membership.roles`) — our domain roles (estimator/salesperson/outside-service/…) are richer than Clerk's member/admin, so Clerk org roles are kept minimal and not the authority for app permissions. The active-org claim is verified server-side and drives the RLS GUC. Matches the spec `#auth` webhook-sync build notes.
**Resolved:** 2026-06-24 (M0.2 grill)
**Affects:** M0.2 (auth wiring, active-org claim, webhook endpoint stub), M0.4 (org switcher), M5.12 (invite → Clerk invitation).

## [2026-06-24] Authorization role set — adopt the 7 spec personas + retain `viewer` (M0.3)
**Status:** RESOLVED
**Question:** Three sources disagree on the canonical role enum. M0.2 shipped `membership_role = {admin, estimator, salesperson, viewer}` (a 4-value starter); the build-plan M0.3 example lists "Admin, Manager, Estimator, Salesperson, Viewer" (5, *"confirm against the spec"*); the authoritative spec `#authz`/`#personas` matrix defines **7** roles — Admin, Exec/Manager, Sales, Estimator, Engineer, Material/Purchasing, Outside-Service — and has **no Viewer**. The enum is schema (a Postgres type), expensive to reshape later and touched by every permission check.
**Decision:** **Adopt the 7 spec personas and keep `viewer` as an 8th, explicitly-non-spec read-only role.** Final `membership_role` = `{admin, manager, salesperson, estimator, engineer, material_purchasing, outside_service, viewer}`. Existing M0.2 spellings (`admin/estimator/salesperson/viewer`) are kept verbatim to avoid a PG enum *rename* (painful, breaks the M0.2 tenancy test); the migration only **adds** the four new values (`manager`, `engineer`, `material_purchasing`, `outside_service`). `viewer` is retained (not in the spec) because dropping a PG enum value requires a full type-rebuild and would break M0.2's `test_tenancy`; it is granted **`view_all` only**. The extension migration is **reversible** (CLAUDE.md §5 — reversible migrations only): `upgrade` adds the values online (`ALTER TYPE … ADD VALUE`, no table rewrite); `downgrade` rebuilds the type to the M0.2 set and re-casts the one dependent column (`user_org_membership.roles`) through `text[]`, raising by design if any membership still uses an M0.3 role (block the rollback rather than lose data). *(Tightened from an initial no-op-downgrade plan during M0.3 code review, to honor the reversible-migration convention.)*
**Resolved:** 2026-06-24 (M0.3 grill)
**Affects:** M0.3 (role enum, migration, permission matrix), M0.5 (seeded memberships use real roles), M5.12 (role-edit UI).

## [2026-06-24] Permission matrix — role-level only; owner/assigned/annotate refinements deferred (M0.3)
**Status:** RESOLVED
**Question:** The spec `#authz` matrix has cells that are **not** pure role→allow: Delete = *"owner"* for Sales/Estimator (only quotes they own); Create/edit = *"view + annotate"* for Engineer/Material/Outside (read + comment, not edit costing); review-step update is *per-assigned-stage*. M0.3 has no `QuoteItem`/ownership/`WorkflowStep` to evaluate object-level conditions against, and the build-plan defers "field-/object-level ABAC beyond role + org (post-pilot)." How permissive should M0.3 be in the meantime?
**Decision:** **Under-grant, never over-grant.** The matrix is **role → capability boolean** only. (1) `quote_delete` is granted to **admin + manager only** — Sales/Estimator get *no* delete in M0.3 (granting it role-wide would let them delete *any* quote, strictly more permissive than the spec's owner-only); owner-scoped delete is added when ownership exists (M1/M5). (2) "view + annotate" is modelled as a real `quote_annotate` capability (held by all 7 spec roles) distinct from `quote_edit` (admin/manager/sales/estimator), so Engineer/Material/Outside are correctly read-plus-annotate, not edit. (3) `review_step_update` enforcement is **deferred to M1** (no quote item/stage yet); granted coarsely to admin/manager, the granular per-stage/assigned mapping lands with `WorkflowStep`. Object-/field-level ABAC remains post-pilot.
**Resolved:** 2026-06-24 (M0.3 grill)
**Affects:** M0.3 (permission matrix), M1 (QuoteItem ownership + WorkflowStep → owner/stage refinement), post-pilot (ABAC).

## [2026-06-24] Manager may finalize/send/convert — intentional divergence from spec `#authz` (M0.3)
**Status:** RESOLVED
**Question:** The spec `#authz` matrix marks Finalize/Send/Convert as `—*` for Exec/Manager: an Exec gets it **only** if also granted a Sales or Estimator role (footnote: *"kept off the Exec preset to mirror the Sales + Estimators + Admin decision"*). Should Tolera keep that exclusion?
**Decision:** **Diverge from the spec — grant `quote_finalize` to `manager` directly** (Benjamin's call). A manager no longer needs a union'd sales/estimator role to send/convert/edit-orders. This is a deliberate override recorded here so it is not later read as a transcription error; per `CLAUDE.md` §2 a tier-1 `DECISIONS.md` entry overrides the spec. Net effect: `admin` and `manager` hold an identical permission set in M0.3 (the two diverge only if a later capability distinguishes them).
**Resolved:** 2026-06-24 (M0.3 grill)
**Affects:** M0.3 (permission matrix — manager row).

## [2026-06-24] Primary navigation pattern — sidebar wins over top-bar tabs (M0.4)
**Status:** RESOLVED
**Question:** The spec is internally inconsistent on the global nav surface. `#ui-system` (confirmed 2026-06-13, with `BidFactory-LiveMock.html` as the reference implementation) states the **dark sidebar** is "the primary navigation surface" (216/56 px, `[` collapse toggle, `localStorage` persistence). `#shell` instead describes a persistent **dark top bar with horizontal nav tabs**. Same spec tier — which is authoritative?
**Decision:** **Sidebar.** The collapsible dark sidebar is the primary nav surface (per the newer, explicitly *confirmed* `#ui-system` + its live reference mock); `#shell`'s top-bar-tabs layout is superseded. The **destinations** still come from `#shell` (Dashboard, Parts, Quotes, Orders, Contacts, Configure, Analytics). Global search lives in the sidebar top row; the account menu + org-switcher live in the sidebar's bottom account area (see next entry). Resolves a tier-2-internal conflict per CLAUDE.md §2 ("more specific / more recent confirmed wins").
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (app shell layout), and every screen rendered inside the shell thereafter.

## [2026-06-24] Org-switcher location — sidebar account area (amends E4-a) (M0.4)
**Status:** RESOLVED
**Question:** The "Multi-organization users (E4-a)" decision (2026-06-19) places the org-switcher in the **top-bar account menu**. M0.4 adopts a sidebar-primary layout with **no top bar** (previous entry). Where does the switcher live, and how functional is it in M0.4?
**Decision:** The org-switcher lives in the **sidebar bottom account area** (alongside the user/account menu) — a wording amendment to E4-a, consistent with the confirmed sidebar design system; the substance of E4-a (switcher exists in v1, active-org as session state, cross-org notifications labelled) is unchanged. **M0.4 ships a stub:** it lists the user's memberships (from `/api/me`) and highlights the active org resolved from the JWT claim; the actual *switch* action (token re-mint via Clerk's native Organizations) is **deferred to M5.12**, where the membership-table → session-token sync is built. This satisfies the M0.4 acceptance criterion ("switcher lists the user's memberships") without depending on un-built sync.
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (org-switcher stub), M5.12 (real switching + membership/token sync).

## [2026-06-24] Default colour mode — light, both token sets shipped (M0.4)
**Status:** RESOLVED
**Question:** `#ui-system` states *"Active defaults: `data-theme=claude` · `data-mode=light`"*, but the build-plan M0.4 scope line says *"dark theme per the design system."* Which is the v1 default colour mode? (A spec-vs-build-plan conflict; per CLAUDE.md §2 the spec outranks the build-plan execution map.)
**Decision:** **Default `data-mode="light"`** per the spec's explicit active default. Both the full light *and* dark token sets (CSS custom properties, the warm-dark palette `#ui-system` specifies) are shipped, with a persisted toggle (the build-plan's "dark theme" is honoured as *shipped & selectable*, not as the default). Reversible — it is a single default value, no schema impact.
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (theming / design tokens).

## [2026-06-24] `/api/me` session-bootstrap contract + permission-gated nav (M0.4)
**Status:** RESOLVED
**Question:** The app shell needs the current user, their active org (name/locale/currency/country), their cross-org memberships (for the switcher), and what nav/actions to show. No such endpoint exists. What is the contract, and does nav gate on roles or capabilities?
**Decision:** Add **`GET /api/me`** (authenticated) returning `{ user, active_org, memberships[], effective_permissions[], roles[] }` — `active_org` carries locale/currency/country/slug/name; `roles`/`effective_permissions` are derived from the **active membership row** (the DB, which `user_org_membership` makes authoritative) via `app.authz.permissions_for(...)` (the M0.3 single source of truth) — **not** the JWT `principal.roles` cache, so a briefly-stale claim can't make the payload overstate access or self-contradict `memberships[*].roles`. The frontend **gates nav/actions on capabilities** (e.g. *Configure* requires `config_edit`), never re-encoding the role→capability matrix client-side. (API-layer `require()` still keys on the claim in M0.3; M5.12 keeps claim↔membership in sync.)
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (`/api/me`, permission-gated nav), all later UI that conditions on permissions.

## [2026-06-24] `/api/me` cross-org identity read under RLS — SECURITY DEFINER function (M0.4)
**Status:** RESOLVED
**Question:** The M0.2 migration deliberately grants the restricted `tolera_app` role **no access to `app_user`** (global PII, no org scope) and applies **FORCE RLS** keyed to the active org on `organization`/`user_org_membership`. `/api/me` must read the caller's *own* identity (name/email) and *cross-org* memberships — neither reachable through the normal request path. The migration's own note defers this: *"a later block that must surface users will mediate via … a scoped view."* How does M0.4 read it safely? (DB-schema + security — block-and-log §6, never guessed.)
**Decision:** A **`SECURITY DEFINER` SQL function** `app_current_identity() → jsonb` (migration `0004`), owned by a dedicated **`BYPASSRLS`, `NOLOGIN`** role `tolera_identity` (a plain table-owner would still be subject to *FORCE* RLS), with a pinned `search_path`, returning `{user, memberships[]}` for the caller identified by the **transaction-local `app.current_user_id` GUC** (stamped by `app.deps.get_session` from the verified principal). The function takes **no argument** — binding to the GUC rather than a parameter means the *database* enforces "read only yourself"; there is no user-id argument to steer at another user. `tolera_app` gets `EXECUTE` only (revoked from `PUBLIC`). **RLS on every table is left untouched** (smallest blast radius); the one privileged path is a single audited function. The `tolera_identity` role follows the M0.2 `tolera_app` precedent (ensure-exists in-migration; attributes provisioned by infra in prod). Rejected: per-user GUC + RLS policy widening (broadens the visibility model app-wide) and a privileged BYPASSRLS connection in the request path (a code slip leaks everything; contradicts the fail-closed design).
**Resolved:** 2026-06-24 (M0.4 grill)
**Affects:** M0.4 (`0004` migration, `/api/me`), any later user-surfacing read (reuses this function/pattern).

---

*Add new entries above this line as ambiguities arise during the build.*
