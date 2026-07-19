"""Vendor ranking for the RFQ batch-send modal (M6.4).

Spec ``#vendor-rfq`` → "AI suggestions" fixes the order exactly:

  1. most recent **accepted** response for the same org,
  2. historical **acceptance rate** for the matching process,
  3. **process** capability match,
  4. **material** match.

"New vendors (zero history) shown with New label, not hidden" — so newness is a
*label*, never a filter, and it falls out of the same signals rather than being a
separate flag someone can forget to set.

This module is deliberately pure: the caller (``app.vendor_rfq``) does the querying and
hands over plain :class:`VendorSignals`, so the documented order is testable without a
database and stays the single definition of "ranked" for both the modal and any later
consumer. Despite the spec's "AI suggestions" heading there is no model in the loop —
the ranking is a deterministic sort over recorded history, which is what makes it
explainable to an estimator who asks why a vendor was pre-checked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

#: How many ranked vendors the modal pre-checks. The spec says suggestions are
#: pre-checked but not how many; three keeps a blind multi-send genuinely
#: comparative without spraying an RFQ at every supplier in the directory.
#: Cheap to reverse — one constant, and the estimator can always tick more.
DEFAULT_PRECHECK_COUNT = 3


@dataclass(frozen=True)
class VendorSignals:
    """One candidate vendor's ranking inputs, as read from the directory + history."""

    vendor_id: uuid.UUID
    name: str
    #: When this vendor last had a response *applied* to costing (M6.6 writes
    #: ``vendor_rfq_response.applied_at``). ``None`` until it has ever won one.
    last_accepted_at: datetime | None
    #: applied responses / responses submitted, over this vendor's history.
    #: ``None`` = no responses at all (which is what makes a vendor "New").
    acceptance_rate: float | None
    process_match: bool
    material_match: bool


@dataclass(frozen=True)
class RankedVendor:
    """A vendor placed in the documented order, carrying why it landed there."""

    signals: VendorSignals
    #: Zero history — never quoted us. Shown with the spec's **New** label.
    is_new: bool
    #: Human-readable contributing factors, in the order they applied. The modal
    #: shows these so a pre-check is explainable rather than oracular.
    reasons: tuple[str, ...]

    @property
    def vendor_id(self) -> uuid.UUID:
        return self.signals.vendor_id

    @property
    def name(self) -> str:
        return self.signals.name


def _sort_key(v: VendorSignals) -> tuple[float, float, bool, bool, str]:
    # Descending on every signal, so each is negated; ``name`` last makes the order
    # total — two vendors with identical history must not depend on row order.
    return (
        -(v.last_accepted_at.timestamp() if v.last_accepted_at is not None else float("-inf")),
        -(v.acceptance_rate if v.acceptance_rate is not None else float("-inf")),
        not v.process_match,
        not v.material_match,
        v.name.casefold(),
    )


def _reasons(v: VendorSignals) -> tuple[str, ...]:
    reasons: list[str] = []
    if v.last_accepted_at is not None:
        reasons.append("last_accepted")
    if v.acceptance_rate is not None:
        reasons.append("acceptance_rate")
    if v.process_match:
        reasons.append("process_match")
    if v.material_match:
        reasons.append("material_match")
    return tuple(reasons)


def rank_vendors(candidates: list[VendorSignals]) -> list[RankedVendor]:
    """Order ``candidates`` by the spec's four signals; label the zero-history ones.

    A vendor is **New** when it has no response history at all. An acceptance rate of
    *zero* is history — it means the vendor has quoted and never won, which is a worse
    signal than unknown, not the same one, so such a vendor sorts below a New vendor
    on signal 2 and is not labelled New."""
    return [
        RankedVendor(
            signals=v,
            is_new=v.acceptance_rate is None and v.last_accepted_at is None,
            reasons=_reasons(v),
        )
        for v in sorted(candidates, key=_sort_key)
    ]


def suggested_ids(
    ranked: list[RankedVendor], limit: int = DEFAULT_PRECHECK_COUNT
) -> set[uuid.UUID]:
    """Which vendors the modal pre-checks: the top ``limit`` of the ranked list."""
    return {r.vendor_id for r in ranked[:limit]}
