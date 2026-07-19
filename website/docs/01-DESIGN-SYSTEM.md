# 01 — Design System (tokens & layout language)

**Purpose:** the complete visual language for tolera.eu, written as an *original token system* derived from studying attio.com (reference frames in `docs/reference/attio/`). We rebuild the structure, rhythm and level of polish from scratch — we never copy Attio's CSS, assets, fonts-we-don't-license, illustrations or copy. Structural measurements (container widths, type sizes) are facts and are recorded here; everything is implemented as our own Tailwind tokens.

**Reference viewport for all values: 1440px.** Scale down with `clamp()` as specified.

---

## 1. Type

Fonts (all free, self-hosted via `next/font`, subset `latin` + `latin-ext` for umlauts):

| Role | Font | Notes |
|---|---|---|
| Display / headings | **Inter Display** | `next/font/local`, weights 500/600 |
| UI / body | **Inter** (variable) | default body font, weight 400–600 |
| Editorial serif (big quotes, manifesto essay) | **Source Serif 4** | italicless usage, weight 400/500 |
| Mono labels (small technical chips, numbers like `[01]`) | **JetBrains Mono** | weight 400/500, sparingly |

Type scale (desktop → mobile via clamp):

| Token | Size / line-height | Weight | Letter-spacing | Use |
|---|---|---|---|---|
| `display-xl` | 96 / 96 → 48/52 | 600 | -2.4% | Manifesto finale, rare set-pieces |
| `display-1` (H1) | 64 / 61 → 40/44 | 600 | -2.0% | Page heroes, one per page |
| `display-2` (H2) | 40 / 44 → 30/36 | 500 | -1.0% | Section headlines |
| `claim` | 32 / 40 → 24/32 | 500 | -1.0% | Two-tone section claims (see §5.3) |
| `h3` | 20 / 28 | 600 | -0.5% | Sub-feature headlines |
| `body-lg` | 18 / 26 | 400 | -0.25% | Hero sub-lines, intro paragraphs |
| `body` | 16 / 22 | 400 (UI chrome 500) | -1.0% | Default text |
| `small` | 14 / 20 | 500 | -0.25% | Buttons, nav links, captions |
| `eyebrow` | 12 / 16 | 600 | +6%, uppercase optional | Badges, section labels, table headers |
| `serif-quote` | 40 / 48 → 28/36 | 400 (serif) | 0 | Giant centered testimonial/quote |
| `mono-label` | 12 / 16 (mono) | 500 | +2% | `[01]`-style indices, technical chips |

Rules: headlines are sentence case and end with a period ("Jede Anfrage ein Angebot."). Never all-caps except `eyebrow`. Max heading width ~14 words.

## 2. Color (light theme — deliberate deviation from Attio's dark sections)

Semantic tokens (Tailwind CSS variables). Positioning doc §6 fixes two rules: **light theme everywhere** (no dark glassmorphism sections) and **purple appears exclusively for AI suggestions**.

| Token | Hex | Use |
|---|---|---|
| `ink` | `#17181A` | Primary text, primary buttons |
| `ink-soft` | `#43464D` | Secondary text |
| `mute` | `#9BA1AC` | The gray half of two-tone claims, captions, inactive tabs |
| `paper` | `#FFFFFF` | Page background |
| `mist` | `#F6F7F8` | Alternate section background, table stripes |
| `line` | `#E7E8EA` | 1px hairlines everywhere (the drafting-frame system, §5.1) |
| `line-strong` | `#D6D8DC` | Emphasized borders (card edges on mist) |
| `accent` | `#1D5FD6` | Links, focus rings, small highlights, chart lines. Steel blue — used sparingly |
| `accent-soft` | `#E8F0FD` | Chip/badge backgrounds |
| `ai-purple` | `#7C3AED` | **AI suggestions only** — the AI-Governor grammar. Fills at 55% opacity (`rgba(124,58,237,.55)` overlays / `#F3EEFD` tints). Never decorative |
| `ok` | `#188A42` | Checkmarks, "Live"-style states |
| `warn` | `#B7791F` | DFM warnings inside product screenshots only |

