# 01 — Strategy & Decisions

## 1. Product facts (from product repo — authoritative there)

- **Product:** Tolera — instant-quoting / RFQ platform for DACH custom manufacturers. Domains: `tolera.eu` (this site), `app.tolera.eu` (product), `{org}@rfq.tolera.eu` (email ingest).
- **Sub-brands:** **Lens** (AI extraction — purple, suggestion-only), **Kalk** (pricing formula language), **Tolera Advisor** / **Tolera Source** (mocked v1 — do not market as live).
- **Processes v1:** CNC-Fräsen, Drehen, Blechbearbeitung, Rohrlaser (+ assemblies/BOM).
- **File types:** STEP/STP/JT native full interrogation; SLDPRT/IPT/CATIA etc. (conversion tier); STL/3MF mesh; DXF/DWG/PDF 2D; max 200 MB.
- **Billing:** Paddle (Merchant of Record, handles EU VAT). Tiers: Free / Starter / Growth / Enterprise. 14-day full trial, no credit card. Free tier: 5 Angebote/Monat.
- **Region:** DE/AT/CH. Metric-native. EUR + CHF. German-first UI. GDPR, GoBD, XRechnung/ZUGFeRD/ebInterface/QR-Rechnung, EU dual-use (not ITAR).

## 2. Audience

**Primary buyer = primary user (self-serve):** owner or Arbeitsvorbereitung/Kalkulation lead of a DACH custom-manufacturing shop (Mittelstand, ~5–100 employees; CNC-Zerspanung, Blech, Rohrlaser, Drehen, Mischbetriebe). Pain: quoting takes hours per RFQ, tribal knowledge in one estimator's head, RFQs lost to slow response. Skeptical of: US cloud, sales calls, "Enterprise-Software-Projekte", anything without a price tag. Formal Sie in all German copy.

**Secondary:** estimators/Kalkulatoren evaluating tools for their boss; English-speaking evaluators (international shops, investors) via `/en/`.

## 3. Positioning

**Category:** Angebots- und Kalkulationssoftware für Lohnfertiger (instant quoting / CPQ for custom manufacturers).

**Core claim:** *Vom RFQ zur fertigen Kalkulation in Minuten — nicht in Wochen der Einführung.* Tolera is the self-serve alternative in a category where the incumbent (Paperless Parts) requires 8–12 weeks of guided onboarding, a 3-person implementation team, and publishes no prices.

**The wedge (messaging hierarchy, in order):**
1. **Selbst starten, heute.** Kostenlos testen ohne Kreditkarte, ohne Sales-Call. Erste eigene Anfrage in <15 Minuten kalkuliert.
2. **Für den DACH-Betrieb gebaut.** Metrisch. EUR/CHF. Werkstoffnummern. MwSt/USt & Reverse-Charge. XRechnung/ZUGFeRD. GoBD. Daten in Deutschland, DSGVO.
3. **Die Maschine sieht das Teil.** Geometrie-Analyse (DFM), Lens liest Zeichnungen & E-Mails, Anforderungsprüfung übersieht nichts.
4. **Ihre Kalkulationslogik, nicht unsere.** Kalk: nachvollziehbare Formeln statt Blackbox — konfigurierbar ohne Berater.

**Golden thread demo narrative (used everywhere: hero, tour, feature pages):**
RFQ-E-Mail trifft ein → Lens extrahiert Positionen, Material, Toleranzen → Geometrie-Analyse des STEP-Files → DFM-Hinweise + Anforderungsprüfung → Kalk berechnet Kosten je Stückzahl → Angebot als PDF/Digital Quote raus. *Eine Anfrage, ein Durchlauf, Minuten.*

**Tone:** sachlich, präzise, selbstbewusst ohne Marketing-Schaum. Short sentences. Numbers over adjectives. No "revolutionär", no "KI-Magie". English mirror: same restraint, sentence case.

## 4. Approved claims register

Only these quantified claims may appear. Anything else = block-and-log.

