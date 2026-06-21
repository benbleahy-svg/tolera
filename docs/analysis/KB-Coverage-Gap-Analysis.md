# Bid Factory (Tolera) — Coverage Gap Analysis vs. Paperless Parts Knowledge Base

**Compared:** `Bid-Factory-Build-Spec.html` (v2.15) against the complete Paperless Parts public help center — **186 articles**, captured 2026-06-19 (see `paperless-parts-kb-reference/`).
**Date:** 2026-06-19
**Method:** Every KB article cross-referenced against the spec (term-coverage probe + section read). This is a *content/behavior* coverage check against the source product's own docs — complementary to the build-readiness `Build-Spec-Gap-Audit.md` (which covered decisions, infra, fixtures).

---

## Verdict

The spec already reflects ~90%+ of what Paperless Parts publicly documents, and in several areas (AI/Lens, Vendor RFQ portal, DACH costing, margin-target mode) it goes **beyond** the source product. DACH tax/e-invoicing is more complete than expected — ZUGFeRD/XRechnung, VIES, reverse-charge and §UStG are all already referenced.

The real gaps are not missing *features* — they're missing **load-bearing detail** the KB can supply, concentrated in three places that your own audit already flagged as risks:

1. **The Kalk language reference is incomplete** — the KB's nine P3L cheat sheets contain the full function/object/variable set per context. (Closes Gap-Audit §8.)
2. **The `part` attribute catalog is thin** — the KB documents 31 `part.*` geometry attributes with units; the spec names ~1. This is the contract between the geometry engine and Kalk. (Feeds Gap-Audit §3.)
3. **DFM/interrogation warnings are named but not catalogued per family** — the KB's interrogation articles enumerate the feature trees and warnings. (Closes the catalogue half of Gap-Audit §3; numeric thresholds still need shop calibration.)

Plus ~10 smaller behavioral items the KB documents and the spec is silent on (multi-org users, replace-referenced-part, dynamic lead times, MBD/PMI viewing, the managed-connector pattern, email DMARC, a few others).

**Highest-leverage next step:** extract the three appendices above straight from the KB (offered at the end). Everything else is small.

**Legend:** ✅ covered in spec · 🟡 partial / thinner than KB (enrich) · ❌ documented in KB, absent from spec · ⚪ out-of-scope or intentionally replaced for DACH/Tolera

---

## A. Priority enrichments

### E1 — Consolidated **Kalk** language reference (closes Gap-Audit §8) 🟡
**KB source:** `05-pricing-costing-p3l/` → `what-is-paperless-parts-pricing-language-p3l`, `operation-p3l-cheat-sheet`, `pricing-items-p3l-cheat-sheet`, `add-ons-p3l-cheat-sheet`, `discounts-p3l-cheat-sheet`, `custom-table-p3l`, `p3l-lists`, `quantity-specific-variables`, `drop-down-variables`; plus `14-other-reference/additional-examples-material`, `additional-examples-outside-service`.
**Spec today:** `{kalk}` sketches the object model; `units_in`, `table_var`, `set_notes_from_list`, `is_close` appear 1–3× each; drop-down variables and quantity-specific variables effectively absent.
**Why it matters:** you are *designing a programming language*. Claude Code needs the definitive builtin list **per context** (pricing / operation-generation / operation-cost) or it will invent inconsistent helpers across the three Kalk interpreters.
**Action:** build a `KALK-REFERENCE.md` appendix that merges, per context: every global object (`part`, `quote`, `workpiece`), every builtin (`units_in()`, `table_var()`, `set_notes_from_list()`, `is_close()`, list helpers from `p3l-lists`, drop-down/quantity-specific variable mechanics), custom-table lookup syntax + quote-time override semantics, and the `CHECK`/error-surfacing model. The KB cheat sheets are effectively this reference already.

