# 02 — Sitemap & Page Specs

## 1. URL structure

German at root; English mirror under `/en/` with translated slugs. Trailing-slash-free. All pages static.

| # | DE | EN | Template |
|---|---|---|---|
| P1 | `/` | `/en/` | home |
| P2 | `/produkt/kalkulation` | `/en/product/quoting` | feature |
| P3 | `/produkt/geometrie` | `/en/product/geometry` | feature |
| P4 | `/produkt/lens` | `/en/product/lens` | feature |
| P5 | `/branchen/cnc-zerspanung` | `/en/industries/cnc-machining` | process |
| P6 | `/branchen/blechbearbeitung` | `/en/industries/sheet-metal` | process |
| P7 | `/branchen/rohrlaser` | `/en/industries/tube-laser` | process |
| P8 | `/branchen/drehteile` | `/en/industries/turning` | process |
| P9 | `/preise` | `/en/pricing` | pricing |
| P10 | `/tour` | `/en/tour` | tour |
| P11 | `/vergleich/paperless-parts` | `/en/compare/paperless-parts` | compare |
| P12 | `/unternehmen` | `/en/company` | company |
| P13a–c | `/impressum` · `/datenschutz` · `/agb` | `/en/imprint` · `/en/privacy` · `/en/terms` | legal (prose) |
| P14 | `/blog` (scaffold, hidden from nav until content exists) | `/en/blog` | blog index |
| — | `/404` | `/en/404` | error |

## 2. Global navigation

**Header (sticky, sand bg, blur-free):** Logo (wordmark `TBD(logo)` — set „Tolera" in Inter SemiBold until logo exists) · Produkt (dropdown: P2/P3/P4 + „Produkt-Tour") · Branchen (dropdown: P5–P8) · Preise · Vergleich → P11 · right side: language switch `DE | EN` · secondary button „Produkt-Tour" → P10 · primary button „Kostenlos testen" → `https://app.tolera.eu/sign-up?utm_source=website` (const `SIGNUP_URL`).
Mobile: hamburger → full-screen panel, same order, CTAs pinned bottom.

**Footer (warm-dark `#1C1916`):** 4 columns — Produkt (P2–P4, P10) · Branchen (P5–P8) · Unternehmen (P12, P11, Blog when live, Kontakt-mailto) · Rechtliches (P13a–c). Below: trust strip „🇩🇪 Daten in Deutschland `TBD(hosting-region)` · DSGVO-konform · Keine Kreditkarte für den Test" + language switch + © Tolera `TBD(entity)`.

## 3. Shared conversion blocks

- **[CTA-BAND]** Full-width warm-dark band, used as last section on every content page: H2 „In 15 Minuten zum ersten Angebot." + primary „Kostenlos testen" + secondary „Produkt-Tour ansehen" + microcopy „14 Tage voller Zugriff · keine Kreditkarte · DSGVO-konform".
- **[TRUST-STRIP]** Inline row of 4 substance markers (icons + short label): Daten in Deutschland · DSGVO & AVV · XRechnung/ZUGFeRD-ready · Metrisch & Werkstoffnummern-nativ.
- **[TOUR-TEASER]** Card linking to P10 with first tour frame as preview image, label „2 Minuten, ohne Anmeldung".

## 4. Per-page section specs

Copy for every block: `04-CONTENT-DE.md` / `05-CONTENT-EN.md` under matching IDs (e.g. `P1-hero`).

