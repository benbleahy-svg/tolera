# website-plan/ — Tolera Marketing Website Build Guide

**Read this first.** This folder is the complete, self-contained plan for the Tolera marketing website at `tolera.eu`. It was produced 2026-07-10 after a decision interview with Benjamin and research into 2026 best practices. A Claude Code session should be able to build the entire site from these docs without inventing positioning, copy, design, or architecture.

**This is a separate deliverable from the product build** (`build-plan/`, `docs/`). The site is its own repo/Vercel project. Product-repo conventions (Celery, Alembic, RLS…) do **not** apply here; the conventions in `06-TECH-SPEC.md` do. The block-and-log spirit of `CLAUDE.md` §6 **does** apply: never invent a fact, price, or legal detail — every unresolved value is marked `TBD(...)` and listed in `09-TBD-REGISTER.md`.

## Document index

| Doc | Authoritative for |
|---|---|
| `01-STRATEGY-AND-DECISIONS.md` | Mission, audience, positioning, messaging hierarchy, all 12 interview decisions + rationale |
| `02-SITEMAP-AND-PAGES.md` | URL structure (de/en), per-page purpose, section-by-section layout specs, internal linking |
| `03-DESIGN-SYSTEM.md` | Tokens, typography, components, layout, motion, imagery rules |
| `04-CONTENT-DE.md` | **Final German copy** for every page (source language) |
| `05-CONTENT-EN.md` | **Final English copy** for every page (`/en/` mirror) |
| `06-TECH-SPEC.md` | Astro architecture, i18n, performance budgets, analytics events, deployment |
| `07-SEO-COMPLIANCE.md` | SEO/AEO, structured data, hreflang, legal pages, WCAG 2.2 AA, GDPR |
| `08-TOUR-SPEC.md` | The interactive product-tour component: behavior spec + full step script |
| `09-TBD-REGISTER.md` | Every placeholder that must be filled before launch (prices, Impressum data, pilot numbers, screenshots) |
| `STYLE-TILE.html` | Visual reference: tokens rendered live + homepage wireframe. Open in a browser. |

**Precedence:** `09-TBD-REGISTER.md` (facts) > `01-STRATEGY` (intent) > page specs (`02`) > copy (`04`/`05`) > design (`03`) > tech (`06`). The product repo's `DECISIONS.md` outranks everything for product facts (names, domains, billing model).

## What we're building (one paragraph)

A German-first, bilingual (de root + `/en/`) marketing site for **Tolera** — the self-serve instant-quoting platform for DACH custom manufacturers (CNC, Blech, Rohrlaser, Drehen). It launches when public self-serve signup is live (post-pilot v1.x). Primary CTA: **Kostenlos testen** (→ `app.tolera.eu` signup). Secondary CTA: **Produkt-Tour** (ungated, hand-built interactive tour). Design: Tolera's warm-light system (sand `#F7F2EA`, terracotta `#CC6431`, Inter). Stack: Astro + Tailwind, Markdown content collections, Vercel, Plausible (cookieless, **no cookie banner**). ~13 pages per language + legal. Full transparency pricing page. One comparison page: vs. Paperless Parts.

## Build order

1. **Scaffold** — Astro project, Tailwind with tokens from `03-DESIGN-SYSTEM.md`, i18n routing per `06-TECH-SPEC.md`, layout shell (header/footer/nav).
2. **Design system pass** — build the component library against `STYLE-TILE.html` before any page.
3. **Pages, German first** — Home → Preise → 3 feature pages → Tour shell → 4 process pages → Vergleich → Unternehmen → legal. Copy comes verbatim from `04-CONTENT-DE.md`.
4. **Tour component** — per `08-TOUR-SPEC.md` (needs app screenshots; placeholder frames until then).
5. **English mirror** — `/en/` from `05-CONTENT-EN.md`.
6. **SEO/AEO + compliance layer** — JSON-LD, llms.txt, sitemap, hreflang, a11y audit per `07-SEO-COMPLIANCE.md`.
7. **Verification** — Lighthouse ≥ 95 all categories, WCAG 2.2 AA check, all `TBD(...)` markers either resolved or intentionally visible in `09-TBD-REGISTER.md`, both locales build with zero broken links.

## Acceptance criteria (launch gate)

- Every page matches its section spec in `02-SITEMAP-AND-PAGES.md` and its copy in `04`/`05`.
- Core Web Vitals: LCP < 2.0 s, INP < 100 ms, CLS < 0.05 (lab); zero client JS except tour, nav toggle, pricing toggle, Plausible.
- No cookies set. No third-party scripts except Plausible (EU endpoint).
- `Impressum`, `Datenschutzerklärung`, `AGB` reachable from every page footer; DDG/TDDDG-correct references.
- hreflang de/en/x-default valid on every page, self-referencing.
- All numeric claims trace to `01-STRATEGY-AND-DECISIONS.md` §Claims or are marked TBD.
