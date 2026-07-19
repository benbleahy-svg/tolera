# 01 — Design System B (tokens & layout language) — "Fulcrum-derived"

**This is Design B**, a second, deliberately *different* visual direction for the Tolera marketing site, to A/B test internally against Design A (the Attio-derived pack in `website/`). Same product, same content, same positioning doc — **different skin and information architecture.**

**Purpose:** an *original token system* derived from studying fulcrumpro.com (reference frames in `docs/reference/fulcrum/`). We rebuild the structure, energy and polish from scratch — we never copy Fulcrum's CSS, assets, fonts-we-don't-license (they use **Gilroy** — we substitute an open font), illustrations, or copy. Structural measurements are facts and are recorded here; everything is implemented as our own Tailwind tokens.

**Where B differs from A in one line:** A is quiet, light, hairline-precise, "technical drawing." **B is loud, high-contrast, bold — heavy black display type, big saturated colored section headers, 3D-tilted product mockups, floating callout bubbles, lime highlighter marks, and full-black interstitial sections.** If A whispers precision, B shouts momentum.

**Reference viewport for all values: 1440px.** Scale with `clamp()`.

---

## 1. Type

Fonts (all free, self-hosted via `next/font/local`, subset `latin` + `latin-ext` for umlauts):

| Role | Font | Notes |
|---|---|---|
| Display + headings + UI | **Hanken Grotesk** (variable) | Open substitute for Fulcrum's Gilroy — geometric-humanist, warm, heavy weights read almost identical. Weights 400/500/600/700/800 |
| Retro / "old software" + technical micro-labels | **JetBrains Mono** | The Why-page "before" columns and small technical chips |

Rationale: Fulcrum's whole personality is one heavy geometric sans (Gilroy) at many weights. We reproduce that with **one** open family (Hanken Grotesk) so the licensing dependency is zero. Swappable in one place; token names stay stable. (Alternatives if the team prefers: Onest, Sora, Mona Sans.)

Type scale (desktop → mobile via clamp):

| Token | Size / line-height | Weight | Letter-spacing | Use |
|---|---|---|---|---|
| `hero` | 96 / 92 → 44/46 | 700 | -2.5% | Page hero headline, one per page. Black. |
| `hero-xl` | 116 / 104 → 52/54 | 700 | -3% | Why-page-style set-pieces on black |
| `section` | 52 / 52 → 34/36 | 600 | -0.75px (as measured) | **The signature colored section header** (§5.1) |
| `h3` | 26 / 32 → 22/28 | 600 | -0.5% | Card titles, sub-feature heads |
| `lead` | 22 / 32 → 18/26 | 400 (light 300 ok) | 0 | Hero sub-line, section intro paragraphs |
| `body` | 18 / 27 | 400 | 0 | Default text |
| `small` | 16 / 22 | 500 | 0 | Captions, labels, footer links |
| `nav` | 20 / 20 | 500 | 0 | Nav links (as measured) |
| `mono-retro` | 20 / 28 (mono) | 400 | 0 | "Old software" columns, Why page |
| `chip` | 14 / 16 | 600 | +2% | Pills, "1 OF 7" badges, eyebrows |

Rules: headlines are sentence case (Fulcrum uses no trailing period on big heads — **B drops the period**, unlike A). Hero can be 2–3 short lines. Section heads are 2–4 words, colored.

## 2. Color

True black + white base with **four saturated brand accents** used boldly (not sparingly — the opposite of A). Semantic Tailwind tokens.

| Token | Hex (measured) | Use |
|---|---|---|
| `ink` | `#000000` | True black — text, black sections, primary pills. Bolder than A's near-black |
| `paper` | `#FFFFFF` | Base background |
| `ash` | `#F4F5F7` | Alt section background, mockup ground |
| `smoke` | `#6B7075` | Secondary text |
| `green` | `#3DC975` | Section head color #1, "live/ok" states, outline cards |
| `orange` | `#FF5C16` | Section head color #2, energy/urgency accents |
| `blue` | `#3840EA` | Section head color #3, links, primary interactive |
| `lime` | `#DDF83B` | **The signature**: highlighter marker behind headline words, big CTA buttons, section bands. High-vis chartreuse |
| `green-wash` | `#F2FBEF` → transparent | Pale card fills (Why "after" cards) |
| `lav-wash` | `#EEF0FF` | Callout-bubble fills / lavender tint |
| `ai-purple` | `#7C3AED` | **AI suggestions only** — carried over from positioning §6 & Design A. Purple never appears in marketing chrome; only inside product screenshots as the „KI schlägt vor" grammar |
| `retro-gray` | `#C0C0C0` / `#3A3F8F` | Win-95 "old software" chrome on the Why page only |

