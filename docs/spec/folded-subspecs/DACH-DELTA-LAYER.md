# DACH Delta Layer (per-feature)

**Status:** Spec appendix for Tolera (Bid Factory). Implements Gap-Analysis §B. **What it is:** the per-feature divergences from the Paperless Parts (US) reference needed to ship in **D**eutschland / **A**ustria / Schweiz (**CH**). The spec already has good bones here (DACH Costing Mode, `{zuschlagskalkulation}` seed, MSS Rate Calculator, VAT incl. ZUGFeRD/XRechnung/VIES/reverse-charge/UStG, GDPR, EUR) — this layer **systematizes it per feature and fills the gaps** (Switzerland specifics, e-invoicing phasing, ISO default tolerances, ISO GPS, DIN material crosswalk, DATEV/ERP targets, dual-use screening, dropping the imperial path).

> **Regulatory facts current as of Jun 2026 — keep all rates/dates configurable and re-verify at build.** Sources in the delivery note.

---

## 0. Region model

Add a per-org **Region/Locale profile** that everything below reads from — country (**DE | AT | CH**) → currency, VAT profile, number/date formatting, e-invoice format, accounting connector, language variant. Don't hardcode "Germany"; the three countries differ (esp. CH). The spec's `BRAND` config extends to a `REGION` config.

## 1. Global conventions (apply everywhere)

| Concern | DE / AT | CH | Note |
|---|---|---|---|
| **Language** | German (de-DE / de-AT) | German (de-CH) + FR/IT later | v1 = Claude-generated de strings, Fechner reviews (`DECISIONS.md`). de-CH uses **ss not ß**. |
| **Decimal / thousands** | `1.234,56` (comma decimal, dot thousands) | `1’234.56` (**point decimal, apostrophe thousands**) | CH is the trap — don't assume one formatter. |
| **Currency format** | `1.234,56 €` (symbol after) | `CHF 1’234.56` | |
| **Date / time** | `TT.MM.JJJJ` (DD.MM.YYYY), 24h, Monday-first; ISO-8601 in storage | same | |
| **Units** | **Metric-native** (mm, mm², kg, °C, µm) | same | **Drop the imperial path** — PP converts metric→imperial; Tolera is metric-only. `units_in()` becomes a no-op/removed; no unit toggle; geometry stored & shown in mm. |
| **Paper / PDF** | **A4 / A3** | same | Quote/invoice PDFs sized A4. |
| **Timezone** | Europe/Berlin (CET/CEST) | Europe/Zurich | same offset across DACH. |

## 2. Per-feature deltas

