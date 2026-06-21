# Paperless Parts KB (TIER 5 — descriptive reference)

The upstream Paperless Parts knowledge base the sub-specs were distilled from — **186 articles in 14 areas**. Now on disk.

- **Canonical copy:** `paperless-parts-kb-reference/`
  - `INDEX.md` — grouped index of all 186 articles (**start here**)
  - `articles/01-…/ … 14-…/` — one Markdown file per article (YAML front-matter + live source link), cited by **slug**
  - `index.html` — single-file browsable version with images (gitignored; on disk only)

## How to treat it (precedence)

- **Tier 5 — descriptive only.** It documents "how Paperless Parts does it," not what Tolera must do.
- Superseded by tiers 1–3 wherever they speak, and **always** by `../../subsystems/DACH-DELTA-LAYER.md` — the KB's US/ITAR/QuickBooks/imperial framing loses to EU dual-use, DATEV, EUR/CHF, metric.
- Cite articles by **slug**, e.g. `building-review-rules`. Coverage vs the spec is mapped in `../../analysis/KB-Coverage-Gap-Analysis.md`.

## Git

The 186 markdown articles + `INDEX.md` are tracked. The generated `index.html` and the source `.zip` are **gitignored** (kept on disk). The original `.zip`, a duplicate copy, and two stray extraction artifacts were moved to `archive/kb-extras/` — safe to delete. See `CLAUDE.md` §4.
