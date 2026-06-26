"""Quote lifecycle — the enforced status state machine (M1.4).

The single source of truth for *which* quote-status transitions are legal and what
each one does. The spec ``#quotelifecycle`` ("decided") is the authority; the graph
below is its M1.4 subset — the revision/reopen/superseded flows it also describes are
deferred to M5 (DECISIONS.md 2026-06-26), so the closed states are terminal here.

Two layers, deliberately split so the rules are unit-testable without a database:

  * :func:`allowed_targets` / :func:`is_legal_transition` — **pure** functions over
    ``(from_status, status_before_hold)``. ``on_hold`` is dynamic: its only legal exit
    is back to the status it was paused from (spec: "returns to the prior status").
  * :func:`transition` — applies a validated change to a :class:`~app.models.Quote`:
    enforces the Draft→Sent contact precondition, stamps the lifecycle timestamps,
    maintains ``status_before_hold``, and appends a :class:`~app.models.QuoteStatusEvent`
    (the append-only audit trail; also the home of the optional Lost reason note).

Authorization is target-aware (:func:`required_permission`) rather than a fixed
``require()`` guard, because the capability needed depends on the destination:
finalize/send needs ``quote_finalize``; Cancel needs ``quote_delete`` (admin/manager
only, per the M0.3 under-grant); everything else needs ``quote_edit``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .authz import Permission
from .errors import AppError
from .models import Quote, QuoteStatus, QuoteStatusEvent

#: The status every new quote opens in.
INITIAL_STATUS = QuoteStatus.draft

#: Static legal transitions (``on_hold`` is handled dynamically — see
#: :func:`allowed_targets`). Closed states (``won``/``lost``/``cancelled``/
#: ``no_quote``) are **terminal in M1.4**: Build-Order, reopen and revisions are M5.
#: ``expired`` is *soft* (spec + DACH delta): acceptance is not blocked, so it can
#: still be won — or marked lost/cancelled.
_TRANSITIONS: dict[QuoteStatus, frozenset[QuoteStatus]] = {
    QuoteStatus.draft: frozenset(
        {QuoteStatus.sent, QuoteStatus.no_quote, QuoteStatus.on_hold, QuoteStatus.cancelled}
    ),
    QuoteStatus.sent: frozenset(
        {
            QuoteStatus.won,
            QuoteStatus.lost,
            QuoteStatus.expired,
            QuoteStatus.cancelled,
            QuoteStatus.on_hold,
        }
    ),
    QuoteStatus.expired: frozenset({QuoteStatus.won, QuoteStatus.lost, QuoteStatus.cancelled}),
    QuoteStatus.on_hold: frozenset(),  # dynamic — only back to status_before_hold
    QuoteStatus.won: frozenset(),
    QuoteStatus.lost: frozenset(),
    QuoteStatus.cancelled: frozenset(),
    QuoteStatus.no_quote: frozenset(),
}


def allowed_targets(
    from_status: QuoteStatus, status_before_hold: QuoteStatus | None
) -> frozenset[QuoteStatus]:
    """The statuses ``from_status`` may legally move to.

    From ``on_hold`` the only legal exit is the status the quote was paused from
    (``status_before_hold``); if that memory is missing the quote is stuck (no exit),
    which is a data-integrity guard rather than a normal state."""
    if from_status is QuoteStatus.on_hold:
        return frozenset({status_before_hold}) if status_before_hold is not None else frozenset()
    return _TRANSITIONS[from_status]


def is_legal_transition(
    from_status: QuoteStatus, to_status: QuoteStatus, status_before_hold: QuoteStatus | None = None
) -> bool:
    """Whether ``from_status → to_status`` is permitted by the state machine."""
    return to_status in allowed_targets(from_status, status_before_hold)


def required_permission(from_status: QuoteStatus, to_status: QuoteStatus) -> Permission:
    """The capability a caller needs to perform this transition.

    Un-holding (leaving ``on_hold``) is ordinary editing even when it restores a Sent
    quote, so it needs only ``quote_edit`` — hence the from-aware check."""
    if from_status is QuoteStatus.on_hold:
        return Permission.quote_edit
    if to_status is QuoteStatus.sent:
        return Permission.quote_finalize
    if to_status is QuoteStatus.cancelled:
        return Permission.quote_delete
    return Permission.quote_edit


async def transition(
    session: AsyncSession,
    quote: Quote,
    to_status: QuoteStatus,
    *,
    actor_id: uuid.UUID | None,
    note: str | None = None,
) -> Quote:
    """Move ``quote`` to ``to_status``, enforcing the state machine server-side.

    Raises ``AppError`` (``409 invalid_transition``) for an illegal move, and
    (``422 missing_contact``) when sending a quote that has no contact assigned.
    Records a :class:`QuoteStatusEvent` for the audit trail. Callers must have
    already authorized via :func:`required_permission`."""
    from_status = quote.status
    if not is_legal_transition(from_status, to_status, quote.status_before_hold):
        raise AppError(
            "invalid_transition",
            f"A quote cannot move from '{from_status.value}' to '{to_status.value}'.",
            status_code=409,
        )
    # Leaving on_hold restores the *prior* status — it is not a fresh forward move,
    # so the entry preconditions/timestamps of that status must NOT re-fire (else
    # un-holding a Sent quote would re-check the contact and clobber the original
    # ``sent_at`` that drives overdue/expiry). CodeRabbit 2026-06-26.
    is_restore = from_status is QuoteStatus.on_hold

    # Send precondition (spec: a contact must be assigned to finalize/send) — forward only.
    if to_status is QuoteStatus.sent and not is_restore and quote.contact_id is None:
        raise AppError(
            "missing_contact",
            "A quote must have an assigned contact before it can be sent.",
            status_code=422,
        )

    now = datetime.now(UTC)
    if to_status is QuoteStatus.on_hold:
        quote.status_before_hold = from_status  # remember where to return
    elif is_restore:
        quote.status_before_hold = None  # restored — clear the memory

    # Stamp lifecycle timestamps only on a genuine forward transition, and never
    # overwrite an existing one (idempotent across a hold/un-hold round-trip).
    if not is_restore:
        if to_status is QuoteStatus.sent and quote.sent_at is None:
            quote.sent_at = now
        elif to_status is QuoteStatus.expired and quote.expired_at is None:
            quote.expired_at = now

    quote.status = to_status
    session.add(
        QuoteStatusEvent(
            org_id=quote.org_id,
            quote_id=quote.id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            note=note,
        )
    )
    await session.flush()
    return quote
