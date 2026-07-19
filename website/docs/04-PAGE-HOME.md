# 04 — Homepage spec (`/`)

The 7-section skeleton is **locked** in the positioning doc §4; this file maps each section onto a layout pattern from the reference frames (`docs/reference/attio/`, see its README for what each frame teaches). Copy = positioning doc §3 verbatim (DE/EN); do not rewrite copy here or in code.

Order top to bottom. Every section sits in the drafting frame (design system §5.1).

## 0. Nav (+ optional announcement bar)
Per 03-SITE-MAP §2. Announcement bar only when there's something real to announce — omit at launch.

## 1. Hero — pain-led
Pattern: `home-1440-01-hero.jpg`.
- Optional badge pill (skip at launch; slot exists).
- H1 `display-1`, centered, max 2 lines: hero headline C1 (DE/EN per positioning §3).
- Sub-line `body-lg` `ink-soft`, centered, max 2 lines.
- CTA row: secondary „Demo ansehen" (anchor to §3) + primary „14 Tage kostenlos testen".
- Trust strip `small mute` under CTAs: „🇩🇪 Daten in Deutschland · DSGVO · keine Kreditkarte".
- Below, overlapping the fold: **hero loop** media card (asset P0-1: STEP → Kontur wireframe → features highlight → price counts up → quote PDF) in `r-xl` card, `shadow-media`, minimal three-dot bar, on a soft `mist` radial wash. Poster image until video exists (see 09-ASSETS-CHECKLIST interim plan).

## 2. Problem — the lost-order story
Pattern: text-led, minimal visuals; use the two-tone intro style of `home-1440-03-platform-intro.jpg` (large claim, first line `ink`, rest `mute`) instead of Attio's product-heavy variant.
- Opener `display-2` two-tone: „Der Auftrag ging an den, der zuerst geantwortet hat." + gray continuation.
- The three beats (RFQ arrives → the week happens → competitor answers first) as three hairline-separated columns (`h3` + 2-line `mute` body), icons outlined-style; no screenshots here.
- Kicker line `claim` centered: „Der schnellste Anbieter gewinnt — auch wenn er nicht der günstigste ist."

## 3. Demo video — „Zeichnung rein. Angebot raus." (`#demo`)
Pattern: `home-1440-11-selfbuilding.jpg` (badge + centered display-2 + big media card).
- Section badge „Demo" (accent-soft chip), H2 `display-2`: the slogan; sub-line one sentence.
- 60–90s uncut demo video (asset P0-6) in the big media card; visible timestamp — honesty is the point. Click-to-play with sound; poster until the video exists.

## 4. Before/after numbers
Pattern: `home-1440-18-scale-stats.jpg` (stat block).
- Honest pre-pilot version (positioning §8.4): the big line is „**Von Stunden auf Minuten pro Teil.**" with 3 capability stats (e.g. „Minuten statt Tage bis zum Angebot" · „Jede Anfrage beantwortet" · „Ihre Stundensätze, nicht Durchschnittswerte") — capability claims, **no invented metrics**. Swap to hard numbers only when golden-fixture runs produce a defensible measurement.
- Background: thin vertical bar pattern + one `accent` line chart (own SVG).

## 5. „Jede Anfrage ein Angebot." — the workflow tabs (flagship section)
Pattern: sticky-rail tab section, `home-1440-03`–`home-1440-10` frames.
- Section intro `display-2` two-tone: „Jede Anfrage ein Angebot." + gray continuation on capacity/triage.
- Left sticky rail = the **5 workflow stages** (positioning §6.3): Anfrage rein · Teil verstehen · Kalkulieren · Anbieten & gewinnen · Abwickeln.
- Each stage panel: two-tone `claim` (product-as-actor formula: active verb + „mit Ihren Daten/Sätzen" + control clause where AI appears) → big cropped UI shot (assets P0-2..5, P1-8) → one pair of sub-features (h3 + 2-line body, hairline-split).
- Brand names surface here: stage panels carry a small mono chip (Lens / Kontur / Kalk / Vergabe) linking to the stage page. AI stages show the purple-suggestion UI *inside the screenshot* with the Vier-Augen line as caption: „KI im Vier-Augen-Prinzip: Tolera schlägt vor — Sie entscheiden."
- Secondary theme (knowledge capture / key-person risk) is the closing claim of stage 3 (Kalkulieren).
- Each panel ends with tertiary link „Mehr zu <Stufe> →" to its platform page.

## 6. DACH trust + integrations
Pattern: icon feature row (5-col, `home-1440-13-context-cards.jpg` structure — but light theme) + logo band (`home-1440-02` bottom).
- H2 two-tone: „Gebaut für deutsche Fertiger." + gray continuation.
- 5 hairline cells: Daten in Deutschland · DSGVO & AVV · DATEV-Export · XRechnung/ZUGFeRD · GoBD — outlined custom badges (never certification-look, 09-ASSETS-CHECKLIST).
- Logo band below: DATEV, SOLIDWORKS, SAP Business One, XRechnung/Peppol, DHL/DPD/GLS — **only logos that clear the per-logo legal check** (positioning §8.3); standards marks first. Until cleared: text-only cells in `mono-label`.
- Optional flow diagram (asset P1-9): E-Mail · STEP · Zeichnung · Stückliste → Tolera → Angebot · DATEV · XRechnung, line-draw on scroll.

## 7. Pricing teaser → CTA
Pattern: pricing cards condensed (`pricing-1440-01-hero-tiers.jpg`) + final CTA.
- H2: „Transparente Preise." + one-line sub; 3 compact tier cards (Starter ~€299 · Growth ~€599–799 · Enterprise auf Anfrage), annual-discount note, link „Alle Details → /preise".
- Final CTA band (light, ink-on-paper — deviation from Attio's dark): `display-2` „Zeichnung rein. Angebot raus." + primary CTA + trust strip repeat.

## 8. Slots that ship EMPTY (build the component, hide until content exists)
- Serif giant testimonial (Fechner GF quote) — after §5. **Never fake an interim one.**
- „Im Einsatz bei"-strip in hero — after Fechner sign-off.
- Changelog section (P2-13) — post-launch.

## Acceptance
- Side-by-side at 1440/768/390 against the reference frames: same section rhythm, hairline system, sticky-rail behavior, two-tone claims. (Structure matches; copy, assets, palette are ours.)
- All copy strings from `content/de.json` and match positioning §3 exactly (umlauts, „" quotes, — dashes).
- Hero LCP < 2.5s (poster image, video lazy); CLS < 0.1; reduced-motion clean.
