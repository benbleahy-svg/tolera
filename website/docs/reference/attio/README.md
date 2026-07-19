# Attio reference frames — index

> 📄 **[VISUAL-REFERENCE.html](./VISUAL-REFERENCE.html)** — every screenshot below plus the measured tokens (type scale, live color swatches, spacing, shadows, motion) in one browsable page. Open it in a browser. See also **[MEASURED-FACTS.md](./MEASURED-FACTS.md)** and the full-page stitches in **[fullpage/](./fullpage/)**.

Captured 2026-07-17 from attio.com at ~1440px (frames 11+ at ~1568px after a window resize — treat as equivalent) and 390px. **Internal build reference only: study structure, rhythm, spacing, motion. Never copy assets, copy, CSS, fonts or illustrations; never deploy these files.** What we take vs. deliberately change is defined in `01-DESIGN-SYSTEM.md` (esp. §5 layout language + the light-theme/purple deviations).

## Homepage (`home-1440-01` … `home-1440-22`)
| Frames | What to study |
|---|---|
| 01 | Hero anatomy: badge pill → centered H1 → sub → CTA pair → product mockup card breaking the fold |
| 02 | Hero media bottom + **logo grid** with hairline cells + hover `↗` |
| 03 | Section intro pattern: badge + two-tone display-2 (black first sentence, gray rest); **sticky left rail** appears (5 tabs, inactive faded) |
| 04–10 | The sticky-rail tab section through all 5 stages: per-stage two-tone claim, full-bleed UI shots, sub-feature pairs with hairline splits, kanban/table/chat UI examples |
| 11 | "Self-building" pattern: badge + centered display-2 + big media card (our demo-video section) |
| 12–14 | Dark sections (context layer, 5-col icon cells, ecosystem logos, SDK/API) — **we rebuild these light**; study structure only |
| 15–16 | Giant serif testimonial on dot pattern (name + role below) |
| 17 | (transition frame) |
| 18 | **Stat block**: display-2 numbers with thin left rules + background line chart |
| 19 | Customer-story cards: logo tab row, category eyebrow, metric headline black + gray, photo card |
| 20 | Changelog 4-col + newsletter row |
| 21 | Dark final CTA band (we do light) |
| 22 | Footer link columns under eyebrow labels (we do light) |

## Pricing (`pricing-1440-01` … `08`)
01 hero + toggle + 4 tier cards (highlight = colored border + chip) · 02 card CTAs + logo band + **sticky compare header** appearing · 03–07 comparison tables by category (check/dash cells, row groups, sticky tier header) · 08 footer.

## Customers (`customers-1440-01` … `05`)
01 hero (badge, display-1, sub on dot pattern) + logo grid · 02 featured story card (logo, eyebrow, metric headline, photo right) · 03–04 alternating story grid · 05 footer.

## Manifesto (`manifesto-1440-01` … `05`)
01 dictionary-definition hero + dot ornament · 02 serif essay, narrow column, margin scroll-dots · 03 numbered `[1]`-`[4]` principles · 04 quiet closing · 05 expressive glowing finale (we keep the idea, tone it to our palette).

## Platform page (`platform-data-1440-01` … `08`)
01 hero: badge + display-1 + floating object cards + CTAs · 02 full app shot with three-dot bar · 03 two-tone H2 + `[01]`/`[02]` numbered demo panels on dot pattern · 04 giant serif quote mid-page · 05 feature pair rows with small UI crops · 06 three-up icon feature row · 07 enrichment card trio · 08 footer.

## Nav & mobile
`nav-dropdown-platform` / `nav-dropdown-resources`: mega-dropdown anatomy (grouped columns, eyebrow labels, icon + title + one-liner rows, right utility column). `mobile-390-01…05`: hero stack, horizontal pinned tab bar, kanban horizontal scroll, footer stack.

## Measured facts (from computed styles, 1440-class viewport)
H1 64/60.8 w600 ls-2% · H2 40/44 w500 ls-1% · display 96 w600 ls-2.4% · body 16/22 (Inter, w500 in UI chrome) · eyebrow 12/16 w600 ls+6% · buttons 14 w500, radius 10, dark bg + inset top-light + soft drop · radii in use: pill/8/10/12/6 · card shadows: layered ≤12% alpha two-part recipes · fonts: Inter + Inter Display (open, we use them too), JetBrains Mono, Tiempos serif (licensed — we substitute Source Serif 4) · content column ≈1280 + hairline frame + dot/hatch gutters · nav row ≈64px + 44px announcement bar.
