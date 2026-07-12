# Golden-fixtures harness (SEED-AND-FIXTURES Part 2 · M1.13)

The machine-checkable acceptance oracle: a runner seeds a **clean org** per
fixture, builds the fixture's quote through the real API, runs pricing, and
diffs the result against `/golden`. Pricing asserts are **exact**; future
geometry asserts (M4) use tolerances per `INTERROGATION-ENGINE-SPEC`.

```
/fixtures
  /cad/        STEP samples          — synthetic placeholder until the Fechner packages land
  /drawings/   PDF prints            — synthetic placeholder (GD&T print arrives with the packages)
  /email/      RFQ .eml sample       — consumed by the M3 ingest goldens
  /parts/      <fixture>.json        — pre-M4 stand-in for "part + router + qty breaks":
                                       declarative quote-build recipes (operations with per-break
                                       costs or Kalk formulas, BOM children, pricing items)
  seed.json    org template (Part 1) — the harness clones it with a unique slug per fixture;
                                       configure_catalog=true also runs the M1.7/M1.12 seeds
  /golden/
    <fixture>.pricing.json           — expected unit/total price per quantity (exact),
                                       plus net/VAT/gross minor units where check_totals is set
    <fixture>.interrogation.json     — expected AnalysisResult        (arrives with M4)
    <fixture>.extraction.json        — expected Lens findings         (arrives with M3)
    <fixture>.bom.json               — expected BomNode tree          (arrives with M4)
    <fixture>.inclusion.json         — per-component material + quote_inclusion (M4.9b/M4.10b)
```

Runner: `tests/golden_harness.py`, wired into CI via
`tests/test_golden_thread_m113.py` — one parametrized test per
`/parts/*.json` plus the golden-thread integration test (seeded catalog →
quote → line → material/ops → costing → pricing → VAT totals).

## Current pricing goldens

| Fixture | Verifies | Figure |
|---|---|---|
| demo-e-ex1-difficult-material | custom category over the titanium slice | 2.160,84 € |
| demo-e-ex2-laser-workcenter | one work center carries extra margin | 1.837,10 € |
| demo-e-ex3-labor-vs-overhead | labor/overhead split markups | 2.028,72 € |
| demo-e-ex4-piece-price-vs-tooling | tooling split from piece price | 1.957,74 € |
| demo-e-ex5-outside-finishes | only outside finishes marked up | 2.124,51 € |
| demo-e-ex6-complexity-level3 / -level2 | PartLevel-driven % | 928,64 € / 857,20 € |
| zuschlagskalkulation-chain | seeded MGK/VwGK/VtGK/Gewinn + 19 % MwSt. | 261,80 € netto |
| ch-zuschlag-quote | the CH region path (CHF, 8.1 % MWST) | CHF 261.80 netto |

## On delivery of the anonymised Fechner packages (target was 2026-06-23)

Drop each package's CAD/print/email into the matching folder, add its
`/parts/<name>.json` recipe (or, from M4, let interrogation derive the router)
and author its goldens. Which fixtures cover which Core-4 family is an open
item in `DECISIONS.md`.
