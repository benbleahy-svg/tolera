"""The Lens extraction **eval harness** (M3.11 — the probabilistic test track).

The deterministic counterpart to :mod:`tests.golden_harness`: where the golden
harness diffs pricing **exactly**, this one scores *probabilistic* Lens
extraction on **precision / recall / F1** against a labelled fixture set and
gates on **thresholds + regression-vs-baseline**, never exact-match (block
M3.11; provider note ``app/lens_provider.py`` "gates quality on thresholds").

Two layers, deliberately split so the scorer is model-free:

* **The scorer** (this module) — pure functions over finding lists. Gated on
  **every PR** by :mod:`tests.test_lens_eval_scorer` (hand-checked math). No
  model, no network, no DB.
* **The live suite** (:mod:`tests.test_lens_eval_suite`, ``@pytest.mark.eval``)
  — runs each labelled print through the real provider and scores it. Cost-
  gated: **not** on every PR (it calls the model); on M3-lens PRs + nightly.

Matching (block Scope-in "normalized value + tolerance + bbox overlap"): a
predicted finding matches a label when they share ``(category, type)`` **and**
their compared value is equal (whitespace-normalized + casefold — the
``app/lens.py`` ``_normalize`` precedent — or within a numeric ``value_tolerance``)
**and** the tolerance spec matches when the label carries one **and** the bbox
IoU ≥ ``BBOX_IOU_MIN`` when the label carries one.

Repeatability posture: **pinned model + versioned prompt** (temperature-0 is
superseded — sampling params are rejected on the pinned model generation,
``app/lens_provider.py``). The report records both so a regression is
attributable to a prompt/model change.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
EVAL_DIR = FIXTURES_DIR / "lens-eval"
DRAWINGS_DIR = FIXTURES_DIR / "drawings"

#: Minimum intersection-over-union for a bbox to count as the same region.
BBOX_IOU_MIN = 0.5

#: The metrics the CI gate tracks against the baseline (block targets:
#: classification ≈95%, recall ≈65%, precision ≈85%). Per-category metrics are
#: reported but not gated — the seed sample is too small to gate per category.
GATED_METRICS = ("classification", "overall.precision", "overall.recall")


# --------------------------------------------------------------------------- #
# Normalized comparable view over both a predicted RawFinding and a label.
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    """Whitespace-collapse + casefold — the ``app/lens.py`` ``_normalize``
    precedent, extended with casefold so benign casing variance still matches."""
    return " ".join(text.split()).casefold()


def _as_float(value: str | None) -> float | None:
    """Parse the first scalar out of a value (``"Ø10,0 mm"`` → ``10.0``),
    reading a German decimal comma. Intended for dimensional scalars, not
    grouped numbers (no thousands-separator handling). ``None`` when there is
    no number."""
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if match is None:
        return None
    return float(match.group().replace(",", "."))


@dataclass(frozen=True)
class Comparable:
    """The uniform view the scorer compares — built from a ``RawFinding`` (the
    prediction) or a ``LabelledFinding`` (the truth)."""

    category: str
    type: str
    value: str | None = None
    normalized_value: str | None = None
    units: str | None = None
    tolerance: dict[str, Any] | None = None
    bbox: dict[str, float] | None = None
    value_tolerance: float | None = None

    @property
    def cmp_value(self) -> str | None:
        """The value the scorer matches on — the normalized form when present
        (block: "matched by normalized value"), else the raw value."""
        return self.normalized_value if self.normalized_value is not None else self.value


@dataclass(frozen=True)
class LabelledFinding:
    """One expected finding in a labelled fixture (``*.expected.json``)."""

    category: str
    type: str
    value: str | None = None
    normalized_value: str | None = None
    units: str | None = None
    tolerance: dict[str, Any] | None = None
    bbox: dict[str, float] | None = None
    #: numeric tolerance for a dimension match (``|pred - label| ≤ value_tolerance``)
    value_tolerance: float | None = None


def _label_to_comparable(label: LabelledFinding) -> Comparable:
    return Comparable(
        category=label.category,
        type=label.type,
        value=label.value,
        normalized_value=label.normalized_value,
        units=label.units,
        tolerance=label.tolerance,
        bbox=label.bbox,
        value_tolerance=label.value_tolerance,
    )


def to_comparable(obj: Any) -> Comparable:
    """Adapt a predicted ``RawFinding`` (or a dict / ``LabelledFinding``) to the
    scorer's uniform view. Enums and Pydantic sub-models are flattened here."""
    if isinstance(obj, LabelledFinding):
        return _label_to_comparable(obj)
    if isinstance(obj, Comparable):
        return obj

    def _get(name: str) -> Any:
        return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)

    def _dump(sub: Any) -> dict[str, Any] | None:
        if sub is None:
            return None
        if isinstance(sub, dict):
            return sub
        return cast("dict[str, Any]", sub.model_dump())

    category = _get("category")
    return Comparable(
        category=str(getattr(category, "value", category)),
        type=str(_get("type")),
        value=_get("value"),
        normalized_value=_get("normalized_value"),
        units=_get("units"),
        tolerance=_dump(_get("tolerance")),
        bbox=_dump(_get("bbox")),
        value_tolerance=None,  # only labels carry a numeric tolerance
    )


