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

## [2026-06-24] Seed framework — Clerk provisioning scope (M0.5)
**Status:** RESOLVED
**Question:** Spec `#onboarding` says the seed script "calls `Clerk.organizations.createMembership()` for the admin user (Clerk fires the invite email)". But `SEED-AND-FIXTURES.md` reuses the *same* idempotent runner for tests (every test run seeds a clean org), where hitting the Clerk API is neither idempotent nor desirable. Should the M0.5 seed call the Clerk API, or only write DB rows?
**Options considered:** (A) DB-only seed — create `Organization`/`AppUser`/`UserOrgMembership` rows idempotently; `clerk_user_id`/`clerk_org_id` left nullable; "login works" proven in tests via the existing `authed()` Principal injection + RLS isolation; real Clerk linkage (createMembership/invite + claim metadata) deferred to the established Clerk→DB webhook mirror (M0.2 stub → M5.12) or a one-off `--with-clerk` side-effect run for the real pilot. (B) Call the Clerk API now (create org + invite admin + set `tolera_*` metadata), mocked/skipped in tests.
**Decision:** **(A) DB-only.** The seed is the DB source of truth; Clerk identity linkage is a separate, deferred side-effect handled by the already-decided *Clerk native Organizations + webhook mirror* path (2026-06-24, M0.2). The spec's "seed calls Clerk" remains the eventual provisioning behaviour for a *real* new org, layered on later — it does not belong in the idempotent, test-reused M0.5 runner. The M0 exit "login works" is satisfied at the test level (a seeded principal authenticates against the seeded pair + cross-org denial passes); real Clerk login is wired when the webhook/`--with-clerk` path lands.
**Resolved:** 2026-06-24 (M0.5 grill)
**Affects:** M0.5 (seed framework), M0.2/M5.12 (Clerk webhook + user-management). Spec-vs-practicality tension logged here per block-and-log (§6).

## [2026-06-24] M0.5 seed scope — §1 only, migration-free
**Status:** RESOLVED
**Question:** `seed.skeleton.json`'s `organization` block carries `default_tolerance_class`, `export_regime`, `brand`, and `rfq_ingest`, but none of these columns exist on the `Organization` model (M0.2). Does M0.5 add them?
**Decision:** **No — M0.5 ships zero new migration.** Scope is `SEED-AND-FIXTURES.md` Part 1 §1 only (org identity + users + `user_org_memberships`), seeding only columns that already exist (`slug`/`name`/`country`/`currency`/`locale`). `rfq_ingest` is **derived** from the slug (`{slug}@rfq.tolera.eu`) per the 2026-06-14 pilot-slug decision, not stored. `default_tolerance_class` (→ M1/geometry), `brand`/white-label (→ M0.4), and `export_regime` (→ M6 export control) are each deferred to their consuming block, which adds the column via its own reversible Alembic migration. The remaining `seed.skeleton.json` sections (materials, 54-op library, processes, interrogation profiles, pricing, rules, templates) are out of M0.5 → extend the framework in M1.12.
**Resolved:** 2026-06-24 (M0.5 grill)
**Affects:** M0.5 (seed scope), M0.4 (brand column), M1 (tolerance/catalog), M6 (export regime).

## [2026-06-24] Second seed org identity (M0.5)
**Status:** RESOLVED
**Question:** The build-plan seeds "two orgs (incl. `fechner`)" to drive the cross-org denial test, but only specifies fechner. What is org #2?
**Decision:** A minimal second org: **`currency=EUR`, `locale=en`** (English UI, to exercise the non-`de` path) — distinct from fechner's `de-DE`. `Organization.country` is a hard enum (`DE`/`AT`/`CH` only, no "EN"), so country is set to **`DE`** (a valid enum value; the org merely prefers English UI). Slug/name are demo data (reversible). One global `AppUser` may hold memberships in both orgs (E4-a) so the framework can later feed M0.4's org-switcher test.
**Resolved:** 2026-06-24 (M0.5 grill)
**Affects:** M0.5 (seed), M0.4 (org-switcher test fixture).

