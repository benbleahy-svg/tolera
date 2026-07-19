# 14 — Motion & CSS notes (Design B)

Measured from fulcrumpro.com (computed styles + stylesheet/interaction inspection, 2026-07-17). These are **facts about how the reference behaves**, to rebuild the *feel* from scratch with our own code (Motion/framer-motion + a scroll lib). We do not copy Fulcrum's CSS or Webflow export.

## 1. Timing & easing (measured)
- Hover/interaction transitions: **0.2s ease** (dominant, ~90+ elements/page). Some **0.4s ease** for larger moves; a few 0.1s/0.05s/0.12s micro-timings.
- Only two CSS `@keyframes` exist site-wide: **`spin`** (loaders) and **`menuIn`** (mega-menu open). Everything else is transition- or scroll-driven.
- Scroll interactions run through **Webflow IX2** — ~23 `data-w-id` interaction nodes per product page. Rebuild these as scroll-progress effects (IntersectionObserver / scroll-linked `useScroll`).

## 2. The highlight marker (signature — exact mechanism)
- It is **not** an animated sweep. It's an **inline `<span>` with a solid brand-color `background-color` and `padding: 0 5px`** (classes `highlight-span-green/yellow/aqua/blue`, `highlight-text-*`, `highlight-hero-title`). The text sits on a solid color block, like a printed highlighter.
- Colors observed: green `rgb(61,201,117)`, blue `rgb(56,64,234)`, yellow, aqua, plus purple `rgb(56,64,234)`-family on some tour chips.
- **Build:** wrap the key words in `<mark class="hl hl--green">`; `mark{background:var(--hl);padding:0 .28em;color:inherit;box-decoration-break:clone}`. Optional entrance: fade/scale-in as it enters view (or a `background-size` sweep if you want more motion than Fulcrum) — keep it static under `prefers-reduced-motion`.
- Per-page/per-module the highlight color changes (green on Job-Tracking, yellow on Autoschedule, orange on Inventory, blue on BOM/Shipping, aqua on Purchasing/Finance/Demand, black box on Contact/Demo). Drive via a CSS var set on the page/section.

## 3. 3D-tilted device mockups
- Implemented via `transform: matrix3d(...)` (a `perspective()` + `rotateY`/`rotateX`). Reproduce with `transform: perspective(1600px) rotateY(-12deg) rotateX(4deg)` range; mockups **bleed past the container** on one edge.
- Big soft shadow measured e.g. `rgba(0,0,0,.23) 3px 30px 50px 30px` and `rgba(0,0,0,.15) 0 40px 80px`. Use `shadow-float` from 01 §4.
- Subtle scroll parallax: tie a few degrees of `rotateY` + small `translateY` to scroll progress. Reduced-motion → static.

## 4. Scroll-linked numbered stepper (product pages)
- A vertical `1..4` list next to a mockup: as you scroll, the **active item becomes bold/expanded with its explanatory sentence**, siblings stay faded; **orange leader-arrows** (SVG) animate from the mockup to result cards.
- Build: IntersectionObserver or scroll-progress → set `active` index → animate opacity/height of the active item's body (0.2–0.4s ease); draw arrows with `stroke-dashoffset`.

## 5. Pinned / scroll-jacked sections
- The **Mission page** ("The future is connected") and the homepage **scheduler/"everything connected"** section are **pinned** (Webflow `pin-spacer` / ScrollTrigger): the section holds while inner content advances. A left **progress-dash rail** fills as beats pass.
- Build with a ScrollTrigger-style pin (`md+` only). **Hazards:** scroll-jacking hurts a11y and mobile — always provide a normal-scroll fallback, never trap scroll, honor `prefers-reduced-motion`. Prefer *non-pinned* scroll-reveal unless a page (Mission) really wants the set-piece.

## 6. Horizontal "Mehr entdecken" slider
- Webflow slider (`explore-more-slider`, `w-slide`, `w-slider-dot`) for the module cross-link cards. Rebuild as a snap-scroll row + dot/arrow nav; on mobile it's the primary way to page the cards (`mobile-390-02`).

## 7. Other
- **Constellation/particle** field on black hero sections (Why): lightweight `<canvas>`, drifting dots + faint links; static under reduced-motion.
- **Mega-menu**: `menuIn` keyframe on open; full-width white panel + dark utility bar.
- **Radii**: 20px dominant (cards/mockups), 24/30 larger, 4 small, pill buttons. **Borders**: 1.5–2px solid brand-color outlines (green/blue/orange/lime) — the card signature.
- **Buttons/hover**: scale ~1.02 + shadow step at 0.2s ease; tertiary links translate the `→` ~3px.

## Global rules
- Everything degrades gracefully under `prefers-reduced-motion: reduce`: no pin, no parallax, no particles, no marker motion (show marker statically), no autoplay; keep opacity fades.
- Keep JS-driven scroll effects off the critical path (lazy, `md+`), so hero LCP < 2.5s and CLS < 0.1.
- Rebuild all of this ourselves — no Webflow export, no Fulcrum CSS/JS.
