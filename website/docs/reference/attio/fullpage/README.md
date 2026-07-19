# Attio full-page reference captures (Design A)

> 📄 See **[../VISUAL-REFERENCE.html](../VISUAL-REFERENCE.html)** to view these stitched pages alongside the per-section frames and measured tokens in one browsable page.

Captured 2026-07-18 from attio.com at 1456px-wide viewport, scrolled and stitched into
full-length page images. **Internal build reference only** — study section order, vertical
rhythm, layout, and spacing. Never copy assets, copy, CSS, or fonts; never deploy these
files. See `../README.md` and the Design-A docs for what we take vs. change.

## Files
- `redefine.jpg` — the /redefine essay page (hero crisp; body text is inherently scroll-faded).
- `customers-part1.jpg`, `customers-part2.jpg` — /customers, top→bottom.
- `pricing-part1.jpg`, `pricing-part2.jpg` — /pricing/eur, top→bottom (4 tier cards → comparison table → FAQ).
- `platform-data-part1..3.jpg` — /platform/data, top→bottom.
- `home-part1..5.jpg` — the homepage, top→bottom.

Multi-part files are simple vertical slices of one tall stitched page; read them in numeric
order as a single continuous page.

## Reading caveat — scroll-jacked / reveal-animated sections
Attio's home and several platform sections are **scroll-driven**: content fades/transforms
in as you scroll, and pinned sections hold while an inner element animates. A static
scroll-and-stitch can't reproduce these, so in the stitched images:
- The **homepage hero** and several mid bands ("intelligent system", "self-building",
  "universal context", "run at any scale") read **blank or ghosted** — that's the pre/mid
  animation state, not missing content.
- `platform-data` has one **blank mid-band** for the same reason (a pinned reveal).

For those sections, use the **per-section hero frames** already in the main
`../` reference set (captured at their revealed state), which show the intended end-state
crisply. The full-page stitches are authoritative for **section order, structure, and the
static lower half** (customer logos, changelog grid, footer); the hero frames are
authoritative for the **animated bands' final look**.
