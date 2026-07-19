# 08 — Manifesto page spec (`/manifest`)

Footer-only page (per Benjamin: linked in the menu at the bottom of the page, like Attio's Manifesto). It's the philosophical version of the positioning: why quoting speed decides who wins, and what we believe about AI in the Werkstatt.

Patterns: `manifesto-1440-01`…`manifesto-1440-05` frames — a dictionary-style hero, a serif essay in a narrow column, a numbered principles list, a quiet closing, one expressive finale.

## Structure

1. **Hero** (dictionary pattern, lots of whitespace): tiny `eyebrow` „/ WARUM TOLERA" top-left of the text block; then `display-1` in two lines:
   - Line 1 (definition subject): „**Angebot** /anˈɡeboːt/ *n.*"
   - Line 2 (the redefinition, `ink`): „Der Moment, in dem ein Auftrag gewonnen wird."
   - (PROPOSED — Benjamin may prefer „Toleranz" as the defined word; decide at build.)
   - Below: a small dot-matrix ornament in `line` (own SVG, not Attio's).
2. **Essay** — Source Serif 4, `680px` column, `20/32` size, generous paragraph spacing, scroll-progress dots in the left margin (3 sections). Content beats (copy TO WRITE by Benjamin with Claude, from positioning §3/§9 raw material — do not invent facts):
   - I. The lost order: the RFQ arrived Monday, the answer was ready Friday, the order went Tuesday. „Der schnellste Anbieter gewinnt — auch wenn er nicht der günstigste ist."
   - II. Why it stayed this way: quoting lives in Excel and in one person's head; every RFQ is triage; the pile decides.
   - III. What has changed: the tools finally exist to answer every RFQ — without giving up control.
3. **Numbered principles** (`[1]`–`[4]` mono-labels, `manifesto-1440-03` pattern): each a one-line `h3` claim + one `mute` sentence:
   - [1] Jede Anfrage verdient eine Antwort.
   - [2] Ihre Preise, nicht Durchschnittswerte.
   - [3] KI im Vier-Augen-Prinzip. — Tolera schlägt vor, Sie entscheiden.
   - [4] Das Wissen gehört dem Betrieb. — nicht einem einzelnen Kopf.
4. **Closing** (serif): „Deshalb bauen wir Tolera." + two short sentences; signature line „Benjamin — Gründer, Tolera" (optional, Benjamin decides).
5. **Finale set-piece:** `display-xl` two-tone line on a soft radial wash — PROPOSED: „Zeichnung rein. *Angebot raus.*" (second half in serif italic) → primary CTA. This is the only expressive gradient on the site; keep it warm-neutral (mist→paper with a hint of `accent-soft`), no purple.
6. Footer.

## Rules
- DE first; EN version is a translation pass, same structure.
- No product screenshots on this page. No stats. It's the one page that is words.
- Copy status: skeleton above is directional. Final essay is a writing task for Benjamin + Claude in the build session, reviewed before launch.

## Acceptance
Reads in under 3 minutes; typography perfect (serif rendering, „" quotes, no widows on the finale); scroll dots track the 3 essay sections; reduced-motion fine.