### E2 — `part` / `quote` attribute catalog = the geometry↔pricing contract (feeds Gap-Audit §3) 🟡
**KB source:** `operation-p3l-cheat-sheet` (31 distinct `part.*` attributes with descriptions + metric/imperial units, e.g. `part.size_x/y/z`, `part.volume`, `part.surface_area`, bend/hole/thread counts), plus the sheet-metal-specific set.
**Spec today:** `Data Model → PartGeometry` lists Common + Sheet-metal fields, but the enumerated, Kalk-addressable attribute names and units are not consolidated (`size_x` appears once).
**Why it matters:** this single list is simultaneously the **output schema of `GeometryService`** and the **input surface of Kalk**. Your Gap-Audit §3 asked for exactly this. Pin it and every downstream consumer (viewer, DFM, costing, nesting, part-library hashing) has a stable contract.
**Action:** lift the full attribute table into `PartGeometry` and reference it from `{kalk}`. Mark which attributes v1 OCCT can populate vs. which are Spatial-only (ties to your `GEOMETRY.md`).

### E3 — Per-family DFM / interrogation warning catalogue (closes the catalogue half of Gap-Audit §3) 🟡
**KB source:** `06-part-analysis-interrogation/` → `sheet-metal-interrogation`, `milling-interrogation`, `lathe-interrogation`, `tube-laser-interrogation`, `interrogations-basics`, `custom-interrogations`, the `*-feature-iteration` articles; plus `12-release-notes/New-Sheet-Metal-Interrogation-Warnings`, `etching-detection`, `angle-and-u-channel-profile-detection`.
**Spec today:** `Geometry Recognition & DFM` lists warning *names* and "79 Warnings" examples; `{interrogations-config}` makes thresholds authorable — but there's no per-family catalogue of *which* warnings exist and *what each detects*.
**Why it matters:** these warnings drive Review Items and Rules. Naming them per family turns "guess the warnings" into a checklist.
**Action:** seed a `DFM-WARNINGS.md` table: family → warning → what it detects → default threshold field. Honest caveat: the KB gives names/behavior and some guidance; **numeric thresholds are largely calibration**, so ship the table with placeholder defaults + per-material/machine overrides (as the spec already envisions).

### E4 — Smaller behavioral gaps (KB documents; spec silent/thin)
| # | Gap | KB source | Suggested action |
|---|---|---|---|
| a | **Multi-organization users** — one user belonging to several orgs and switching between them (distinct from multi-tenancy) | `functionality-for-multi-organizational-users`; `multi-organizational-functionality-…` | One-line decision: in scope or post-v1. Affects auth/session + org switcher UI. Likely post-pilot — but state it. |
| b | **Replace-referenced-part / deep copy** — semantics when a library-referenced part is replaced or deep-copied across quotes & assemblies | `deep-copy-replace-referenced-part-faq`; `replace-referenced-part-with-new-version-…` | Specify the behavior in Assembly/Part-Library sections (what re-prices, what detaches). Real correctness risk for assemblies. |
| c | **Dynamic lead times** — rules that auto-adjust lead time by qty/process/load | `dynamic-lead-times-guide`; `final-touches-…` | Spec has Lead Times + Expedite but not the rules-driven variant by name. Add to Lead Times + Rules engine. |
| d | **Behavior on pricing-config change for existing quotes** — what happens to open quotes when materials/operations/Kalk change | `working-with-existing-quotes-after-an-update-to-pricing-configuration` | Define recalc vs. freeze policy (decision + UX). Currently unspecified. |
| e | **MBD / PMI viewing** — model-based-definition annotations in 3D | `mbd-support-viewing-pmi-…`; `viewing-individual-face-colors-…` | Likely roadmap; note explicitly in 3D viewer scope. |
| f | **Managed-connector pattern** — local on-prem agent to pull from on-prem ERP / file shares | `paperless-parts-managed-connector-ppmc-guide`, `ppmc-connectivity---next-steps`, `ppmc-whitelisting-guide` | Your adapters + SFTP cover cloud/file import; the on-prem agent is a distinct deployment some shops need. Note as adapter variant / post-v1. |
| g | **Direct DB historical import (MSSQL)** alongside SFTP | `getting-paperless-parts-access-to-mssql` | Optional second import path for shops with SQL-based legacy systems. |
| h | **Email deliverability (DMARC)** | `improving-email-deliverability` | Spec has SPF/DKIM; add DMARC alignment guidance for org sending domains (you send via Mailgun EU + customer domains). |
| i | **Keyboard navigation on Build-a-Quote** | `keyboard-navigation-on-the-build-a-quote-page-…` | Power-user shortcut map; minor but cheap UX win — add to Part Estimating View. |
| j | **Swap primary/supporting file roles** | `swap-primary-and-supporting-files` | Confirm the per-file "make primary" action exists in Quote Files (Split PDF is covered; role-swap may not be). |
| k | **Analytics** is a stub (your audit §9) | `analytics`, `analytics-query-builder-deep-dive`, `setting-up-an-analytics-dashboard` | If/when analytics is built, the KB query-builder article is a ready spec. Fine to keep stubbed for v1 — just cite the source. |

