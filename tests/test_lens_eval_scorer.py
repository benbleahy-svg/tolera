"""M3.11 — the eval **scorer** meta-test (the every-PR deterministic gate).

The live extraction suite calls the model and is cost-gated (``@pytest.mark.eval``,
not on every PR). *This* file has no model, no network, no DB: it pins the
scorer's precision/recall/F1 math, its match semantics, its classification
accuracy, and its baseline-regression logic on hand-checked mini-cases — so a
change that silently breaks the scorer can never merge (block Test-plan: "a
meta-test asserts the scorer's precision/recall math on a hand-checked
mini-case").
"""

from __future__ import annotations

import math
from typing import ClassVar

import pytest

from tests.lens_eval_harness import (
    BBOX_IOU_MIN,
    GATED_METRICS,
    Comparable,
    Counts,
    LabelledFinding,
    category_counts,
    classification_accuracy,
    compare_to_baseline,
    fixture_names,
    load_baseline,
    load_fixture,
    match_counts,
    metrics_from_counts,
    precision_recall_f1,
    score_findings,
    to_comparable,
)


def _qs(type_: str, value: str | None, **kw: object) -> Comparable:
    return Comparable(category="quote_setup", type=type_, value=value, **kw)  # type: ignore[arg-type]


class TestPrecisionRecallF1Math:
    """The P/R/F1 arithmetic, hand-checked."""

    def test_two_of_three_matched(self) -> None:
        m = precision_recall_f1(Counts(tp=2, fp=1, fn=1))
        assert m.precision == 2 / 3
        assert m.recall == 2 / 3
        assert m.f1 == 2 / 3

    def test_precision_differs_from_recall(self) -> None:
        # 2 correct, 1 spurious prediction, nothing missed.
        m = precision_recall_f1(Counts(tp=2, fp=1, fn=0))
        assert m.precision == 2 / 3
        assert m.recall == 1.0
        assert math.isclose(m.f1, 0.8)

    def test_no_predictions_is_perfect_precision_vacuous_recall(self) -> None:
        # Convention: no predictions ⇒ no false positives ⇒ precision 1.0;
        # nothing to find ⇒ recall 1.0; F1 collapses to 1.0.
        m = precision_recall_f1(Counts(tp=0, fp=0, fn=0))
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1 == 1.0

    def test_all_wrong_is_zero_f1(self) -> None:
        m = precision_recall_f1(Counts(tp=0, fp=3, fn=2))
        assert m.precision == 0.0
        assert m.recall == 0.0
        assert m.f1 == 0.0


