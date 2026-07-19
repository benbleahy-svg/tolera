# 09 — Assets checklist & production plan (Design B)

Shares the same underlying asset inventory as Design A (positioning doc §7, P0/P1/P2) — the **product screenshots are identical assets**; only the framing differs (A = flat cropped cards; B = tilted device frames + callout bubbles). Producing screenshots once serves both A/B builds.

## 1. Interim states (docs → launch)
Every media slot has three states: (1) `ash` placeholder with the asset name in mono; (2) static cropped screenshot on a tilted frame; (3) motion (hero loop / demo video / interactive tour). No page ships publicly with a state-1 placeholder above the fold.

## 2. Screenshot rules (positioning §6.1)
Real app, seeded org, German UI, Werkstoffnummer `1.4301`, mm, ISO 2768-m, German ops, `1.234,56 €`. AI shots show purple 55% suggestions + „Übernehmen". Export @2x. B additionally needs each hero shot to work **tilted** (leave head-room around the UI so the 3D rotation doesn't clip content).

## 3. Design-B-specific assets (not in §7, and different from Design A)

| Asset | Spec |
|---|---|
| Fonts | **Hanken Grotesk** (all weights) + **JetBrains Mono**, OFL, self-host woff2 (substitute for Fulcrum's Gilroy) |
| Wordmark + mark SVG | 02-BRAND-KIT (shared concept with A) incl. white-on-black variant |
| Device bezels | iPad + desktop rounded frames as SVG/CSS to mount tilted screenshots |
| Callout-bubble component art | tails + colored glow (CSS, no image) |
| Lime highlighter mark | CSS `<mark>` sweep (no image) |
| Constellation particle field | lightweight `<canvas>` for black sections |
| Retro "old-software" artifacts | **our own crude mocks** for the Warum page: fake spreadsheet, Win-95 dialog, error box, overflowing-inbox, "employee unavailable" — original SVG/HTML, never real competitor screenshots |
| Technical line-art | caliper / gear / sheet-metal / STEP-wireframe outlines bleeding off section edges (our SVGs) |
| Module icons | 5 stage + 4 brand icons, 2px stroke (heavier than A's 1.5px) |
| OG images | 1200×630, black bg + lime-marked head |
| Interactive tour | Walkthrough embed or scripted click-through (08) |

## 4. Blocked / legal-gated
Integration logos (per-logo permission, positioning §8.3) · Fechner name/quote/photo (sign-off, §8.1) · trademark screening Tolera/Lens/Kontur/Kalk/Vergabe (§8.2). **Do not** put ITAR/CMMC or any compliance Tolera doesn't hold on the KI page (see 06).

## 5. Forbidden
Fulcrum's Gilroy font, assets, illustrations, retro artefacts, copy, or CSS. Reference frames in `docs/reference/fulcrum/` are **internal build reference only** — never imported by the app, never deployed, kept outside `app/`/`public/`. Grep-gate before any PR/deploy: no bundle file references `reference/fulcrum` and no Fulcrum asset/string ships.
