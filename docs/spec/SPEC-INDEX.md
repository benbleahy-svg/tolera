# SPEC-INDEX — navigable map of the master build spec

> Auto-generated 2026-06-21 from the curated TOC inside **Bid-Factory-Build-Spec.html** (tier-2, ~492 KB).
> Use this to jump straight to a section instead of loading the whole HTML. Anchor = `#id`; open as `Bid-Factory-Build-Spec.html#id`.
> **Governs** = the tier-3 sub-spec authoritative for that section's *internals* (precedence: DECISIONS.md > this spec > sub-specs; DACH-DELTA-LAYER overrides region behavior).


## Front matter

- [Overview](Bid-Factory-Build-Spec.html#intro) — `#intro`
- [The Fourteen Demos](Bid-Factory-Build-Spec.html#demos) — `#demos`
- [Screenshot Index](Bid-Factory-Build-Spec.html#screenshots-index) — `#screenshots-index`
- [Personas & Roles](Bid-Factory-Build-Spec.html#personas) — `#personas`

## Foundations

- [Design System & UI Direction](Bid-Factory-Build-Spec.html#ui-system) — `#ui-system`
- [App Shell & Navigation](Bid-Factory-Build-Spec.html#shell) — `#shell`
- [Data Model](Bid-Factory-Build-Spec.html#model) — `#model`  →  **governs:** ../subsystems/DOMAIN-MODEL.md + ../subsystems/DB-SCHEMA.sql
- [Workflow State Machines](Bid-Factory-Build-Spec.html#states) — `#states`  →  **governs:** ../subsystems/USER-STORIES-AND-WORKFLOWS.md

## Screens

  - [Dashboard](Bid-Factory-Build-Spec.html#dashboard) — `#dashboard`
  - [Quotes & Saved Views](Bid-Factory-Build-Spec.html#quoteslist) — `#quoteslist`
  - [Quote Detail](Bid-Factory-Build-Spec.html#quotedetail) — `#quotedetail`
  - [Line-Item Creation](Bid-Factory-Build-Spec.html#linecreate) — `#linecreate`
  - [Part Estimating View](Bid-Factory-Build-Spec.html#partview) — `#partview`  →  **governs:** ../subsystems/INTERROGATION-ENGINE-SPEC.md + ../subsystems/PartGeometry-Attribute-Catalog.md
  - [3D CAD Viewer](Bid-Factory-Build-Spec.html#cad) — `#cad`  →  **governs:** ../subsystems/VIEWER-AND-FILE-TYPES.md
  - [PDF / Drawing Viewer](Bid-Factory-Build-Spec.html#pdf) — `#pdf`  →  **governs:** ../subsystems/VIEWER-AND-FILE-TYPES.md
  - [Part Library](Bid-Factory-Build-Spec.html#partlib) — `#partlib`
  - [BOM Builder](Bid-Factory-Build-Spec.html#bombuilder) — `#bombuilder`
  - [Assembly Data Model](Bid-Factory-Build-Spec.html#assemblies-model) — `#assemblies-model`  →  **governs:** ../subsystems/DOMAIN-MODEL.md
  - [Assembly & Bulk Edit](Bid-Factory-Build-Spec.html#assembly) — `#assembly`
  - [Sheet-Metal Engine](Bid-Factory-Build-Spec.html#sheetmetal) — `#sheetmetal`  →  **governs:** ../subsystems/INTERROGATION-ENGINE-SPEC.md
  - [Nesting Module](Bid-Factory-Build-Spec.html#nesting) — `#nesting`  →  **governs:** ../subsystems/INTERROGATION-ENGINE-SPEC.md
  - [Costing & Pricing](Bid-Factory-Build-Spec.html#costing) — `#costing`  →  **governs:** ../subsystems/PRICING-ENGINE-SPEC.md + ../subsystems/KALK-REFERENCE.md
  - [Add-Ons & Lead Times](Bid-Factory-Build-Spec.html#addons) — `#addons`  →  **governs:** ../subsystems/PRICING-ENGINE-SPEC.md
  - [Order Build / Checkout](Bid-Factory-Build-Spec.html#order) — `#order`
  - [Digital Quote (Buyer Portal)](Bid-Factory-Build-Spec.html#digitalquote) — `#digitalquote`
  - [Smart RFQ Form](Bid-Factory-Build-Spec.html#smart-rfq) — `#smart-rfq`  →  **governs:** ../subsystems/DOMAIN-MODEL.md
  - [Orders List](Bid-Factory-Build-Spec.html#orderslist) — `#orderslist`
  - [Contacts & Accounts](Bid-Factory-Build-Spec.html#contacts) — `#contacts`
  - [Collaboration & Sourcing](Bid-Factory-Build-Spec.html#collab) — `#collab`
  - [Vendor RFQ Portal ✦](Bid-Factory-Build-Spec.html#vendor-rfq) — `#vendor-rfq`  →  **governs:** ../subsystems/INTEGRATION-API-CONTRACT.md

## Intelligence

- [AI Extraction (Lens)](Bid-Factory-Build-Spec.html#wingman) — `#wingman`  →  **governs:** ../subsystems/AI-LENS-ENGINE-SPEC.md
- [Rules & Review Items](Bid-Factory-Build-Spec.html#rules) — `#rules`  →  **governs:** ../subsystems/RULES-ENGINE-SPEC.md
- [Geometry & DFM](Bid-Factory-Build-Spec.html#geometry) — `#geometry`  →  **governs:** ../subsystems/INTERROGATION-ENGINE-SPEC.md + ../subsystems/DFM-WARNINGS.md

## Cross-cutting

- [Integrations / ERP](Bid-Factory-Build-Spec.html#integrations) — `#integrations`  →  **governs:** ../subsystems/INTEGRATION-API-CONTRACT.md
  - [DACH Costing Mode](Bid-Factory-Build-Spec.html#dach-costing) — `#dach-costing`  →  **governs:** ../subsystems/PRICING-ENGINE-SPEC.md + ../subsystems/DACH-DELTA-LAYER.md
- [CAD Connectors](Bid-Factory-Build-Spec.html#cadconnectors) — `#cadconnectors`  →  **governs:** ../subsystems/INTEGRATION-API-CONTRACT.md
- [Operation Library](Bid-Factory-Build-Spec.html#oplibrary) — `#oplibrary`  →  **governs:** ../subsystems/PRICING-ENGINE-SPEC.md + ../subsystems/KALK-REFERENCE.md
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
