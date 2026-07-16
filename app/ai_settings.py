"""Per-org AI feature gate (spec ``#ai-settings``; M3.9).

Every AI code path checks the relevant flag before executing; ``master_enabled``
is checked first (spec build-note). This module is the single read seam.

Correctness posture: a **direct DB read**, not the spec's optional Redis 5-min
cache — the cache exists so disablement isn't *delayed* ("short enough to not
delay disablement in sensitive situations"); a direct read has zero staleness,
which is strictly safer, so the cache is deferred as a pure optimisation.

An **absent row is treated as all-enabled** — matching "seed the fixture orgs
with AI fully enabled" and the migration's all-TRUE defaults — so a missing row
(e.g. an org provisioned before the default-row insert) never silently disables
AI. ``master_enabled=False`` in a present row is the only way AI is off.
"""

from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import OrgAiSettings


@dataclasses.dataclass(frozen=True, slots=True)
class AiFlags:
    """A resolved snapshot of an org's AI toggles (all default enabled)."""

    master_enabled: bool = True
    wingman_enabled: bool = True
    triage_brief_enabled: bool = True
    quote_assembly_enabled: bool = True
    estimation_coaching_enabled: bool = True
    presend_review_enabled: bool = True
    assistant_enabled: bool = True
    mcp_enabled: bool = True
    customer_brief_enabled: bool = True
    requote_diff_enabled: bool = True
    rule_suggest_enabled: bool = True
    margin_coach_enabled: bool = True
    benchmarking_opt_out: bool = True

    @property
    def triage_enabled(self) -> bool:
        """The M3.9 gate: master first, then the triage-brief flag."""
        return self.master_enabled and self.triage_brief_enabled


#: All-enabled default returned when an org has no ``org_ai_settings`` row.
DEFAULT_AI_FLAGS = AiFlags()

_FIELDS = tuple(f.name for f in dataclasses.fields(AiFlags))


async def get_ai_flags(session: AsyncSession, org_id: uuid.UUID) -> AiFlags:
    """The org's AI flags, or the all-enabled default when no row exists.

    Reads within the caller's org-scoped session (RLS already pins ``org_id``).
    """
    row = (
        await session.scalars(select(OrgAiSettings).where(OrgAiSettings.org_id == org_id))
    ).one_or_none()
    if row is None:
        return DEFAULT_AI_FLAGS
    return AiFlags(**{name: getattr(row, name) for name in _FIELDS})