No gradients except: soft radial hero wash (`mist` → `paper`) and the manifesto finale. No dark sections; where Attio goes dark (context section, final CTA, footer) we stay on `paper`/`mist` with `ink` text.

## 3. Space, grid, containers

- Base unit 4px. Section vertical padding: **112px** desktop / 64px mobile (hero: 96 top). Between related blocks: 48/32. Card padding 24 or 32.
- Content container: **max-width 1280px** with 24px gutters; inner 12-col grid, 24px gap.
- Narrow text container (manifesto essay, legal): max-width **680px**.
- Breakpoints: 1440 (design ref), `lg` 1024, `md` 768, `sm` 390.

## 4. Radii, borders, shadows

- Radii: `r-sm` 6 (chips), `r-md` 10 (buttons, inputs), `r-lg` 12 (cards), `r-xl` 16 (large media cards), `pill` 999 (badge pills, toggles).
- Borders: 1px `line` everywhere. Cards on `paper` = border, no shadow OR shadow-card; never heavy borders.
- Shadow recipes (own values, in the same quiet register):
  - `shadow-card`: `0 0 1px 1px rgba(16,24,40,.02), 0 4px 12px -2px rgba(16,24,40,.05)`
  - `shadow-media` (big UI screenshots): `0 1px 3px rgba(16,24,40,.06), 0 12px 32px -8px rgba(16,24,40,.10)`
  - `shadow-btn` (primary): subtle top-light inset `inset 0 1px 0 rgba(255,255,255,.08)` + `0 1px 2px rgba(16,24,40,.25)`

## 5. The layout language (what makes it feel "Attio")

These five devices carry ~80% of the feel. Every page uses them.

### 5.1 The drafting frame
Content sits inside a hairline "technical drawing" frame: two vertical 1px `line` rules run the full page height at the container edges; sections are separated by full-width 1px horizontal rules. The gutters outside the frame carry a **dot pattern** (`radial-gradient(circle, #DADCE0 1px, transparent 1px)`, 8px grid) or **diagonal hatching** (45° 1px stripes, 6px period, `line` at 50%) on feature sections. See `home-1440-19-customer-cards.jpg`, `platform-data-1440-03-numbered-features.jpg`. For Tolera this reads as *technische Zeichnung* — lean into it.

### 5.2 Screenshot-as-claim media cards
Product UI is shown cropped, **no browser chrome** (or a minimal three-dot bar for full-app shots), `r-xl` radius, `shadow-media`, 1px border, sitting on `paper` or on the dot pattern. The screenshot is the argument; the caption under/next to it is short. All screenshots show DACH-native data (see positioning doc §6.1).

### 5.3 Two-tone claims
Section claims set in `claim`/`display-2` where the **first sentence is `ink`, the rest is `mute`** — one `<h2>`/`<h3>`, two `<span>`s. Example register: "Ihr Team, entlastet." + gray continuation. Used for every feature block. See `home-1440-04-tab-pipeline.jpg`.

### 5.4 Sticky-rail tab sections
The flagship homepage pattern: left rail lists the 5 workflow stages; the active stage is `ink` with a 2px `ink` left indicator, inactive are `mute`; the right column scrolls through each stage's claim + media. Rail is `position: sticky`. On mobile it becomes a horizontal scrollable tab bar pinned under the nav (see `mobile-390-02-tabs.jpg`).

### 5.5 Numbered feature blocks
Deep-dive pages use `[01]`, `[02]` mono-labels in the corner of alternating demo blocks (media + short claim), inside dot-pattern panels. See `platform-data-1440-03-numbered-features.jpg` and `platform-data-1440-05-feature-pair.jpg`.

## 6. Components (build in this order)

