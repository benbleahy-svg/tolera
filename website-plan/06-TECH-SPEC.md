# 06 — Tech Spec

## 1. Stack

- **Astro** (latest stable; islands architecture, static output `output: 'static'`) + **Tailwind CSS** (tokens from `03-DESIGN-SYSTEM.md` in `tailwind.config`).
- **TypeScript** strict. **MDX** for content collections.
- **Vercel** hosting (same account as app). Apex `tolera.eu` + `www` redirect → apex. No server functions needed at launch.
- **No CMS.** All content in repo. **Separate repo** from the product (suggested: `tolera-website`).

## 2. Project structure

```
src/
├── content/            # Astro content collections (zod-validated frontmatter)
│   ├── pages/de/…      # page copy as MDX (one file per page, sections as components/frontmatter)
│   ├── pages/en/…
│   ├── faq/…           # FAQ entries (page, order, q, a) — feeds accordion + JSON-LD
│   └── tour/…          # tour steps (de/en, image, hotspot coords) per 08-TOUR-SPEC
├── components/         # Button, Header, Footer, Bento, StepFlow, PricingCards, FaqAccordion,
│   │                   # CompareTable, TrustStrip, CtaBand, TourPlayer (island), Screenshot
├── layouts/            # Base.astro (head/meta/JSON-LD/hreflang), Page.astro, Legal.astro
├── lib/                # i18n helpers, analytics.ts, jsonld.ts, brand.ts
└── pages/              # thin route files mapping to content collections
public/                 # favicons, og/, llms.txt, robots.txt
```

- **`lib/brand.ts`:** central consts — `BRAND_NAME`, `SIGNUP_URL = 'https://app.tolera.eu/sign-up'`, `APP_URL`, `CONTACT_EMAIL`, prices object (all `TBD` values live HERE only, imported everywhere — one place to fill before launch).
- Copy lives in content files, never hardcoded in components.

## 3. i18n

- Astro built-in i18n: `defaultLocale: 'de'`, `locales: ['de','en']`, `prefixDefaultLocale: false` (German at root).
- Translated slugs per the P-table in `02-SITEMAP-AND-PAGES.md` (route map in one `lib/routes.ts`, used by nav, hreflang, sitemap — single source).
- Every page emits: self-referencing + alternate `<link rel="alternate" hreflang>` for `de`, `en`, `x-default` (x-default → German page). Language switch preserves the page (route-map lookup), falls back to locale home.
- `<html lang>` correct per locale; `lang="en"` spans not needed (no mixed copy).

## 4. Performance budget (hard gates)

- **Zero client JS by default.** Islands only: TourPlayer, mobile-nav toggle, pricing toggles, Plausible (~1 kB). Everything else pure HTML/CSS (FAQ = `<details>`, dropdowns = CSS/`:focus-within` + small progressive enhancement if needed).
- Budgets: total JS < 40 kB gz on any page (tour page exempt: < 90 kB) · LCP < 2.0 s lab / 2.5 s field · INP < 100 ms · CLS < 0.05 · Lighthouse ≥ 95 all categories, both locales.
- Images: Astro `<Image>`/`<Picture>` — AVIF primary, WebP fallback, explicit dimensions, `loading="lazy"` below fold, hero image `fetchpriority="high"` + preloaded. Screenshots exported 2x, max 1600 px wide.
- Fonts: Inter variable woff2 self-hosted, `font-display: swap`, preload, subset `latin,latin-ext`. No icon font — Lucide as inline SVG (tree-shaken via `@lucide/astro`).

## 5. Analytics (Plausible, cookieless)

Script: `https://plausible.io/js/script.js` EU-served, `data-domain="tolera.eu"`, deferred; **or self-hosted proxy** `TBD(plausible-mode)`. No cookies, no consent banner required (document this in Datenschutzerklärung).

Custom events (`lib/analytics.ts`, `window.plausible` guard):
`CTA: Signup Click` (props: location = header/hero/cta-band/pricing-tier) · `CTA: Tour Click` (location) · `Tour: Started` · `Tour: Step` (step-n) · `Tour: Completed` · `Tour: CTA Click` · `Pricing: Currency Toggle` (chf/eur) · `Pricing: Billing Toggle` · `Pricing: Enterprise Contact` · `Compare: Source Click` · `Lang: Switch`.
Goal funnel: entry → Tour Started → Tour Completed → Signup Click.

## 6. Quality gates & CI

- GitHub Actions on PR: `astro check` + `tsc` · build both locales · **Lighthouse CI** (budgets §4) · **linkinator** (zero broken internal links) · **pa11y-ci** (WCAG 2.2 AA, all pages) · grep-gate: fail if `TBD(` appears in built HTML **unless** launch flag `ALLOW_TBD=true` (dev default true, launch false).
- Preview deploys per PR (Vercel). `main` = production.

## 7. Redirects / headers / misc

- `www.tolera.eu` → 308 → `tolera.eu`. Trailing slashes normalized.
- Security headers (vercel.json): CSP (self + plausible), X-Content-Type-Options, Referrer-Policy `strict-origin-when-cross-origin`, HSTS.
- `robots.txt`: allow all incl. GPTBot/ClaudeBot/PerplexityBot; sitemap ref. `sitemap-index.xml` via @astrojs/sitemap with i18n. `llms.txt` per `07-SEO-COMPLIANCE.md` §3.
- 404 pages per locale. OG images per page (build-time, 03 §7).
- Blog scaffold: content collection + index route exists, `noindex` + hidden from nav while empty.

## 8. Definition of done (per page)

Copy verbatim from `04`/`05` · sections match `02` spec · JSON-LD valid (Rich Results test) · hreflang triple present · budgets green · pa11y clean · screenshots have alt text per `07 §5` · CTA events fire.
