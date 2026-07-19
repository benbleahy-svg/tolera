# 13 — Company pages: Mission/Vision, Contact, Schedule-Demo (Design B)

Three small pages from the Why/Start submenus. References: `pages/mission-01-hero-pinned.jpg`, `pages/contact.jpg`, `pages/schedule-demo.jpg`.

## 1. Mission / Vision — `/mission` (Why submenu)

Fulcrum's Mission page is a **scroll-jacked pinned story** ("The future is connected") with a left stepper rail whose dashes fill as you progress — a manifesto/vision experience. For Tolera, this is the **vision page** and it overlaps the manifesto ideas already folded into `/warum` (07). Decide with Benjamin: either (a) fold vision into `/warum` and skip a separate page, or (b) build a short pinned vision page.

If built:
- **Pinned scroll story** (§5.6 + 14-MOTION §5): a few full-viewport "beats", each a short vision statement (large, centered, color-highlighted key word) on a neutral/black ground, advancing on scroll; left rail = progress dashes.
- Content: Tolera's vision from positioning §9 background (speed decides who wins; every RFQ answered; knowledge in the system) — values-level, **no invented facts/metrics**.
- **Reduced-motion / accessibility:** scroll-jacking is risky — provide a non-pinned fallback (normal vertical scroll of the same beats) and honor `prefers-reduced-motion`. Do not trap scroll on mobile.
- Ends with a CTA to /warum or /demo/rundgang.

## 2. Contact — `/kontakt` (Start submenu)

Simple, honest, Design-B-styled:
- Centered eyebrow („Kontakt", solid black highlight box like Fulcrum's) + `hero`-lite headline + one-line subhead.
- Three quick links row: **Anrufen** (phone) · **E-Mail** (contact@tolera.eu or real) · **Mehr erfahren → Demo vereinbaren**.
- **Contact form**: Vorname, Nachname, E-Mail, Firma, Nachricht. Per safety rules: the build renders the form; **form submission and any data handling is the app/backend's job** — the marketing site only POSTs to a DSGVO-clean endpoint (define endpoint as `OPEN:`; no third-party form that sets cookies pre-consent).
- Footer.

## 3. Schedule a Demo — `/demo` (Start submenu)

- Centered eyebrow („Demo vereinbaren", highlight box) + subhead („Wählen Sie einen Termin — Einladung kommt direkt in Ihren Kalender.").
- **Embedded scheduler** (calendar). Vendor choice is an `OPEN:` — must be DSGVO-clean/EU-hosted, lazy-loaded behind consent (no pre-consent cookies). Fulcrum uses a calendar embed; pick an EU-friendly equivalent.
- Minimal nav (focus on booking). Footer.

## Rules (all three)
- No fake metrics/logos/testimonials. Vision copy stays values-level.
- Any third-party embed (scheduler, form) is DSGVO-gated and EU-hosted where possible; note as `OPEN:`.
- Prohibited-action guardrails: the site never itself submits forms or books on a visitor's behalf — it provides the UI; the visitor acts.

## Acceptance
- Mission (if built): pinned story works at 1440/768, has a reduced-motion + mobile fallback, never traps scroll.
- Contact/Demo: match reference structure; forms/scheduler are consent-gated; all contact details real or clearly-placeholder (`OPEN:`).