---

## B. DACH deltas

Mostly **already handled** — call this out as a strength. Present in spec: DACH Costing Mode, `{zuschlagskalkulation}`, MSS Rate Calculator, VAT (incl. ZUGFeRD/XRechnung/VIES/reverse-charge/UStG), GDPR, EUR. The KB has **no** DACH content, so these are net-new and must be validated locally (Fechner pilot), not against PP.

Small additions to verify:
- **Terminology pass:** ensure German tax surfaces use *MwSt/USt* and *USt-IdNr.* labels; spec uses generic "VAT" in places.
- **DATEV** (accounting export) as the DACH analogue to the KB's `quickbooks-online-integration` / `accounting-settings` — confirm it's the planned accounting target (vs. QuickBooks).
- **Export control reframe:** the KB's ITAR/CUI model (`itar-and-data-security`, `improved-user-permissions-and-cui-audit`) appears ~30× in the spec; confirm these are reframed as **EU dual-use / GDPR data-handling**, not literal ITAR (your audit flagged this; partially done).

---

## C. Beyond Paperless Parts (no KB baseline to validate against)

These spec areas have **no source-product equivalent**, so acceptance criteria can't be checked against PP behavior — they need their own fixtures/goldens: the entire **Intelligence Layer / Lens** AI features (triage, rule-suggest, requote-diff, agentic assembly, customer brief, pre-send review, coaching, margin coach, NL search), the **Vendor RFQ Portal** (outside-process sourcing), **margin-target pricing mode**, the **first-principles Dashboard redesign**, **two-way email threading**, and the **DACH costing engine**. Good differentiation — just flag in acceptance criteria that "matches Paperless Parts" doesn't apply here.

---

## D. Full coverage matrix (all 186 articles)

Covered rows are terse; enrich/gap rows carry the detail. Spec anchors in `{braces}`.

### 01 · Getting Started & Platform
| Article | | Note |
|---|:--:|---|
| logging-in-to-paperless-parts | ✅ | Clerk auth `{auth}` |
| two-factor-authentication-2fa | ✅ | Clerk passkey/2FA `{auth}` |
| user-profile-settings | ✅ | Settings → user |
| team-page-and-user-permissions | ✅ | `{user-management}` `{authz}` |
| wingman-assistance | ✅ | → "Lens" AI layer |
| staying-secure-with-paperless-parts | ✅ | Auth/security + CUI audit |
| itar-and-data-security-with-paperless-parts | 🟡 | Reframe ITAR→EU export-control/GDPR for DACH |
| common-part-errors-and-troubleshooting | 🟡 | Could seed Review-Item/validation copy |
| how-to-reach-support | ⚪ | Support contact, not product |
| how-we-build-paperless-parts | ⚪ | Marketing/values |
| privacy-policy | ⚪ | Legal (informs GDPR scope) |

