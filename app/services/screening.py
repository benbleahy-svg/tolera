"""Restricted-party (sanctions) screening — the optional hook (M6.9).

DACH-DELTA-LAYER §5 asks for exactly this and no more: *"add an **optional**
restricted-party screening hook (EU consolidated sanctions list)"*. The word
optional is load-bearing — screening is a hook the product can call, not a gate
it ships switched on, and nothing here refuses anything by itself.

**Mock-first, per the M6 adapter posture** (build-plan M6 §13; DECISIONS' Würth
entry): built against a documented fixture so a real list provider slots in
**without code changes**. The pilot needs no credential and this block does not
block on procurement.

**Why a screener never decides.** The EU consolidated list is name-matched, and
name matching produces false positives — "Müller GmbH" is not evidence. A
:class:`ScreeningResult` is therefore a *finding for a human*, in the same family
as a Lens suggestion: it is recorded in the export-control compliance log
(:attr:`~app.models.ExportControlAction.screening`) and surfaced, never
auto-blocking. The one place a hard refusal exists is the M6.7c marketplace lane,
where the decision is the adapter's and this only supplies evidence for it
(DECISIONS 2026-07-07).

**No list is bundled.** Shipping a stale copy of a sanctions list would be worse
than shipping none: it would look authoritative while being wrong, and the list
changes by EU regulation. :class:`NullScreeningProvider` is the honest default —
it returns :attr:`ScreeningStatus.not_screened`, which reads as "this was not
checked", never as "this is clear".
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class ScreeningStatus(enum.StrEnum):
    """The outcome of one screening call."""

    #: No provider is configured. Explicitly **not** a pass — the distinction
    #: between "checked and clear" and "never checked" is the whole point.
    not_screened = "not_screened"
    #: Screened against a list; nothing matched.
    clear = "clear"
    #: One or more candidate matches. A finding for a human, never a verdict.
    potential_match = "potential_match"


@dataclass(frozen=True)
class ScreeningMatch:
    """One candidate hit from a list."""

    #: The list entry's name as published.
    matched_name: str
    #: Which list it came from (e.g. the EU consolidated list's identifier).
    list_name: str
    #: Provider-reported confidence 0-100. Reported verbatim, never thresholded
    #: here: where the cut-off sits is a compliance-officer decision.
    score: int
    #: The list's own reference for the entry, so a human can look it up.
    reference: str | None = None


@dataclass(frozen=True)
class ScreeningResult:
    status: ScreeningStatus
    #: The name that was screened — echoed back so a log entry is self-contained.
    query: str
    matches: list[ScreeningMatch] = field(default_factory=list)
    #: Which provider answered, for the audit entry.
    provider: str = "null"

    @property
    def needs_review(self) -> bool:
        """True when a human must look. ``not_screened`` does **not** need review
        by itself — it means the org has not opted into screening at all."""
        return self.status is ScreeningStatus.potential_match


@runtime_checkable
class ScreeningProvider(Protocol):
    """The seam a real list provider implements."""

    name: str

    async def screen(self, query: str) -> ScreeningResult: ...


class NullScreeningProvider:
    """The shipped default: answers ``not_screened`` for everything.

    Deliberately not a "clear" answer. An org that has not configured screening
    has not been screened, and the compliance log must say that rather than
    record a pass nobody performed.
    """

    name = "null"

    async def screen(self, query: str) -> ScreeningResult:
        return ScreeningResult(status=ScreeningStatus.not_screened, query=query, provider=self.name)


class FixtureScreeningProvider:
    """A deterministic provider driven by a supplied name list (mock-first).

    Used by tests and by the pilot's dry runs; a real EU-consolidated-list client
    implements the same :class:`ScreeningProvider` protocol and drops in with no
    change to the call sites.

    Matching is deliberately crude — casefolded substring — because the point of
    the fixture is to exercise the *plumbing* (a match surfaces, gets audited,
    reaches a human), not to model a real matcher. A real provider brings its own.
    """

    name = "fixture"

    def __init__(self, entries: dict[str, str], *, list_name: str = "eu-consolidated") -> None:
        #: name -> list reference.
        self._entries = entries
        self._list_name = list_name

    async def screen(self, query: str) -> ScreeningResult:
        needle = query.casefold().strip()
        matches = [
            ScreeningMatch(
                matched_name=name,
                list_name=self._list_name,
                score=100,
                reference=reference,
            )
            for name, reference in self._entries.items()
            if needle and (needle in name.casefold() or name.casefold() in needle)
        ]
        return ScreeningResult(
            status=ScreeningStatus.potential_match if matches else ScreeningStatus.clear,
            query=query,
            matches=matches,
            provider=self.name,
        )


#: The process-wide provider. Swapped by :func:`register` (the same seam the Lens
#: provider uses), so a test or a future Settings-driven wiring can install one
#: without touching call sites.
_provider: ScreeningProvider = NullScreeningProvider()


def register(provider: ScreeningProvider | None) -> None:
    """Install a provider (``None`` restores the null default)."""
    global _provider
    _provider = provider if provider is not None else NullScreeningProvider()


def resolve() -> ScreeningProvider:
    return _provider