Section-color rotation: successive big sections cycle **green → orange → blue** for their headers (see reference `home-1440-02/03/05`). Lime is the punctuation, used on ≤1 element per viewport (a highlight swipe or one CTA). Black sections are intentional full-bleed interstitials.

## 3. Space, grid, containers

- Base unit 4px. Section vertical padding **128px** desktop / 72px mobile — B breathes bigger than A. Hero: 120 top.
- Content container: **max-width 1300px**, 32px gutters, 12-col grid, 32px gap.
- Mockups deliberately **bleed past the container** on one side (signature move — see `home-1440-03/06`).
- Breakpoints: 1440 (ref), `lg` 1024, `md` 768, `sm` 390.

## 4. Radii, borders, shadows

- Radii: `r-sm` 4, `r-md` 12, `r-card` 20 (dominant — measured 65× uses), `r-lg` 24, `r-pill` 9999 (buttons, chips, bubbles).
- Borders: **1.5px colored outlines** are the signature card treatment — `green`/`lime`/`blue`/`orange`/`ink`. Callout bubbles: 1px white or 1.5px color.
- Shadows (own values, generous — B is bolder than A):
  - `shadow-float` (tilted mockups): `0 40px 80px -20px rgba(0,0,0,.18), 0 8px 24px -8px rgba(0,0,0,.10)`
  - `shadow-bubble` (callouts): soft colored glow, e.g. `0 0 24px -4px rgba(56,64,234,.25)` + `0 2px 8px rgba(0,0,0,.06)` (color matches the bubble border)
  - `shadow-card`: `0 4px 4px rgba(0,0,0,.04), 0 1px 3px rgba(0,0,0,.08)`

## 5. The layout language (what makes it feel "Fulcrum")

Six devices carry the personality. Every page uses several.

### 5.1 Bold colored section headers + lime marker
Each major section opens with a `section` head (52px/600) in a **saturated color** that rotates green→orange→blue down the page. Key words get a **lime highlighter swipe** — a `lime` rectangle behind the text that animates in left-to-right on scroll (see `why-1440-02` "Real, Human", `why-1440-05` "See and learn more"). Implement as an inline `<mark>` with an animated `background-size` sweep. This is B's answer to A's two-tone claim.

### 5.2 3D-tilted device mockups
Product UI shown on tilted iPad/desktop frames — `perspective(1600px) rotateY(-12deg) rotateX(4deg)` range (measured as `matrix3d`), `r-lg`, `shadow-float`, often **overlapping and bleeding off one edge**, connected to callouts by thin 1px leader lines. Cropped app screenshots (DACH-native data per positioning §6.1) sit inside a rounded device bezel. See `home-1440-01/03/06`.

### 5.3 Floating callout bubbles
Rounded-rect bubbles (`r-lg`, 1.5px colored border, `shadow-bubble` colored glow, `lav-wash`/tint fill) holding **one short claim**, pointing at a mockup with a little tail. Used to annotate the product like sticky notes. See `home-1440-03` (blue/orange bubbles). B uses these where A uses captions.

### 5.4 Colored-outline feature cards
White cards, **1.5px colored outline** (rotating green/lime/blue), `r-card`. Anatomy: cropped product screenshot on top → `h3` title → one line → **action link "verb →"** (e.g. "Los geht's →"). Displayed in 3-up rows or a horizontal slider. See `home-1440-07`.

### 5.5 Old-vs-New split (the Why page signature)
Two columns per row: **left = the "before"** rendered as an intentionally ugly retro artifact (Win-95 dialog, serif body, mono, gray chrome, blue error box) representing the status quo; **right = the "after"** as a bright card with a `green-wash` fill and a lime-marked colored header + `Learn more →`. Devastatingly on-brand for Tolera's pain-first story (Excel/tribal-knowledge vs Tolera). See `why-1440-02/03/04`.

### 5.6 Full-black interstitial sections
Full-bleed `ink` sections with white heads and an **animated constellation** (drifting dots + faint connecting lines) or particle field behind — used for hero set-pieces and section breaks (`why-1440-01`, `archie-1440-02/05`). Big lime CTA pills sit inside these.