class TestMatchSemantics:
    """Match predicate: value normalization, units, tolerance, bbox, max 1:1."""

    def test_normalized_value_absorbs_whitespace_and_case(self) -> None:
        pred = [_qs("material", "1.4301  (x5crni18-10)")]
        labels = [LabelledFinding("quote_setup", "material", value="1.4301 (X5CrNi18-10)")]
        assert match_counts(
            [to_comparable(p) for p in pred], [to_comparable(x) for x in labels]
        ) == Counts(tp=1, fp=0, fn=0)

    def test_wrong_value_is_fp_and_fn(self) -> None:
        pred = [_qs("revision", "C")]
        labels = [LabelledFinding("quote_setup", "revision", value="B")]
        assert match_counts(
            [to_comparable(p) for p in pred], [to_comparable(x) for x in labels]
        ) == Counts(tp=0, fp=1, fn=1)

    def test_type_mismatch_never_matches(self) -> None:
        pred = [_qs("drawing_number", "4711")]
        labels = [LabelledFinding("quote_setup", "part_number", value="4711")]
        assert match_counts(
            [to_comparable(p) for p in pred], [to_comparable(x) for x in labels]
        ) == Counts(tp=0, fp=1, fn=1)

    def test_numeric_value_tolerance(self) -> None:
        label = LabelledFinding("dimensions", "hole_diameter", value="10.0", value_tolerance=0.05)
        near = Comparable("dimensions", "hole_diameter", value="10,02")  # German comma
        far = Comparable("dimensions", "hole_diameter", value="10.1")
        assert match_counts([near], [to_comparable(label)]) == Counts(tp=1, fp=0, fn=0)
        assert match_counts([far], [to_comparable(label)]) == Counts(tp=0, fp=1, fn=1)

    def test_tolerance_spec_must_match_when_labelled(self) -> None:
        label = LabelledFinding(
            "dimensions",
            "hole_diameter",
            value="10.0",
            tolerance={"kind": "bilateral", "upper": "+0.1", "lower": "-0.1"},
        )
        good = Comparable(
            "dimensions",
            "hole_diameter",
            value="10.0",
            tolerance={"kind": "bilateral", "upper": "+0.1", "lower": "-0.1"},
        )
        bad = Comparable(
            "dimensions",
            "hole_diameter",
            value="10.0",
            tolerance={"kind": "bilateral", "upper": "+0.2", "lower": "-0.2"},
        )
        assert match_counts([good], [to_comparable(label)]) == Counts(tp=1, fp=0, fn=0)
        assert match_counts([bad], [to_comparable(label)]) == Counts(tp=0, fp=1, fn=1)

    def test_bbox_overlap_gate(self) -> None:
        label = LabelledFinding(
            "regions", "note", value=None, bbox={"x": 0, "y": 0, "width": 10, "height": 10}
        )
        overlapping = Comparable(
            "regions", "note", value=None, bbox={"x": 1, "y": 1, "width": 10, "height": 10}
        )  # IoU ≈ 0.68 ≥ 0.5
        disjoint = Comparable(
            "regions", "note", value=None, bbox={"x": 50, "y": 50, "width": 10, "height": 10}
        )
        assert match_counts([overlapping], [to_comparable(label)]) == Counts(tp=1, fp=0, fn=0)
        assert match_counts([disjoint], [to_comparable(label)]) == Counts(tp=0, fp=1, fn=1)

    def test_one_to_one_no_double_claim(self) -> None:
        # Two identical labels, one matching prediction: exactly one TP.
        preds = [_qs("part_number", "4711")]
        labels = [
            LabelledFinding("quote_setup", "part_number", value="4711"),
            LabelledFinding("quote_setup", "part_number", value="4711"),
        ]
        assert match_counts(
            [to_comparable(p) for p in preds], [to_comparable(x) for x in labels]
        ) == Counts(tp=1, fp=0, fn=1)

    def test_units_must_match_when_labelled(self) -> None:
        # 10 in must never satisfy a 10 mm label (metric-native invariant).
        label = LabelledFinding("dimensions", "length", value="10", units="mm", value_tolerance=0.1)
        metric = Comparable("dimensions", "length", value="10", units="mm")
        imperial = Comparable("dimensions", "length", value="10", units="in")
        assert match_counts([metric], [to_comparable(label)]) == Counts(tp=1, fp=0, fn=0)
        assert match_counts([imperial], [to_comparable(label)]) == Counts(tp=0, fp=1, fn=1)

    def test_maximum_matching_beats_first_fit_ordering(self) -> None:
        # pred0 carries the bbox; pred1 does not. label0 is unconstrained (matches
        # both); label1 needs a bbox (only pred0). Greedy first-fit lets label0 grab
        # the low-index pred0 and strands label1 → 1 TP. Maximum matching reassigns
        # label0 to pred1 via an augmenting path → 2 TP, independent of ordering.
        box: dict[str, float] = {"x": 0, "y": 0, "width": 10, "height": 10}
        preds = [
            Comparable("regions", "note", value="A", bbox=box),  # pred0: has bbox
            Comparable("regions", "note", value="A"),  # pred1: no bbox
        ]
        labels = [
            LabelledFinding("regions", "note", value="A"),  # unconstrained
            LabelledFinding("regions", "note", value="A", bbox=box),  # needs a bbox
        ]
        assert match_counts(preds, [to_comparable(x) for x in labels]) == Counts(tp=2, fp=0, fn=0)


class TestScoreFindings:
    """End-to-end scoring: micro-averaged overall + per-category."""

    def test_overall_and_by_category(self) -> None:
        predicted = [
            _qs("part_number", "4711"),
            _qs("material", "1.4301"),
            Comparable("requirements", "general_tolerance", value="ISO 2768-m"),  # spurious
        ]
        labels = [
            LabelledFinding("quote_setup", "part_number", value="4711"),
            LabelledFinding("quote_setup", "material", value="1.4301"),
        ]
        run = score_findings(predicted, labels)
        # TP=2, FP=1, FN=0 → precision 2/3, recall 1.0, f1 0.8
        assert run.overall.precision == 2 / 3
        assert run.overall.recall == 1.0
        assert math.isclose(run.overall.f1, 0.8)
        assert run.by_category["quote_setup"].precision == 1.0
        assert run.by_category["quote_setup"].recall == 1.0
        assert run.by_category["requirements"].tp == 0
        assert run.by_category["requirements"].fp == 1

    def test_flat_view_exposes_gated_keys(self) -> None:
        run = score_findings([_qs("part_number", "4711")], [], classification=0.9)
        flat = run.flat()
        for key in GATED_METRICS:
            assert key in flat