| Feature / spec area | DACH delta |
|---|---|
| **Smart RFQ form** | German labels; metric inputs (mm/kg); DIN/EN material picker; requested-date `TT.MM.JJJJ`; replace ITAR question with **EU dual-use / export-control** flag; GDPR consent + privacy-policy (Datenschutzerklärung) link + Impressum. |
| **Quote builder / Part Estimating** | Metric-only dimensions & rates (€/h, €/kg, CHF); comma-decimal entry; material = Werkstoffnummer; tolerances default ISO 2768-m (§4). |
| **Pricing (Kalk)** | `currency` type → EUR (or CHF) with locale formatting; metric defaults (drop `units_in`); supports **Zuschlagskalkulation** (overhead-surcharge costing) already seeded; **tax is NOT in Kalk** (computed at quote/order, §3). |
| **Interrogation / materials** | Material master keyed on **DIN EN** designations (§4); ISO GPS / Ra-Rz extraction (§4); thickness/gauges in mm. |
| **Digital Quote (buyer portal)** | German UI; net prices with **MwSt/USt** shown separately (or reverse-charge note); EUR/CHF; A4 PDF; expedite shown in days; GDPR cookie/consent. |
| **Checkout / Orders** | Payment = **invoice on account / SEPA / PO** dominant (cards secondary); **VAT logic** (§3) incl. reverse-charge & VAT-ID; CH **QR-bill**; shipping via DHL/DPD/GLS/Swiss Post (not UPS). |
| **Accounts / Contacts** | Account fields: **USt-IdNr** (VAT ID, VIES-validated), tax profile (domestic/EU-B2B-reverse-charge/non-EU/Kleinunternehmer), country; billing/ship-to EU address formats; DATEV debtor account no. |
| **Settings / Config** | Region profile (§0); VAT profile; e-invoice format selector; accounting connector; default ISO tolerance class; export-control settings. |
| **Email** | **Mailgun EU** (already decided); German templates; footer with legal **Impressum** / company register (HRB/Firmenbuch/HR) + USt-IdNr; SPF/DKIM/**DMARC** (E4-h). |
| **Integrations** | **DATEV** (accounting) not QuickBooks; German/EU ERPs; HubSpot (EU); Würth/EU suppliers (§6). |
| **Lens / AI extraction** | Recognize **German** drawing text & title blocks; **ISO GPS** GD&T symbols + Ra/Rz; metric callouts; LLM data-processing under GDPR (EU region / DPA; flag CUI-equiv handling). |
| **Analytics** | EUR/CHF measures, de formatting; reframe ITAR/export dimensions as dual-use; tax-exclusive revenue. |
| **Vendor RFQ / Collaboration** | German vendor portal; EU vendor VAT-ID; GDPR data-handling for external parties (§5). |
| **Auth / Org** | Clerk with EU data residency; German UI; multi-org (E4-a). |

## 3. Tax & e-invoicing (deep)

**VAT rates (configurable seed — verify at build):**

| Country | Standard | Reduced | Tax term |
|---|---|---|---|
| Germany | **19%** | **7%** | USt / MwSt |
| Austria | **20%** | **13% / 10%** *(verify)* | USt |
| Switzerland | **8.1%** | **2.6% / 3.8%** *(verify)* | MWST/TVA |

- **Reverse charge (intra-EU B2B):** when selling to a VAT-registered business in another EU member state, no VAT is charged; invoice must note *"Steuerschuldnerschaft des Leistungsempfängers" (reverse charge)* and carry both VAT-IDs (§13b UStG). Requires the buyer's valid **USt-IdNr**.
- **VAT-ID validation:** validate customer **USt-IdNr against VIES** at account setup / quote finalize; store result + timestamp.
- **§14 UStG mandatory invoice fields:** full name+address of supplier and customer; supplier USt-IdNr (or tax number); invoice date; **sequential unique invoice number**; quantity + description; delivery/service date; net amount per VAT rate; VAT rate + amount (or reverse-charge note); any pre-agreed reductions. Switzerland/Austria have analogous required fields.
- **E-invoicing (Germany, phased — Growth Opportunities Act):**
  - **Jan 2025:** every domestic B2B must be able to **receive + archive** structured e-invoices (EN 16931). Paper/PDF still allowed transitionally.
  - **Jan 2027:** mandatory **issuance** for suppliers with **> €800k** prior-year turnover.
  - **Jan 2028:** all remaining domestic B2B.
  - **Formats:** **XRechnung** (pure XML; B2G via **Peppol** + **Leitweg-ID**), **ZUGFeRD ≥ 2.1** (hybrid PDF/A-3 + embedded XML — best when a human-readable PDF is also needed), Peppol BIS 3.0. **Tolera implication:** support **receiving** EN-16931 e-invoices early and **issuing** ZUGFeRD (hybrid) + XRechnung; wire Peppol for B2G.
  - **Austria:** B2G via **ebInterface** / Peppol through the **USP** portal. **Switzerland:** no general mandate; **QR-bill (QR-Rechnung)** is standard on invoices; swissDIGIN for B2B.
- **GoBD (DE) retention:** invoices/quotes/order records retained **immutably ~10 years** with audit trail — applies to Order/Invoice/Quote records and the e-invoice archive.
- **Kleinunternehmer (§19 UStG):** small-business no-VAT option → a per-org flag that suppresses VAT lines.
- **Placement:** a **Tax/Region service** computes VAT at quote/order level (not in Kalk, per `PRICING-ENGINE-SPEC.md §1`); Paddle as merchant-of-record can handle EU VAT for the SaaS subscription — but **customer-facing manufacturing invoices** are the shop's own (DATEV/e-invoice), separate from Tolera's billing.

## 4. Materials & engineering standards

- **Material designations — DIN EN 10027:** primary key = **Werkstoffnummer** (e.g. `1.4301`) + name (`X5CrNi18-10`); show AISI/UNS (`304`) as an **alias** for reference. Aluminium = **EN AW-6061 / 3.3211**. Seed a DIN↔AISI/UNS crosswalk; the `Material` entity (`DOMAIN-MODEL.md`) stores `werkstoffnummer`, `en_name`, `aisi_alias`, `family`, `class`.
- **General tolerances — ISO 2768 (-f/-m/-c) / ISO 22081:** the assumed tolerance when a drawing specifies none — drives DFM + cost. **Default to ISO 2768-m**, configurable. (US PP assumes ASME defaults; this is a real divergence.)
- **GD&T → ISO GPS:** datums/symbols per **ISO 1101 / ISO GPS**, not ASME Y14.5 — the Lens extractor + viewer must recognize ISO symbology.
- **Surface finish:** **Ra / Rz in µm** (ISO 1302).
- **Threads:** **metric ISO** (M-series, ISO 261/965) default; UNC/UNF only as imports.
- **Welding symbols:** **ISO 2553** (not AWS A2.4).
- **Sheet:** thickness in **mm** (+ EN gauges); bend tables metric.

## 5. Export control & data privacy (replace ITAR/CUI)

- **GDPR / DSGVO:** lawful basis + **AVV/DPA** with every sub-processor (Clerk, Mailgun EU, LLM provider, hosting); **EU data residency** (EU region for hosting, email, AI — ties to the audit's CUI/cloud-LLM concern); data-subject rights (Auskunft/Löschung/Portabilität); **ROPA** (Verzeichnis von Verarbeitungstätigkeiten); retention reconciled with GoBD; Impressum + Datenschutzerklärung on all customer-facing surfaces.
- **EU dual-use export control:** **Regulation (EU) 2021/821** + national **AWG/AWV** and the **Ausfuhrliste / EU control lists** — replace the **ITAR/CUI** flag with an **`export_control` (Güterlistenrelevanz / dual-use)** flag on Part / Quote Item / RFQ; add an optional **restricted-party screening** hook (EU consolidated sanctions list). Keep the access-restriction/audit behavior the spec attached to CUI, but relabel and re-base on EU law.
- **Note:** ITAR can still bind US-origin technical data, but Tolera's **native** model is EU; don't hardcode ITAR/CUI semantics — make the control regime a config.

## 6. Integrations (DACH-local) — replace US partners

| US (PP) | DACH (Tolera) |
|---|---|
| QuickBooks (accounting) | **DATEV** (DATEV-Schnittstelle / DATEVconnect / "DATEV-Format" export); SMEs also Lexware / sevDesk |
| JobBOSS / Global Shop (ERP) | **SAP Business One, abas, proALPHA, Sage, ams.erp, work»plan** — adapter targets; first DACH ERP TBD with pilot |
| UPS rating (shipping) | **DHL / DPD / GLS / Swiss Post**; or manual/flat |
| Online Metals / MSC (material) | EU metal suppliers; **Würth** already chosen ("Tolera Source", `DECISIONS.md`) |
| HubSpot/Salesforce CRM | **HubSpot (EU data center)** already decided |
| Stripe-style PSP | **Paddle** (decided) for SaaS billing; shop-side: SEPA / invoice / CH QR-bill |

Keep the **adapter interface** (mock-first per audit); only the *targets* change. Mailgun EU already decided.

## 7. What this adds vs. the spec's existing DACH handling

Already in spec (keep): DACH Costing Mode, Zuschlagskalkulation seed, MSS Rate Calculator, VAT w/ ZUGFeRD/XRechnung/VIES/reverse-charge/UStG, GDPR, EUR, Mailgun EU, Paddle, Würth/DATEV mentions.
**This layer adds:** the **Region profile** (DE/AT/**CH** split), **Switzerland** specifics (8.1% VAT, **point-decimal/apostrophe** formatting, **QR-bill**), **Austria** rates + ebInterface/USP, the **phased e-invoicing timeline** (receive-first 2025 → 2027 → 2028) and the **receive vs issue** distinction, **ISO 2768 default tolerances**, **ISO GPS / Ra-Rz / ISO threads / ISO 2553**, the **DIN↔AISI material crosswalk** on the Material entity, **dropping the imperial path**, **GoBD 10-yr retention**, **dual-use screening** + sanctions hook, and concrete **DATEV / EU-ERP / shipping** targets.

## 8. Implementation notes

1. **One Region/Locale service** per org → drives currency, VAT profile, formatting (use ICU/Intl but **special-case de-CH**), e-invoice format, accounting connector, language. Everything reads it; no hardcoded locale.
2. **Tax engine** at quote/order (not Kalk): rate tables (configurable), reverse-charge logic, VIES validation, §14/e-invoice field assembly, GoBD-compliant immutable archive.
3. **Material master** keyed on Werkstoffnummer with alias crosswalk; interrogation + Kalk read DIN names.
4. **Drop unit-conversion code** (metric-only) — simplifies the geometry engine + Kalk.
5. **Export-control = config** (regime + lists), not a hardcoded ITAR flag.
6. **i18n** de-DE catalog now (Fechner review), de-CH/de-AT variants + FR/IT post-pilot.
7. Log the open rate/format choices in `DECISIONS.md` (AT reduced rates; first DACH ERP target; e-invoice issue-vs-receive scope for pilot).
