# 09 — TBD Register (fill before launch)

Every `TBD(key)` in these docs, who resolves it, and what blocks on it. CI blocks launch builds while any of these remain in rendered HTML (`06 §6`). Sorted by owner.

## Benjamin (business decisions)

| Key | What | Blocks |
|---|---|---|
| `prices` / `price-starter` / `price-growth` | Numeric EUR + CHF prices, Starter & Growth | P9, P1-faq, JSON-LD offers |
| `annual-discount` | Annual billing discount % | P9 toggles/FAQ |
| `tier-features` / `quota` / `integrations-tier` / `sso-tier` | Feature matrix per tier (from product feature gates) | P9 cards |
| `logo` | Wordmark/logo files (SVG + favicon set) | Header, footer, OG images |
| `entity` | Legal entity: name, form, address, register, USt-IdNr., W-IdNr., phone | Impressum, footer ©, Datenschutz controller |
| `contact-email` | Public contact address (suggest hallo@tolera.eu) | P12, Organization JSON-LD |
| `founder-bio` | 3–4 sentence founder story (+ photo?) | P12 |
| `agb` | Terms: lawyer-reviewed or link to app terms | P13 |
| `privacy-review` | Legal review of Datenschutzerklärung draft | P13 |
| `social` | Any social profiles (LinkedIn?) for sameAs | JSON-LD |
| `plausible-mode` | Plausible cloud (EU) vs self-host/proxy | 06 §5 |

## Fechner pilot (needs permission + measurement)

| Key | What | Blocks |
|---|---|---|
| `fechner` / `fechner-details` / `fechner-quote` | Permission, company descriptor, testimonial quote + name/role, shop photos | P1-case, P12 |
| `pilot-metrics` (claim C5) | Measured before/after time per quote | P1-case numbers; until then qualitative only |

## Product build (verify against shipped v1.x)

| Key | What | Blocks |
|---|---|---|
| `hosting-region` (C7) | Actual DB/file hosting region of the app — is „Daten in Deutschland" literally true? | Trust strip, P1-dach, P4-trust, P11 table, Datenschutz |
| `format-tier` (C6) | Are conversion-tier formats (SLDPRT, IPT, CATIA…) live at launch? | P1/P3 format lists |
| `ai-routing` | Lens EU/GDPR model-routing statement — exact wording from product | P4-trust |
| `scan-limits` | What scanned/raster drawings actually work | P4-faq |
| `thread-detection` / `profile-scope` / `dxf-scope` / `nesting` / `wuerth-live` | Feature nuances claimed on process pages — confirm shipped behavior | P5–P8 |
| `export-scope` / `avv-process` | Data export mechanism; AVV signing flow | P9-faq |
| `screenshots` | Real app screenshots per `08 §4` | All heroes, bento, tour |

## Website build phase

| Key | What | Blocks |
|---|---|---|
| `pp-verify-date` | Re-verify every PP claim against paperlessparts.com public pages; record URLs + date as footnotes | P11 launch |

## Standing rule

If, while building, a fact is needed that isn't in these docs and isn't resolvable from the product repo's `DECISIONS.md`/spec: **do not invent it** — add it here as a new `TBD(key)`, use the marker in copy, and continue.
