# 04 — Home spec (`/`) — Design B

Maps Tolera's locked positioning (copy = positioning doc §3, verbatim DE/EN — never rewritten here or in code) onto Fulcrum's homepage layout archetypes. Reference frames: `docs/reference/fulcrum/home-1440-*.jpg` (see the reference README for what each teaches). Design language: 01-DESIGN-SYSTEM.

Order top to bottom.

## 0. Nav
Transparent over the hero, solidifies on scroll. Per 03 §3.

## 1. Hero — pain-led, big black display
Pattern: `home-1440-01-hero.jpg` (left-aligned huge headline + sub + CTA on the left; a tilted product mockup bleeding in from the right).
- H1 `hero` (black, left-aligned, 2 lines): hero headline C1 (positioning §3). B drops the trailing period.
- Sub-line `lead` `smoke`, with the key phrase wrapped in a **lime marker** (`<mark>`), e.g. „…kalkuliert mit **Ihren Stundensätzen**, nicht mit Durchschnittswerten."
- CTA row: primary „Demo vereinbaren" (ink pill) + tertiary „Rundgang starten →" (→ Walkthrough).
- Trust strip `small smoke`: „🇩🇪 Daten in Deutschland · DSGVO · keine Kreditkarte".
- Right/overlap: the **hero mockup** (asset P0-1) on a tilted device frame (§5.2), bleeding off the right edge, `shadow-float`. Poster until the loop exists.
- "Scroll Down ↓" vertical ticker on the far left (Fulcrum detail, optional).

## 2. „Zeichnung rein. Angebot raus." — green section + tilted tablet
Pattern: `home-1440-02-paper-is-dead-green.jpg`.
- `section` head in **green**: „Zeichnung rein. Angebot raus." with lime mark on „Angebot raus".
- `lead` sub: one sentence (the demo mechanism).
- Big tilted tablet mockup of the hero flow (STEP → Kontur → price → quote), our own technical caliper/wireframe line-art bleeding off-edge.
- One **callout bubble** (§5.3, green border) e.g. „Aus Zeichnung + STEP wird ein kalkuliertes Angebot."

## 3. „Jede Anfrage ein Angebot." — blue section + job-costing mockup + callouts
Pattern: `home-1440-03-job-costs-blue-callouts.jpg`.
- `section` head in **blue**: „Jede Anfrage ein Angebot" (lime on „Jede Anfrage").
- Body paragraph (capacity/triage + knowledge-capture theme, positioning §3).
- Large costing/pipeline mockup (asset P0-4 Kalk) bleeding off, with **two floating callout bubbles** (blue + orange) annotating it: „Ihre Sätze, Ihre Maschinen." / „Kalkuliert — nichts überschrieben."

## 4. Problem → "On-time"/capacity — orange section
Pattern: `home-1440-05-on-time-orange.jpg` + the lost-order story (positioning §3 Problem).
- `section` head in **orange**: „Der schnellste Anbieter gewinnt" (lime on „schnellste").
- The three-beat lost-order story as short stacked lines beside a scheduler/triage mockup (asset P0-2 Lens inbox).
- Kicker: „…auch wenn er nicht der günstigste ist."

## 5. „Alles verbunden" — the workflow, pinned/slider section (flagship)
Pattern: `home-1440-06-scheduler-pinned.jpg` (pinned) + `home-1440-07-connected-cards-tricolor.jpg` (card grid).
- `section` head: „Alles verbunden — von der Anfrage bis zum Auftrag."
- Represent the **5 workflow stages** (positioning §6.3: Anfrage rein · Teil verstehen · Kalkulieren · Anbieten & gewinnen · Abwickeln) as **colored-outline feature cards** (§5.4) in a 3-up row / horizontal „Mehr entdecken" slider — outlines rotate green/lime/blue. Each card: cropped stage screenshot + `h3` stage name + mono brand chip (Lens/Kontur/Kalk/Vergabe where applicable) + „Mehr → /produkt#<stage>".
- AI (Lens) card shows the purple-suggestion UI *inside its screenshot* with the Vier-Augen caption.
- Optional pinned intro where stage mockups slide across as you scroll (md+ only; reduced-motion → static grid).

## 6. Before/after numbers — honest, on a black interstitial
Pattern: black interstitial (§5.6) like `archie-1440-02` structure.
- Full-`ink` section, white heads: „Von Stunden auf Minuten pro Teil" + 3 capability stats (positioning §8.4 — **capability claims, no invented metrics**): „Minuten statt Tage bis zum Angebot" · „Jede Anfrage beantwortet" · „Ihre Sätze, nicht Durchschnitte".
- Constellation particle background. Swap to hard numbers only when golden-fixture runs justify them.

## 7. DACH trust + integrations
Pattern: colored-outline cards / logo strip.
- `section` head (green): „Gebaut für deutsche Fertiger".
- Row of trust cards: Daten in Deutschland · DSGVO & AVV · DATEV · XRechnung/ZUGFeRD · GoBD — custom 2px-stroke badges (never certification-look).
- Integration logo strip **only for logos that clear the per-logo legal check** (positioning §8.3); until then text chips.

## 8. Social proof + CTA
Pattern: `home-1440-09-testimonial-video.jpg` + a big lime CTA band.
- Testimonial slot (video or quote) — **ships empty until Fechner sign-off; never fake** (positioning §8.1). Until then, render the CTA band alone.
- Final CTA: big **lime pill** „Zeichnung rein. Angebot raus. →" + „Demo vereinbaren" + trust strip. Optionally the inline scheduling calendar (Fulcrum `home-1440-10`) — or link out.

## 9. Slots that ship EMPTY (build component, hide until content)
Testimonial video/quote (Fechner) · „Im Einsatz bei" logo strip · changelog. Never fabricate.

## Acceptance
- Side-by-side vs `home-1440-*` frames at 1440/768/390: same energy — bold colored heads, lime marks, tilted bleeding mockups, floating callouts, one black interstitial. Structure matches; **copy, assets, palette, fonts are ours**.
- Copy strings from `content/de.json`, matching positioning §3 exactly (umlauts, „" quotes, — dashes).
- Hero LCP < 2.5s (poster; video/particles lazy); CLS < 0.1; `prefers-reduced-motion` disables pin/parallax/particles.
