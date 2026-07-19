# CLAUDE.md — Tolera Marketing Website, Design B ("Fulcrum-derived") — `website-b/`

**Read this first** in any session building Design B. This is a **second, independent design direction** for the Tolera marketing site, meant to be **A/B tested internally against Design A** (the Attio-derived pack in `website/`). Same product, same positioning, same copy — different skin and information architecture. This folder is self-contained; it must never touch the product app, the build-plan pipeline, Design A, or anything outside `website-b/` (except reading the repo-root `docs/` for content).

## What we're building

The Tolera marketing site in a **bold, high-energy, Fulcrum-inspired** visual language — heavy black display type, big saturated colored section headers (green/orange/blue), a lime highlighter accent, 3D-tilted product mockups, floating callout bubbles, an Old-vs-New comparison page, and full-black interstitial sections. Rebuilt 100% from scratch as our own design system: our light/dark palette, our open fonts (Hanken Grotesk — substitute for Fulcrum's licensed Gilroy), our assets, our copy. **No Fulcrum asset, CSS, font, retro artefact, or copy ever ships or is imported.** Reference screenshots are internal-only (`docs/reference/fulcrum/`, never deployed).

Pages (Fulcrum's IA, per Benjamin's scope): **Home · Produkt · KI · Warum · Walkthrough** (+ legal). No separate Pricing/Manifest page in B (pricing = section/CTA; manifesto ideas fold into Warum). Ask before adding.

## How B differs from A (the A/B variables)
- **Skin:** A = quiet, light, hairline "technical drawing." B = loud, high-contrast, colored heads + lime marks + tilted mockups + black interstitials.
- **IA:** A = Home + Platform/5-stages + Kunden + Preise + Manifest. B = Home + Produkt + KI + Warum + Walkthrough.
- **Type:** A = Inter/Inter Display. B = Hanken Grotesk (heavier, geometric).
- **Shared, unchanged:** all copy (positioning doc), the 5 workflow stages + 4 brands, DACH/DE-first rules, the „purple = AI only" grammar, and every honesty gate.

## Document map (read in order)

| File | Authoritative for |
|---|---|
| `../docs/decisions/DECISIONS.md` | Overrides everything (pricing, packaging, brands) |
| `../docs/analysis/POSITIONING-AND-MESSAGING.md` | **All copy** (DE/EN), positioning, asset plan §7 — quoted, never rewritten |
| `docs/01-DESIGN-SYSTEM.md` | Tokens, layout devices, motion, components |
| `docs/02-BRAND-KIT.md` | Fonts, palette, wordmark, voice, don'ts |
| `docs/03-SITE-MAP-AND-NAV.md` | Routes, nav/mega-menu/footer, i18n, SEO |
| `docs/04…08-PAGE-*.md` | Per-page section specs + acceptance (Home, Produkt, KI, Warum, Walkthrough) |
| `docs/09-ASSETS-CHECKLIST.md` | Asset states, production rules, legal gates |
| `docs/10-PAGE-PRODUCT-DETAIL.md` | Shared product-module template + the 5 Tolera stage detail pages |
| `docs/11-PAGE-LAUNCH.md` | Einführung & Support (Launch equivalent) |
| `docs/12-PAGE-INTEGRATIONS.md` | Integrationen page |
| `docs/13-PAGE-COMPANY.md` | Mission/Vision, Kontakt, Demo-scheduler |
| `docs/14-MOTION-AND-CSS.md` | Measured timings, the highlight-marker mechanism, tilt/parallax, pinned scroll, sliders |
| `docs/15-COPY-STRUCTURE.md` | Replicable copy skeleton per page-type (slots/formulas), mapped to positioning copy |
| `docs/reference/fulcrum/` (+ `products/`, `pages/`) + README | Reference frames + measured facts |

Precedence: DECISIONS.md > positioning doc (copy) > page specs > design system > reference frames. A reference pixel never outranks a spec. Unresolved + expensive-to-reverse → `OPEN:` in DECISIONS.md.

## Stack (same as A, for a clean A/B and shared components where sensible)
- **Next.js (App Router) + Tailwind v4 + Motion**, TypeScript; `next-intl` DE/EN; copy in `content/*.json`.
- Fonts self-hosted via `next/font/local`: **Hanken Grotesk + JetBrains Mono** (OFL).
- Add a lightweight scroll lib for pin/parallax (e.g. a ScrollTrigger-style util) — used sparingly, `md+`, reduced-motion-safe.
- Static-first, Vercel. Its own npm app; do not merge deps into the product app or Design A.

## Build order
1. Scaffold + tokens (01 §1–4) + fonts + i18n + a `/styleguide` dev page.
2. Components in 01 §6 order (buttons → … → footer), incl. the **signature set**: colored section head w/ lime marker, tilted mockup frame, callout bubble, outline card + slider, old-vs-new split, black-constellation interstitial.
3. Home (04) with placeholder media. 4. Produkt overview (05) + mega-menu + the shared module template (10) → 5 stage detail pages. 5. KI (06). 6. Warum (07). 7. Einführung (11), Integrationen (12). 8. Walkthrough (08), Kontakt + Demo (13). 9. Mission (13 §1, optional). 10. Legal, SEO, sitemap.
11. Asset/screenshot pass when the seeded demo org exists (09) — shared with Design A.

Reference for motion + copy shape while building: **14-MOTION-AND-CSS** (behaviour) and **15-COPY-STRUCTURE** (slot skeleton, mapped to positioning copy).

## Verification (every page, before PR)
- Side-by-side vs matching reference frames at 1440/768/390 (Playwright) — same energy/structure; **our** palette/copy/assets/fonts.
- Copy diff vs positioning doc (umlauts, „" quotes, `1.234,56 €`, Sie-Form).
- Lighthouse ≥ 95 on `/`, `/produkt`; CLS < 0.1; `prefers-reduced-motion` disables pin/parallax/particles/marker-motion.
- Grep-gate: no `public/`/`app/` file references `reference/fulcrum`; no Fulcrum asset/string/font in the bundle.
- Honesty gates (shared with A): no invented metrics, no fake testimonials/logos, „~"-indicative pricing, purple only inside AI screenshots. **KI page:** no ask-anything/app-builder/agents/ITAR/CMMC claims (see 06).

## Open items owned by Benjamin
Whether B also needs a Pricing + Manifest page · interactive-tour vendor for Walkthrough (DSGVO-clean) · wordmark approval (shared w/ A) · logo-wall permissions · trademark screening · analytics choice · which design (A or B) wins the A/B → becomes the production site.
