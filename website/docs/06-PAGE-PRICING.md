# 06 — Pricing page spec (`/preise`)

Binding pricing decisions: `DECISIONS.md` [2026-07-17] — **indicative tiers published now**: Starter ~€299/Monat · Growth ~€599–799/Monat · Enterprise auf Anfrage; annual discount shown; **no free tier**; 14-day full-featured trial, keine Kreditkarte. „~"-Indikativ bleibt, bis Paddle-Checkout live ist (positioning §8.5).

Patterns: `pricing-1440-01`…`pricing-1440-08` frames.

## Sections

1. **Hero:** centered `display-1` — PROPOSED: „Ein Preis, der sich mit einem Auftrag rechnet." + sub „Alle Preise offen. 14 Tage kostenlos testen — keine Kreditkarte." + **Monatlich/Jährlich toggle** (pill, default Jährlich with „Spart 2 Monate"-style note — exact discount is an `OPEN:` until Benjamin fixes it).
2. **Three tier cards** (not four — we have 3):
   - **Starter** — ab ~299 € / Monat. „Für den Einstieg: ein Betrieb, die Kern-Pipeline." CTA „Kostenlos testen".
   - **Growth** (highlighted, `accent` border, „Beliebt"-chip) — ab ~599 € / Monat. „Für Betriebe, die jede Anfrage beantworten wollen." CTA „Kostenlos testen".
   - **Enterprise** — Auf Anfrage. „Mehrere Standorte, besondere Anforderungen." CTA „Kontakt aufnehmen".
   - Card anatomy per design system §6.11: name, price (`display-2` number + `small` „pro Monat, jährlich abgerechnet"), one-line audience, 5–7 check bullets, CTA.
   - **Tier feature allocation is an `OPEN:` decision** — Benjamin must approve which capabilities land in Starter vs Growth before launch. Build with a placeholder allocation clearly marked in the PR.
3. **Trust strip** under cards: „🇩🇪 Daten in Deutschland · DSGVO · keine Kreditkarte · monatlich kündbar" (kündbar-claim only if true — confirm).
4. **Comparison table** (sticky tier header on scroll, `pricing-1440-03`-style): categories = the 5 workflow stages + „Plattform" (Nutzer, Support, API, DSGVO/AVV). Cells: `ok` check / dash / short text. Content follows the approved allocation; keep rows to capabilities that exist in v1.
5. **FAQ** (6–8 items, accordion — this is our addition; honest answers): Testphase, keine Kreditkarte, Kündigung, Datenstandort/AVV, Onboarding-Aufwand, Preise indikativ?, Rabatt Jahreszahlung, Wer zählt als Nutzer?
6. **Final CTA band** + footer.

## Rules
- Prices always German format („299 €", nbsp before €), „~"/„ab" honesty marker consistently.
- No fake logos/testimonials on this page pre-pilot.
- The tier names Starter/Growth/Enterprise are per DECISIONS; German descriptors around them, no Denglisch beyond the names.

## Acceptance
Toggle switches all prices without layout shift; sticky header behavior matches reference at 1440; table collapses to per-tier accordions at `sm`; all price strings from one `content/pricing.json` source.
