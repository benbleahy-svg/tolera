# Tolera (working title "Bid Factory")

A **DACH-region instant-quoting / RFQ platform** for custom manufacturers (CNC, sheet metal, tube laser, turning, assembly) — a clone and intended better version of Paperless Parts. It ingests RFQs and CAD/print files, interrogates geometry, extracts print requirements with AI, and produces priced quotes fast. Region: DE/AT/CH · metric-native · EUR/CHF · German-first · GDPR + EU dual-use.

**Start here:** read [`CLAUDE.md`](CLAUDE.md) — it is the orientation file (what we're building, the document precedence ladder, repo conventions, and the block-and-log rule for ambiguity).

## Repository layout

| Path | Tier | Contents |
|---|---|---|
| `docs/decisions/` | 1 | `DECISIONS.md` — living decision log; **overrides everything** |
| `docs/spec/` | 2 | `Bid-Factory-Build-Spec.html` (master spec — now the self-contained build source) + `SPEC-INDEX.md` (section map) + `folded-subspecs/` (13 engine sub-specs folded in; frozen provenance) |
| `docs/subsystems/` | 3 | `E4-Behavioral-Gaps.md` + `DOMAIN-MODEL.mermaid` (the 13 engine/contract sub-specs were folded into the spec → `docs/spec/folded-subspecs/`) |
| `docs/fixtures/` | 3 | `SEED-AND-FIXTURES.md` + `seed.skeleton.json` (golden-test harness) |
| `docs/analysis/` | 4 | Gap audits, onboarding & infra research; `analysis/ui/` holds UI research + the `BidFactory-LiveMock.html` |
| `docs/reference/` | 5 | `screenshots/`, `Screenshot-Mapping.*`; `kb/` is a signpost (PP KB parked in `archive/kb-reference/`) |
| `ui-prototype/` | — | Throwaway UI prototype, built in a separate `/prototype` session (see its `README.md`) |
| `build-plan/` | — | Milestone → build-block plan (added in the next phase) |
| `archive/` | — | Superseded spec backups + parked PP KB (`kb-reference/`) — gitignored |

Application code lives at the repo root: `app/` (FastAPI backend package), `frontend/` (React + TypeScript + Vite), `alembic/` (migrations), `scripts/` (seed/ops), `tests/`.

## Running locally (M0.1 walking skeleton)

Requires Docker + Docker Compose. Copy `.env.example` → `.env` (the dev secrets live there; never commit `.env`).

```bash
docker compose up                                   # db + redis + app (:8000) + worker
docker compose exec app pytest                      # backend tests
docker compose exec app mypy app/                   # type check
docker compose exec app python -m scripts.seed_demo # seed (no-op until M0.5)
```

- Health: `GET /healthz` (liveness) · `GET /readyz` (Postgres round-trip) · `GET /metrics` (Prometheus).
- Frontend dev server: `npm install && npm run dev` in `frontend/` (serves `:5173`, proxies API to `:8000`).
- Without Docker: `uv sync` then `uv run pytest` (the Postgres round-trip test skips unless `TEST_DATABASE_URL` is set).

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

- **PP KB parked** in `archive/kb-reference/` (tier-5; on disk + greppable; restore command in `CLAUDE.md` §4).
- **Golden fixtures due 2026-06-23** — 5–10 anonymised Fechner RFQ packages → `docs/fixtures/`.
- **Screenshots are gitignored** (125 MB) but remain on disk. To version them, install Git LFS and run `git lfs track "docs/reference/screenshots/**"`.

## Build order (summary — full list in `CLAUDE.md` §7)

Schema + tenancy + auth → GeometryService + viewer → Lens + rules engine → Kalk + cost roll-up → quote/RFQ workflow + integrations → DACH delta applied throughout. Verify each milestone against the golden fixtures.
