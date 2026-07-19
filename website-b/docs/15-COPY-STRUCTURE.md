# 15 — Copy structure (replicable skeleton) — Design B

**What this is:** the *structure* of the reference site's copy — the slots each page has, the formula for each slot, how many blocks, and the ordering — so we can replicate the **pattern** with **Tolera's own words** (from the positioning doc). This is the reusable skeleton, not a reproduction of the reference's marketing prose. For each slot: its role, a length/formula guide, and the Tolera source. Where a short fragment is shown, it's an *illustrative label*, not copy to ship.

**Copy source of truth:** `docs/analysis/POSITIONING-AND-MESSAGING.md` (§3 hero/messaging, §6 taxonomy). All shippable strings come from there, in `content/de.json` / `content/en.json`. Tone: plain technical German, Sie-Form, verbs over adjectives; Design-B headlines are short (2–4 words in the colored highlight) with the trailing period dropped.

## 1. Global copy formulas (used everywhere)

- **Eyebrow (highlighted):** the section/module *label*, 2–4 words, in a color-highlight box. Formula: `[Was dieser Abschnitt ist]`. Tolera: stage/brand name („Anfrage rein", „Kalkulieren", „KI").
- **Hero headline:** `[Nutzen] + [Mechanismus]` in one line, benefit first. Tolera: from positioning §3 (e.g. the C1 hero line). Big, black, no period.
- **Hero subhead:** `[Was das Produkt tut, ein Satz] + [pointierter Kontrast]`, the contrast clause highlighted. Tolera formula: „Tolera macht aus jeder Anfrage … — [Kontrast]".
- **Section head:** short colored-highlight phrase + a one-sentence expansion below.
- **Feature line (product-as-actor):** `[aktives Verb] + [mit Ihren Daten/Sätzen] + [Kontrollklausel bei KI]`. Verbs: liest, erkennt, kalkuliert, markiert, schlägt vor.
- **CTA labels:** primary „Demo vereinbaren"; secondary „Rundgang starten →" / „<Stufe> ansehen →"; tertiary „Mehr zu <X> →".
- **Trust strip:** „🇩🇪 Daten in Deutschland · DSGVO · keine Kreditkarte".
- **Never:** invented metrics, fake testimonials, ITAR/CMMC, ask-anything/agents claims (see per-page rules).

## 2. Homepage copy skeleton
1. Eyebrow/none → **Hero headline** (pain-led, positioning §3) → **subhead** (mechanism, contrast highlighted) → CTA pair → trust strip.
2. **3–4 rotating color sections**, each: `[Highlight-Headline 2–4 Worte]` + one supporting sentence + mockup + optional callout bubble. (Reference uses: a "paper is dead"-type provocation, an "on autopilot" capability, an "exact costs" capability — Tolera maps these to: Zeichnung→Angebot, Jede Anfrage ein Angebot, Ihre Sätze nicht Durchschnitte.)
3. **„Alles verbunden" module grid** — intro sentence + N cards, each `[Modulname]` + `[Ein-Satz-Nutzen]` + `[Verb-Link]` (e.g. „Los geht's →"). Tolera: the 5 stages.
4. **Onboarding teaser** — `[Highlight] + [Zahl?]` headline + one paragraph + link. Tolera: „Einführung" (no "80% faster"-style metric unless real).
5. **Social proof** (founder interview / testimonial) — **empty until Fechner** (positioning §8.1).
6. **Closing CTA** — scheduler invite line + phone/CTA.

