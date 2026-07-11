# 08 — Interactive Product Tour (hand-built)

## 1. What it is

An ungated, self-hosted interactive walkthrough of the golden thread (RFQ email → Lens → geometry → Kalk price → quote out), built as one Astro island (`TourPlayer`). Real app screenshots as frames, hotspot + dialog per step. Benchmarks applied: 8 steps (within the 5–13 sweet spot), ≤ 30 words per dialog, multi-CTA at the end, completable in ~2 minutes.

Used: full-viewport on `/tour` (P10); [TOUR-TEASER] cards elsewhere link there. No embedding of the full player on other pages at launch (keeps their JS at zero).

## 2. Component behavior

- **Frames:** AVIF screenshots (1600×1000, browser-chrome framed per 03 §4), preloaded next-frame. Until real screenshots exist: gray placeholder frames with step labels — `TBD(screenshots)`, structure ships regardless.
- **Hotspot:** pulsing ring (brand color; purple for Lens steps) positioned by % coords per step; click/tap/Enter advances. Dialog card anchored to hotspot: step copy + counter („3/8") + Weiter/Zurück.
- **Navigation:** click hotspot, arrow keys, or dots; Esc = restart prompt on final. Progress bar top. Deep-linkable (`/tour#5` → step 5).
- **A11y:** WAI-ARIA — dialog `role="dialog"` `aria-live="polite"`, step change announced („Schritt 3 von 8: …"), hotspot is a `<button>`, full keyboard path, reduced-motion kills pulse.
- **Mobile:** frames pan/zoom to hotspot region (CSS transform-origin per step); dialogs bottom-sheet style. Keep total time under 90 s on mobile.
- **Analytics:** events per `06 §5` (Started on first advance, Step per step, Completed, CTA Click).
- **Data:** steps as content collection entries: `{ step, image, hotspot: {x%, y%}, de: {title, body}, en: {…}, accent: 'brand'|'lens' }`.

## 3. Step script (final copy)

| # | Frame (app view) | Accent | DE (title / body) | EN |
|---|---|---|---|---|
| 1 | Inbox/quote list with fresh RFQ email item | brand | **Eine Anfrage kommt rein.** Der Kunde hat seine RFQ einfach per E-Mail geschickt — Tolera hat daraus schon einen Angebotsentwurf gemacht. | **An RFQ arrives.** The customer simply emailed their RFQ — Tolera already turned it into a draft quote. |
| 2 | Draft quote with parsed line items, Lens suggestions at 55% opacity | lens | **Lens hat mitgelesen.** Positionen, Mengen, Werkstoff — als lila Vorschläge. Nichts wird ohne Ihr OK übernommen. | **Lens read along.** Line items, quantities, material — as purple suggestions. Nothing is applied without your OK. |
| 3 | Found-in-Files panel over drawing, finding highlighted | lens | **Jeder Fund zeigt seine Quelle.** Toleranz 
„±0,02" gefunden — ein Klick springt zur Stelle auf der Zeichnung. | **Every finding shows its source.** Tolerance "±0.02" found — one click jumps to the spot on the drawing. |
| 4 | 3D viewer, part loaded, feature highlights | brand | **Die Geometrie ist analysiert.** Maße, Volumen, Bearbeitungsmerkmale — direkt aus der STEP-Datei, in Sekunden. | **Geometry analyzed.** Dimensions, volume, machined features — straight from the STEP file, in seconds. |
| 5 | DFM warning pointing at model region | brand | **Ein Hinweis, bevor es teuer wird.** Tolera markiert eine kritische Stelle — Sie entscheiden, ob Sie anders anbieten. | **A warning before it gets expensive.** Tolera flags a critical feature — you decide whether to quote differently. |
| 6 | Costing view: Kalk formula + quantity breaks | brand | **Kalk rechnet mit Ihrer Logik.** Lesbare Formeln, Preise je Stückzahl. Jeder Wert zeigt seinen Rechenweg. | **Kalk prices with your logic.** Readable formulas, prices per quantity. Every value shows its math. |
| 7 | Review/approval state on quote | brand | **Regeln sichern die Freigabe.** Enge Toleranz erkannt → Technik muss freigeben. Nichts rutscht durch. | **Rules guard the approval.** Tight tolerance detected → engineering must sign off. Nothing slips through. |
| 8 | Digital Quote buyer view with order button | brand | **Das Angebot ist draußen.** Ihr Kunde wählt Stückzahl und Termin — und bestellt online. Minuten, nicht Tage. | **The quote is out.** Your customer picks quantity and lead time — and orders online. Minutes, not days. |

**Final card (after step 8):** H3 „Das war der Weg einer Anfrage." / "That was one RFQ's journey." + primary **Kostenlos testen** + secondary **Preise ansehen** (`/preise`) + tertiary „Tour neu starten".

## 4. Screenshot production checklist (`TBD(screenshots)`)

Take from the seeded demo org (golden fixtures), German UI, realistic Fechner-like data (no lorem): 8 frames per §3 + hero composite (P1) + per-page heroes (P2 costing, P3 viewer, P4 Found-in-Files) + bento crops. Consistent window size 1600×1000, light theme, no personal data, Werkstoffnummern visible where natural (1.4301!). Export PNG → build converts to AVIF.
