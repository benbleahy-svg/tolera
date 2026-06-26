"""Pure unit tests for the quote state machine (no database).

These encode the spec ``#quotelifecycle`` graph **independently** of the
implementation's transition table, so they are a real check on the rules — not a
tautology that mirrors the code. The DB/API enforcement is tested in
``test_quotes_api.py``.
"""

from __future__ import annotations

import pytest

from app.authz import Permission
from app.models import QuoteStatus as S
from app.quote_lifecycle import (
    allowed_targets,
    is_legal_transition,
    required_permission,
)

# The legal edges for non-``on_hold`` source states (``on_hold`` is dynamic and is
# checked separately). Closed states are terminal in M1.4 (reopen/revisions are M5);
# ``expired`` is soft, so it can still be won/lost/cancelled.
_EXPECTED: dict[S, set[S]] = {
    S.draft: {S.sent, S.no_quote, S.on_hold, S.cancelled},
    S.sent: {S.won, S.lost, S.expired, S.cancelled, S.on_hold},
    S.expired: {S.won, S.lost, S.cancelled},
    S.won: set(),
    S.lost: set(),
    S.cancelled: set(),
    S.no_quote: set(),
}


@pytest.mark.parametrize("from_status", list(_EXPECTED))
@pytest.mark.parametrize("to_status", list(S))
def test_static_transition_matrix(from_status: S, to_status: S) -> None:
    """Every (from, to) pair from a static state matches the expected graph exactly."""
    assert is_legal_transition(from_status, to_status) is (to_status in _EXPECTED[from_status])


def test_allowed_targets_matches_expected() -> None:
    for from_status, expected in _EXPECTED.items():
        assert set(allowed_targets(from_status, None)) == expected


def test_terminal_states_have_no_exits() -> None:
    for terminal in (S.won, S.lost, S.cancelled, S.no_quote):
        assert allowed_targets(terminal, None) == frozenset()


def test_on_hold_returns_only_to_prior_status() -> None:
    # Paused from a draft → only draft is a legal exit.
    assert is_legal_transition(S.on_hold, S.draft, S.draft) is True
    assert is_legal_transition(S.on_hold, S.sent, S.draft) is False
    # Paused from sent → only sent is a legal exit.
    assert is_legal_transition(S.on_hold, S.sent, S.sent) is True
    assert is_legal_transition(S.on_hold, S.draft, S.sent) is False


def test_on_hold_without_prior_status_is_stuck() -> None:
    # A data-integrity guard: no remembered prior status ⇒ no legal exit.
    assert allowed_targets(S.on_hold, None) == frozenset()


def test_expired_is_soft_can_still_be_won() -> None:
    assert is_legal_transition(S.expired, S.won) is True


def test_a_quote_cannot_transition_to_itself() -> None:
    for s in S:
        assert is_legal_transition(s, s, S.draft) is False


@pytest.mark.parametrize(
    ("from_status", "to_status", "expected"),
    [
        (S.draft, S.sent, Permission.quote_finalize),  # finalize/send
        (S.draft, S.cancelled, Permission.quote_delete),  # cancel is destructive-ish
        (S.sent, S.cancelled, Permission.quote_delete),
        (S.expired, S.cancelled, Permission.quote_delete),
        (S.draft, S.no_quote, Permission.quote_edit),
        (S.draft, S.on_hold, Permission.quote_edit),
        (S.sent, S.won, Permission.quote_edit),
        (S.sent, S.lost, Permission.quote_edit),
        (S.on_hold, S.draft, Permission.quote_edit),  # un-hold is ordinary editing
        (S.on_hold, S.sent, Permission.quote_edit),  # …even when restoring a sent quote
    ],
)
def test_required_permission(from_status: S, to_status: S, expected: Permission) -> None:
    assert required_permission(from_status, to_status) is expected
