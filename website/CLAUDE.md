# CLAUDE.md — Tolera Marketing Website (`website/`)

**Read this first** in any session building the marketing site. This folder is self-contained: the site is a separate Next.js app and must never touch the product app, the build-plan pipeline, or anything outside `website/` (except reading `docs/` at the repo root for content).

## What we're building

The public marketing site for **Tolera** (tolera.eu): homepage, platform overview + 5 stage pages, Kunden, Preise, Manifest, legal pages. Bilingual DE (default) / EN.

**Design goal:** match the *structure, layout system, rhythm, motion and polish level* of attio.com — rebuilt 100% from scratch as our own design system, with our light theme, our palette, our assets, our copy. We never ship or import any Attio asset, CSS, font we don't license, illustration, or copy. Reference screenshots exist for study only (`docs/reference/attio/` — internal, never deployed).

## Document map (read in this order for a build session)

| File | Authoritative for |
|---|---|
| `../docs/decisions/DECISIONS.md` | Overrides everything (pricing, packaging, feature brands) |
| `../docs/analysis/POSITIONING-AND-MESSAGING.md` | **All copy** (DE/EN), page skeleton, asset plan §7, layout philosophy §6. Copy is quoted from here, never rewritten |
| `docs/01-DESIGN-SYSTEM.md` | Tokens, layout language, components, motion, locale rules |
| `docs/02-BRAND-KIT.md` | Fonts, palette rationale, wordmark, voice, don'ts |
| `docs/03-SITE-MAP-AND-NAV.md` | Routes, nav/footer, i18n, SEO |
| `docs/04…08-PAGE-*.md` | Per-page section specs + acceptance |
| `docs/09-ASSETS-CHECKLIST.md` | Asset states, production rules, legal gates |
| `docs/reference/attio/` + its README | Visual reference frames + measured facts |

Precedence: DECISIONS.md > positioning doc (copy/content) > page specs > design system > reference frames. A reference pixel never outranks a spec. Unresolved + expensive-to-reverse → `OPEN:` in DECISIONS.md (repo rule §6 of root CLAUDE.md).

## Stack (decided)

- **Next.js (App Router, latest stable) + Tailwind CSS v4 + Motion (framer-motion successor)**, TypeScript.
- `next-intl` for DE/EN; copy in `content/*.json` — never hard-coded in components.
- Fonts self-hosted via `next/font/local`: Inter, Inter Display, Source Serif 4, JetBrains Mono (woff2, OFL — download from official releases).
- Static-first (`generateStaticParams`, no server state), deploy target Vercel. No CMS, no analytics until a GDPR-clean choice is decided (`OPEN:`).
- Repo location: this folder is its own npm workspace/app — do not merge deps into the product app.

## Build order

1. Scaffold app + tokens (Tailwind theme from 01 §1–4) + fonts + i18n plumbing.
2. Core components in the order of 01 §6 (buttons → … → footer), with a `/styleguide` dev-only page rendering all of them.
3. Homepage (04) with state-1 placeholders for media.
4. Platform template + 5 stage pages (05). 5. Preise (06). 6. Kunden (07). 7. Manifest (08). 8. Legal pages, SEO, sitemap.
9. Screenshot/asset pass when the seeded demo org exists (09).

## Verification (every page, before PR)

- Side-by-side vs the matching reference frames at 1440 / 768 / 390 (Playwright screenshots) — same section rhythm, hairline frame, sticky behaviors; **our** palette/copy/assets.
- Copy diff against the positioning doc (umlauts, „"-quotes, `1.234,56 €` formatting, Sie-Form).
- Lighthouse ≥ 95 perf/a11y/SEO on `/`, `/preise`; CLS < 0.1; `prefers-reduced-motion` clean.
- Grep-gate before any deploy/PR: no file under `public/` or `app/` references `reference/attio`, no Attio string/asset in the bundle.
- Honesty gates: no invented metrics, no fake testimonials/logos, „~"-indicative pricing kept, purple only inside AI screenshots.

## Open items owned by Benjamin (block only what depends on them)

Tier feature allocation (06) · annual-discount number · manifesto essay copy + defined word (08) · wordmark approval (02 §2) · logo-wall permissions · trademark screening · GDPR-clean analytics choice · final domain (tolera.eu assumed).