# --------------------------------------------------------------------------- #
# The match predicate.
# --------------------------------------------------------------------------- #
def values_match(pred: Comparable, label: Comparable) -> bool:
    """Values match when both absent, or equal after normalization, or (when
    the label sets ``value_tolerance``) within that numeric tolerance."""
    if label.value_tolerance is not None:
        a, b = _as_float(pred.cmp_value), _as_float(label.cmp_value)
        return a is not None and b is not None and abs(a - b) <= label.value_tolerance
    pv, lv = pred.cmp_value, label.cmp_value
    if pv is None or lv is None:
        return pv is None and lv is None
    return _norm(pv) == _norm(lv)


def units_match(pred: Comparable, label: Comparable) -> bool:
    """When the label specifies units, the prediction's must match (normalized):
    ``10 in`` must never satisfy a ``10 mm`` label (metric-native invariant,
    CLAUDE.md §5). Not scored when the label carries no units."""
    if label.units is None:
        return True
    if pred.units is None:
        return False
    return _norm(pred.units) == _norm(label.units)


def tolerance_match(pred: Comparable, label: Comparable) -> bool:
    """When the label carries a tolerance spec, the prediction's must equal it
    on ``(kind, upper, lower)``; otherwise tolerance is not scored."""
    if label.tolerance is None:
        return True
    if pred.tolerance is None:
        return False
    keys = ("kind", "upper", "lower")
    return all(pred.tolerance.get(k) == label.tolerance.get(k) for k in keys)


def _iou(a: dict[str, float], b: dict[str, float]) -> float:
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0


def bbox_match(pred: Comparable, label: Comparable, iou_min: float = BBOX_IOU_MIN) -> bool:
    """When the label carries a bbox, the prediction's must overlap it with
    IoU ≥ ``iou_min``; otherwise bbox is not scored."""
    if label.bbox is None:
        return True
    if pred.bbox is None:
        return False
    return _iou(pred.bbox, label.bbox) >= iou_min


def is_match(pred: Comparable, label: Comparable) -> bool:
    return (
        pred.category == label.category
        and pred.type == label.type
        and values_match(pred, label)
        and units_match(pred, label)
        and tolerance_match(pred, label)
        and bbox_match(pred, label)
    )


# --------------------------------------------------------------------------- #
# Scoring.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def __add__(self, other: Counts) -> Counts:
        return Counts(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)