### P1 Home
1. `P1-hero` — Split hero. Left: H1 + subline + paired CTAs + microcopy. Right: product screenshot composition (quote detail with Lens panel + 3D viewer visible, `TBD(screenshots)`), slight parallax-free tilt, AVIF. Below: [TRUST-STRIP].
2. `P1-thread` — "Der Weg einer Anfrage" — 5-step horizontal flow (E-Mail → Lens → Geometrie → Kalk → Angebot), each step icon + 1 sentence; steps link to P4/P3/P2. This is the golden thread, visualized.
3. `P1-bento` — Bento grid, 6 tiles (2 large, 4 small): Kalkulation/Kalk (large, → P2) · Geometrie & DFM (large, → P3) · Lens E-Mail/Zeichnungs-Extraktion (→ P4, purple accents) · Anforderungsprüfung (→ P4) · Digital Quote & Checkout (→ P2) · Dateiformate (STEP, JT, DXF… → P3). Real UI crops per tile; hover reveals 1-line detail.
4. `P1-dach` — Warm-dark band: „Für DACH gebaut, nicht übersetzt." 2×2: EUR/CHF & MwSt/Reverse-Charge · XRechnung/ZUGFeRD/QR-Rechnung · Werkstoffnummern & DIN/EN · DSGVO/GoBD/EU-Exportkontrolle.
5. `P1-selfserve` — Contrast section: „Ohne Einführungsprojekt." 3 columns Heute testen / Eigene Logik in Kalk / Support auf Deutsch — implicit anti-PP framing, links P11.
6. `P1-case` — Fechner case study teaser: quote + shop photo `TBD(fechner)`; numbers only when C5 resolved.
7. `P1-tour` — [TOUR-TEASER] wide.
8. `P1-faq` — 5 questions (accordion, FAQPage JSON-LD): Was kostet Tolera? · Welche Dateiformate? · Wo liegen die Daten? · Wie lange dauert die Einrichtung? · Ersetzt Tolera mein ERP?
9. [CTA-BAND].

### P2 Kalkulation (Kalk + workflow + outputs)
1. `P2-hero` — H1 + sub + CTAs + screenshot (costing view, quantity breaks).
2. `P2-workflow` — Quote lifecycle: Anfrage → Kalkulation → Prüfung → Versand → Auftrag; multi-quantity breaks, margin per category.
3. `P2-kalk` — Kalk section, mono-styled formula snippet (real Kalk syntax), „Formeln, die Sie lesen können" — transparency vs blackbox.
4. `P2-outputs` — Digital Quote & A4-PDF (white-label, MwSt correct), buyer checkout (PO/SEPA/QR-Rechnung), e-invoicing readiness.
5. `P2-review` — Freigabestufen (Sales/Technik/Material/Exec) — team workflow.
6. `P2-faq` (3 Qs) · [TOUR-TEASER] · [CTA-BAND].

### P3 Geometrie & DFM (GeometryService + viewer + files)
1. `P3-hero` — screenshot: 3D viewer with feature highlights.
2. `P3-interrogation` — what's extracted per family (dimensions, volume, sheet thickness, bends, machined features) — mono value chips.
3. `P3-dfm` — DFM warnings catalogue teaser: „Fertigungsprobleme sehen, bevor sie teuer werden."
4. `P3-viewer` — 3D + PDF viewer (measure, section, face-pick; annotation).
5. `P3-files` — file-format matrix (tiered per C6), 200 MB, Baugruppen/BOM.
6. `P3-faq` (3 Qs) · [TOUR-TEASER] · [CTA-BAND].

### P4 Lens (AI: ingest, extraction, review rules)
Purple accent rules apply (03 §5). Must state the trust posture explicitly: suggestion-only, click-to-source, never auto-priced, never invented.
1. `P4-hero` — screenshot: Found-in-Files panel over a real drawing.
2. `P4-ingest` — `ihr-betrieb@rfq.tolera.eu`: forward an email → draft quote with parsed positions/contacts/files.
3. `P4-extract` — Zeichnungen & Prints: GD&T, Toleranzen, Oberflächen, Zertifikate — grouped findings, jump-to-source.
4. `P4-rules` — Anforderungsprüfung: rule chips (Geometrie/Text/GD&T/Datei), review items, „nie wieder eine kritische Anforderung übersehen".
5. `P4-trust` — „KI, die Vorschläge macht — nicht Entscheidungen." The AI-Governor pattern, GDPR/EU routing.
6. `P4-faq` (3 Qs) · [TOUR-TEASER] · [CTA-BAND].

