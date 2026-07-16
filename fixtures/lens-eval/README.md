# Lens extraction eval fixtures (M3.11)

The labelled set the **probabilistic test track** scores against — the
counterpart to `fixtures/parts/` + `fixtures/golden/` (the deterministic
pricing goldens). See `tests/lens_eval_harness.py` (the model-free scorer),
`tests/test_lens_eval_scorer.py` (the every-PR meta-test that pins the scorer
math), and `tests/test_lens_eval_suite.py` (the live, cost-gated quality gate).

## `<name>.expected.json` — one labelled print

```jsonc
{
  "pdf": "halter-4711-rev-b.pdf",   // under fixtures/drawings/ (or a path from fixtures/)
  "pipeline": "document-extraction", // default; email-ingest / bom-detection accrue later
  "pages_total": 1,
  "print_pages": [1],                // pages that ARE prints (classification truth)
  "findings": [
    { "category": "quote_setup", "type": "part_number", "value": "Halter 4711" },
    { "category": "requirements", "type": "general_tolerance", "value": "ISO 2768-m" }
    // optional per-finding: normalized_value, units,
    //   tolerance {kind, upper, lower}, bbox {x, y, width, height},
    //   value_tolerance (numeric ± for a dimension match)
  ]
}
```

A prediction matches a label on `(category, type)` **and** normalized value
(whitespace + case-folded, or within `value_tolerance`) **and** the tolerance
spec (when labelled) **and** bbox IoU ≥ 0.5 (when labelled). `category` is the
5-value `FindingCategory` taxonomy; `type` mirrors `ExtractionFinding.type`.

## `baseline.json` — the regression gate

Tracks the gated metrics (`classification`, `overall.precision`,
`overall.recall`) + a `margin`. The live suite fails only when a metric drops
**more than `margin` below** its baseline (benign phrasing variance passes).

**Provisional until first real run.** `metrics` is seeded from the spec targets
(AI-LENS §7: classification ≈95%, recall ≈65%, precision ≈85%). Recalibrate
`metrics` from the first live `lens-eval` report — and again when the Fechner
labelled packages land (DECISIONS: *Fixture packages*). The seed set here is
2–3 synthetic prints; it grows over the pilot.

## Pipelines

The scorer measures the `document-extraction` pipeline (the `ExtractionFinding`
taxonomy). The other Lens pipelines get their own labelled fixtures as they
mature: `email-ingest` (parts-list `RawLineItem`), `bom-detection` (M4 — not yet
built), `file-processing` (upstream text/split). Tag a fixture with `pipeline`;
the live suite scores the `document-extraction` set today.

## Running

- Every PR (model-free): `pytest tests/test_lens_eval_scorer.py` — runs by default.
- Live gate (needs `ANTHROPIC_API_KEY`): `pytest -m eval tests/test_lens_eval_suite.py`.
  CI runs it in the `lens-eval` workflow (nightly + Lens-path PRs), never on every PR.
