# Fulcrum — measured design facts (Design B)

Extracted **2026-07-18 from the live fulcrumpro.com DOM** (CSS custom properties + computed
styles at 1440px), not eyeballed. Exact numbers for **scale, rhythm, color, and motion**.
Fulcrum is built on **Webflow** (so motion is JS/IX2, not CSS-token easings, and many extra
webfonts are loaded but unused). **Never ship Fulcrum's licensed Gilroy font, its hexes, its
retro artefacts, or copy** — substitute **Hanken Grotesk** for Gilroy and recolor to Tolera's
kit. This deepens the measured-facts already summarized in `README.md` §"Measured facts".
Internal reference only; never deployed.

## 1. Type scale (exact, font Gilroy → substitute Hanken Grotesk)

| Role | family | size | weight | line-height | tracking | color |
|---|---|---|---|---|---|---|
| **Hero headline** (big black display) | Gilroy | **72px** | **700** | 72px (1.0) | -0.2px | #000 |
| Hero subline / lead | Gilroy | ~19px | **300** | ~1.4 | normal | #000 |
| **Section head** (the signature) | Gilroy | **51.84px** | **600** | 51.84px (1.0) | **-0.75px** | **saturated color** (green/orange/blue, one per section) |
| Nav link | Gilroy | 20px | 500 | 20px | normal | #fff on dark / #000 on light |
| Body paragraph | Gilroy | 15px | **500** | 22.5px (1.5) | -0.2px | **#2a3360** (dark navy, not pure black) |

Two things define Design B's type: **heavy 700 display headlines at ~72px with 1.0 line-height**
(tight, punchy) and **section heads at ~52px/600 each rendered in a different saturated
color**. Body text is medium-weight (500) in a **dark navy #2a3360**, not gray — warmer and
heavier than Design A's cool captions. Weights loaded: 300/400/500/600/700/800.

## 2. Palette (exact CSS variables — REPLACE hexes, keep the roles)

Core accents (the ones Tolera's Design B actually uses):
- **green** `#3dc975` · **orange** `#ff5c16` · **blue** `#3840ea` — the three rotating
  section-head colors.
- **dark-neon-yellow (lime)** `#ddf83b` — the highlighter/marker + CTA accent (the signature).
- Also: neon-yellow `#e8ff5e`, light-neon-yellow `#f4ffb0`, aqua `#82e1ff`, gold `#ffdf4f`,
  pink `#eda6ff`, light-pink `#ebc9f3`, sherbet `#94ffcb`.
- Tints (card washes): green-light `#d8f4e3`, orange-light `#ffded0`, blue-light `#d7d9fb`,
  aqua-light `#ddf3f8`, light-gold `#fbf1d1`.
- Neutrals: black `#000`, white `#fff`, slate `#3d414a`, dark-grey `#6b6b6b`, grey `#a0a0a0`,
  light-grey `#e2e2e2`, transparent-black `#000000a6`, body-navy `#2a3360`.

Fulcrum also carries a **funding-round accent set** (seed `#72fff7`, series-a `#8894ff`,
series-a2 `#fc77ff`, founding `#5bfe62`, sa2-accent `#5bfecc`) used only on its
investor/Launch pages — **Tolera doesn't need these**; documented for completeness. Keep
Design B to the green/orange/blue + lime core, recolored to Tolera's kit; **purple stays
AI-only** per our grammar.

## 3. Radius, container, buttons

- **Radius:** dominant **20px** card; also 24, 12, 10, 6, 4, 2, and **30–32px** on pills.
  (Contrast Design A, which centers on 12–16px.)
- **Container:** main content max ≈ **1296px** (~1300px), sections breathe large and device
  mockups **bleed past the container** on one edge.
- **Buttons are pills:** black bg / white text at **radius 20px**, 20px/500 label; secondary
  = white or tinted bg (`#d7d9fb` etc.) / black text at **radius 24px**, 16px label. The lime
  `#ddf83b` is the loud CTA fill on dark sections.

## 4. Shadows (soft, warm-neutral)
- Resting card: `rgba(0,0,0,.16) 4px 4px 17px` (offset down-right, single soft layer — note
  the **directional offset**, unlike Design A's centered stacks).
- Small card: `rgba(179,179,179,.2) 0 10px 14px`.
- Big floating mockup: a deep multi-layer stack
  (`0 40px 86px rgba(0,0,0,.1)` … up to `0 631px 252px rgba(0,0,0,.01)`) — the dramatic
  "device floating over the section" look.
- Colored inset glow appears on the floating callout bubbles.

## 5. Motion (Webflow IX2 — timings measured)
No CSS easing tokens (Webflow drives animation in JS). Measured transition durations in use:
**0.2s ease** is the workhorse (hovers, `all`), with **0.4s ease** opacity, **0.5s** color,
and a spread of 0.05–0.3s for micro-interactions (`background 0.12s`, `transform 0.1s`,
`height 0.2s`). Rebuild as:
- 0.2s ease default hover / 0.4s ease for larger reveals (matches `14-MOTION-AND-CSS.md`).
- **matrix3d device tilts** (perspective + rotateX/rotateY), **ScrollTrigger-style pinned**
  sections (cards slide across a board), a horizontal **"explore-more" slider**, and
  **constellation particles** on the black interstitials. Only keyframes are `spin` + `menuIn`.
- The **highlight marker** is a static inline `<span>` with a solid brand background +
  ~5px horizontal padding (emphasis, not an animated sweep).
- All of the above must be **reduced-motion-safe** and degrade to static on `md-`.

## 6. What Design B adopts vs. replaces
- **Adopt:** the type rhythm (72px/700 tight hero + ~52px/600 colored section heads with
  -0.75px tracking, 500-weight navy body), the 20px card radius + pill buttons, the
  ≈1300px container with edge-bleed mockups, the 0.2s/0.4s ease motion, and the
  soft directional shadow recipe.
- **Replace:** licensed **Gilroy → Hanken Grotesk**; every hex → Tolera's recolored
  green/orange/blue + lime; all copy/retro artefacts/certs/assets. Drop the funding-round
  palette and any ISO/ITAR/CMMC badges (honesty gates).
- **Keep the feel:** loud saturated section heads, lime highlighter emphasis, 3D-tilted
  mockups bleeding off one edge, black constellation interstitials alternating with white.
