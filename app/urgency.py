"""The Dashboard work-queue **urgency score** (M6.1) — pure, deterministic math.

Spec ``#newscope`` §2 fixes the formula::

    w1*days_to_due^-1 + w2*quote_value_band + w3*unresolved_count + w4*flags

with the weights **org-configurable** (``org_dashboard_settings``, sensible
defaults shipped here) and the result **deterministic and explainable** — the
row's hover panel shows each factor's contribution, so every term is returned
alongside the score rather than folded into it.

Three properties this module exists to guarantee:

* **One scale.** Each raw factor is normalised to 0-1 (the overdue branch of
  ``due_factor`` is the single deliberate exception, 1.0-2.0) so the weights are
  actually comparable — a weight of 0.4 means "40% of the ranking", whatever the
  underlying units.
* **Determinism.** Everything is :class:`~decimal.Decimal`; the score is
  quantised to 4 dp. No float appears anywhere on the path, so the same seed
  yields byte-identical ordering on every machine (block acceptance criterion).
  The only time-varying input is ``days_to_due``, which the caller derives once
  per request from a single UTC **date** — day granularity, not clock time.
* **Totality.** Every input has a defined answer, including the ones the bare
  formula does not cover: no due date, due *today* (the inverse is undefined),
  and long-overdue (unbounded without a cap).

The undefined-at-zero handling is an ASSUMED default (cheap to reverse — it
changes a ranking, never stored data; CLAUDE.md §6.3): due today clamps to the
1.0 floor and each overdue day adds 0.1 up to 2.0, so overdue always outranks
"due tomorrow" without letting a year-late quote dwarf the other three terms.

Money note: value enters **only** as a band. No monetary amount is returned by
the queue, so the tier-1 "integer minor units + currency" rule is satisfied by
never handing a number to the UI in the first place. Band thresholds are read in
the org's own currency (EUR/CHF) — v1 is single-currency per org, no FX.
"""

from __future__ import annotations

import dataclasses
from decimal import ROUND_HALF_UP, Decimal

#: Score precision. 4 dp is far finer than any tie the UI can show, and pins the
#: ordering exactly (two rows are equal only if they are *really* equal).
_SCORE_EXP = Decimal("0.0001")
#: Normalised-factor precision (thirds and sevenths are non-terminating).
_NORM_EXP = Decimal("0.000001")

#: Overdue ramp: +0.1 per day past due, capped this many days out.
_OVERDUE_CAP_DAYS = 10
#: Unresolved review items above this count add nothing further.
_UNRESOLVED_CAP = 10
#: The three urgency flags (spec ``#newscope``: expedite / VIP / export).
_FLAG_COUNT = 3

#: Value-band upper bounds in **minor units** (cents) of the org's currency —
#: EUR 1 000 / 10 000 / 50 000 / 250 000. A quote at or above the last bound is
#: the top band. Bands (not amounts) are what the score and the API expose.
_VALUE_BAND_BOUNDS: tuple[int, ...] = (100_000, 1_000_000, 5_000_000, 25_000_000)
#: The top band index — the divisor that normalises a band onto 0-1.
TOP_VALUE_BAND = len(_VALUE_BAND_BOUNDS)


@dataclasses.dataclass(frozen=True, slots=True)
class UrgencyWeights:
    """The org's four weights. Defaults are the shipped sensible set: due-date
    dominates (it is the only term with a deadline behind it), value and open
    work split the middle, flags are a tiebreaker. They sum to 1.0 so a score is
    readable as a 0-1 urgency (nothing enforces the sum — an org is free to
    re-weight past it; only negatives are rejected)."""

    due: Decimal = Decimal("0.40")
    value: Decimal = Decimal("0.25")
    unresolved: Decimal = Decimal("0.25")
    flags: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        for name in ("due", "value", "unresolved", "flags"):
            if getattr(self, name) < 0:
                # A negative weight inverts the term's meaning (an overdue quote
                # would *sink*). Reject at the boundary, never persist it.
                raise ValueError(f"urgency weight {name!r} must be >= 0")


#: The weights an org gets before anyone opens Settings.
DEFAULT_URGENCY_WEIGHTS = UrgencyWeights()