## [2026-06-25] Contact↔Account cardinality — `contact.account_id` nullable (M1.1)
**Status:** RESOLVED
**Question:** `DB-SCHEMA.sql` declares `contact.account_id` **nullable** (`REFERENCES account(id)`), but `DOMAIN-MODEL.md` §3 says a Contact "belongs to **exactly one** Account." Which governs the column M1.1 creates? (Schema/FK — expensive to reverse, block-and-log §6.)
**Decision:** **Nullable** — the canonical DDL wins on the column. The domain "exactly one account" is the *happy path* the CRUD UI always follows (a contact is created under an account), but the column stays nullable because RFQ intake (M3) will create account-less contacts before an account exists, and **loosening** a NOT NULL later would need a data backfill while **tightening** is cheap. The list/detail UI treats an account-less contact as an edge state, not the norm.
**Resolved:** 2026-06-25 (M1.1 grill)
**Affects:** M1.1 (contact model/migration), M3 (RFQ-origin contacts), any quote↔contact wiring (M1.4: "every quote requires a contact").

## [2026-06-25] Soft-delete × unique email — partial unique index on `contact` (M1.1)
**Status:** RESOLVED
**Question:** `DB-SCHEMA.sql` puts `UNIQUE (org_id, email)` on `contact`, but contacts are soft-deleted (`deleted_at`). A plain unique constraint would let an **archived** contact's email permanently block re-creating a contact with that address. Is that intended? (Schema/constraint — cheap now, painful after data lands.)
**Decision:** Replace the table-level unique with a **partial unique index** `UNIQUE (org_id, email) WHERE deleted_at IS NULL`, so email is unique only among *live* contacts and an archived email frees up for reuse. This is the general soft-delete + natural-key pattern; later org-scoped tables with a soft-deletable natural key reuse it. (Account name is intentionally **not** unique — multiple sites/legal entities may share a name — so it needs no such index.)
**Resolved:** 2026-06-25 (M1.1 grill)
**Affects:** M1.1 (contact migration), the soft-delete convention for later natural-key tables.

## [2026-06-25] Archive semantics + cascade for Account/Contact (M1.1)
**Status:** RESOLVED
**Question:** The M1.1 slice says "archive an Account and its Contacts." What does *archive* mean concretely, what happens to an archived account's contacts, and is hard delete in scope? (Data-lifecycle — defines what "archive" means for every downstream reader.)
**Decision:** **Archive = soft-delete** (set `deleted_at`); it is **reversible via Restore** (clear `deleted_at`). Default list endpoints exclude archived rows; a direct `GET /{id}` still returns an archived row (so the detail/restore UI works); `?include_archived=true` opts a list back in. **Archiving an account does *not* mutate its contacts' `deleted_at`** — instead the **cross-account** contact list (`GET /api/contacts`) excludes contacts **whose account is archived** (they disappear from general browsing with the account, but a Restore brings them back intact, and no child rows are silently rewritten). The **per-account** list (`GET /api/accounts/{id}/contacts`, the account-detail Contacts tab) still shows them even when the account is archived, since you've navigated into that specific account to review/restore it. **No hard delete in v1** (no `DELETE` route — and the restricted DB role is granted only `SELECT/INSERT/UPDATE`, not `DELETE`). Archive/restore are gated on `quote_delete` (the only role granted destructive-ish actions in the M0.3 matrix); create/edit on `quote_edit`.
**Resolved:** 2026-06-25 (M1.1 grill)
**Affects:** M1.1 (account/contact archive+restore endpoints, list filters), all later list/detail surfaces that read accounts/contacts, M6 CRM-sync (archive ≠ delete on the CRM side).

