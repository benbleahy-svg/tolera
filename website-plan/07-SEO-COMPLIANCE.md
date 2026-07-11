# 07 — SEO, AEO & Compliance

## 1. SEO fundamentals

- One H1 per page = head term (see P5–P8 head terms in `02`). Answer-shaped H2s where natural („Was kostet Tolera?" style) — they serve featured snippets AND LLM citation.
- Title pattern: `{Page head term} – Tolera` (≤ 60 chars); meta descriptions 150–160 chars, benefit-led, written per page at build (draft from copy doc heros).
- Canonicals self-referencing; paginated/param URLs: none at launch.
- Internal linking per `02 §5`. Descriptive anchor text (never „hier klicken").
- Keyword targets (DE primary): Kalkulationssoftware CNC / Blech / Drehteile · Angebotssoftware Lohnfertigung · CPQ Fertigung · Paperless Parts Alternative (P11) · instant quoting (EN). No keyword stuffing — copy in `04`/`05` is already written; do not pad it.

## 2. Structured data (JSON-LD, every page via `lib/jsonld.ts`)

- Site-wide: `Organization` (name Tolera, url, logo, sameAs `TBD(social)`, contactPoint email) + `WebSite`.
- Home + Preise: `SoftwareApplication` (applicationCategory BusinessApplication, offers per tier with priceCurrency EUR — fill when `TBD(prices)` resolves; aggregateRating **omitted** until real ratings exist — never fake).
- FAQ sections: `FAQPage` from the faq content collection (exact on-page text only).
- All pages: `BreadcrumbList`. Vergleich: plain `WebPage` (no product-comparison schema games).
- Validate in CI or manually with Rich Results Test before launch.

## 3. AEO / AI-readability layer

- **robots.txt allows AI crawlers** (GPTBot, ClaudeBot, PerplexityBot, Google-Extended). Rationale: being cited by answer engines is a discovery channel; PP already ships an LLM content API.
- **`/llms.txt`:** curated Markdown index — one-paragraph product description (from P1-hero copy), then links with one-line descriptions to all P1–P12 pages (both locales) and pricing facts. Regenerate at build from the route map.
- Content patterns already baked into the copy: one topic per section, definition-style openers, tables for comparisons, explicit entity naming („Tolera ist eine Angebots- und Kalkulationssoftware für…").
- Entity consistency: identical company descriptor in footer, Organization JSON-LD, llms.txt, and `/unternehmen`.

## 4. Legal pages (DE governs; EN = convenience translation)

**Impressum (`/impressum`) — §5 DDG.** Required content — all `TBD(entity)`: full legal name + legal form, representative(s), postal address (no PO box), email + phone, commercial register + number, USt-IdNr., **W-IdNr. (mandatory from Dec 2026 — include field now)**, supervisory authority if applicable. Cite **DDG** (not TMG). **Do NOT include an EU-ODR-platform link** (discontinued 2025). Footer link „Impressum" on every page.

**Datenschutzerklärung (`/datenschutz`) — DSGVO Art. 13/14 + TDDDG.** Must cover: controller identity (= Impressum entity) · hosting/Vercel (note: US provider — name the transfer mechanism, or `TBD(hosting-region)` if EU-pinned) · Plausible (cookieless, no personal profiles, legal basis berechtigtes Interesse Art. 6(1)(f)) · outbound links to app.tolera.eu (Clerk/Paddle live in the APP's privacy policy — link it, don't duplicate) · contact-email processing · rights of data subjects · **statement that this site sets no cookies and uses no tracking requiring consent**. Cite TDDDG (not TTDSG). `TBD(privacy-review)` — have it legally reviewed; generate a solid draft, mark as draft.

**AGB (`/agb`).** `TBD(agb)` — product terms belong to the app/Paddle flow; the website page can link the canonical terms. Do not generate binding AGB text — lawyer task. Ship the page as a stub linking to the app terms until then.

**Accessibility statement (optional but recommended):** short „Barrierefreiheit" section in the footer or on `/impressum`: target WCAG 2.2 AA, feedback email. B2B site is likely out of BFSG scope, but the self-serve checkout adjacency makes voluntary conformance the safe posture.

## 5. Accessibility (WCAG 2.2 AA — CI-enforced via pa11y)

Beyond the design-system rules (03 §8): every screenshot gets a real alt text describing what the UI shows (not „Screenshot") · decorative icons `aria-hidden` · tour fully keyboard-operable + screen-reader step announcements (see `08`) · skip-link to main · forms (none at launch except none — contact is mailto) · color never sole carrier (comparison table uses ✓/— text, not color dots) · `prefers-reduced-motion` respected globally · focus order follows DOM.

## 6. Pre-launch compliance checklist

1. All `TBD(entity)` fields filled; Impressum reviewed against current §5 DDG list.
2. Datenschutzerklärung legally reviewed; Vercel data-processing location verified (`TBD(hosting-region)` resolved — if app claims „Daten in Deutschland", the SITE claim must match reality of the marketing site too, or be scoped to the product).
3. PP comparison claims re-verified against live paperlessparts.com; footnote URLs + retrieval date updated (`TBD(pp-verify-date)`).
4. C4 (free tier) and prices confirmed in product DECISIONS.md.
5. pa11y + Lighthouse + Rich Results green on production build.
6. hreflang validated (e.g. Merkle tool) on production URLs.
