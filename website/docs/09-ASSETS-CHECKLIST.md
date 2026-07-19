# 09 — Asset checklist & production plan

The authoritative asset inventory is **positioning doc §7** (P0/P1/P2 tables) — this file adds only website-build specifics and the interim plan. Rule from §7: 9 of 12 P0+P1 assets come from **one well-seeded demo org in the real app** — the seeding (Fechner-style parts, German ops, realistic rates) is the critical path, not design.

## 1. Interim plan (docs → launch)

The site gets built **before** all P0 assets exist. Every media slot therefore has three states, in this order:
1. **Placeholder** — gray `mist` panel with the asset name in `mono-label` (build time).
2. **Static screenshot** — real app on seeded data, cropped per design system §5.2 (as soon as seeding lands).
3. **Motion asset** — hero loop / demo video, motion-polished (pre-launch).

Launch gate: no page ships publicly with a state-1 placeholder above the fold.

## 2. Screenshot production rules (from positioning §6.1)
- Real app UI on seeded org; German UI strings; Werkstoffnummer `1.4301`; mm; ISO 2768-m; German ops (Laserschneiden, Abkanten); `1.234,56 €`.
- Crop: no browser chrome (three-dot bar only on full-app shots), `r-xl`, export @2x PNG, target widths 2400px (full) / 1600px (crops).
- AI shots must show the purple 55% suggestions + „Übernehmen" — the Vier-Augen-Prinzip visible (don't crop it out).
- Store originals in `website/assets-src/`, optimized copies in `website/public/`.

## 3. Website-specific assets (not in §7)

| Asset | Spec | Owner |
|---|---|---|
| Wordmark + mark SVG | 02-BRAND-KIT §2 (tolerance-band concept) | Benjamin approves direction → draw as SVG in build |
| Favicon set + app icons | mark on paper, 16–512px | build |
| OG-image template | 1200×630: wordmark + two-tone claim on drafting frame | build |
| 5 stage icons + 4 brand icons + 5 trust badges | outlined 1.5px stroke, 24px grid, Lucide-compatible | build (custom SVG) |
| Flow diagram SVG | P1-9 content, line-draw animation | build |
| Stat-section chart SVG | own data-free decorative chart, `accent` | build |
| Manifesto dot ornament + finale wash | own SVG/CSS | build |
| Fonts | Inter, Inter Display, Source Serif 4, JetBrains Mono — download from official sources (OFL), self-host woff2 | build |

## 4. Blocked / legal-gated (do not ship until cleared)
- Integration logos (DATEV, SOLIDWORKS, SAP, carriers) — per-logo permission check (positioning §8.3). Until then: text cells.
- Fechner name, quote, photo — pilot success + written sign-off (§8.1).
- Trademark screening Tolera/Lens/Kontur/Kalk/Vergabe (§8.2) before print/paid reach.

## 5. Explicitly forbidden in the repo & on the site
Attio screenshots, illustrations, icons, fonts (Tiempos/Inter-Display-copies-from-their-CDN), copy, CSS. The reference frames live in `website/docs/reference/attio/` for **internal build reference only** — they are never imported by the app, never deployed, and excluded from any public bundle. Add `website/docs/` to the Next.js build's ignore surface (it's outside `app/`/`public/`, so default-safe — keep it that way).