@dataclass(frozen=True)
class Metrics:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def precision_recall_f1(counts: Counts) -> Metrics:
    """P/R/F1 from raw counts. Conventions (pinned by the meta-test): with no
    predictions precision is 1.0 (no false positives); with nothing to find
    recall is 1.0 (vacuous); F1 is 0.0 when both P and R are 0."""
    tp, fp, fn = counts.tp, counts.fp, counts.fn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return Metrics(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def match_counts(predicted: list[Comparable], labels: list[Comparable]) -> Counts:
    """**Maximum** one-to-one matching between predictions and labels (Kuhn's
    augmenting-path algorithm). TP = matched pairs, FN = unmatched labels,
    FP = unmatched predictions. Maximum (not greedy first-fit) so the score is
    independent of fixture ordering — a greedy pass can undercount when an
    unconstrained label claims the only prediction a bbox-constrained label
    needs; maximum matching frees it via an augmenting path."""
    # adj[label] = prediction indices that satisfy the match predicate.
    adj = [[i for i, pred in enumerate(predicted) if is_match(pred, label)] for label in labels]
    matched_pred_to_label = [-1] * len(predicted)

    def _augment(label_idx: int, seen: list[bool]) -> bool:
        for pred_idx in adj[label_idx]:
            if seen[pred_idx]:
                continue
            seen[pred_idx] = True
            owner = matched_pred_to_label[pred_idx]
            if owner == -1 or _augment(owner, seen):
                matched_pred_to_label[pred_idx] = label_idx
                return True
        return False

    tp = 0
    for label_idx in range(len(labels)):
        if _augment(label_idx, [False] * len(predicted)):
            tp += 1
    return Counts(tp=tp, fp=len(predicted) - tp, fn=len(labels) - tp)


@dataclass(frozen=True)
class RunMetrics:
    #: per-page is-print accuracy across the run; ``None`` when no pages labelled
    classification: float | None
    overall: Metrics
    by_category: dict[str, Metrics]

    def flat(self) -> dict[str, float]:
        """The gate-facing flat view: ``classification``, ``overall.precision``,
        ``overall.recall``, ``overall.f1`` (+ per-category)."""
        out: dict[str, float] = {
            "overall.precision": self.overall.precision,
            "overall.recall": self.overall.recall,
            "overall.f1": self.overall.f1,
        }
        if self.classification is not None:
            out["classification"] = self.classification
        for cat, m in self.by_category.items():
            out[f"{cat}.precision"] = m.precision
            out[f"{cat}.recall"] = m.recall
            out[f"{cat}.f1"] = m.f1
        return out


def category_counts(predicted: list[Any], labels: list[Any]) -> dict[str, Counts]:
    """TP/FP/FN per category for **one document** — predictions matched only
    against that document's labels. Aggregate across documents by summing these
    (``Counts.__add__``), never by pooling finding lists: pooling would let a
    prediction on print A satisfy a label on print B, which can only inflate the
    score (a hallucinated duplicate could mask a real miss). Per-document counts
    summed give an honest micro-average."""
    preds = [to_comparable(p) for p in predicted]
    labs = [to_comparable(label) for label in labels]
    categories = sorted({c.category for c in preds} | {c.category for c in labs})
    return {
        cat: match_counts(
            [p for p in preds if p.category == cat],
            [label for label in labs if label.category == cat],
        )
        for cat in categories
    }


def metrics_from_counts(
    by_category_counts: dict[str, Counts], *, classification: float | None = None
) -> RunMetrics:
    """Build per-category + micro-averaged overall metrics from summed counts."""
    by_category = {cat: precision_recall_f1(c) for cat, c in by_category_counts.items()}
    total = Counts()
    for counts in by_category_counts.values():
        total += counts
    return RunMetrics(
        classification=classification,
        overall=precision_recall_f1(total),
        by_category=by_category,
    )


def score_findings(
    predicted: list[Any],
    labels: list[Any],
    *,
    classification: float | None = None,
) -> RunMetrics:
    """Score one document's prediction/label set into per-category +
    micro-averaged overall metrics. For a multi-document run, sum
    :func:`category_counts` per document and call :func:`metrics_from_counts`."""
    return metrics_from_counts(category_counts(predicted, labels), classification=classification)


def classification_accuracy(
    predicted_print_pages: set[int], expected_print_pages: set[int], pages_total: int
) -> float:
    """Per-page is-print accuracy: pages where predicted-is-print agrees with
    expected-is-print. The page universe is ``1..pages_total`` **plus** any
    out-of-range page either side claims — so a prediction for page 0 or
    ``pages_total + 1`` is a disagreement (penalized), never silently ignored.
    1.0 for an empty universe (vacuous)."""
    if pages_total < 0:
        raise ValueError(f"pages_total must be >= 0, got {pages_total}")
    universe = set(range(1, pages_total + 1)) | predicted_print_pages | expected_print_pages
    if not universe:
        return 1.0
    correct = sum(
        (page in predicted_print_pages) == (page in expected_print_pages) for page in universe
    )
    return correct / len(universe)


# --------------------------------------------------------------------------- #
# The baseline / regression gate.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)


def compare_to_baseline(
    current: dict[str, float],
    baseline: dict[str, float],
    margin: float,
    *,
    metrics: tuple[str, ...] = GATED_METRICS,
) -> GateResult:
    """Regression gate: fail a tracked metric only when it drops **more than
    ``margin`` below** its baseline (block: "fail on regression-vs-baseline
    beyond a margin"). Benign phrasing variance — a drop within the margin —
    passes. An *improvement* always passes and never re-baselines here.

    **Fails closed on a missing metric**: a gated metric absent from the
    baseline or the current run is a misconfiguration/harness bug, not a pass —
    otherwise a typo or an omitted ``classification`` entry silently bypasses a
    tracked gate."""
    failures: list[str] = []
    for name in metrics:
        base = baseline.get(name)
        cur = current.get(name)
        if base is None:
            failures.append(f"{name}: missing from baseline (gate cannot evaluate)")
            continue
        if cur is None:
            failures.append(f"{name}: missing from current run (gate cannot evaluate)")
            continue
        if cur < base - margin:
            failures.append(
                f"{name}: {cur:.3f} regressed below baseline {base:.3f} "
                f"(margin {margin:.3f}, floor {base - margin:.3f})"
            )
    return GateResult(passed=not failures, failures=failures)


# --------------------------------------------------------------------------- #
# Fixture loading.
# --------------------------------------------------------------------------- #
#: The Lens pipelines a fixture can exercise. Only ``document-extraction``
#: produces the ``ExtractionFinding`` taxonomy this scorer measures today;
#: ``email-ingest`` (RawLineItem parts-list) and ``bom-detection`` (M4, not yet
#: built — DECISIONS 2026-06-26 "M4 pipeline 5") accrue their own labelled
#: fixtures as those tracks mature. Tagging keeps the format honest about which
#: pipeline a fixture belongs to without pretending a run exists.
DOCUMENT_EXTRACTION = "document-extraction"
LENS_PIPELINES = (DOCUMENT_EXTRACTION, "email-ingest", "bom-detection", "file-processing")


@dataclass(frozen=True)
class LabelledFixture:
    name: str
    pdf_path: Path
    pages_total: int
    print_pages: set[int]
    findings: list[LabelledFinding]
    pipeline: str = DOCUMENT_EXTRACTION

    @property
    def pdf_bytes(self) -> bytes:
        return self.pdf_path.read_bytes()


def fixture_names() -> list[str]:
    return sorted(path.stem.removesuffix(".expected") for path in EVAL_DIR.glob("*.expected.json"))


def load_fixture(name: str) -> LabelledFixture:
    raw = json.loads((EVAL_DIR / f"{name}.expected.json").read_text(encoding="utf-8"))
    pdf_ref = raw["pdf"]
    pdf_path = DRAWINGS_DIR / pdf_ref if "/" not in pdf_ref else FIXTURES_DIR / pdf_ref
    findings = [LabelledFinding(**f) for f in raw.get("findings", [])]
    return LabelledFixture(
        name=name,
        pdf_path=pdf_path,
        pages_total=int(raw["pages_total"]),
        print_pages=set(raw.get("print_pages", [])),
        findings=findings,
        pipeline=raw.get("pipeline", DOCUMENT_EXTRACTION),
    )


def load_baseline() -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        json.loads((EVAL_DIR / "baseline.json").read_text(encoding="utf-8")),
    )