| ID | Claim (DE) | Source / status |
|---|---|---|
| C1 | „In unter 15 Minuten von der Anfrage zum kalkulierten Angebot" | Product north-star activation metric. Frame as product promise, **verify in pilot before launch**. |
| C2 | „Paperless Parts: 8–12 Wochen Einführung mit Implementierungsteam" | PP public materials (onboarding research). Re-verify against pp.com before launch; cite source on Vergleich page. |
| C3 | „Keine Kreditkarte, kein Sales-Call, 14 Tage voller Zugriff" | Billing decision (spec `#billing-decided`). |
| C4 | „5 Angebote pro Monat dauerhaft kostenlos" | Packaging decision — **confirm in DECISIONS.md before launch** (currently recommendation-status). |
| C5 | Fechner case-study numbers (Zeit pro Angebot vorher/nachher) | `TBD(pilot-metrics)` — measure in pilot. Until then the case study uses qualitative quotes only. |
| C6 | „STEP, JT, SolidWorks, Inventor, CATIA … über 20 Dateiformate" | Spec `#supported-file-types`. Only list conversion-tier formats if the Spatial/HOOPS kernel decision is live at launch — else STEP/JT/STL/DXF/PDF only. Check with product. |
| C7 | „Daten in Deutschland / EU-Hosting" | **Verify actual hosting region of app DB before publishing** — `TBD(hosting-region)`. |

## 5. The 12 interview decisions (2026-07-10, Benjamin)

| # | Decision | Choice |
|---|---|---|
| D1 | Site mission | Full site; **goes live only when self-serve signup is live (v1.x)**. No waitlist phase. Design purely for conversion. |
| D2 | Languages | German at root, full English mirror at `/en/`. hreflang `de`/`en`/`x-default`. One `de` locale for DE/AT/CH. fr/it: not at launch. |
| D3 | Sitemap size | Standard ~13 pages/language (see `02`). Blog scaffolded, empty at launch. |
| D4 | Pricing page | Full numeric prices for Starter + Growth (`TBD(prices)` placeholders), Enterprise = Kontakt. Free tier + trial prominent. EUR/CHF toggle. Monthly/annual toggle. |
| D5 | Hero & demo | Real product UI in hero. Paired CTA: primary „Kostenlos testen", secondary „Produkt-Tour". Ungated tour. Live STEP-upload widget = **v2 roadmap, not launch**. |
| D6 | Visual identity | App's warm-light system: sand canvas, terracotta accent, Inter, Lucide. Warm-dark full-bleed sections for rhythm. Purple exclusively for Lens/AI content. No user-facing dark-mode toggle at launch. |
| D7 | Stack | Astro + Tailwind on Vercel. Markdown/MDX content collections. No CMS. Site = own repo, apex domain `tolera.eu`. |
| D8 | Analytics/consent | Plausible (EU, cookieless) only. **No cookie banner.** No ad pixels at launch. Funnel events per `06-TECH-SPEC.md` §Analytics. |
| D9 | Comparison | One page: **vs. Paperless Parts only** (named, factual, UWG-§6-compliant, claims sourced). No Spanflug page. |
| D10 | Social proof | One deep Fechner pilot case study (permission + numbers = TBD) + substance trust strip (DSGVO, Daten in DE, XRechnung, metrisch-nativ). **No logo wall.** |
| D11 | Tour | Hand-built Astro component (no Navattic/Arcade). Spec in `08`. |
| D12 | Copy depth | Full final copy DE + EN in `04`/`05` + `STYLE-TILE.html` wireframe. Build = assembly, not drafting. |

## 6. Research-derived standards (not user decisions; treat as requirements)

- **Design:** bento feature grids; real product UI, never stock illustration; oversized headlines with variable-font Inter; monospace accents for technical values; motion subtle and CLS-free; no glassmorphism/WebGL heroes/kinetic type.
- **Conversion:** one primary CTA per page; outcome-framed CTA copy; tour CTAs above the fold + in navbar; pricing FAQ answers objections on-page; every extra second of load ≈ −7% conversion.
- **SEO/AEO:** classic SEO fundamentals + AI-readability layer (JSON-LD everywhere, llms.txt, answer-shaped H2s, AI crawlers allowed). PP already ships an LLM content API — parity is table stakes.
- **Compliance:** WCAG 2.2 AA (EN 301 549 v4 harmonizing 2026); TDDDG/DSGVO; DDG-compliant Impressum (note: W-IdNr. required from Dec 2026); no ODR-platform link (discontinued).
- **Performance:** AVIF-first images, explicit dimensions, zero-JS pages by default (Astro islands only where interactive).

## 7. Out of scope (launch)

Waitlist mechanics · fr/it locales · role/industry pages · blog content · live upload widget · CMP/cookie banner · logo wall · webinars/demo library · Spanflug comparison · dark-mode toggle · de-AT/de-CH splits.
