# 08 — Walkthrough spec (`/demo/rundgang`) — Design B

Fulcrum's `/lp/walkthrough` is a **full-viewport embedded interactive product tour** (Storylane) with a step-picker overlay listing workflows, a „KEEP EXPLORING" button, and a step counter („1 OF 7"). For Tolera this is the self-serve „Rundgang" — a guided click-through of the real app on seeded data.

Reference: `walkthrough-1440-01-storylane-tour.jpg`. This page is mostly a host for the tour, so it's light on our own layout.

## Structure

1. **Minimal nav** — logo + „Demo vereinbaren" only (focus the visitor on the tour; Fulcrum strips the nav here too).
2. **Full-viewport tour host** — the embedded interactive demo fills the screen. Options, in order of preference:
   - **a) Real embedded tour** (Storylane/Navattic/Arcade or self-hosted) of the actual app on the seeded Fechner-style org — the honest, best version.
   - **b) Interim:** a scripted click-through built from cropped app screenshots with our own step overlay (below), until a real tour exists.
3. **Step-picker overlay** (our component, styled in Design B): a floating `r-lg` card, „Rundgang" title + sub „Wählen Sie einen Ablauf." + a numbered list = the **5 workflow stages** (positioning §6.3):
   1. Anfrage rein — E-Mail wird zum strukturierten Auftrag *(Lens)*
   2. Teil verstehen — 3D & DFM *(Kontur)*
   3. Kalkulieren — Ihre Sätze, Ihre Margen *(Kalk)*
   4. Anbieten & gewinnen — White-Label-Angebot
   5. Demo vereinbaren — „Es gibt noch mehr zu sehen."
   Step counter chip („1 VON 5") + „Weiter erkunden →" lime button.
4. **Fallthrough CTA** — after the tour, a lime CTA band „Bereit? 14 Tage kostenlos testen · keine Kreditkarte" + „Demo vereinbaren".

## Rules
- If using a third-party tour embed, load it lazily and **behind a DSGVO-clean consent** (no cookies set pre-consent); prefer EU-hosted or self-hosted. Note the vendor choice as an `OPEN:` for Benjamin.
- The tour shows the **real app on seeded data** — same DACH-native data rules (positioning §6.1). No mocked-up capabilities the product lacks.
- Don't imply „LIVE" if it's a recorded tour.

## Acceptance
- Tour fills the viewport at 1440/768/390 (mobile: overlay becomes a bottom sheet, `mobile` pattern); step-picker matches the 5 stages; consent gate present if third-party; lime CTA on exit.
