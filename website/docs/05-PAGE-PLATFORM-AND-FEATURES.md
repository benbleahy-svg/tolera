# 05 — Platform overview + the 5 stage pages

Grouping rule (positioning §6.3): **by workflow stage, never by subsystem.** One overview page + five stage pages. The four feature brands (Lens, Kontur, Kalk, Vergabe) appear *inside* their stage, never as the page structure.

Product substance for feature claims: pull from the repo spec (`docs/spec/SPEC-INDEX.md` anchors per subsystem) — capabilities only, no invented features. **Ignore any UI/brand styling shown in repo screenshots — the marketing design system (01) is what counts.**

## 1. Shared page template (pattern: `platform-data-1440-*.jpg`)

1. **Hero:** section badge (stage name), centered `display-1` claim, `body-lg` sub, CTA pair, then a full-width product shot (the stage's P0 asset) in a media card breaking the fold.
2. **Full app shot** (`platform-data-1440-02-product-shot.jpg`-style): the stage's screen in context, three-dot bar.
3. **Two-tone H2 intro** for the capability story.
4. **Numbered feature blocks** `[01]`/`[02]` — 2-up dot-pattern panels, each a mini-demo (cropped UI or short loop) + `h3` + 2-line body.
5. **Serif quote slot** (empty until Fechner; hidden at launch).
6. **Feature pair rows** (h3 + body, hairline-split, small UI crops).
7. **Three-up icon row** (secondary capabilities).
8. **Cross-links:** „Nächste Stufe →" (workflow order) + pricing CTA band.

## 2. Overview page `/plattform`

- Hero: `display-1` „Vom Eingang der Anfrage bis zum Auftrag." (PROPOSED copy — Benjamin confirms) + sub + CTAs.
- Then five stage sections in workflow order, each: two-tone claim + hero shot of that stage + 3 bullet capabilities + „Mehr zu <Stufe> →".
- Flow diagram (P1-9) between hero and stages, line-draw on scroll.

## 3. The five stage pages (content skeletons)

Copy status: section claims below are PROPOSED skeletons following the product-as-actor formula; final DE copy is written during build and reviewed by Benjamin. Capabilities listed are from the build spec — verify each against its spec anchor before writing it into copy (never promise unbuilt features; v1 = what the pilot ships).

### 3.1 `/plattform/anfrage` — Anfrage rein (brand: **Lens**)
- Claim direction: Tolera liest jede Anfrage — E-Mail, PDF, STEP, Stückliste — und macht daraus strukturierte Positionen. Mit Vier-Augen-Kontrolle.
- `[01]` E-Mail-Eingang: eigene RFQ-Adresse (`…@rfq.tolera.eu`), Anhänge automatisch erkannt. `[02]` Lens-Extraktion: purple suggestions over a German RFQ email, „Übernehmen"-buttons (asset P0-2). Others: BOM-Erkennung, Triage/Prioritäten, Found-in-Files.
- AI control line appears verbatim under the Lens block.

### 3.2 `/plattform/teil` — Teil verstehen (brand: **Kontur**)
- Claim direction: Tolera versteht das Teil — Geometrie, Features, Fertigbarkeit — ohne CAD-Arbeitsplatz.
- `[01]` 3D-Viewer (STEP im Browser, Messen, Schnitt). `[02]` DFM-Hinweise: open flags with real catalogue text („Biegeradius < Blechdicke", asset P0-3). Others: Feature-Erkennung (Bohrungen, Biegungen, Gewinde), PDF-Zeichnungs-Viewer, unterstützte Formate.

### 3.3 `/plattform/kalkulation` — Kalkulieren (brand: **Kalk**)
- Claim direction: Tolera kalkuliert mit Ihren Stundensätzen, Ihren Maschinen, Ihren Prozessen — nicht mit Durchschnittswerten.
- `[01]` Kalkulationsraster: German ops, Stundensätze, `1.4301`, `1.234,56 €` (asset P0-4). `[02]` Regeln & Margen: Zielmargen, Staffelpreise, Prüfpunkte (Requirements Review). Others: DIN/EN-Werkstoffe, Mengenstaffeln, kalkuliert-vs-überschrieben (nothing overwritten).
- Knowledge-capture claim closes the page (key-person risk / succession).

### 3.4 `/plattform/angebot` — Anbieten & gewinnen
- Claim direction: Aus der Kalkulation wird in einem Klick ein Angebot — Ihr Logo, Ihr Briefkopf, versandfertig.
- `[01]` White-Label-PDF + digitales Angebot side by side (asset P1-8). `[02]` E-Mail-Threading & Nachfassen. Others: Requote-Diff, Gültigkeit/Konditionen.
- No feature brand here — descriptive only.

### 3.5 `/plattform/abwicklung` — Abwickeln (brand: **Vergabe**)
- Claim direction: Nach dem Zuschlag: Zukauf anfragen, vergleichen, exportieren — DATEV, XRechnung, GoBD.
- `[01]` Vergabe: 3 Gebote für „Verzinken", eines gewählt, Preis fließt in die Kalkulation (asset P0-5). `[02]` DATEV-Export & XRechnung/ZUGFeRD. Others: GoBD-Ablage, Versandanbindung (nur wenn im v1-Scope!).

## Acceptance
- Template parity with `platform-data-1440-*` frames at 3 breakpoints (structure only).
- Every capability claim traceable to a spec anchor; anything uncertain → `OPEN:` in DECISIONS.md, not on the website.
- Stage pages interlink in workflow order; brands anchor-linked from the nav dropdown.