class TestPerDocumentAggregation:
    """Multi-document runs must sum per-document counts, never pool findings —
    pooling lets a prediction on print A satisfy a label on print B, masking a
    real miss with a hallucinated duplicate elsewhere (fresh-eyes review)."""

    @staticmethod
    def _docs() -> list[tuple[list[Comparable], list[LabelledFinding]]]:
        return [
            # Doc A: a real material + a hallucinated duplicate, one label.
            (
                [
                    Comparable("quote_setup", "material", value="1.4301"),
                    Comparable("quote_setup", "material", value="1.4301"),
                ],
                [LabelledFinding("quote_setup", "material", value="1.4301")],
            ),
            # Doc B: the model MISSED material; the label is unmatched.
            ([], [LabelledFinding("quote_setup", "material", value="1.4301")]),
        ]

    def test_summed_counts_catch_the_miss(self) -> None:
        agg: dict[str, Counts] = {}
        for preds, labels in self._docs():
            for cat, counts in category_counts(preds, labels).items():
                agg[cat] = agg.get(cat, Counts()) + counts
        run = metrics_from_counts(agg)
        # A: tp1 fp1 fn0 ; B: tp0 fp0 fn1 → summed tp1 fp1 fn1
        assert run.overall.precision == 0.5
        assert run.overall.recall == 0.5

    def test_pooling_would_have_masked_it(self) -> None:
        # The rejected approach, pinned as a regression guard: pooling scores a
        # false perfect (tp2) — proving per-document summation is not cosmetic.
        preds = [p for docs in self._docs() for p in docs[0]]
        labels = [label for docs in self._docs() for label in docs[1]]
        pooled = score_findings(preds, labels)
        assert pooled.overall.precision == 1.0
        assert pooled.overall.recall == 1.0


class TestClassificationAccuracy:
    def test_perfect(self) -> None:
        assert classification_accuracy({1}, {1}, 1) == 1.0

    def test_partial(self) -> None:
        # page1 print✓, page2 expected-print but predicted-not ✗, page3 both-not ✓
        assert classification_accuracy({1}, {1, 2}, 3) == 2 / 3

    def test_zero_pages_is_vacuously_perfect(self) -> None:
        assert classification_accuracy(set(), set(), 0) == 1.0

    def test_out_of_range_predicted_page_is_penalized(self) -> None:
        # Model calls page 2 a print in a 1-page doc: a disagreement, not ignored.
        # Universe = {1, 2}: page1 both-print ✓, page2 predicted-not-expected ✗.
        assert classification_accuracy({1, 2}, {1}, 1) == 0.5

    def test_negative_pages_total_rejected(self) -> None:
        with pytest.raises(ValueError, match="pages_total"):
            classification_accuracy(set(), set(), -1)


class TestBaselineRegressionGate:
    BASE: ClassVar[dict[str, float]] = {
        "classification": 0.95,
        "overall.recall": 0.65,
        "overall.precision": 0.85,
    }

    def test_benign_variance_within_margin_passes(self) -> None:
        current = {"classification": 0.90, "overall.recall": 0.60, "overall.precision": 0.80}
        assert compare_to_baseline(current, self.BASE, margin=0.10).passed

    def test_improvement_passes(self) -> None:
        current = {"classification": 0.99, "overall.recall": 0.80, "overall.precision": 0.95}
        assert compare_to_baseline(current, self.BASE, margin=0.10).passed

    def test_regression_beyond_margin_fails_and_names_metric(self) -> None:
        current = {"classification": 0.70, "overall.recall": 0.64, "overall.precision": 0.84}
        result = compare_to_baseline(current, self.BASE, margin=0.10)
        assert not result.passed
        assert any("classification" in f for f in result.failures)
        # metrics still within margin are not reported as failures
        assert not any("overall.recall" in f for f in result.failures)

    def test_missing_metric_fails_closed(self) -> None:
        # A gated metric absent from the current run must NOT bypass the gate —
        # an omitted/typo'd metric is a misconfiguration, not a silent pass.
        current = {"classification": 0.95}  # recall/precision absent this run
        result = compare_to_baseline(current, self.BASE, margin=0.10)
        assert not result.passed
        assert any("overall.recall" in f for f in result.failures)
        assert any("overall.precision" in f for f in result.failures)

    def test_missing_baseline_metric_fails_closed(self) -> None:
        current = {"classification": 0.95, "overall.recall": 0.65, "overall.precision": 0.85}
        assert not compare_to_baseline(current, {"classification": 0.95}, margin=0.10).passed


class TestSeededFixtures:
    """The seeded labelled set loads and is internally consistent."""

    def test_at_least_two_fixtures_seeded(self) -> None:
        names = fixture_names()
        assert len(names) >= 2, "block asks for 2-3 labelled prints seeded now"

    def test_fixtures_load_and_reference_real_pdfs(self) -> None:
        for name in fixture_names():
            fx = load_fixture(name)
            assert fx.pdf_path.exists(), f"{name} → missing pdf {fx.pdf_path}"
            assert fx.pages_total >= 1
            assert fx.findings, f"{name} has no labelled findings"
            assert fx.print_pages <= set(range(1, fx.pages_total + 1))

    def test_baseline_declares_gated_targets_and_margin(self) -> None:
        baseline = load_baseline()
        assert isinstance(baseline["margin"], (int, float))
        for key in GATED_METRICS:
            assert key in baseline["metrics"], f"baseline missing gated metric {key}"


def test_bbox_iou_min_is_half() -> None:
    assert BBOX_IOU_MIN == 0.5
