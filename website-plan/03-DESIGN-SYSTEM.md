# 03 — Design System (Marketing Site)

Derived from the product's design system (spec `#ui-system`), **sharpened per decisions D13/D14 (2026-07-11): "Precision warm"** — the sand canvas is replaced by near-white, the ink hardens, terracotta stays as the single accent. The app's tokens should follow suit (canvas/ink only — log in product `DECISIONS.md`). `STYLE-TILE.html` renders all of this — build to it.

## 1. Design tokens

```css
:root {
  /* Brand */
  --brand:        #CC6431;  /* terracotta — primary CTAs, links, accents */
  --brand-hover:  #B35428;
  --brand-dark:   #E07845;  /* terracotta on dark sections */
  /* Canvas & surfaces (light default) — D13 "Precision warm" */
  --canvas:       #FCFBF9;  /* near-white, faint warmth — page background */
  --surface:      #FFFFFF;  /* cards, tiles */
  --surface-2:    #F4F0E9;  /* subtle warm alt sections, code blocks, chips */
  --border:       #E7E2D9;
  /* Dark sections (warm-dark, brown-black — never blue-slate) */
  --dark-bg:      #1C1916;
  --dark-surface: #262220;
  --dark-border:  #3A342F;
  --dark-text:    #F3EFE9;
  --dark-muted:   #A89F94;
  /* Text — hardened ink (D13) */
  --text:         #1A1815;
  --text-muted:   #6B655D;
  /* Lens/AI ONLY (see §5) */
  --lens:         #7A4FD0;
  --lens-bg:      #F1EBFC;
  --lens-dark:    #A183E8;
  /* Semantic */
  --success: #1F7A4D;  --warning: #B57E00;  --error: #C2333B;
}
```

Tailwind: map these as `brand`, `canvas`, `surface`, `ink`, `lens` etc. in `tailwind.config`. No raw hex in components.

## 2. Typography

- **Family:** Inter variable (self-hosted woff2, `font-display: swap`, subset latin + latin-ext). Mono: `ui-monospace, 'SF Mono', 'JetBrains Mono', monospace` (system stack — no mono webfont download).
- **Scale (desktop / mobile):** H1 clamp(2.5rem→4.5rem), weight 600, tracking −0.02em, line-height 1.05 · H2 clamp(2rem→3rem)/600 · H3 1.375rem/600 · body 1.0625rem/400/1.65 · small 0.875rem · mono-chip 0.8125rem/500.
- **Rules:** H1s are oversized and short (max 8 words DE). One H1 per page. `text-wrap: balance` on headings. Technical values (formats, tolerances, prices, Kalk code, Werkstoffnummern) always mono — this is the "technical credibility" accent.
- German typography: real „quotes", no fake straight quotes in visible copy; non-breaking space before units (`15 Min`, `200 MB`).

## 3. Layout

- Max content width 1200 px; text measure ≤ 68ch. 12-col grid, 24 px gutter; section vertical rhythm 96–128 px desktop / 64 px mobile.
- **Section rhythm on Home:** sand → sand → sand → warm-dark → sand → sand → sand → warm-dark [CTA-BAND]. Max two dark bands per page; CTA-BAND is always dark.
- **Bento grid:** CSS grid, 12-col; large tiles 8×2 rows, small 4×1. Tiles: `--surface`, 1 px `--border`, radius 16 px, no shadow at rest; hover: translateY(−2px) + shadow-sm + border-brand — 150 ms ease-out. Whole tile is the link.
- Fully responsive 360 px → 1600 px (unlike the app, which is desktop-only — the site must not inherit that).

## 4. Components

- **Buttons:** Primary = brand bg, white text, radius 10 px, padding 12/24, hover `--brand-hover` (no scale). Secondary = transparent, 1.5 px border `--border`, text `--text`; on dark: border `--dark-border`, text `--dark-text`. Sizes md/lg. Focus: 2 px offset outline in brand — always visible (WCAG 2.2).
- **Header:** sticky, `--canvas` at 97% opacity (no backdrop blur), 1 px bottom border on scroll. Dropdowns are plain popovers (no glass).
- **Cards/tiles, FAQ accordion** (`<details>`-based, no JS), **step-flow** (numbered, connecting line), **comparison table** (sticky first column on mobile), **pricing cards** (highlighted tier: brand border + „Empfohlen" badge), **trust-strip** (icon + label row), **mono chips** (surface-2 bg, mono font — for formats/values), **footnote/source links** (Vergleich page).
- **Screenshots:** real app UI only, in a browser-chrome frame (minimal, warm gray), radius 12 px, 1 px border, AVIF + WebP fallback, explicit width/height. Never stock illustration, never fake UI. Until real screenshots exist: neutral placeholder frames labeled `TBD(screenshots)` with correct aspect ratios (16:10 hero, 4:3 tiles).

## 5. The purple rule (Lens)

Purple (`--lens`) appears **only** where Lens/AI capability is the subject: P4 accents, Lens bento tile, Lens tour steps, „Lens" name highlight. Never for generic decoration, never on CTAs. In screenshots, Lens suggestions appear at 55% opacity with accept-buttons — pick screenshots that show this; it *is* the trust story.

## 6. Motion

- Scroll-reveal: opacity 0→1 + translateY 12 px, 400 ms, `IntersectionObserver` once, `prefers-reduced-motion` disables everything.
- Step-flow draws its connecting line on scroll (CSS only). Hover states 150 ms.
- **Banned:** kinetic typography, parallax, glassmorphism/backdrop-blur, WebGL/3D scenes, autoplaying video with sound, marquee logo walls, cursor effects.

## 7. Iconography & imagery

Lucide icons, 1.5 px stroke, `--text-muted` default / `--brand` in feature contexts / `--lens` in Lens contexts. Photography only in the Fechner case study: real shop, warm grade, AVIF. Favicon/OG: wordmark on sand `TBD(logo)`; OG images per page 1200×630, generated at build (satori or static), sand bg + page H1 + wordmark.

## 8. Accessibility baked into the system

Contrast: `--text` on `--canvas` = 12.4:1 ✓; `--brand` on white = 4.6:1 ✓ (buttons ok); muted text ≥ 4.5:1 verified in STYLE-TILE. Target size ≥ 24×24 px (WCAG 2.2). Focus never obscured by sticky header (scroll-margin-top). All interactive components keyboard-operable; accordion/tour follow WAI-ARIA APG patterns. Language switch marked with `lang` + `hreflang` attributes.