1. **Buttons** — primary: `ink` bg, `paper` text, `r-md`, h-40 (h-36 in nav), `small` weight 500, `shadow-btn`, hover lifts luminance ~8%. Secondary: `paper` bg, 1px `line-strong` border. Tertiary: text + `→` arrow that translates 2px on hover.
2. **Badge pill** — hero eyebrow: pill, 1px border, `eyebrow` type, optional `→`; also the section badges ("Plattform", "Changelog") in `accent-soft`/`accent`.
3. **Nav bar** — h-64, `paper` at 90% opacity + blur(12px), 1px bottom `line`. Logo left, center links (Plattform ▾, Kunden, Preise), right: language toggle DE/EN, "Anmelden" (secondary), "14 Tage kostenlos testen" (primary). Announcement bar above: h-44, `mist` bg, `small` text + `→`, dismissible (deviation: light, not black).
4. **Mega-dropdown** — full-width white panel, `r-lg`, `shadow-media`, grouped columns under `eyebrow` labels; rows = outlined icon (20px, 1.5px stroke) + `h3`-weight title + `mute` one-liner. Content = the 5 workflow stages + 4 feature brands (see 03-SITE-MAP).
5. **Media card** (§5.2) — with optional autoplaying muted loop `<video>`.
6. **Sticky-rail section** (§5.4).
7. **Logo band** — grid cells separated by 1px `line`, logos grayscale `ink` at 60%, hover 100% + tiny `↗` for linked cells. (Content pending legal check — see 09-ASSETS-CHECKLIST.)
8. **Icon feature row** — 5-col (desktop) row of outlined icons + `h3` + 2-line `mute` text, cells separated by hairlines. Used for the DACH-trust strip.
9. **Stat block** — big `display-2` numbers with 2px `accent` left rule, label in `small mute`; background: thin vertical bar-chart pattern in `line` + one `accent` line chart (own SVG).
10. **Serif quote** — `serif-quote` centered on dot pattern, name + role in `small`. Ships empty-slotted until the Fechner quote exists (never fake it).
11. **Pricing tier card** — `r-lg`, 1px border, recommended tier gets `accent` border + "Beliebt" chip; feature list with `ok` checks; footer CTA per tier.
12. **Comparison table** — sticky tier header row on scroll; category `h3` rows; `ok` check / `line-strong` dash cells; row hover `mist`.
13. **Footer** — light (deviation): `mist` bg, top 1px `line`, wordmark left, 4 link columns under `eyebrow` labels (incl. **Manifest** under "Unternehmen"), bottom row: legal links (Impressum, Datenschutz, AGB), language toggle, © line. 
14. **AI-suggestion visual** — inside product screenshots only: `ai-purple` 55% underline/fill + „Übernehmen"-button. Marketing site itself never uses purple chrome.

## 7. Iconography & illustration

Outlined icons, 1.5px stroke, `r-sm` joins, 20/24px grid — use **Lucide** as the base set; custom-draw the 4 brand icons + 5 stage icons + trust badges in the same stroke style (see 09-ASSETS-CHECKLIST). Diagrams (flow/node) are 1px `line` strokes with `accent` highlights and line-draw-on-scroll animation. No 3D, no glassmorphism, no stock photography except real customer/shop photos later.

## 8. Motion

- Scroll reveal: fade + translateY(12px), 350ms `cubic-bezier(.2,.6,.2,1)`, stagger 60ms, once.
- Sticky-rail: active tab crossfades media 250ms.
- Hero loop / demo videos: `<video autoplay muted loop playsinline>`, poster images, lazy.
- Diagrams: SVG `stroke-dashoffset` line-draw over 800ms when 30% in view.
- Hovers: buttons/cards translateY(-1px) + shadow step, 150ms.
- Respect `prefers-reduced-motion`: disable transforms/autoplay, keep opacity fades.

## 9. Locale & formatting (non-negotiable)

German-first: `de` at `/`, `en` at `/en`. Sie-Form. Numbers `1.234,56 €`, dates `17.07.2026`, units mm/kg. All screenshots German UI. EN pages keep German-UI screenshots with English captions (positioning §7 P2-15).