### 02 · Setup, Config & Org Settings
| Article | | Note |
|---|:--:|---|
| company-settings | ✅ | `{company-settings-detail}` |
| setting-up-your-organization | ✅ | Org onboarding/seed |
| team-page-and-user-permissions | ✅ | `{user-management}` |
| workflows | ✅ | Workflow state machines |
| tasks | ✅ | Dashboard "Tasks assigned to me" |
| Saved-Views | ✅ | Saved-view filters |
| managing-materials / adding-a-supplier-material | ✅ | Materials section |
| operations / setting-up-operations | ✅ | Operation Library |
| creating-email-templates | ✅ | Email Templates |
| email-notifications | ✅ | Email Notification Settings |
| internal-collaboration | ✅ | TEAM channels |
| external-collaboration-customer-perspective / how-to-adjust-external-collaboration-settings | ✅ | Collaboration & Sourcing |
| supported-file-types | 🟡 | Confirm parity with KB list `{supported-file-types}` |
| swap-primary-and-supporting-files | 🟡 | Confirm "make primary" file-role action (E4-j) |
| online-metals-available-materials / online-metals-material-calculator | 🟡 | Material supplier catalog + cost calc; partial via supplier mock |

### 03 · Quoting Workflow (Build a Quote)
| Article | | Note |
|---|:--:|---|
| creating-a-new-quote / Quote-Setup / updated-build-a-quote-page | ✅ | Quote Detail + Line-Item Creation |
| setting-up-quote-items | ✅ | Line Item Management `{line-item-management}` |
| the-smart-rfq-form / smart-rfq-settings | ✅ | `{smart-rfq-settings}` |
| the-digital-quote / digital-quote-settings / Configuring-finalized-quotes | ✅ | `{digital-quote-settings}` |
| quote-actions / sending-quotes | ✅ | Quote ACTIONS menu |
| quote-notes | ✅ | Notes |
| requirements-review | ✅ | Rules Engine & Review Items |
| tracking-outstanding-quotes | ✅ | Saved views / Dashboard |
| quoting-from-pdfs--tips-and-tricks | ✅ | PDF viewer + extraction |

### 04 · Analytics & Reporting
| Article | | Note |
|---|:--:|---|
| analytics | 🟡 | Spec = stub only (audit §9) |
| analytics-query-builder-deep-dive | 🟡 | KB is a ready spec if/when built |
| setting-up-an-analytics-dashboard | 🟡 | Roadmap |

### 05 · Pricing, Costing & P3L → **Kalk**
| Article | | Note |
|---|:--:|---|
| what-is-paperless-parts-pricing-language-p3l | ✅ | `{kalk}` overview |
| pricing-a-part / costing-a-part / pricing-table / costing-table | ✅ | Costing & Pricing engine, verified math |
| discounts | ✅ | Discounts |
| final-touches-add-ons-discounts-and-dynamic-lead-times | ✅ | Add-Ons/Lead Times |
| how-do-i-copy-pricing-between-quote-items | ✅ | Copy Pricing |
| operation-p3l-cheat-sheet | 🟡 | **E2** part attributes + operation Kalk |
| pricing-items-p3l-cheat-sheet | 🟡 | **E1** pricing-context builtins |
| add-ons-p3l-cheat-sheet | 🟡 | **E1** add-on-context builtins |
| discounts-p3l-cheat-sheet | 🟡 | **E1** discount-context builtins |
| custom-table-p3l / custom-tables | 🟡 | **E1** lookup syntax + override semantics |
| p3l-lists | 🟡 | **E1** list helpers |
| quantity-specific-variables | 🟡 | **E1** per-qty-break variable mechanics |
| drop-down-variables | ❌ | **E1** drop-down variable mechanics (absent) |
| dynamic-lead-times-guide | 🟡 | **E4-c** rules-driven lead time |
| working-with-existing-quotes-after-an-update-to-pricing-configuration | 🟡 | **E4-d** recalc-vs-freeze policy |

