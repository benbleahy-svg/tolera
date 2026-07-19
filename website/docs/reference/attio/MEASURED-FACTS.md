# Attio — measured design facts (Design A)

Extracted **2026-07-18 from the live attio.com DOM** (Tailwind v4 `@theme` custom
properties + computed styles), not eyeballed from screenshots. These are exact numbers for
**scale, rhythm, and motion** — adopt them for structural fidelity. **Do not ship Attio's
brand hexes or licensed fonts**: swap the palette for Tolera's and the licensed serif
(Tiempos) for an OFL serif. Precedence unchanged: a reference value never outranks a Tolera
spec or the positioning doc. Internal reference only; never deployed.

Attio's own stack is **Tailwind v4** with tokens under `--text-*`, `--color-*`, `--radius-*`,
`--container-*`, `--ease-*`. Because Design A is also Tailwind v4, most of this maps **1:1
into our `@theme`** — you can lift the scale and easings verbatim and only change the palette
+ serif.

## 1. Type scale (exact)

Fonts in use: **Inter** (`--font-inter`), **Inter Display** (`--font-inter-display`, used for
large headings), **JetBrains Mono** (`--font-mono`, eyebrows/labels/`[01]` indices), and
**Tiempos Text** (licensed serif — used only for italic pull-quotes like the "It finally
felt like I could configure our CRM…" testimonial). We already self-host Inter / Inter
Display / JetBrains Mono (OFL); **substitute the serif** with an OFL face (Newsreader or
Source Serif 4, italic) for pull-quotes.

Headings (`--text-heading-*`), font Inter Display, weight 600:

| Token | size | line-height | letter-spacing |
|---|---|---|---|
| heading-xl | 4rem / 64px | 4rem / 64px (1.0) | -0.02em |
| heading-lg | 3.5rem / 56px | 3.75rem / 60px | -0.015em |
| heading-md | 2.5rem / 40px | 2.75rem / 44px | -0.01em |
| heading-sm | 2rem / 32px | 2.25rem / 36px | -0.01em |
| heading-xs | 1.75rem / 28px | 2.125rem / 34px | -0.01em |

Body / UI text (`--text-*`), font Inter, default weight **500** (Attio sets medium as the
base UI weight; body copy that reads lighter uses 400):

| Token | size | line-height | letter-spacing | weight |
|---|---|---|---|---|
| text-2xl | 1.5rem / 24px | 1.875rem / 30px | -0.01em | 500 |
| text-xl | 1.25rem / 20px | 1.625rem / 26px | -0.01em | 500 |
| text-lg | 1.125rem / 18px | 1.5rem / 24px | -0.01em | 500 |
| text-base | 1rem / 16px | 1.375rem / 22px | -0.01em | 500 |
| text-sm | 0.875rem / 14px | 1.25rem / 20px | -0.005em | 500 |
| text-xs | 0.75rem / 12px | 1.125rem / 18px | 0 | 500 |

Font weights available: light 300, normal 400, medium 500, semibold 600, bold 700.
Named leading: tight 1.25, relaxed 1.625. Named tracking: tighter -0.05em, tight -0.025em,
normal 0, wide 0.025em, wider 0.05em.

**Eyebrows / section labels** (e.g. "Platform", "Signals", `[01]`): JetBrains Mono, small
(text-xs/sm), often uppercase with wide tracking; the colored pill eyebrows ("Platform",
"Self-building", "Connectivity") use Inter at text-sm on a tinted background.

## 2. Palette (exact hex — REPLACE with Tolera's, keep the roles)

Attio's system is near-neutral with cool undertones (defined in `lab()`; converted to sRGB):

Neutrals / surfaces:
- page background `#ffffff` · secondary background `#fafafb` · surface (muted) `#edeff3`
- primary foreground (near-black text) `#1c1d1f` · secondary foreground `#232529`
- caption / muted foreground `#a4adba`
- strokes: subtle `#e4e7ec` · default `#d3d8df` · strong `#cad0d9` · true black `#000000`

The near-black-on-white with cool-gray captions and hairline `#e4e7ec`–`#d3d8df` strokes is
the whole "technical drawing" feel of Design A — **keep the *role structure* (near-black ink,
one muted caption gray, hairline strokes ~#e4e7ec), recolor to Tolera's ink/paper.**

Accents (used sparingly — links, tags, AI accents):
- link / accent blue `#266df0` · lighter blue-400 `#709ff5`
- green-500 `#0fc27b` · yellow-500 `#f5b900` · red-500 `#ff5b59`
- changelog tags: design `#00b5e6`, feature `#72a4fb`

Note Attio's "accent foreground" token is a **desaturated blue-gray** `#6f7988`, not the
vivid blue — the vivid `#266df0` is reserved for actual links. For Tolera keep accents
this restrained, and reserve any purple strictly for AI-suggestion UI per our grammar.

## 3. Spacing, radius, container, breakpoint

- **Spacing base** `--spacing: 0.25rem` (4px) — all padding/margin/gap are 4px multiples
  (Tailwind v4). Sections breathe large (hero blocks ≈ 100–160px vertical padding measured).
- **Radius:** xs 2px · sm 4px · md 6px · lg 8px · xl 12px · 2xl 16px · 3xl 20px. Cards
  cluster at **12–16px**; buttons use md–lg (6–8px), not full pills (contrast this with
  Design B, which is pill-heavy).
- **Containers:** xs 20rem · sm 24rem · md 28rem · lg 32rem · xl 36rem · 2xl 42rem ·
  4xl 56rem · 5xl 64rem · 6xl 72rem · **7xl 80rem (1280px)** — main content max-width is
  the 6xl–7xl band (~1152–1280px).
- **Breakpoint:** `--breakpoint-lg: 992px` (their primary desktop/mobile switch). Design A
  should keep our existing 768/1024 stops but note Attio pivots layout at ~992.

## 4. Header / layout constants
- Nav height **68px**; promo banner **48px** (`--site-header-height` = 68 + 48 when banner
  shown). Nav is transparent over hero, solid `page-bg` on scroll.
- z-index layers (for parity): site-header 92, nav-menu 93, dialog overlay 100 / content 101,
  context-menu 200–202, style-overlay 999.

## 5. Shadows (layered, very soft — the signature "float")
Attio never uses one hard shadow; cards stack many low-alpha layers. Two canonical stacks:

- **Big floating card** (mockups, dialogs):
  `0 1px 2px rgba(28,29,31,.05), 0 2px 4px -1px rgba(28,29,31,.02), 0 4px 8px -2px rgba(28,29,31,.03), 0 8px 16px -4px rgba(28,29,31,.04), 0 16px 32px -8px rgba(28,29,31,.05), 0 32px 64px -8px rgba(28,29,31,.06)` + a `0 0 0 1px rgba(255,255,255,.2)` inner hairline.
- **Small resting card:** `0 2px 8px rgba(11,13,24,.04), 0 16px 40px rgba(11,13,24,.08)`.
- Blue-tinted focus/active glow on accented chips: `0 2px 4px -2px rgba(15,107,233,.12), 0 3px 6px -2px rgba(15,107,233,.08)`.

Reproduce the **multi-layer, sub-6%-alpha, cool-tinted** recipe rather than any single value.

## 6. Motion (named easings + durations — lift verbatim)
Default transition: **0.15s `cubic-bezier(.4,0,.2,1)`** (`--default-transition-*`). Named
easing curves in the system (use these tokens, they're what the site actually animates on):

- ease-out `cubic-bezier(0,0,0,1)` · ease-in `cubic-bezier(.3,0,1,1)`
- ease-in-out (emphasized) `cubic-bezier(.2,0,0,1)` · ease-in-out-cubic `cubic-bezier(.65,0,.35,1)`
- ease-out-cubic `cubic-bezier(.33,1,.68,1)` · ease-in-out-quad `cubic-bezier(.45,.05,.55,.95)`
- ease-in-out-expo `cubic-bezier(1,0,0,1)` (used for big dramatic reveals) · ease-reveal `cubic-bezier(0,0,.58,1)`

Component animations (durations measured from the token set):
- dropdown/collapsible slide 0.3s ease-in-out-cubic; dialog scale-in/out 0.2s quad;
  nav enter/exit 0.2s ease-in-out-cubic; pulse 2s; spin 1s linear.
- **Scroll-reveal** is the home page's core device: `--ease-reveal` opacity/translate fades,
  plus pinned "productivity intro" width/height animations at 0.8s linear. This is why the
  home hero and mid-bands don't flatten in the full-page stitches (see `fullpage/README.md`)
  — rebuild them as reduced-motion-safe scroll reveals, not as static blocks.

## 7. What Design A adopts vs. replaces
- **Adopt 1:1:** the whole type scale + tracking, the 4px spacing base, radius scale
  (cards 12–16px, buttons 6–8px), container band (max ~1280px), the named easings +
  0.15s default, and the multi-layer soft-shadow recipe.
- **Replace:** every hex (→ Tolera ink/paper + restrained accents; purple = AI only), the
  licensed **Tiempos** serif (→ OFL Newsreader/Source Serif for italic pull-quotes), and all
  copy/assets. Keep accents as sparse as Attio does.
- **Keep the feel:** near-black ink on white, one cool caption gray, hairline `#e4e7ec`-weight
  strokes, generous section padding, mono eyebrows.
