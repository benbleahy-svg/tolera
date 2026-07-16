"""M3.11 — the **live** Lens extraction quality gate (cost-gated).

Marked ``@pytest.mark.eval`` and **deselected by default** (``pyproject.toml``
``addopts = -m 'not eval'``) so it never runs on an ordinary PR — it calls the
model. It runs where cost is acceptable: the dedicated ``lens-eval`` workflow
(M3-lens PRs + nightly), via ``pytest -m eval``.

What it does: runs each labelled print through the **real** provider
(``run_document_extraction`` — the pure two-pass extractor, no DB), scores the
predictions with the model-free harness, and gates on **regression-vs-baseline**
(never exact-match). Repeatability rides on the **pinned model + versioned
prompt** recorded in the report (``app/lens_provider.py`` — temperature-0 is
superseded on the pinned model generation).

Skips cleanly when ``ANTHROPIC_API_KEY`` is unset so a local ``pytest -m eval``
without a key is a no-op rather than a failure; the CI job supplies the secret.
"""

from __future__ import annotations

import json

import pytest
from anthropic import APIConnectionError, AuthenticationError, PermissionDeniedError

from app.config import get_settings
from app.lens import PROMPT_VERSION, run_document_extraction
from app.lens_provider import make_provider
from tests.lens_eval_harness import (
    DOCUMENT_EXTRACTION,
    GATED_METRICS,
    Counts,
    category_counts,
    classification_accuracy,
    compare_to_baseline,
    fixture_names,
    load_baseline,
    load_fixture,
    metrics_from_counts,
)

pytestmark = pytest.mark.eval


def _provider_or_skip() -> object:
    settings = get_settings()
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY unset — live Lens eval skipped (CI job supplies it)")
    return make_provider(settings)


@pytest.mark.asyncio
async def test_lens_extraction_quality_gate(capsys: pytest.CaptureFixture[str]) -> None:
    """Score the whole labelled set through the live model; fail only on a
    baseline regression beyond the margin."""
    provider = _provider_or_skip()
    baseline = load_baseline()
    settings = get_settings()

    scored_fixtures = [
        name for name in fixture_names() if load_fixture(name).pipeline == DOCUMENT_EXTRACTION
    ]
    # A vacuous gate is worse than no gate: refuse to go green having scored
    # nothing (e.g. every fixture retagged off document-extraction).
    assert scored_fixtures, "no document-extraction fixtures to score"

    agg: dict[str, Counts] = {}
    errors: list[str] = []
    correct_pages = 0
    total_pages = 0
    for name in scored_fixtures:
        fx = load_fixture(name)
        try:
            result = await run_document_extraction(provider, fx.pdf_bytes)  # type: ignore[arg-type]
        except (AuthenticationError, PermissionDeniedError, APIConnectionError) as exc:
            # The provider is unreachable/unauthenticated → the QUALITY gate
            # simply can't run (bad/absent key, network). That's a SKIP, not a
            # quality failure — otherwise every M3-lens PR and nightly goes red
            # on infra, not on a regression. Surfaces the fix (the secret).
            pytest.skip(
                f"Lens provider unavailable ({type(exc).__name__}) — live eval cannot run; "
                "check the ANTHROPIC_API_KEY CI secret is valid"
            )
        except Exception as exc:  # a real per-fixture bug must not discard the rest
            # Keep scoring the others so the report still emits; fail at the end.
            errors.append(f"{name}: {exc!r}")
            continue
        # Score each document independently and SUM the counts — never pool the
        # finding lists (a prediction on print A must not satisfy a label on B).
        for cat, counts in category_counts(result.findings, fx.findings).items():
            agg[cat] = agg.get(cat, Counts()) + counts
        correct_pages += round(
            classification_accuracy(set(result.print_pages), fx.print_pages, fx.pages_total)
            * fx.pages_total
        )
        total_pages += fx.pages_total

    classification = correct_pages / total_pages if total_pages else None
    run = metrics_from_counts(agg, classification=classification)

    report = {
        "model": settings.lens_model,
        "prompt_version": PROMPT_VERSION,
        "fixtures": scored_fixtures,
        "metrics": run.flat(),
        "targets": baseline.get("targets"),
    }
    # Emitted for the CI log / artifact — the per-category diff-vs-baseline.
    print("LENS_EVAL_REPORT " + json.dumps(report, indent=2, sort_keys=True))

    # A fixture that errored is a hard failure — but only after the report for
    # the fixtures that DID score has been emitted (surfaced above).
    assert not errors, "Live extraction call(s) failed:\n" + "\n".join(errors)

    gate = compare_to_baseline(
        run.flat(), baseline["metrics"], float(baseline["margin"]), metrics=GATED_METRICS
    )
    with capsys.disabled():
        for line in gate.failures:
            print("REGRESSION " + line)
    assert gate.passed, "Lens extraction regressed vs baseline:\n" + "\n".join(gate.failures)
