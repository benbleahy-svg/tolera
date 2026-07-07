# SPEC-INDEX — navigable map of the master build spec

> Auto-generated 2026-06-21 from the curated TOC inside **Bid-Factory-Build-Spec.html** (tier-2, ~640 KB, self-contained).
> Use this to jump straight to a section instead of loading the whole HTML. Anchor = `#id`; open as `Bid-Factory-Build-Spec.html#id`.
> **Governs** = the tier-3 sub-spec authoritative for that section's *internals* (precedence: DECISIONS.md > this spec > sub-specs; DACH-DELTA-LAYER overrides region behavior).

> **2026-06-21 — Fold-in.** The tier-3 engine sub-specs are now **folded inline** into `Bid-Factory-Build-Spec.html` (KB-enriched, self-contained — the single build source). The **governs:** pointers below now mark *provenance only*; the source files are frozen in `folded-subspecs/`. New fold-in sub-anchors are listed at the bottom.


## Front matter

- [Overview](Bid-Factory-Build-Spec.html#intro) — `#intro`
- [The Fourteen Demos](Bid-Factory-Build-Spec.html#demos) — `#demos`
- [Screenshot Index](Bid-Factory-Build-Spec.html#screenshots-index) — `#screenshots-index`
- [Personas & Roles](Bid-Factory-Build-Spec.html#personas) — `#personas`

## Foundations

- [Design System & UI Direction](Bid-Factory-Build-Spec.html#ui-system) — `#ui-system`
- [App Shell & Navigation](Bid-Factory-Build-Spec.html#shell) — `#shell`
- [Data Model](Bid-Factory-Build-Spec.html#model) — `#model`  →  **governs:** folded-subspecs/DOMAIN-MODEL.md + folded-subspecs/DB-SCHEMA.sql
- [Workflow State Machines](Bid-Factory-Build-Spec.html#states) — `#states`  →  **governs:** folded-subspecs/USER-STORIES-AND-WORKFLOWS.md

## Screens

  - [Dashboard](Bid-Factory-Build-Spec.html#dashboard) — `#dashboard`
  - [Quotes & Saved Views](Bid-Factory-Build-Spec.html#quoteslist) — `#quoteslist`
  - [Quote Detail](Bid-Factory-Build-Spec.html#quotedetail) — `#quotedetail`
  - [Line-Item Creation](Bid-Factory-Build-Spec.html#linecreate) — `#linecreate`
  - [Part Estimating View](Bid-Factory-Build-Spec.html#partview) — `#partview`  →  **governs:** folded-subspecs/INTERROGATION-ENGINE-SPEC.md + folded-subspecs/PartGeometry-Attribute-Catalog.md
  - [3D CAD Viewer](Bid-Factory-Build-Spec.html#cad) — `#cad`  →  **governs:** folded-subspecs/VIEWER-AND-FILE-TYPES.md
  - [PDF / Drawing Viewer](Bid-Factory-Build-Spec.html#pdf) — `#pdf`  →  **governs:** folded-subspecs/VIEWER-AND-FILE-TYPES.md
  - [Part Library](Bid-Factory-Build-Spec.html#partlib) — `#partlib`
  - [BOM Builder](Bid-Factory-Build-Spec.html#bombuilder) — `#bombuilder`
  - [Assembly Data Model](Bid-Factory-Build-Spec.html#assemblies-model) — `#assemblies-model`  →  **governs:** folded-subspecs/DOMAIN-MODEL.md
  - [Assembly & Bulk Edit](Bid-Factory-Build-Spec.html#assembly) — `#assembly`
  - [Material-Scoped Quoting (Angebotsumfang) ✦](Bid-Factory-Build-Spec.html#quote-inclusion) — `#quote-inclusion`
  - [Sheet-Metal Engine](Bid-Factory-Build-Spec.html#sheetmetal) — `#sheetmetal`  →  **governs:** folded-subspecs/INTERROGATION-ENGINE-SPEC.md
  - [Nesting Module](Bid-Factory-Build-Spec.html#nesting) — `#nesting`  →  **governs:** folded-subspecs/INTERROGATION-ENGINE-SPEC.md
  - [Costing & Pricing](Bid-Factory-Build-Spec.html#costing) — `#costing`  →  **governs:** folded-subspecs/PRICING-ENGINE-SPEC.md + folded-subspecs/KALK-REFERENCE.md
  - [Add-Ons & Lead Times](Bid-Factory-Build-Spec.html#addons) — `#addons`  →  **governs:** folded-subspecs/PRICING-ENGINE-SPEC.md
  - [Order Build / Checkout](Bid-Factory-Build-Spec.html#order) — `#order`
  - [Digital Quote (Buyer Portal)](Bid-Factory-Build-Spec.html#digitalquote) — `#digitalquote`
  - [Smart RFQ Form](Bid-Factory-Build-Spec.html#smart-rfq) — `#smart-rfq`  →  **governs:** folded-subspecs/DOMAIN-MODEL.md
  - [Orders List](Bid-Factory-Build-Spec.html#orderslist) — `#orderslist`
  - [Contacts & Accounts](Bid-Factory-Build-Spec.html#contacts) — `#contacts`
  - [Collaboration & Sourcing](Bid-Factory-Build-Spec.html#collab) — `#collab`
  - [Vendor RFQ Portal ✦](Bid-Factory-Build-Spec.html#vendor-rfq) — `#vendor-rfq`  →  **governs:** folded-subspecs/INTEGRATION-API-CONTRACT.md
  - [Live Sourcing Adapters ✦ (MaterialPricingFeed · PartQuotingAdapter)](Bid-Factory-Build-Spec.html#sourcing-adapters) — `#sourcing-adapters` · `#material-pricing-feed` · `#part-quoting`

## Intelligence

- [AI Extraction (Lens)](Bid-Factory-Build-Spec.html#wingman) — `#wingman`  →  **governs:** folded-subspecs/AI-LENS-ENGINE-SPEC.md
- [Rules & Review Items](Bid-Factory-Build-Spec.html#rules) — `#rules`  →  **governs:** folded-subspecs/RULES-ENGINE-SPEC.md
- [Geometry & DFM](Bid-Factory-Build-Spec.html#geometry) — `#geometry`  →  **governs:** folded-subspecs/INTERROGATION-ENGINE-SPEC.md + folded-subspecs/DFM-WARNINGS.md

## Cross-cutting

- [Integrations / ERP](Bid-Factory-Build-Spec.html#integrations) — `#integrations`  →  **governs:** folded-subspecs/INTEGRATION-API-CONTRACT.md
  - [DACH Costing Mode](Bid-Factory-Build-Spec.html#dach-costing) — `#dach-costing`  →  **governs:** folded-subspecs/PRICING-ENGINE-SPEC.md + folded-subspecs/DACH-DELTA-LAYER.md
- [CAD Connectors](Bid-Factory-Build-Spec.html#cadconnectors) — `#cadconnectors`  →  **governs:** folded-subspecs/INTEGRATION-API-CONTRACT.md
- [Operation Library](Bid-Factory-Build-Spec.html#oplibrary) — `#oplibrary`  →  **governs:** folded-subspecs/PRICING-ENGINE-SPEC.md + folded-subspecs/KALK-REFERENCE.md
- [Onboarding & First-Run](Bid-Factory-Build-Spec.html#onboarding) — `#onboarding`
- [Settings & Admin](Bid-Factory-Build-Spec.html#settings) — `#settings`
  - [User Management](Bid-Factory-Build-Spec.html#user-management) — `#user-management`
- [Tech Stack](Bid-Factory-Build-Spec.html#stack) — `#stack`
- [Build Phases](Bid-Factory-Build-Spec.html#phases) — `#phases`  →  **governs:** build-plan/ (to be written)
- [Acceptance Criteria](Bid-Factory-Build-Spec.html#acceptance) — `#acceptance`
- [Open Questions](Bid-Factory-Build-Spec.html#questions) — `#questions`

## v2.15 Addendum

- [Resolved Decisions](Bid-Factory-Build-Spec.html#decisions) — `#decisions`  →  **governs:** ../decisions/DECISIONS.md (tier-1 override log)
- [AI Architecture & Feature Roadmap](Bid-Factory-Build-Spec.html#ai-arch) — `#ai-arch`
- [New v1 Scope](Bid-Factory-Build-Spec.html#newscope) — `#newscope`
- [Milestone Plan](Bid-Factory-Build-Spec.html#milestones) — `#milestones`  →  **governs:** build-plan/ (to be written)
- [Dev Workflow & Git](Bid-Factory-Build-Spec.html#devworkflow) — `#devworkflow`

## Other in-page anchors (not in the TOC — grep-only)

These finer sub-section ids exist in the HTML but aren't top-level TOC entries:

`#demos-h`, `#authz`, `#quotelifecycle`, `#line-item-management`, `#supported-file-types`, `#customcat`, `#kalk`, `#shipping-options`, `#no-cad-license`, `#interrogations-config`, `#zuschlagskalkulation`, `#integration-manager`, `#crm`, `#quick-setup`, `#operation-rates-banner`, `#missing-rates-warning`, `#advanced-setup`, `#auth`, `#digital-quote-settings`, `#smart-rfq-settings`, `#company-settings-detail`, `#ai-settings`, `#geometry-engine`, `#email-connectivity`, `#billing-decided`, `#ai-tier3-spec`, `#ai-triage`, `#ai-rule-suggest`, `#ai-requote-diff`, `#ai-quote-assembly`, `#ai-customer-brief`, `#ai-presend`, `#ai-coaching`, `#ai-margcoach`, `#ai-nlsearch`, `#lightbox`

### Fold-in sub-anchors (added 2026-06-21)

Engine internals folded inline, by subsystem:

- **Kalk / pricing** (`PRICING-ENGINE-SPEC` + `KALK-REFERENCE`): `#kalk-exec`, `#kalk-python`, `#kalk-vars`, `#kalk-lists`, `#kalk-tables`, `#kalk-geo`, `#kalk-workpiece`, `#kalk-custattr`, `#kalk-bom`, `#kalk-objects`, `#kalk-contexts`, `#kalk-rollup`, `#kalk-freeze`, `#kalk-determinism`, `#kalk-golden`
- **Geometry / DFM** (`INTERROGATION-ENGINE-SPEC` + `DFM-WARNINGS` + `PartGeometry-Attribute-Catalog`): `#partgeometry`, `#geometryservice`, `#dfm-catalogue`
- **Viewer** (`VIEWER-AND-FILE-TYPES`): `#viewer3d-tools`, `#viewer3d-limits`, `#pdf-capabilities`
- **Rules** (`RULES-ENGINE-SPEC`): `#rules-engine`, `#rules-signals`, `#rules-resolutions`, `#rules-schema`, `#rules-paths`, `#rules-fixtures`, `#rules-lifecycle`, `#rules-integration`, `#rules-accept`
- **Lens / AI** (`AI-LENS-ENGINE-SPEC`): `#lens-engine`, `#lens-pipeline`, `#lens-extraction`, `#lens-finding`, `#lens-models`, `#lens-accept`
- **Domain model / schema** (`DOMAIN-MODEL` + `DB-SCHEMA`): `#model-4layer`, `#db-schema`
- **Workflows / stories** (`USER-STORIES-AND-WORKFLOWS`): `#states-roles`, `#states-choreography`, `#states-machines`, `#states-stories`
- **Integration API** (`INTEGRATION-API-CONTRACT`): `#api-contract`, `#api-events`, `#api-webhooks`, `#api-rest`
- **DACH delta** (`DACH-DELTA-LAYER`): `#dach-delta`, `#dach-region`, `#dach-tax`, `#dach-standards`, `#dach-export`, `#dach-connectors-tbl`
- **Conventions:** `#conventions` (KB chips, folded notes, DACH callouts)
