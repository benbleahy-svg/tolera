"""M6.1 — the urgency score's arithmetic (pure, no DB).

The spec (``#newscope`` §2) fixes the shape of the score:

    w1·days_to_due⁻¹ + w2·quote_value_band + w3·unresolved_count + w4·flags

…and demands it be **deterministic and explainable** (the hover panel shows the
contributing factors). These tests pin the four factor functions, the exactness
of the roll-up (contributions sum to the score, no float drift), and the
re-ordering behaviour the block's acceptance criterion calls out ("reordering org
weights re-sorts deterministically").
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.urgency import (
    DEFAULT_URGENCY_WEIGHTS,
    UrgencyInputs,
    UrgencyWeights,
    due_factor,
    flags_factor,
    score_urgency,
    unresolved_factor,
    value_band,
)


def _inputs(**kw: object) -> UrgencyInputs:
    base: dict[str, object] = {
        "days_to_due": None,
        "value_minor": None,
        "unresolved_count": 0,
        "expedite": False,
        "vip": False,
        "export_controlled": False,
    }
    base.update(kw)
    return UrgencyInputs(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Factor functions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (None, "0"),  # no due date — the term drops out entirely
        (1, "1"),  # due tomorrow
        (2, "0.5"),
        (4, "0.25"),
        (10, "0.1"),
        (1000, "0.001"),
        (0, "1"),  # due today — the inverse is undefined, clamped to the 1.0 floor
        (-1, "1.1"),  # overdue outranks due-tomorrow
        (-5, "1.5"),
        (-10, "2"),
        (-999, "2"),  # capped: a year-late quote cannot dwarf every other factor
    ],
)
def test_due_factor(days: int | None, expected: str) -> None:
    assert due_factor(days) == Decimal(expected)


@pytest.mark.parametrize(
    ("value_minor", "band"),
    [
        (None, 0),  # unpriced quote
        (0, 0),
        (99_999, 0),  # < €1 000
        (100_000, 1),  # €1 000
        (999_999, 1),
        (1_000_000, 2),  # €10 000
        (4_999_999, 2),
        (5_000_000, 3),  # €50 000
        (24_999_999, 3),
        (25_000_000, 4),  # €250 000
        (900_000_000, 4),
    ],
)
def test_value_band(value_minor: int | None, band: int) -> None:
    assert value_band(value_minor) == band


def test_value_factor_is_the_band_normalised_to_the_top_band() -> None:
    # The four factors must share one 0-1 scale or the weights are not comparable.
    got = score_urgency(_inputs(value_minor=25_000_000), UrgencyWeights(value=Decimal(1)))
    assert got.score == Decimal("1.0000")


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0"), (1, "0.1"), (5, "0.5"), (10, "1"), (25, "1")],  # capped at 10
)
def test_unresolved_factor(count: int, expected: str) -> None:
    assert unresolved_factor(count) == Decimal(expected)


@pytest.mark.parametrize(
    ("expedite", "vip", "export", "expected"),
    [
        (False, False, False, "0"),
        (True, False, False, "0.333333"),
        (True, True, False, "0.666667"),
        (True, True, True, "1"),
        (False, False, True, "0.333333"),
    ],
)
def test_flags_factor(expedite: bool, vip: bool, export: bool, expected: str) -> None:
    assert flags_factor(expedite=expedite, vip=vip, export_controlled=export) == Decimal(expected)


# --------------------------------------------------------------------------- #
# Roll-up
# --------------------------------------------------------------------------- #
def test_default_weights_sum_to_one() -> None:
    w = DEFAULT_URGENCY_WEIGHTS
    assert w.due + w.value + w.unresolved + w.flags == Decimal(1)


def test_empty_row_scores_zero() -> None:
    assert score_urgency(_inputs()).score == Decimal("0.0000")


def test_score_is_the_sum_of_its_contributions_exactly() -> None:
    got = score_urgency(
        _inputs(days_to_due=2, value_minor=6_000_000, unresolved_count=3, expedite=True)
    )
    assert sum((f.contribution for f in got.factors), Decimal(0)) == got.score
    # Hand-computed with the shipped defaults (0.40/0.25/0.25/0.10):
    #   due       0.5      * 0.40 = 0.2
    #   value     3/4=0.75 * 0.25 = 0.1875
    #   unresolved 0.3     * 0.25 = 0.075
    #   flags     1/3      * 0.10 = 0.0333333  -> 0.0333
    assert got.score == Decimal("0.4958")


def test_every_factor_is_explainable() -> None:
    """The hover panel needs key + raw + normalized + weight + contribution for
    all four terms — even the ones contributing nothing (spec ``#newscope``)."""
    got = score_urgency(_inputs(days_to_due=3))
    assert [f.key for f in got.factors] == ["due", "value", "unresolved", "flags"]
    due = got.factors[0]
    assert due.raw == "3"
    assert due.normalized == Decimal("0.333333")
    assert due.weight == DEFAULT_URGENCY_WEIGHTS.due
    assert due.contribution == Decimal("0.1333")
    assert all(f.contribution == Decimal("0.0000") for f in got.factors[1:])


def test_scores_are_quantised_to_four_places_no_float_drift() -> None:
    got = score_urgency(_inputs(days_to_due=7, value_minor=123_456, unresolved_count=7, vip=True))
    assert got.score.as_tuple().exponent == -4
    assert (
        score_urgency(
            _inputs(days_to_due=7, value_minor=123_456, unresolved_count=7, vip=True)
        ).score
        == got.score
    )  # stable across calls


def test_reordering_weights_re_sorts_deterministically() -> None:
    """Acceptance criterion: changing the org's weights re-orders the queue."""
    near_due_cheap = _inputs(days_to_due=1, value_minor=50_000)
    far_due_rich = _inputs(days_to_due=20, value_minor=900_000_000)

    due_heavy = UrgencyWeights(
        due=Decimal("0.90"), value=Decimal("0.10"), unresolved=Decimal(0), flags=Decimal(0)
    )
    value_heavy = UrgencyWeights(
        due=Decimal("0.10"), value=Decimal("0.90"), unresolved=Decimal(0), flags=Decimal(0)
    )

    assert (
        score_urgency(near_due_cheap, due_heavy).score
        > score_urgency(far_due_rich, due_heavy).score
    )
    assert (
        score_urgency(far_due_rich, value_heavy).score
        > score_urgency(near_due_cheap, value_heavy).score
    )


def test_weights_reject_negative_values() -> None:
    """A negative weight would invert the formula's meaning (an overdue quote
    sinking) — reject at the boundary rather than persist nonsense."""
    with pytest.raises(ValueError):
        UrgencyWeights(due=Decimal("-1"))