### 06 · Part Analysis & Interrogation
| Article | | Note |
|---|:--:|---|
| interrogations-basics / processes / assigning-a-process-material-and-finish | ✅ | Geometry Recognition + Processes |
| Found-in-files-extractions / PDF-file-processing / PDF-Extraction-Beta | ✅ | Lens extraction + "Found in Files" |
| CAD-assembly-file-processing | ✅ | Assembly file handling |
| Part-setup-tool / Entering-part-number-revision-and-description | ✅ | Part Setup + identity |
| custom-operation-generation | ✅ | Custom Operation Generation `{interrogations-config}` |
| similar-parts-search-beta | ✅ | Part Library matching |
| milling/sheet-metal/lathe/tube-laser/wire-edm-process | ✅ | "Core 4" families covered |
| additive-process / cast-urethane-process | 🟡 | Confirm in/after v1 family scope |
| sheet-metal/milling/lathe/tube-laser-interrogation + *-feature-iteration | 🟡 | **E3** per-family warning catalogue |
| custom-interrogations | 🟡 | **E3** enrich Configure → Interrogations specifics |
| multi-component-sheet-metal-nesting | ✅ | Nesting module |

### 07 · Part Viewer (3D / PDF / Models)
| Article | | Note |
|---|:--:|---|
| 3d-viewer-tools / part-viewer-display-options | ✅ | 3D CAD Viewer |
| pdf-viewer-guide | ✅ | PDF/2D viewer |
| 3D-viewing-limits | 🟡 | Capture viewer limits/perf envelope |

### 08 · Assemblies & BOM
| Article | | Note |
|---|:--:|---|
| The-BOM-Builder / intro-to-the-assembly-toolkit / building-boms-additional-faq | ✅ | BOM Builder |
| assemblies-data-types-and-terminology | ✅ | Assembly Data Model |
| purchased-components | ✅ | Purchased Components (real-time) |
| quoting-an-assembly-part-from-a-model / -from-a-pdf | ✅ | Assembly quoting |
| quoting-a-part-with-hardware-from-a-model | ✅ | Hardware/fasteners |
| quoting-children-of-assemblies-as-separate-parts | ✅ | Assembly actions |
| add-an-existing-part-in-your-library-to-an-assembly-bom | ✅ | BOM build actions |
| manual-component-nesting / multi-component-linear-nesting / multi-component-nesting-module | ✅ | Nesting |

### 09 · Part Library
| Article | | Note |
|---|:--:|---|
| navigate-and-manage-the-part-library | ✅ | Part Library (historical match) |
| uploading-parts-to-your-part-library | ✅ | Upload/organise |

### 10 · Accounts, Contacts & CRM
| Article | | Note |
|---|:--:|---|
| accounts-and-contacts | ✅ | Contacts — Accounts & People `{crm}` |
| exporting-quotes-orders-and-accounts-contacts | ✅ | Standard quote exporter / export |
| accounting-settings | 🟡 | DACH = DATEV vs KB's QuickBooks (B) |

### 11 · Orders, Checkout & Fulfillment
| Article | | Note |
|---|:--:|---|
| order-facilitation | ✅ | Facilitate Order drawer |
| online-checkout-in-paperless-parts | ✅ | Digital Quote checkout |
| accepting-credit-cards-in-paperless-parts | ✅ | Checkout + Paddle/PSP `{billing-decided}` |
| shipping-options | ✅ | `{shipping-options}` |
| filtering-orders | ✅ | Orders list |
| post-order-changes-and-limitations | ✅ | OrderAdjustment / OrderHistory |