@dataclasses.dataclass(frozen=True, slots=True)
class UrgencyInputs:
    """The raw signals behind one queue row.

    ``value_minor`` is the parent quote's value proxy in minor units (see
    :mod:`app.work_queue` for the derivation); ``None`` for a row with no quote
    or no priced quantity yet. Rows hanging off a quote (task, review item,
    mention) inherit that quote's value/flags/unresolved signals so all five
    sources land on one comparable scale."""

    days_to_due: int | None
    value_minor: int | None
    unresolved_count: int
    expedite: bool
    vip: bool
    export_controlled: bool


@dataclasses.dataclass(frozen=True, slots=True)
class Factor:
    """One term of the score, as the hover panel renders it: what it was
    (``raw``), what it became on the 0-1 scale, its weight, and what it actually
    added. ``raw`` is a display-neutral string — the UI localises the label from
    ``key``, so no English prose crosses the API boundary (German-first)."""

    key: str
    raw: str
    normalized: Decimal
    weight: Decimal
    contribution: Decimal


@dataclasses.dataclass(frozen=True, slots=True)
class UrgencyScore:
    """A row's score plus its four factors, always in formula order."""

    score: Decimal
    factors: tuple[Factor, ...]


def due_factor(days_to_due: int | None) -> Decimal:
    """``days_to_due^-1``, made total.

    No due date -> 0 (the term drops out; an undated row is ranked by its other
    signals). Due today or overdue -> 1.0 plus 0.1 per overdue day, capped at
    2.0. Otherwise the literal inverse, so due-in-2-days scores half of
    due-tomorrow."""
    if days_to_due is None:
        return Decimal(0)
    if days_to_due <= 0:
        overdue = min(-days_to_due, _OVERDUE_CAP_DAYS)
        return (Decimal(1) + Decimal(overdue) / Decimal(10)).quantize(_NORM_EXP).normalize()
    return (Decimal(1) / Decimal(days_to_due)).quantize(_NORM_EXP).normalize()


def value_band(value_minor: int | None) -> int:
    """The quote's value band, 0 (or unpriced) through :data:`TOP_VALUE_BAND`."""
    if value_minor is None:
        return 0
    return sum(1 for bound in _VALUE_BAND_BOUNDS if value_minor >= bound)


def unresolved_factor(unresolved_count: int) -> Decimal:
    """Open review items, normalised against the cap — 10 unresolved items is
    already "maximally blocked"; the 11th should not keep pushing the row up."""
    capped = min(max(unresolved_count, 0), _UNRESOLVED_CAP)
    return (Decimal(capped) / Decimal(_UNRESOLVED_CAP)).quantize(_NORM_EXP).normalize()


def flags_factor(*, expedite: bool, vip: bool, export_controlled: bool) -> Decimal:
    """The share of the three urgency flags that are set."""
    raised = sum((expedite, vip, export_controlled))
    return (Decimal(raised) / Decimal(_FLAG_COUNT)).quantize(_NORM_EXP).normalize()


def _term(key: str, raw: str, normalized: Decimal, weight: Decimal) -> Factor:
    return Factor(
        key=key,
        raw=raw,
        normalized=normalized,
        weight=weight,
        # Each contribution is rounded to the score's precision *before* summing,
        # so the four numbers the hover panel shows add up to the score exactly —
        # a user checking the arithmetic by hand must never find a stray digit.
        contribution=(normalized * weight).quantize(_SCORE_EXP, rounding=ROUND_HALF_UP),
    )


def score_urgency(
    inputs: UrgencyInputs, weights: UrgencyWeights = DEFAULT_URGENCY_WEIGHTS
) -> UrgencyScore:
    """Score one row and return every contributing factor with it."""
    band = value_band(inputs.value_minor)
    factors = (
        _term(
            "due",
            "" if inputs.days_to_due is None else str(inputs.days_to_due),
            due_factor(inputs.days_to_due),
            weights.due,
        ),
        _term(
            "value",
            str(band),
            (Decimal(band) / Decimal(TOP_VALUE_BAND)).quantize(_NORM_EXP).normalize(),
            weights.value,
        ),
        _term(
            "unresolved",
            str(inputs.unresolved_count),
            unresolved_factor(inputs.unresolved_count),
            weights.unresolved,
        ),
        _term(
            "flags",
            str(sum((inputs.expedite, inputs.vip, inputs.export_controlled))),
            flags_factor(
                expedite=inputs.expedite,
                vip=inputs.vip,
                export_controlled=inputs.export_controlled,
            ),
            weights.flags,
        ),
    )
    total = sum((f.contribution for f in factors), Decimal(0))
    return UrgencyScore(score=total.quantize(_SCORE_EXP), factors=factors)
