# 07 — Customers page spec (`/kunden`)

**Reality check:** pre-pilot we have zero publishable references (positioning §8.1: Fechner slot is blocked until pilot success + written sign-off; **never fake an interim testimonial**). So `/kunden` launches as an honest **pilot-recruiting page** in the customers-page layout, and converts into a real customers page as stories land.

Patterns: `customers-1440-01`…`customers-1440-05` frames.

## Launch variant (v1 — „Pilotbetriebe")

1. **Hero:** badge „Kunden" · `display-1` PROPOSED: „Gebaut im Betrieb, nicht im Büro." + sub about building with German job shops.
2. **Industry band** (replaces Attio's logo band until logos exist): hairline grid of the segments we serve, `mono-label` text cells — Blechbearbeitung · CNC-Zerspanung · Laserschneiden · Abkanten · Baugruppen. No fake logos.
3. **Featured story slot** (big card, `customers-1440-02` layout): shipped as the **Fechner placeholder** — grayed wordmark slot, eyebrow „PILOT", claim „Unser Pilotbetrieb: ein Lohnfertiger aus [Region]." + neutral photo placeholder. Hidden behind a content flag until sign-off; until then the slot renders the **pilot-program card** instead: „Pilotbetrieb werden" — 3 bullet benefits + CTA (mailto/form).
4. **Story card grid** (2-col, alternating media/text): v1 renders 2–4 **capability vignettes** instead of case studies — each an honest mini-story of the product on seeded data („Von der E-Mail zum Angebot in einer Sitzung" etc.), clearly framed as product walkthroughs, not customer claims. Each links to the matching stage page.
5. **CTA band** + footer.

## Post-pilot conversion (documented now, built later)
Featured card gets the real Fechner story (metric headline black + gray subtitle, „Zur Geschichte →"); vignettes are progressively replaced by real stories (Uptool format: first name + shop + number). Logo band replaces industry band once ≥4 logos with written permission exist.

## Rules
- Nothing on this page may imply a customer relationship that doesn't exist. Legal-safe framing: „Pilot", „Walkthrough", „auf Beispieldaten".
- Fotografie: only real shop photos with permission; until then UI media cards.

## Acceptance
Layout parity with reference at 3 breakpoints; the page reads honest and confident with zero customers; flag-flip to the Fechner variant requires only content changes, no layout work.
