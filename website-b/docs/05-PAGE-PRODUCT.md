# 05 — Produkt spec (`/produkt`) — Design B

Fulcrum's "Product" is a mega-menu of modules; the on-page equivalent is an overview that walks the modules. For Tolera we map that onto the **5 workflow stages + 4 feature brands** (grouping rule, positioning §6.3: by workflow stage, never by subsystem). Product substance = the repo build spec capabilities (`docs/spec/SPEC-INDEX.md` anchors) — capabilities only, no invented features. **Ignore the repo's own UI/brand styling; Design B's system (01) is what counts.**

Reference: `nav-mega-product.jpg` (menu), `home-1440-07-connected-cards-tricolor.jpg` (card grid), `home-1440-03/06` (mockup+callout blocks).

## 1. Mega-menu (nav)
3-column white panel. Columns grouped by workflow stage; each row = 2px icon + brand/stage title + one-line tagline (positioning §6.3):
- **Anfrage rein** — E-Mail-Eingang, Extraktion, Stücklisten, Triage *(Lens)*
- **Teil verstehen** — 3D-Viewer, Feature-Erkennung, DFM *(Kontur)*
- **Kalkulieren** — Sätze, DIN/EN-Werkstoffe, Margen *(Kalk)*
- **Anbieten & gewinnen** — White-Label-Angebot, Threading, Requote
- **Abwickeln** — Zukauf-Anfrage *(Vergabe)*, DATEV, XRechnung, GoBD
Dark bottom bar: „Einführung & Support · API-Doku · Integrationen".

## 2. Overview page sections

1. **Hero** — `hero` head (PROPOSED: „Von der Anfrage bis zum Auftrag. Ein System.") + `lead` sub + CTA pair + one wide tilted app-overview mockup bleeding off-edge.
2. **Five stage blocks**, alternating layout (mockup left / right), each:
   - `section` head in the rotating color (green→orange→blue→green→orange), lime mark on the key word.
   - Two-line body (product-as-actor formula: active verb + „mit Ihren Daten/Sätzen" + control clause where AI is involved). Verbs: liest, erkennt, kalkuliert, markiert, schlägt vor.
   - Tilted stage mockup (assets P0-2..5, P1-8) + 1–2 **callout bubbles** for sub-features.
   - Mono brand chip (Lens/Kontur/Kalk/Vergabe) where the stage has one.
   - `[stage]` gets an `id` so the mega-menu deep-links to it.
   - Stage content skeletons (verify each capability against its spec anchor before writing copy; v1 = what the pilot ships):
     - **Anfrage rein / Lens** — E-Mail-Eingang (eigene RFQ-Adresse), Lens-Extraktion (purple suggestions + „Übernehmen"), BOM-Erkennung, Triage. Vier-Augen line under the AI callout.
     - **Teil verstehen / Kontur** — 3D-Viewer (STEP im Browser, Messen), DFM-Hinweise (real catalogue text „Biegeradius < Blechdicke"), Feature-Erkennung, ohne CAD-Arbeitsplatz.
     - **Kalkulieren / Kalk** — Kalkulationsraster (Sätze, `1.4301`, `1.234,56 €`), Regeln & Margen, DIN/EN-Werkstoffe, kalkuliert-vs-überschrieben. Knowledge-capture closes the block.
     - **Anbieten & gewinnen** — White-Label-PDF + digitales Angebot, E-Mail-Threading, Requote-Diff. No feature brand.
     - **Abwickeln / Vergabe** — Vergabe (3 Gebote „Verzinken", Zuschlag fließt in die Kalkulation), DATEV, XRechnung/ZUGFeRD, GoBD.
3. **„Alles verbunden" recap** — the 5 stages as a colored-outline card slider (§5.4) reinforcing the loop.
4. **DACH trust strip** (as home §7).
5. **CTA band** (lime) + footer.

## Acceptance
- Mega-menu + overview parity with reference at 3 breakpoints (structure only).
- Every capability claim traceable to a spec anchor; uncertain → `OPEN:` in DECISIONS.md, not on the site.
- Deep-links from mega-menu resolve to stage anchors; brand chips consistent.
