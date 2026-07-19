# Fulcrum reference frames — index (Design B)

> 📄 **[VISUAL-REFERENCE.html](./VISUAL-REFERENCE.html)** — every screenshot below (frames, product template, sub-pages, full-page stitches) plus the measured tokens (type scale, live color swatches, radii, shadows, motion) in one browsable page. Open it in a browser. See also **[MEASURED-FACTS.md](./MEASURED-FACTS.md)**.

Captured 2026-07-17 from fulcrumpro.com at 1440px and 390px. **Internal build reference only: study structure, energy, motion, spacing. Never copy assets, copy, CSS, fonts (Gilroy → substitute Hanken Grotesk), retro artefacts or illustrations; never deploy these files.** What we take vs. change is defined in `01-DESIGN-SYSTEM.md` (esp. §5 layout devices + §8 motion).

**Folders:** top-level frames (home/why/archie/walkthrough/nav) = the core pages; `products/` = the product-module pages (a shared template `_template-*` + one hero per module); `pages/` = Launch, Integrations, Mission, Contact, Schedule-Demo, and the Why/Start nav dropdowns. Motion facts are consolidated in `14-MOTION-AND-CSS.md`; the copy skeleton in `15-COPY-STRUCTURE.md`.

## products/ — product module pages (shared template)
`_template-01-hero-job-tracking` (eyebrow color-highlight → big black headline → tilted iPad, the reusable hero) · `_template-02-black-interstitial` (white headline + green highlight) · `_template-03-numbered-stepper-arrows` (scroll-linked 1–4 list + orange leader-arrows to result cards) · `_template-04-interactive-tour` (guided-demo tooltip) · `_template-05-howitworks-stepper` (Autoschedule "here's how it works" + highlighted keyword list) · `_template-06-feature-zoom-certs` (feature zoom + ISO/ITAR badges — **do NOT copy the certs**). Per-module heroes (each with its own highlight color): `quoting` (lime), `production-scheduling` (yellow), `quality-control` (fulcrum-brand hero), `job-costing` (blue), `real-time-inventory` (orange), `grouped-work` (blue), `live-reports` (yellow), `shipping-receiving` (blue), `bom-routing` (blue), `purchasing-planning` (aqua), `finance` (aqua), `demand-planning` (aqua). → 10-PAGE-PRODUCT-DETAIL maps these to Tolera's 5 stage pages.

## pages/ — Launch, Integrations, Mission, Contact, Demo, nav dropdowns
`launch-01…04` (floating team cards → "weeks not years" comparison → phase cards → simplicity/integrate/support → testimonial pile + CTA; → 11) · `integrations-01…03` ("Let It Flow" + data-flow mockups → category-filter + logo grid → missing/partner + FAQ; → 12) · `mission-01-hero-pinned` (scroll-jacked vision story, progress-dash rail; → 13 §1 + 14-MOTION §5) · `contact` (black-box eyebrow + 3 quick links + form; → 13 §2) · `schedule-demo` (black-box eyebrow + scheduler; → 13 §3) · `nav-dropdown-why` (Why Fulcrum + Mission + Blog[excluded] + "Built for" industry pages[excluded]) · `nav-dropdown-start` (Try Now/Test Drive + phone + Contact + Schedule a Demo).

## Home (`home-1440-01` … `10`)
| Frame | What to study |
|---|---|
| 01 hero | Left huge black headline + sub + CTA; tilted iPad+desktop mockups bleeding in from the right; "Scroll Down" ticker |
| 02 paper-is-dead-green | **Green** section head; tilted tablet mockup; faint caliper line-art bleeding off-edge |
| 03 job-costs-blue-callouts | **Blue** section head; big costing mockup; **floating callout bubbles** (blue/orange, colored glow) annotating it |
| 04 autoschedule-board | Full scheduler UI mockup in a rounded frame |
| 05 on-time-orange | **Orange** section head; mockup + body left/right split |
| 06 scheduler-pinned | Pinned-scroll section: cards slide across a large board (ScrollTrigger pin) |
| 07 connected-cards-tricolor | 3-up **colored-outline feature cards** (green/lime/blue borders): screenshot + title + "action →" |
| 08 launch-team-cards | Team-photo cards with colored outlines + name tags |
| 09 testimonial-video | Framed customer video + name; green stamp motif |
| 10 testimonial-calendar | Inline scheduling calendar card |

## Nav
`nav-mega-product`: 3-col icon-grid mega-menu + dark bottom utility bar. `nav-dropdown-archie`: left promo card + Chat/Build/Agents rows with status chips.

## KI / Archie (`archie-1440-01` … `07`)
01 centered big hero + "LIVE INTERACTIVE DEMO" framed app · 02 **black** "Built Secure" interstitial · 03 chat split (claim left, chat UI right) · 04 build-tools section · 05 big **lime** CTA pill on black · 06 agents cards · 07 footer mega. *(For Tolera we use the layout, not Archie's ask/build/agents/ITAR claims — see 06.)*

## Warum / Why (`why-1440-01` … `07`)
01 **black hero + animated constellation** · 02–04 **Old-Software-vs-Fulcrum split**: left = crude retro artefact (Win-95 dialog, serif/mono, gray/blue chrome), right = bright `green-wash` card with **lime-marked** colored header · 05 black "See and learn more" · 06 inline scheduler · 07 footer. This split is Design B's signature — see 07-PAGE-WARUM.

## Walkthrough (`walkthrough-1440-01`)
Full-viewport embedded interactive tour (Storylane) with a step-picker overlay (numbered workflows), "1 OF 7" counter, "KEEP EXPLORING" button. See 08.

## Mobile (`mobile-390-01…03`)
Home hero (headline over tilted mockup), home card slider with dot/arrow nav, Why old-vs-new stacked (before-then-after).

## Measured facts (computed styles, 1440)
- Font **Gilroy** (licensed → we use Hanken Grotesk): H1 subline w300; **section heads 51.84px / w600 / ls -0.75px, each in a saturated color** (green `#3DC975`, orange `#FF5C16`, blue `#3840EA`); nav 20px w500.
- Accent palette: green `#3DC975`, orange `#FF5C16`, blue `#3840EA`, **lime `#DDF83B`** (highlighter/CTA), true black `#000`.
- Radii: **20px** dominant card, 24/30/4. Buttons pill.
- Shadows: big soft `0 40px 80px rgba(0,0,0,.15)`; colored inset glow on callout bubbles.
- Borders: **1.5px colored outlines** (blue/orange/green/lime/black) — the card signature; 1px white on callouts.
- Transforms: `matrix3d` — device mockups tilted in 3D (perspective + rotateY/rotateX).
- Transitions: **0.2s ease** (hovers) / 0.4s ease (larger). Webflow + ScrollTrigger (pin-spacer), horizontal "explore-more-slider", `menuIn`/`spin` keyframes, constellation particles on black sections.
- Container ≈1300px; sections breathe large; mockups bleed past the container on one edge; full-black interstitials alternate with white.