### P5–P8 Process pages (shared template, differentiated content)
1. `Px-hero` — process-specific H1 (SEO head term), UI screenshot in process context.
2. `Px-pains` — 3 pains of quoting this process.
3. `Px-features` — 4 feature tiles mapped to the process (each links P2–P4).
4. `Px-specifics` — process-specific extraction/DFM values table (mono chips).
5. `Px-faq` (3 Qs, process-specific, FAQPage JSON-LD) · [CTA-BAND].
Head terms: P5 „CNC Kalkulationssoftware" · P6 „Kalkulationssoftware Blechbearbeitung" · P7 „Rohrlaser Angebotssoftware" · P8 „Kalkulation Drehteile Software".

### P9 Preise
1. `P9-hero` — H1 „Preise. Öffentlich." + currency toggle EUR/CHF + billing toggle monatlich/jährlich (−`TBD(annual-discount)`%).
2. `P9-tiers` — 4 cards: **Free** (0 €, 5 Angebote/Monat, C4) · **Starter** `TBD(price-starter)` · **Growth** `TBD(price-growth)` (highlighted „Empfohlen") · **Enterprise** („Kontakt"). Feature matrix per tier `TBD(tier-features)` — structure now, gates from product feature-gate list.
3. `P9-trial` — trial explainer band: 14 Tage, voller Zugriff, keine Kreditkarte, endet automatisch (kein Abo-Fallenmuster).
4. `P9-faq` — 6 Qs (VAT/reverse-charge via Paddle, CHF billing, Kündigung, Datenexport, AVV, Rabatt Jahreszahlung). FAQPage JSON-LD.
5. [CTA-BAND].

### P10 Tour
Full-viewport tour component (`08-TOUR-SPEC.md`), ungated. Below: paired CTAs + 3-bullet „Was Sie gesehen haben" summary + link P9.

### P11 Vergleich: Paperless Parts
Factual, sourced, fair — UWG §6: objective, verifiable, no denigration. Every PP claim carries a footnote link to PP's public source, retrieved-date noted.
1. `P11-hero` — H1 „Tolera vs. Paperless Parts" + one-paragraph framing (respectful: PP defined the category in the US; Tolera is built for DACH self-serve).
2. `P11-table` — comparison table: Einführung (self-serve <1 Tag vs 8–12 Wochen C2) · Preistransparenz (öffentlich vs auf Anfrage) · Einheiten (metrisch-nativ vs imperial-first) · Währung/Steuer (EUR/CHF, MwSt, Reverse-Charge vs USD/US-Tax) · E-Rechnung (XRechnung/ZUGFeRD vs —) · Datenstandort (DE/EU `TBD(hosting-region)` vs US/GovCloud) · Sprache (Deutsch-first vs Englisch) · Exportkontrolle (EU-Dual-Use vs ITAR) · Kalkulationslogik (Kalk selbst editierbar vs PP-Team konfiguriert).
3. `P11-fit` — „Wann Paperless Parts die bessere Wahl ist" (US/ITAR shops, imperial supply chains) — honesty section, builds credibility.
4. `P11-migrate` — Umstieg: parallel testen im Free-Tier.
5. [CTA-BAND].

### P12 Unternehmen
Mission (self-serve quoting for the Mittelstand), founder story `TBD(founder-bio)`, „gebaut mit einem echten Betrieb" (Fechner), contact block (email `TBD(contact-email)`, address from Impressum), no careers section at launch.

### P13 Legal
Prose templates in `07-SEO-COMPLIANCE.md` §4 with `TBD(entity)` fields. Noindex: no; plain layout; German + English versions (English marked as convenience translation, German governs).

## 5. Internal linking rules

Every feature page links ≥2 process pages contextually and vice versa. Every page except legal ends in [CTA-BAND]. Vergleich linked from Home `P1-selfserve` and footer only (not header-primary). Blog hidden until first post.