## 3. Product module page copy skeleton (the template — build once)
Order (fill with each stage's copy; see 10-PAGE-PRODUCT-DETAIL):
- **A. Hero:** eyebrow `[Stage/Brand label]` (color highlight) → headline `[Nutzen + Mechanismus]` → subhead `[Was es tut] + [Kontrast, highlighted]` → CTA.
- **B. Black interstitial:** `[Highlight-Aussage]` + one sentence („… gibt Ihrem Team die Infos, die es braucht").
- **C. Numbered stepper (1..4):** each = `[Fähigkeit, 2–4 Worte]` + `[1 Satz Erklärung]`. Tolera: the stage's 3–4 capabilities (verify vs spec anchor).
- **D. Interactive-demo band:** „Sehen Sie selbst. Jetzt gleich." + „Klicken Sie sich durch die Demo".
- **E. Second feature block:** paired headline + micro-list `1..3` (`[Aktion]` each).
- **F. Pain Q&A (×4):** each = `[Painfrage]?` + one honest paragraph. Tolera: draw from the lost-order pains (Excel, tribal knowledge, no instant reply, idle WIP) — reframed to Tolera's shop, no invented numbers.
- **G. FAQ (×N):** `[Frage]?` + factual answer (Dateiformate, DSGVO/AVV, Geräte, Onboarding-Aufwand, warum Live-Daten).
- **H. Closing CTA** + **I. module grid** (same as home §3) + footer.

## 4. KI / Archie page copy skeleton
- **Hero:** big centered headline (Tolera: „KI, die vorschlägt. Sie entscheiden.") + subhead (what Lens reads, control clause).
- **Live-demo band:** „LIVE"-chip *only if truly live* + framed extraction demo.
- **Differentiator block:** „Vier-Augen-Prinzip" headline + suggest-then-accept explanation. (Reference splits into Chat/Build/Agents — **Tolera keeps only the read-and-suggest story**; no ask-anything/app-builder/agents.)
- **"What it reads" cards (×4):** E-Mail/PDF · Zeichnungen · STEP · Stücklisten.
- **Security (black):** „In Deutschland gehostet. Ihre Daten bleiben Ihre." — DSGVO/AVV only (**no ITAR/CMMC**).
- **Never-hallucinated block** + **CTA**.

## 5. Why page copy skeleton (Old-vs-New)
- **Black hero:** `[Provokation/Vision headline]` + one-line subhead.
- **Split band label:** left „Bisher" · right „Tolera".
- **Old-vs-New rows (×5–6):** each = **left** `[Status-quo-Artefakt-Titel]` + short ugly-truth sentence; **right** `[Highlight-Headline]` + benefit paragraph + `[Link →]`. Tolera pains → gains (07-PAGE-WARUM lists the rows). No named competitor.
- **Vision/adapting row** + **"See & learn" black section** (links only; no fake press) + **CTA**.

## 6. Launch / Einführung copy skeleton
- **Hero:** eyebrow + `[Differenzierungs-Headline]` + subhead (only true claims) + team photos (real or omit).
- **"Wochen statt Jahre"** comparison (status quo, generic).
- **Phase cards (1..4):** `PHASE n` + `[Titel]` + 1–2 sentences.
- **Shop-simplicity block** + **integrations tie-in** + **support model** (Tolera-true; no invented metrics/community/conference) + **CTA**.

## 7. Integrations copy skeleton
- **Hero:** eyebrow + `[Flow-Headline]` (Tolera: „Alles fließt zusammen.") + subhead (remove data gaps/manual entry/paper) + CTA.
- **"Alles verbinden":** intro + category filter pills + logo/text grid (mark live vs geplant).
- **"Fehlt eine?" / "Partner werden"** pair.
- **FAQ (×3):** offene API? / plug-and-play? / fehlende Integration? — honest.
- **CTA.**

## 8. Small pages
- **Mission/Vision:** 3–5 pinned "beats", each `[kurze Vision-Aussage, Highlight-Keyword]`; values-level (positioning §9), no metrics.
- **Contact:** eyebrow (black box) + headline + subhead + 3 quick links (Anrufen/E-Mail/Demo) + form labels (Vorname/Nachname/E-Mail/Firma/Nachricht).
- **Schedule-Demo:** eyebrow (black box) + „Termin wählen"-subhead + scheduler.

## Rules
- Every slot's *shippable* text comes from the positioning doc or is written with Benjamin — the skeleton here defines only the **shape**.
- Keep the highlight-phrase short (2–4 words) so the marker reads as emphasis, not a banner.
- Bilingual: DE first, EN mirror (mark EN `"draft": true` until native pass).
- Honesty gates apply per §1 and per-page notes above.