## 6. Components (build in this order)

1. **Buttons** — primary: `ink` pill, white text, `r-pill`, h-44, `nav`-weight; hover: subtle scale 1.02 + shadow, 0.2s ease. **Lime CTA**: big `lime` pill, `ink` text, oversized (h-64, 22px) for section CTAs ("Demo ansehen →"). Secondary: white pill, 1.5px `ink` border. Tertiary: text + `→` (translate 3px on hover).
2. **Chip / badge** — pill, small caps mono-ish, e.g. „LIVE-DEMO", „1 VON 7", section eyebrows.
3. **Nav bar** — transparent over hero, solidifies to `paper` on scroll; logo left; center links (Produkt ▾, KI, Warum, Start, Neues); right: DE/EN toggle + „Demo vereinbaren" (ink pill). h-72. On black pages, nav is white. Mega-menu: full-width white panel, 3-col icon grid + a dark bottom utility bar (see `nav-mega-product`).
4. **Tilted mockup frame** (§5.2) — device bezel + cropped screenshot + optional autoplay muted loop.
5. **Callout bubble** (§5.3).
6. **Outline feature card** (§5.4) + a **horizontal card slider** ("Mehr entdecken") with dot nav + arrows (Fulcrum's `explore-more-slider`).
7. **Colored section header w/ lime marker** (§5.1).
8. **Old-vs-New split row** (§5.5) — retro "before" component (a small library of fake-legacy artifacts: Excel grid, Win-95 dialog, error box, blue screen) + bright "after" card.
9. **Black interstitial + constellation canvas** (§5.6) — lightweight `<canvas>` particle field, `prefers-reduced-motion` → static.
10. **Stat / logo strip** — bold numbers or (legally-cleared) integration marks.
11. **Big serif-free pull quote / testimonial** — ships empty until real (positioning §8.1; **never fake**).
12. **Footer** — 4 columns (Produkt / Entdecken / Ressourcen / Wechseln-equivalent), social row, `Fulcrum Series A2`-style tagline slot → Tolera's own. Light.
13. **Embedded interactive tour** wrapper (Walkthrough page) — full-viewport iframe/host + step-picker overlay.

## 7. Iconography & illustration

- UI icons: **Lucide**, but heavier stroke (2px) to match Fulcrum's bolder feel; brand/module icons custom-drawn in the same weight.
- Signature decorative line-art: technical sketches (calipers, gears, rulers) as faint 1px outlines bleeding off section edges (see `home-1440-02`, `why-1440-03`). For Tolera: caliper / sheet-metal / STEP-wireframe motifs — our own SVGs.
- The "old software" retro artifacts (Why page) are our own crude recreations — do **not** screenshot real legacy products.

## 8. Motion (Fulcrum is motion-forward — the user asked to note this)

Measured: transitions mostly **0.2s ease** (hovers), some **0.4s ease** (larger), Webflow + ScrollTrigger stack. Reproduce the *feel* with Motion (framer-motion) + a lightweight scroll lib:

- **Lime marker sweep**: `background-size: 0% 100% → 100% 100%` over 500ms `ease-out` when the head enters view.
- **Tilted-mockup parallax**: mockups drift/rotate a few degrees on scroll (subtle `rotateY` + `translateY`), tied to scroll progress.
- **Callout bubbles**: fade + pop (scale .92→1) + colored glow, staggered as the section enters.
- **Pinned sections**: the flagship "everything connected" / scheduler section pins while cards slide across (Fulcrum's `pin-spacer`). Use a ScrollTrigger-style pin; keep it optional/`md+` only.
- **Horizontal "Mehr entdecken" slider**: snap scroll + dot/arrow nav.
- **Constellation**: slow drifting particle canvas on black sections.
- **Hovers**: buttons scale 1.02 / cards lift 2px + shadow step, 0.2s ease.
- **Reduced motion**: disable pin, parallax, marker-sweep-as-motion (show marker statically), particles → static; keep opacity fades. Honor `prefers-reduced-motion` everywhere.

## 9. Locale & formatting

Identical to Design A: German-first (`de` at `/`, `en` at `/en`), Sie-Form, `1.234,56 €`, mm/kg, German-UI screenshots on both locales. Copy from the positioning doc; strings in `content/*.json`, never hard-coded.