### 12 · Release Notes (What's New) — features folded into spec unless noted
| Article | | Note |
|---|:--:|---|
| multi-organizational-functionality-… | ❌ | **E4-a** multi-org user switching |
| replace-referenced-part-with-new-version-… | 🟡 | **E4-b** |
| mbd-support-viewing-pmi-… / viewing-individual-face-colors-… | 🟡 | **E4-e** MBD/PMI viewing |
| keyboard-navigation-on-the-build-a-quote-page-… | 🟡 | **E4-i** |
| angle-and-u-channel-profile-detection-… | 🟡 | Niche profile detection (sheet/extrusion) |
| etching-detection-… | 🟡 | Etch/engrave feature detection |
| streaming-api-and-developer-portal-… | 🟡 | → webhooks (terminology; confirm event parity) |
| Assembly-Table-Updates / better-bom-builder / flexible-bom-editing / bom-in-viewer / smart-purchased-component-assignment / multi-component-(linear/sheet-metal)-nesting(-improvements) | ✅ | Folded into BOM/Nesting/Assembly |
| New-Sheet-Metal-Interrogation-Warnings / expanded-file-interrogation-support / geometry-kernel-upgrade / duplicate-processes-… | ✅ | Folded into interrogation/process (warnings → E3) |
| New-actions-for-Quote-Supporting-Files / quote-supporting-files / supporting-files-update / flexible-primary-file-assignment / externally-share-any-file / viewing-email-files / ms-office-files-support | ✅ | Quote Files actions / file handling |
| Thumbnail-Enhancements | ✅ | Thumbnail generation |
| pdf-viewer-improvements / viewer-improvements | ✅ | Viewer |
| read-only-collaboration-… | ✅ | Collaboration |
| improved-user-permissions-and-cui-audit-… | ✅ | Permissions + CUI audit (reframe per B) |
| integration-actions-… | ✅ | Integration Manager actions |
| import-historical-work-… | ✅ | Historical import (SFTP) — see E4-g for MSSQL |
| bulk-update-workflow-status-… | ✅ | Bulk actions |
| new-contacts-page-… | ✅ | Contacts |
| new-email-template-placeholders-… | ✅ | Email templates (verify placeholder set) |
| p3l-revision-control-… | 🟡 | Kalk versioning/revision — confirm in `{kalk}` |
| standard-quote-exporter-… | ✅ | Export |
| Updated-Quotes-and-Orders-Dasboards / Updated-Paperless-Parts-Support-Form | ⚪ | Dashboard (redesigned) / support form |

### 13 · Integrations & Developer Docs
| Article | | Note |
|---|:--:|---|
| integration-manager / integration-development-guide | ✅ | `{integration-manager}` + adapters |
| autodesk-fusion-integration | ✅ | CAD connectors (Fusion first) `{cadconnectors}` |
| paperless-parts-streaming-api | 🟡 | → webhooks; confirm event coverage |
| paperless-parts-managed-connector-ppmc-guide / ppmc-connectivity---next-steps / ppmc-whitelisting-guide | 🟡 | **E4-f** on-prem managed-connector pattern |
| getting-paperless-parts-access-to-mssql | 🟡 | **E4-g** direct-DB import path |
| how-do-i-whitelist-my-ip-address | 🟡 | IP allow-listing for integrations (minor) |
| quickbooks-online-integration | 🟡 | DACH = DATEV (B) |
| 5-minute-tutorial-…-trello-…-zapier-… | ⚪ | Tutorial example (Zapier middleware pattern already noted in spec) |

### 14 · Other / Reference
| Article | | Note |
|---|:--:|---|
| building-review-rules | ✅ | Rules Engine (rich — could enrich rule library) |
| chat-with-msc | ✅ | → "Tolera Advisor" mock |
| vendor-rfqs-early-access | ✅ | Vendor RFQ Portal (beyond PP) |
| additional-examples-material / additional-examples-outside-service | 🟡 | Fold Kalk examples into E1 |
| deep-copy-replace-referenced-part-faq | 🟡 | **E4-b** |
| functionality-for-multi-organizational-users | ❌ | **E4-a** |
| improving-email-deliverability | 🟡 | **E4-h** DMARC |

---

## E. Recommended next artifacts (extractable straight from the KB)

In priority order — each is built from the articles already in `paperless-parts-kb-reference/` and drops into the project as a spec appendix:

1. **`KALK-REFERENCE.md`** — full builtin/object/variable reference per context (E1). Single highest-value item; closes Gap-Audit §8.
2. **`PartGeometry` attribute catalog** — the 31+ `part.*` attributes with units, merged into the Data Model + Kalk `part` object (E2). The geometry↔pricing contract.
3. **`DFM-WARNINGS.md`** — per-family warning catalogue with placeholder thresholds + override fields (E3).

Say the word and I'll generate any/all of these into the Bid Factory folder next.
