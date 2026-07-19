# 03 — Site map, navigation, i18n

## 1. Routes (v1)

German is default at `/`; English mirrors at `/en/...`. Route slugs are German on the DE tree, English on the EN tree.

| DE route | EN route | Page | Spec |
|---|---|---|---|
| `/` | `/en` | Homepage | 04 |
| `/plattform` | `/en/platform` | Platform overview | 05 §2 |
| `/plattform/anfrage` | `/en/platform/intake` | Stage 1 — Anfrage rein (**Lens**) | 05 §3 |
| `/plattform/teil` | `/en/platform/part` | Stage 2 — Teil verstehen (**Kontur**) | 05 §3 |
| `/plattform/kalkulation` | `/en/platform/pricing-engine` | Stage 3 — Kalkulieren (**Kalk**) | 05 §3 |
| `/plattform/angebot` | `/en/platform/quote` | Stage 4 — Anbieten & gewinnen | 05 §3 |
| `/plattform/abwicklung` | `/en/platform/fulfillment` | Stage 5 — Abwickeln (**Vergabe**) | 05 §3 |
| `/kunden` | `/en/customers` | Kunden (pre-pilot variant) | 07 |
| `/preise` | `/en/pricing` | Preise | 06 |
| `/manifest` | `/en/manifesto` | Manifest | 08 |
| `/impressum`, `/datenschutz`, `/agb` | `/en/legal/...` | Legal (required in DE!) | plain narrow-text pages |

Later (not v1): `/changelog`, `/kunden/<story>`, `/karriere`.

## 2. Top navigation

Announcement bar (optional, dismissible) → Nav bar:

- **Logo** (left) → `/`
- **Plattform ▾** — mega-dropdown, two groups:
  - Group „**Arbeitsablauf**" (eyebrow label): the 5 stages, each = icon + title + one-line tagline (taglines from positioning §6.3, e.g. „Anfrage rein — E-Mail-Eingang, Extraktion, Stücklisten, Triage"). Links to the 5 stage pages.
  - Group „**Werkzeuge**": the 4 feature brands — **Lens** (KI-Extraktion), **Kontur** (3D & DFM), **Kalk** (Kalkulations-Engine), **Vergabe** (Lieferanten-Anfragen) — each links to its stage page + `#brand` anchor.
  - Right column „**Erste Schritte**": Demo ansehen (`/#demo`), Preise, Kontakt.
- **Kunden** → `/kunden`
- **Preise** → `/preise`
- Right side: **DE/EN toggle** (text button) · **Anmelden** (app.tolera.eu, secondary) · **„14 Tage kostenlos testen"** (primary → signup).

Mobile: hamburger → full-screen sheet, stages as accordion, CTA pinned bottom.

**Manifest is NOT in the top nav** — footer only (per Benjamin's decision, mirroring Attio).

## 3. Footer (light theme)

Columns under `eyebrow` labels:

- **Plattform:** the 5 stage pages, Preise, Changelog (later)
- **Unternehmen:** Kunden, **Manifest**, Karriere (later), Kontakt
- **Ressourcen:** Hilfe-Center (later), Status, Sicherheit & DSGVO
- **Rechtliches:** Impressum, Datenschutz, AGB, AVV (Auftragsverarbeitung)

Bottom row: © 2026 Tolera · language toggle · LinkedIn. Trust strip repeats: „🇩🇪 Daten in Deutschland · DSGVOkonform".

## 4. i18n implementation

- `next-intl` with locale segment; `de` default (no prefix), `en` prefixed. `hreflang` pairs on every page.
- All copy lives in `content/de.json` / `content/en.json` (or per-page MDX) — **never hard-coded in components**, so Benjamin can edit copy without touching code.
- Screenshots stay German on both locales (positioning §7 P2-15). Captions/alt text localized.
- EN copy status: directional drafts (positioning §8.6) — mark EN strings `"draft": true` until the native pass.

## 5. SEO/meta

Title pattern: `<Seite> | Tolera` ; DE meta descriptions from positioning copy. OG image per page (template in 09-ASSETS-CHECKLIST). `sitemap.xml`, `robots.txt`, canonical URLs, `lang` attributes correct per locale.
