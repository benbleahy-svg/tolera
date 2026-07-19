# 03 — Site map, navigation, i18n (Design B)

Design B follows **Fulcrum's information architecture** (the pages you asked for) mapped onto Tolera content — this is deliberately different from Design A's IA (Home + Platform/5-stages + Kunden + Preise + Manifest), so the A/B compares *both* skin and structure.

## 1. Scope (expanded — full Product/Why/Start submenus)

Included: **Home · Produkt (overview + mega-menu + per-stage detail pages) · KI ("Archie"-equivalent) · Warum · Mission/Vision · Einführung (Launch) · Integrationen · Walkthrough · Kontakt · Demo vereinbaren.**
Excluded (per request): blog, resources, "switch"/migration pages, Sheet-Metal-Fabrication LP, Precision-Machining (CNC) LP, Operations-Leader persona page, Product Updates/changelog (later). Legal pages (Impressum/Datenschutz/AGB/AVV) required in DE, in scope as plain pages.

**Mapping note:** Fulcrum exposes 13 product-module pages. Tolera's product is narrower, so those collapse into **5 stage detail pages** (built on the shared module template, 10-PAGE-PRODUCT-DETAIL) rather than 13. Pricing surfaces as a section/CTA (no standalone Preise page in B — add if wanted). Fulcrum's Mission page overlaps the manifesto ideas already in `/warum`; build it only if Benjamin wants the separate pinned vision page (13 §1).

## 2. Routes

DE default at `/`; EN mirrors at `/en/...`.

| DE route | EN route | Page | Spec |
|---|---|---|---|
| `/` | `/en` | Home | 04 |
| `/produkt` | `/en/product` | Produkt overview (module grid + mega-menu) | 05 |
| `/produkt/anfrage` · `/teil` · `/kalkulation` · `/angebot` · `/abwicklung` | `/en/product/*` | 5 stage detail pages (module template) | 10 |
| `/ki` | `/en/ai` | KI (Lens / „Archie"-equivalent) | 06 |
| `/warum` | `/en/why` | Warum Tolera (old-vs-new) | 07 |
| `/mission` | `/en/mission` | Mission/Vision (pinned; optional) | 13 §1 |
| `/einfuehrung` | `/en/onboarding` | Einführung & Support (Launch) | 11 |
| `/integrationen` | `/en/integrations` | Integrationen | 12 |
| `/demo/rundgang` | `/en/demo/walkthrough` | Interactive Walkthrough | 08 |
| `/kontakt` | `/en/contact` | Kontakt | 13 §2 |
| `/demo` | `/en/demo` | Demo vereinbaren (scheduler) | 13 §3 |
| `/impressum`,`/datenschutz`,`/agb`,`/avv` | `/en/legal/*` | Legal | plain pages |

Mega-menu deep-links resolve to the 5 stage detail pages (or their anchors on `/produkt` until the detail pages ship).

## 3. Top navigation (Fulcrum-style)

Nav bar, transparent over hero → solid `paper` on scroll (white text on black pages):

- **Logo** (left) → `/`
- **KI** → `/ki` (with a ✦ sparkle glyph, Fulcrum puts Archie first — we put KI first too; it's the differentiator)
- **Produkt ▾** — mega-menu: full-width white panel, **3-column icon grid** of capabilities grouped by the 5 workflow stages + 4 brands (Lens · Kontur · Kalk · Vergabe), each row = 2px icon + title + one-line tagline (taglines from positioning §6.3), deep-linking to the 5 stage detail pages (10). Dark bottom utility bar: „Einführung & Support (`/einfuehrung`) · API-Doku · Integrationen (`/integrationen`)". (Ref `nav-mega-product`.)
- **Warum ▾** — dropdown: „Warum Tolera" (`/warum`) · „Mission" (`/mission`). (Blog excluded; the two industry pages excluded.) (Ref `nav-dropdown-why`.)
- **Start ▾** — dropdown: „Rundgang / Test Drive" (`/demo/rundgang`) · „Kontakt" (`/kontakt`) · „Demo vereinbaren" (`/demo`). (Ref `nav-dropdown-start`.)
- Right: **DE/EN toggle** · **„Demo vereinbaren"** (ink pill primary).

Mobile: hamburger → full-screen sheet, Produkt as accordion, „Demo" pill pinned.

## 4. Footer (light)

Four columns under bold labels:
- **Produkt:** the 5 stage pages, KI, Preise (anchor)
- **Entdecken:** Warum, Mission, Einführung, Integrationen, Walkthrough, Changelog (later)
- **Ressourcen:** Hilfe (later), Status, Sicherheit & DSGVO, API-Doku, Kontakt
- **Rechtliches:** Impressum, Datenschutz, AGB, AVV

Bottom: social row (LinkedIn), DE/EN toggle, © 2026 Tolera, a tagline slot (Fulcrum's "Series A2" line → Tolera's own, or omit), trust strip „🇩🇪 Daten in Deutschland · DSGVO".

## 5. i18n / SEO

Same as Design A: `next-intl`, `de` default / `en` prefixed, `hreflang` pairs, copy in `content/de.json`/`content/en.json` (never hard-coded), German-UI screenshots on both locales, EN strings flagged `"draft": true` until native pass. Title `<Seite> | Tolera`; sitemap/robots/canonical; correct `lang`.
