# 10 — Product module detail pages (Design B)

Fulcrum ships one detail page per product module, all on **one shared template**. This doc captures that template (from `docs/reference/fulcrum/products/_template-*.jpg`) and maps Fulcrum's 13 modules onto **Tolera's actual surface**: the 5 workflow stages + 4 feature brands (positioning §6.3). We build detail pages to this template for **Tolera's stages**, not a 1:1 copy of Fulcrum's 13.

Design language: 01-DESIGN-SYSTEM. Copy = positioning doc, mapped via 15-COPY-STRUCTURE §3. Product substance = repo build spec (`docs/spec/SPEC-INDEX.md`); capabilities only, verify each claim against its anchor; v1 = what the pilot ships.

## 1. Which detail pages Tolera builds

Fulcrum's 13 modules collapse into Tolera's 5 stage pages (each already anchored from `/produkt` in 05; this doc upgrades them to full pages built on the module template). Mapping:

| Fulcrum module(s) | → Tolera stage page | Brand |
|---|---|---|
| Job Tracking, Grouped Work | Anfrage rein *(intake)* — or a dedicated „Werkstatt/Job-Tracking" later | Lens |
| Quoting & Sales Orders, Job Costing, BOM & Routing | Kalkulieren + Anbieten | Kalk |
| Quality Control, (part of Job Tracking) | Teil verstehen (DFM/QA) | Kontur |
| Autoschedule/Production Scheduling, Demand Planning, Purchasing Planning | Abwickeln / planning | Vergabe |
| Real-time Inventory, Shipping & Receiving, Finance, Live Reports | Abwickeln (fulfilment + reporting) | — |

v1 = the 5 stage pages (Anfrage rein · Teil verstehen · Kalkulieren · Anbieten & gewinnen · Abwickeln). Fulcrum's finer module splits (inventory, finance, reports as separate pages) are **later**, if ever — Tolera's product is narrower. Do not invent 13 pages.

## 2. The shared module-page template (build once, reuse)

Section order (each stage page fills these slots; copy skeleton in 15-COPY-STRUCTURE §3):

1. **Hero** — centered: eyebrow with **module-color highlight** (§5.1, static solid `<span>` bg + 5px x-pad, see 14-MOTION §3) → big black `hero` headline (benefit + mechanism) → subhead (what it does + a punchy contrast line, contrast line highlighted) → CTA pill („<Stage> ansehen") → **tilted app mockup** bleeding down (§5.2). Each stage gets its own accent color (Lens = ai-purple-adjacent? no — keep purple for AI only; assign Lens=green, Kontur=blue, Kalk=orange, Vergabe=lime; see note below).
2. **Black interstitial** (§5.6) — white headline with green/color highlight on the key line + one supporting sentence.
3. **Numbered scroll-stepper** — a vertical `1..4` list beside a tilted mockup; the active step is bold/expanded (with a 1-sentence explanation), the rest faded; **orange leader-arrows** point from the mockup to result cards. Scroll-linked (14-MOTION §4). Content = the stage's 3–4 key capabilities.
4. **Interactive demo band** — „Sehen Sie selbst. Jetzt gleich." + „Klicken Sie sich durch die Demo" → embedded tour or click-through (links to /demo/rundgang).
5. **Second feature block** — a paired headline (e.g. „Hardware trifft Software") + a numbered `1..3` micro-list (scan → pick → label style), with a cropped UI detail.
6. **Pain Q&A block** („Reimagine how you work"-style, SEO/depth) — 4 items, each `[Painfrage]?` + one honest paragraph. Maps to positioning's lost-order pains. Great for SEO; keep it real, no invented metrics.
7. **FAQ accordion** — N items `[Frage]?` + answer. Content from real product facts (supported file types, DSGVO, devices, onboarding).
8. **Closing CTA** — „Ihre Werkstatt in Tolera" + „14 Tage kostenlos testen" + optional inline scheduler.
9. **„Alles verbunden" module grid** — the 5 stages as cross-link cards ([name] + one-line tagline + „verb →"), reused site-wide (same as home §5).
10. Footer.

**Color note:** Fulcrum gives each module its own highlight color. Tolera reuses this device but keeps the positioning-locked rule: **purple = AI suggestions only, inside screenshots**. So marketing highlight colors per stage rotate green/blue/orange/lime (never purple). The AI-Governor purple appears only *within* the Lens mockups.

## 3. Per-stage content skeletons

Same as 05 §3 (verify capabilities against spec anchors), now rendered on the full template above. Each stage page must:
- open with its module-color eyebrow + benefit-mechanism headline (see 15-COPY-STRUCTURE §3.A);
- carry the product-as-actor formula in the black interstitial + stepper (liest/erkennt/kalkuliert/markiert/schlägt vor);
- show DACH-native screenshots (`1.4301`, mm, ISO 2768-m, `1.234,56 €`);
- put the Vier-Augen line under any AI (Lens) block;
- end with the shared module grid + CTA.

## Acceptance
- Template parity with `products/_template-*.jpg` at 1440/768/390 (structure only; our palette/copy/fonts).
- Numbered stepper is scroll-linked and reduced-motion-safe (static list under `prefers-reduced-motion`).
- Every capability claim traceable to a spec anchor; uncertain → `OPEN:` in DECISIONS.md.
- No ISO/ITAR/CMMC-style badges Tolera doesn't hold (Fulcrum's quality-control page shows these — do not copy; use DSGVO/AVV/GoBD only).
