# E4 — Behavioral Gaps: Spec Enrichment

**Status:** Spec appendix for Tolera (Bid Factory). Resolves the E4 cluster from `KB-Coverage-Gap-Analysis.md`. **Provenance:** the KB source articles cited per item. Decisions taken 2026-06-19 (logged in `DECISIONS.md`).

## Decisions applied

| Item | Decision | In v1? |
|---|---|:--:|
| E4-a Multi-organization users | **Build in v1** | ✅ |
| E4-b Replace-referenced-part / deep copy | Spec as v1 (correctness) | ✅ |
| E4-c Dynamic lead times | Already covered by Expedite/Lead-Times — confirm nuances | ✅ (no new build) |
| E4-d Pricing-config-change | **Freeze + manual refresh** | ✅ |
| E4-h Email deliverability (SPF/DKIM/**DMARC**) | Spec as v1 (infra) | ✅ |
| E4-i Keyboard navigation | Spec as v1 (polish) | ✅ |
| E4-j Swap primary/supporting files | Spec as v1 (correctness) | ✅ |
| E4-k Analytics | **Full query-builder** | ✅ |
| E4-e MBD/PMI viewing | Post-pilot roadmap | ⬜ |
| E4-f On-prem managed connector | Post-pilot roadmap | ⬜ |
| E4-g MSSQL direct-DB import | Post-pilot roadmap | ⬜ |

---

# v1 — build now

## E4-a · Multi-organization users  `→ App Shell / {auth} / Data Model / Notifications`
**Source:** `functionality-for-multi-organizational-users`.
**Behavior:** a single user can belong to multiple orgs and move between them two ways:
1. **Switch Organization** — Account menu (top-right name) → *Switch Organization* → searchable list of the user's orgs → confirm → browser reloads into the destination org.
2. **Cross-org notifications** — the Notifications panel shows messages from *all* orgs the user belongs to (regardless of the currently-active org). Each notification carries an **org label** (the active org's is greyed); selecting a notification from another org prompts a switch.

**Spec additions**
- **Data model:** `UserOrgMembership` (User ⋈ Org many-to-many, with role per membership — ties to `{authz}`). "Active org" is session state, not a user attribute.
- **Auth/session (Clerk):** active-org claim in the session; switching reloads/re-scopes. (⚠️ Interacts with the multi-tenancy decision — every tenant-scoped query already keys on org; this just lets one identity hold several memberships.)
- **App shell:** org switcher in the top-bar account menu (searchable). Notifications panel: cross-membership query + per-item org label + switch-on-select.
- **Provisioning:** in PP this is enabled by support; for Tolera, an admin action to grant a user membership in another org.
**Acceptance:** a user in orgs A+B sees B's notifications while in A (labeled), can switch to B via the menu, and lands in B scoped correctly.
**DACH/pilot note:** Fechner is single-org, so this won't be exercised at pilot — but the membership model must exist from M0 so it isn't retrofitted into auth later.

## E4-b · Replace-referenced-part / Deep copy  `→ Data Model / Quote Detail actions / Part Library`
**Source:** `deep-copy-replace-referenced-part-faq` (+ `swap-primary-and-supporting-files`).
**Core model (load-bearing):** a **Part** holds the primary file, geometry, and BOM/assembly structure (the source of truth). A **Component** holds materials, operations, and pricing logic, and *references* a Part's data (volume, bend count, qty-per-assembly…). One Part can be referenced by **multiple** quote items (including multiple times in the same quote).
**Behavior:** when a Part is referenced by >1 quote item, **part-mutating actions are blocked** (disabled control + tooltip: *"…replace the referenced part with a new version."*). Two resolutions:
- **Replace referenced part with new version** — creates a new Part (new library entry), keeps the *same* quote item, severs the shared reference so you can edit freely. Use after copying/revising a quote or adding from the library.
- **Deep copy quote item** — creates a new Part **and** a new quote item beneath the current one (template-part workflow).
- Contrast **Duplicate quote item** — another instance that *shares* the underlying Part (no new library entry).

**Actions blocked while a Part is multiply-referenced** (spec as guard): edit part number/revision/description; edit custom part attributes; manually edit geometry; upload component file; add manual sub-assembly / manufactured / purchased component; delete component from flat BOM; delete node; switch primary file; change purchased-component reference; convert to purchased/manufactured; update node qty; move node up/down; make assembly; merge quote items as supporting files; merge quote items as components.
**Situations that create multi-reference:** copying quotes; making quote revisions; adding parts from the library; duplicating quote items.
**Spec additions:** model Part↔Component reference cardinality explicitly; the two resolution actions in the quote-item ⋮ menu; the blocked-action guard + tooltip; a "Quotes/Orders" tab on the part viewer listing every quote/order a Part is on.
**Acceptance:** attempting a blocked action on a multiply-referenced part shows the guard; "Replace referenced part" unblocks it without adding a line; "Deep copy" adds a new line + library part.

## E4-c · Dynamic lead times — *already covered; confirm nuances*  `→ Add-Ons, Lead Times & Expedite`
**Source:** `dynamic-lead-times-guide`. This is Paperless Parts' name for the **Expedite/Lead-Times** system your spec already has. No new build — just confirm these UX nuances are captured:
- Per-quote-item lead-time options = **relative "Days Faster" + % markup** (not fixed dates, not flat fees) — deliberately, because buyers sit on quotes and % scales across items.
- **Apply-to-all** from the quote top (Standard lead time + expedite options); leave Standard blank to add expedites without changing base lead time.
- **Default set** of expedite options configurable in Settings (Digital Quote → Expedite).
- Digital Quote presents options **highest-price-at-top** so longer/cheaper lead times look attractive.
**Action:** confirm `Expedite Pricing` + `Lead Times` sections reflect relative-days + %-markup + apply-to-all + settings default. (No new milestone work.)

## E4-d · Pricing-config-change policy — FREEZE + manual refresh  `→ Quote Detail (Process actions) / Workflow`
**Source:** `working-with-existing-quotes-after-an-update-to-pricing-configuration`. **Decision: freeze.**
**Behavior:** changes to pricing config (operations, Kalk formulas, materials, pricing items, discounts) **do not** affect existing draft quotes or revisions of old quotes — only quotes created *after* the change reflect it. To opt-in an existing quote, provide:
- **Regenerate Operations** (Process → Actions) — for items *without* overrides/manual ops: deletes all operations, overrides, and manual ops and repopulates from the latest process version.
- **Refresh Pricing** (single item) / **Bulk Refresh Pricing** (multi-select via the left-panel checkbox → Actions) — for items *with* overrides/manual ops: re-runs pricing while preserving overrides.
- **Post-refresh manual cleanup:** if ops/pricing items were removed/added in config, the user manually removes stale ops/pricing items and adds any newly-required pricing items.
**Spec additions:** these three actions on the Process section; the freeze rule stated in the Quote lifecycle; copy/revision inherits frozen config until refreshed.
**Acceptance:** editing a process does not change an open draft's numbers until Regenerate/Refresh is run.

## E4-h · Email deliverability — SPF + DKIM + **DMARC** + verification  `→ {email-connectivity} (outbound) / Settings`
**Source:** `improving-email-deliverability` (+ `how-do-i-whitelist-my-ip-address`). PP sends via **Amazon SES** with the customer's address in FROM; Tolera sends via **Mailgun EU** — same model.
**Spec additions (outbound email):**
- **Per-org sender/domain verification** before mail sends as the org's domain; until verified, fall back to a system FROM (PP uses `noreply@digital-quote.com` → Tolera: `noreply@<tolera-domain>`).
- DNS guidance the org's IT adds: **SPF** (include Mailgun's sending hosts in the domain TXT), **DKIM** (CNAME/TXT keys Tolera generates; PP notes a 72-hour validity window before regeneration), and **DMARC** (alignment record — *missing in current spec; add it*).
- A Settings panel showing per-org verification status + a "resend/regenerate" action; surface the verified FROM vs fallback.
**DACH note:** Mailgun **EU** region for data residency; document SPF/DKIM/DMARC setup in German for Fechner.
**Acceptance:** an unverified org's quote email sends from the fallback FROM; a verified org's sends as its own domain and passes SPF/DKIM/DMARC.

## E4-i · Keyboard navigation (Build-a-Quote / Part Estimating table)  `→ Part Estimating View (interaction patterns)`
**Source:** `keyboard-navigation-on-the-build-a-quote-page`. After selecting a cell (setup/run time, operation cost, pricing-item value):
- **Arrows** move between cells (but move the caret *within* a cell while editing).
- **TAB** saves the override edit and advances (highlighting cells and actions like expand/delete op); at a table's end, TAB moves to the next table.
- **SHIFT+TAB** moves backward.
- **ENTER** saves the current cell's override.
- **ESC** exits a cell without saving (then arrows navigate); ESC inside an expanded operation closes it.
**Spec addition:** add this shortcut map to the Part Estimating View interaction patterns. Low effort, high estimator-velocity payoff.

## E4-j · Swap primary / supporting files  `→ Quote Files / Part Files`
**Source:** `swap-primary-and-supporting-files`.
**Behavior:** each Part has one **primary file** (source of truth for geometry/features/BOM) + many **supporting files** (drawings, vendor quotes — no effect on definition). Only the primary file drives automation, so a print-primary part won't autofill geometry from an attached model until you **swap** the model to primary (double-arrow next to a supporting file). Same-named uploads (CAD + drawing) auto-assign the CAD as primary.
- **Blank line items** (no primary file; formerly "manual parts"): *any* file can be set primary **until** a process is selected or child components are added — so a multi-body CAD becomes primary and builds the BOM.
- **Assembly restrictions:** cannot swap CAD files with **different BOM structures**; assemblies generated from a single CAD can't have their (or children's) primary swapped; manually-built assembly children *can* swap (except across different BOM structures).
- **Multi-reference:** if the part is on multiple line items, swapping requires **Replace referenced part** first (E4-b).
- **Tip (PDF→DXF):** vectorize flat-pattern PDF pages, then swap primary to the generated DXF so sheet-metal Kalk reads cut length/pierce count.
**Spec addition:** "make primary" (double-arrow) + single-arrow for blank items + drag-drop primary assignment; the assembly/BOM-structure guards; cross-reference to E4-b.

## E4-k · Analytics — full query-builder  `→ replaces the Analytics stub`
**Source:** `analytics` + `analytics-query-builder-deep-dive`. **Decision: build the full query-builder.** This is a **BI semantic layer** — budget for it accordingly (consider a semantic-layer lib, e.g. Cube-style, behind the Postgres warehouse; tech choice is yours).

**Model**
- **Measures** = aggregatable quantities (counts, costs, prices, %, times). **Dimensions** = categorical attributes (names, part numbers, statuses, dates). A query = any mix; measures aggregate by the chosen dimensions.
- **Time:** a "For" interval on a time field + "By" grouping; many time-based dimensions (Quotes Sent Date, Orders Created, RFQ Received, etc.).
- **Filters:** numeric, date (YYYY-MM-DD / ranges), and string filters on most measures/dimensions.
- **Dashboards** hold tiles; tiles have per-tile date + field filters and editable titles; users create dashboards and copy/edit queries in a **Query Editor**.

**Entities to model** (each exposes measures + dimensions — full field list in the source article; replicate the *working* fields and **omit the many fields the KB marks "broken/deprecated, do not use"**):
Accounts · Contacts · Facilities · Estimators · Component Estimators · Salespersons · Team Members · Materials / Material Families / Material Classes · Processes · Operations · Op Defs · Parts · Components · **Component Quantities** (the richest — per-quantity cost/price/profit) · Quote Items · Quotes · Quote Cells · Quote Add Ons / Add On Cells · Quote Discounts / Discount Cells · Quote Profit Items / Profit Item Cells · Quote Custom Cost Category Cells · Orders · Order Items · Request for Quotes · Request for Quote Views.

**High-value computed fields to guarantee** (these power the dashboards):
- `Quotes Win Rate` = accepted quote items ÷ total quote items.
- Profit margin = `(total_price_incl_discounts − total_estimated_cost) / total_price_incl_discounts` (per Component Quantity; matches your `DECISIONS.md` margin formula).
- Turnaround: `Received→Draft`, `Draft→Send`, `Received→Send` (hours/days + bucketed ranges: <1h, 1–4h, 4–12h, 12–24h, 1–2d, 2–5d, 5+d), `Sent On Time` (vs due date).
- Cost split per Component Quantity: material / inside / outside / purchased-component / total; unit vs total price; discount totals & %.
- Part dimensions (X/Y/Z min/avg/max), file-type spread, assemblies/subassemblies counts.

**Default dashboard (seed 12 tiles)** from the KB: Quotes Sent (30d), Orders Created (30d), Quotes Count/Amount (7d), Orders Count/Revenue (7d), Customer Metrics (quote vs order items, win rate, revenue per account/contact), SmartRFQ Count, SmartRFQ Quotes Sent, Draft-to-Send for SmartRFQs, SmartRFQ Win Rate, Expedite Revenue. Plus advanced dashboards (Part Metrics, Performance, Revenue).
**DACH:** EUR + de-DE number/date formatting; "ITAR/export-controlled" dimensions → reframe as EU export-control flags.
**Spec action:** replace the Analytics stub with: the measures/dimensions semantic model, query-builder UI (measures + dimensions + time + filters), dashboards + query editor, and the seed default dashboard. Mark **Segments** as out (KB: "not functional").

---

# Post-pilot — roadmap (specify interface, defer build)

## E4-e · MBD / PMI viewing  `→ 3D CAD Viewer (roadmap)`
**Source:** `mbd-support-viewing-pmi`. Toggle to display Product Manufacturing Information (dimensions, tolerances, parallelism, datums, text annotations) embedded in MBD files — STEP AP242, JT, 3D PDF, native SolidWorks/Catia/Creo/NX. PMI is only visible if extracted at upload (re-upload needed otherwise). **Why post-pilot:** robust PMI extraction is Spatial-grade; v1 OCCT won't deliver it. Keep a viewer toggle stub; wire when the geometry engine supports PMI.

## E4-f · On-prem managed connector  `→ {cadconnectors}/{integration-manager} (roadmap)`
**Source:** `paperless-parts-managed-connector-ppmc-guide`, `ppmc-connectivity---next-steps`, `ppmc-whitelisting-guide`. A local agent installed in the shop to bridge on-prem ERP / file shares to the cloud (with IP whitelisting). **Why post-pilot:** your adapters + SFTP cover v1; on-prem agent is a distinct deployment some shops need later. Define the adapter interface now; build the agent post-pilot.

## E4-g · MSSQL direct-DB historical import  `→ Part Library / historical import (roadmap)`
**Source:** `getting-paperless-parts-access-to-mssql`. Direct SQL pull of historical quote/part data as an alternative to SFTP file import. **Why post-pilot:** SFTP import covers v1; add a DB-source importer later for shops with SQL-based legacy systems.

---

## Spec-insert summary

| Item | Spec destination | Action |
|---|---|---|
| E4-a Multi-org users | App Shell, `{auth}`, Data Model, Notifications | Add `UserOrgMembership`, org switcher, cross-org notifications |
| E4-b Replace/deep-copy | Data Model, Quote Detail ⋮, Part Library | Add Part↔Component cardinality + guard + 2 resolution actions |
| E4-c Dynamic lead times | Add-Ons/Lead Times/Expedite | Confirm relative-days/%/apply-to-all/default-set nuances |
| E4-d Config-change | Quote Detail (Process), lifecycle | Add freeze rule + Regenerate/Refresh/Bulk-Refresh |
| E4-h Deliverability | `{email-connectivity}`, Settings | Add domain verify + SPF/DKIM/**DMARC** + fallback FROM |
| E4-i Keyboard nav | Part Estimating View | Add shortcut map |
| E4-j Swap files | Quote Files / Part Files | Add make-primary + assembly guards |
| E4-k Analytics | Analytics (replace stub) | Add semantic model + query-builder + seed dashboard |
| E4-e / f / g | Viewer / Integrations / Part Library | Roadmap stubs + interfaces only |

**Sources:** all under `paperless-parts-kb-reference/` — `functionality-for-multi-organizational-users`, `deep-copy-replace-referenced-part-faq`, `dynamic-lead-times-guide`, `working-with-existing-quotes-after-an-update-to-pricing-configuration`, `improving-email-deliverability`, `how-do-i-whitelist-my-ip-address`, `keyboard-navigation-on-the-build-a-quote-page`, `swap-primary-and-supporting-files`, `analytics`, `analytics-query-builder-deep-dive`, `mbd-support-viewing-pmi`, `paperless-parts-managed-connector-ppmc-guide`, `ppmc-connectivity---next-steps`, `ppmc-whitelisting-guide`, `getting-paperless-parts-access-to-mssql`.
