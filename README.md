# Tolera (working title "Bid Factory")

A **DACH-region instant-quoting / RFQ platform** for custom manufacturers (CNC, sheet metal, tube laser, turning, assembly) — a clone and intended better version of Paperless Parts. It ingests RFQs and CAD/print files, interrogates geometry, extracts print requirements with AI, and produces priced quotes fast. Region: DE/AT/CH · metric-native · EUR/CHF · German-first · GDPR + EU dual-use.

**Start here:** read [`CLAUDE.md`](CLAUDE.md) — it is the orientation file (what we're building, the document precedence ladder, repo conventions, and the block-and-log rule for ambiguity).

## Repository layout

| Path | Tier | Contents |
|---|---|---|
| `docs/decisions/` | 1 | `DECISIONS.md` — living decision log; **overrides everything** |
| `docs/spec/` | 2 | `Bid-Factory-Build-Spec.html` (master spec) + `SPEC-INDEX.md` (section map) |
| `docs/subsystems/` | 3 | All engine/contract sub-specs (domain model, DB schema, geometry, pricing/Kalk, AI/Lens, rules, integrations, viewer, DACH delta, DFM, user stories…) |
| `docs/fixtures/` | 3 | `SEED-AND-FIXTURES.md` + `seed.skeleton.json` (golden-test harness) |
| `docs/analysis/` | 4 | Gap audits, onboarding & infra research; `analysis/ui/` holds UI research + the `BidFactory-LiveMock.html` |
| `docs/reference/` | 5 | `kb/` (Paperless Parts KB — **to be added**), `screenshots/`, `Screenshot-Mapping.*` |
| `ui-prototype/` | — | Throwaway UI prototype, built in a separate `/prototype` session (see its `README.md`) |
| `build-plan/` | — | Milestone → build-block plan (added in the next phase) |
| `archive/` | — | Superseded spec backups — ignore |

Application code (e.g. `backend/`, `frontend/`) is added at the repo root during the build.

## Precedence (when docs disagree)

`DECISIONS.md` **>** master spec **>** sub-specs **>** analysis **>** PP KB.
`docs/subsystems/DACH-DELTA-LAYER.md` is cross-cutting: it overrides any US/imperial/ITAR/QuickBooks behavior anywhere. Full rules in `CLAUDE.md` §2.

## Conventions (summary — full list in `CLAUDE.md` §5)

- **Tenancy:** every domain table org-scoped via RLS; no cross-org reads.
- **Money:** integer minor units + explicit `currency` (EUR/CHF), never a bare float.
- **Units:** metric-native (mm/kg/deg); imperial dropped.
- **AI output:** suggestions only (explicit accept), never auto-fed into pricing, never hallucinated.
- **Calculated vs override:** persist both; resolve with `COALESCE(manual_*, calc_*)`.

## Open action items

- **KB not on disk** — unzip the Paperless Parts KB into `docs/reference/kb/` (tier-5 reference; see `CLAUDE.md` §4).
- **Golden fixtures due 2026-06-23** — 5–10 anonymised Fechner RFQ packages → `docs/fixtures/`.
- **Screenshots are gitignored** (125 MB) but remain on disk. To version them, install Git LFS and run `git lfs track "docs/reference/screenshots/**"`.

## Build order (summary — full list in `CLAUDE.md` §7)

Schema + tenancy + auth → GeometryService + viewer → Lens + rules engine → Kalk + cost roll-up → quote/RFQ workflow + integrations → DACH delta applied throughout. Verify each milestone against the golden fixtures.