## [2026-06-25] Salesperson assignment must be an active member of the active org (M1.1)
**Status:** RESOLVED
**Question:** `account.salesperson_id` / `contact.salesperson_id` reference **`app_user`**, which is **global, not org-scoped** (no `org_id`, no RLS). So org RLS *cannot* stop assigning a salesperson who belongs to a different org (or to no org at all) — a cross-tenant identity leak. How is the assignment constrained? (Security/tenancy — never guessed, block-and-log §6.)
**Decision:** Guard at **two layers** (defense in depth):
1. **DB (schema):** the `salesperson_id` column carries **no direct `app_user` FK**; instead a **composite FK `(salesperson_id, org_id) → user_org_membership(user_id, org_id)`** makes "is a member of *this* org" a database invariant a cross-org reference physically cannot satisfy. (Likewise `contact.account_id` uses a composite FK to `account(org_id, id)` so a contact's account is same-org.) Identity to `app_user` is preserved transitively via the membership row.
2. **App (write path):** create/edit additionally validates that a non-null `salesperson_id` resolves to an **`active`** membership (the FK alone permits a `disabled` one) and returns the clean envelope **`422` code `invalid_salesperson`** rather than surfacing a DB error.

The check runs through the org-pinned session, so it reads only the active org's memberships. We deliberately **do not** require the assignee to hold the `salesperson` *role* — any active member is assignable (matches PP).

> Strengthened during the M1.1 CodeRabbit review (2026-06-25): the original plan kept a direct `app_user` FK + app-layer check only; the composite-FK approach makes the tenancy guarantee a DB invariant, not merely RLS/app-enforced.

**Resolved:** 2026-06-25 (M1.1 grill; FK approach strengthened in review)
**Affects:** M1.1 (account/contact schema + write validation + test), any later entity that references a `User`/account cross-row (reuse the composite-FK-to-membership pattern + active-member check).

## [2026-06-25] M1.2 file-owner model — files attach to `part`; minimal `part` stub created now (M1.2)
**Status:** RESOLVED
**Question:** What entity owns an uploaded file in M1.2? The canonical `DB-SCHEMA.sql` models `part_file.part_id → part(id)` + `part.primary_file_id`, and the spec/KB are explicit that files belong to a **Part** (PRIMARY = the part's geometry source of truth). But the M1.2 block text says "upload a file to a **quote**" / "file↔**line-item** association", and `quote`/`quote_item`/full `part` are M1.4/M1.5 — none of which M1.2 depends on (M1.2 is orthogonal, depends only on M0.2). Files can't honour "file↔part" while staying standalone unless the owner is resolved. (Schema/FK — expensive to reverse, block-and-log §6.)
**Options considered:** (a) create a **minimal `part` stub** now (only the columns `part_file` needs) and attach files to it, M1.5 extends `part`; (b) attach files to a generic/polymorphic owner and reconcile in M1.5; (c) pull `quote`/`quote_item` forward (breaks orthogonality, expands scope).
**Decision:** **(a) Minimal `part` stub.** KB + domain model confirm files are **part-level**, never line-item-level: the *Part Library* (`uploading-parts-to-your-part-library`) creates a Part by **file upload alone, no quote involved**, and the Quote-level "Quote Files" panel is a *UI aggregation* of all parts' files in a quote, not a storage layer. A Part therefore legitimately exists independently of any quote → a standalone stub is upstream-correct. M1.2 creates `part` with exactly `{id, org_id uuid NOT NULL → organization, primary_file_id uuid NULL (FK part_file, added after part_file exists), created_at, updated_at, deleted_at}` plus `part_file(part_id → part)`. The block's "upload to a quote" wording resolves to "upload to a part." M1.5 **extends** `part` (part_number, revision, is_assembly, obtain_method, BOM/Node tree, geom_hash, export_controlled…) via a forward reversible migration — no reshaping of what M1.2 lays down.
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (part stub + part_file schema), M1.5 (extends part; Component/Node/QuoteItem link the part to a quote).

## [2026-06-25] PRIMARY-per-part — `part.primary_file_id` authoritative + partial-unique enforcement (M1.2)
**Status:** RESOLVED
**Question:** The canonical schema represents the PRIMARY relationship **twice** — `part.primary_file_id` (FK) *and* `part_file.role ∈ {primary, supporting}`. Dual representation can drift; which is the source of truth, and how is "exactly one PRIMARY per part" enforced?
**Decision:** **`part.primary_file_id` is the authority**; `part_file.role` is a denormalized convenience kept in sync **within the same transaction**. One-PRIMARY-per-part is also enforced at the DB with a **partial unique index** `UNIQUE (part_id) WHERE role = 'primary'` (belt-and-braces alongside the single FK). Auto-PRIMARY on first upload uses a **file-type-tier rank** (B-Rep CAD > mesh > 2D/vector/print) matching the upstream "most geometric information wins" heuristic; ties → first uploaded. **Swap** = one transaction flipping the FK + both rows' `role`. Multi-quote/assembly swap guards (deep-copy / replace-referenced-part) are **deferred to M1.5+** (no Node/Component/multi-quote refs exist yet).
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (primary enforcement + swap), M1.5+ (multi-quote/assembly swap guards).

## [2026-06-25] Object-storage backend — S3 API via MinIO (dev/CI), tenant-scoped key scheme (M1.2)
**Status:** RESOLVED
**Question:** No object storage exists. What backend + abstraction + key layout does M1.2 build against, and how is tenant isolation enforced in storage?
**Decision:** Build against the **S3 API** (`aioboto3` / `boto3`) behind a thin storage-service seam so the provider is swappable. **Dev/CI:** add **MinIO** to docker-compose. Object keys are **tenant-scoped**: `org/<org_id>/part/<part_id>/<file_id>/<filename>` (the `org_id` prefix is defence-in-depth alongside RLS on `part_file`). Stored bytes are **raw / unmodified** (acceptance: byte-identical round-trip). **No** content-hash dedup/versioning in M1.2 (schema carries no hash column). Bucket name from config. The S3 access/secret keys live in `Settings` as plain strings, **consistent with the existing M0 pattern** (`clerk_secret_key`, the DB DSNs); they are never logged or dumped. Production provider is a separate OPEN (EU residency — below).

> **Follow-up (ship review, 2026-06-25, CodeRabbit):** secret-bearing `Settings` fields (S3 keys + the pre-existing `clerk_secret_key` / DB DSNs) should adopt Pydantic `SecretStr` **repo-wide** so an accidental `Settings` repr/`model_dump` can't expose them. Deferred from M1.2 as a cross-cutting hardening (doing it piecemeal for only the S3 fields would be inconsistent with the merged M0 convention) — track as a config-hardening task.
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (storage service, docker-compose MinIO, config), all later file-handling blocks (reuse the storage seam); a later config-hardening pass (SecretStr).

## [2026-06-25] File upload constraints + type validation — 200 MB, allow-list + magic-byte, proxy-stream (M1.2)
**Status:** RESOLVED
**Question:** What size cap, transport, and type-validation does M1.2 enforce on uploads? `MAX_UPLOAD_MB` is spec-sourced (`#viewer3d-limits` = 200) but was absent from DECISIONS.
**Decision:** **`MAX_UPLOAD_MB = 200`** (config constant) — reconciles the upstream conflict (3D viewer 250 / supported-file-types 150 / Lens ≤250) per spec `#viewer3d-limits`; recorded here as resolved. **Transport:** proxy-through-API with **streaming** to storage (never buffer 200 MB in memory); presigned direct-to-S3 is a later optimisation. **Type gate:** an **app-level allow-list constant/enum** (the `VIEWER-AND-FILE-TYPES.md` ~50-extension matrix, grouped B-Rep / mesh / 2D-vector / office-email / zip) **plus** a cheap **magic-byte sniff** for common containers (ZIP, PDF) to resist extension spoofing; full content validation belongs to interrogation (M4). Disallowed types are rejected at the edge (Pydantic v2 + the standard error envelope).
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (upload endpoint, validation, config), M4 (interrogation-grade content validation).

## [2026-06-25] File delete semantics — hard-delete blob; PRIMARY-delete blocked while supporting files remain (M1.2)
**Status:** RESOLVED
**Question:** `part_file`'s DDL has no `deleted_at` (implies hard delete) while M1.1/`part` use soft-delete; and deleting the current PRIMARY must not leave a dangling `part.primary_file_id`. What are the delete semantics?
**Decision:** **Hard-delete the blob from object storage always** (GDPR erasure), and **hard-delete the `part_file` row** (matches the DDL; cleanest erasure). **PRIMARY-delete guard:** deleting the current PRIMARY is **rejected while any supporting file remains** (force an explicit swap first); the FK is nulled only when the PRIMARY is the part's **last** file. (Rejected: auto-promote-next — it silently changes the part's geometry source of truth.) `part` itself keeps soft-delete (`deleted_at`), consistent with M1.1.

> **Implementation note (M1.2 ship review, 2026-06-25):** the blob is purged via a FastAPI `BackgroundTask` that runs *after* the DB commit (so a failed commit never deletes a referenced object). A single S3 `delete_object` is short + idempotent, so it isn't Celery-class "long work" — but a failed background delete has **no retry/dead-letter**, leaving an orphan blob. **Follow-up (post-pilot hardening):** move the orphan purge to a retried Celery task for GDPR-erasure durability; pairs naturally with the AV-scan/quarantine OPEN below.
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (delete endpoint + guard), later GDPR erasure flows + M6 hardening (Celery-backed blob purge).

## [2026-06-25] M1.2 surface scope — minimal Files panel + file-op permissions; ZIP/redaction/dedup/AV deferred (M1.2)
**Status:** RESOLVED
**Question:** How much of the rich `#partview` Files UI ships in M1.2, who may upload/delete, and which adjacent features are out?
**Decision:** **API + storage + a minimal React Files panel** in the existing shell (list, upload, set/swap PRIMARY, download, delete) — enough to demo the vertical slice; drag-drop reorder, "Download All", and explicit file ordering (no `sort_order` column) are deferred. **Permissions:** file *writes* (upload / set-primary / delete) gate on the **existing `quote_edit`** capability (admin / manager / salesperson / estimator) — managing a part's files is editing the quote's content, and reusing `quote_edit` keeps the M0.3 matrix untouched; reads need only an authenticated org session (`view_all`). The support roles (engineer / material-purchasing / outside-service) are therefore **read-only** on files — consistent with their spec "view + annotate" semantics (uploading changes the part's geometry source-of-truth, which is an edit, not an annotation). *(This refines the grill-time sketch "estimator/engineer/admin/manager" to the spec-consistent `quote_edit` set: drops engineer, adds salesperson; a dedicated `file_manage` capability for support roles can be added later if a real need appears.)* **Explicitly OUT of M1.2** (confirmed): ZIP pack-and-go *unpacking* (.zip is stored opaque, unpacked in M4); redaction logic (`is_redacted` column exists, unused — later GDPR feature); content-hash dedup/versioning; thumbnails / rendering / interrogation (M2/M4).
**Resolved:** 2026-06-25 (M1.2 grill)
**Affects:** M1.2 (Files panel, file-op capabilities), M2/M4 (rendering, ZIP unpack, interrogation), later GDPR (redaction).

## [2026-06-25] OPEN: Production object-store provider — EU data residency (M1.2)
**Status:** OPEN
**Question:** Customer CAD/print files are personal-data-bearing under GDPR and must reside in the EU. M1.2 builds against the S3 API (MinIO locally) but the **production** provider is unchosen. Candidates: **Hetzner Object Storage** (matches the Hetzner infra anchor), **Cloudflare R2** (EU jurisdiction), **AWS S3 `eu-central-1`**, **Scaleway** — differ on cost, EU-residency guarantees, and S3-API compatibility.
**Options considered:** Hetzner (cheapest, in-region, S3-compatible, smaller ecosystem); R2 (no egress fees, EU-jurisdiction toggle); S3 eu-central-1 (most mature, dearer + egress).
**Recommended default:** Hetzner Object Storage (region-aligned, S3 API, cost) unless an existing AWS footprint argues otherwise. No code impact — deploy-time config behind the storage seam.
**Affects:** M1.2 (storage config / deploy), any block that stores blobs.

## [2026-06-25] OPEN: Antivirus / malware scanning of customer uploads (M1.2)
**Status:** OPEN
**Question:** Customers (and later, external vendors via email ingest) upload arbitrary files that staff download and forward to vendors. Should uploads be AV/malware-scanned, and where (sync at upload vs async Celery post-store vs at download/forward)?
**Options considered:** ClamAV sidecar scanned async on a Celery task after store (quarantine flag on `part_file`); a cloud scanning API; or accept-risk for the pilot.
**Recommended default:** **Defer to a later hardening block** (not M1.2) but logged now: async ClamAV scan on store with a quarantine flag, blocking download/forward until clean. Revisit before email-ingest (M3) opens an untrusted upload path.
**Affects:** M3 (email ingest = untrusted uploads), M6 (hardening), `part_file` (possible future `scan_status` column).

---

*Add new entries above this line as ambiguities arise during the build.*
