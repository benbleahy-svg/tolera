"""Export-control (EU dual-use) compliance auditing — M6.9 pilot hardening.

The one place that writes :class:`ExportControlAccess`. Every call site — a
FastAPI route, a Celery worker, an outbound adapter — goes through
:func:`record_access` so the compliance log has a single, greppable seam.

**The posture this implements** (spec ``#authz``, marked ``decision``):

    Export-controlled (ITAR / CUI / EU dual-use): **flag + audit, no hard block
    in v1** — any internal user may open flagged quotes/parts/files, but access
    is **logged** (an access log on flagged items). A future "authorized user"
    attribute can turn this into a hard restriction without changing the model.

So nothing here refuses a read. What it does is make every touch of a flagged
record evidential. The one place the product *does* refuse is AI: per the spec's
AI-architecture section, "CUI/ITAR-flagged files are **always skipped**
regardless of the toggle" — those refusals already live at their call sites
(``lens_extract``, ``vendor_reply_lens``, ``triage``, ``requote_diff``,
``email_parts``, ``rule_suggest``) and record an :attr:`ExportControlAction.ai_skip`
entry here so the skip is provable, not merely asserted.

DACH-DELTA-LAYER §5 re-bases the regime on Regulation (EU) 2021/821 + national
AWG/AWV; the org's :class:`ExportRegime` is denormalised onto each entry so the
log stays truthful after a Settings change.

**Never log content.** ``detail`` carries identifiers and reasons only — never
print contents, extracted text, or customer PII (CLAUDE.md §5).
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ExportControlAccess,
    ExportControlAction,
    ExportControlSubject,
    ExportRegime,
    Organization,
)

#: Keys never permitted in ``detail`` — a cheap structural guard against a call
#: site drifting into logging print content or customer PII.
_FORBIDDEN_DETAIL_KEYS = frozenset(
    {
        "text",
        "content",
        "body",
        "page_text",
        "extracted",
        "email",
        "phone",
        "address",
        "prompt",
        "response",
    }
)


class ForbiddenAuditDetailError(ValueError):
    """Raised when a call site tries to log content or PII into ``detail``."""


def _check_detail(detail: dict[str, Any]) -> dict[str, Any]:
    offending = sorted(_FORBIDDEN_DETAIL_KEYS.intersection(detail))
    if offending:
        raise ForbiddenAuditDetailError(
            "export-control audit detail must carry identifiers and reasons only, "
            f"never content or PII; offending keys: {offending}"
        )
    return detail


async def org_export_regime(session: AsyncSession, org_id: uuid.UUID) -> ExportRegime:
    """The org's configured regime, or ``none`` if the org is unreachable.

    Falling back to ``none`` rather than raising is deliberate: an audit write
    must never be the thing that fails a request. The entry is still written —
    it just carries no regime label.
    """
    org = await session.get(Organization, org_id)
    return org.export_regime if org is not None else ExportRegime.none


async def record_access(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    subject_type: ExportControlSubject,
    subject_id: uuid.UUID,
    action: ExportControlAction,
    actor_user_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ExportControlAccess:
    """Append one entry to the compliance log and return it.

    Callers are responsible for having established that the subject really is
    export-controlled — this function does not re-check, because the flag lives
    on six different models and the caller always has the row in hand.

    The row is added to the caller's session (not committed) so the audit entry
    shares the transaction of the action it describes: if the action rolls back,
    so does its audit entry, and the log never claims something that did not
    happen.
    """
    entry = ExportControlAccess(
        org_id=org_id,
        actor_user_id=actor_user_id,
        subject_type=subject_type,
        subject_id=subject_id,
        action=action,
        regime=await org_export_regime(session, org_id),
        detail=_check_detail(dict(detail or {})),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(entry)
    return entry


async def list_access(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 5000,
) -> Sequence[ExportControlAccess]:
    """The org's compliance log, newest first — the CSV export's data source.

    ``limit`` is a hard ceiling rather than a pagination cursor: the CSV download
    is a compliance artefact pulled occasionally, not a browsing surface, and an
    unbounded export of a busy tenant is a memory hazard. The export reports the
    ceiling when it truncates (never a silent cap — CLAUDE.md engineering rules).
    """
    stmt = select(ExportControlAccess).where(ExportControlAccess.org_id == org_id)
    if since is not None:
        stmt = stmt.where(ExportControlAccess.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(ExportControlAccess.occurred_at <= until)
    stmt = stmt.order_by(ExportControlAccess.occurred_at.desc()).limit(limit)
    return (await session.execute(stmt)).scalars().all()


#: CSV column order — stable, because compliance officers diff these files.
CSV_COLUMNS = (
    "occurred_at",
    "action",
    "subject_type",
    "subject_id",
    "actor_user_id",
    "regime",
    "ip_address",
    "user_agent",
    "detail",
)


def to_csv(entries: Sequence[ExportControlAccess]) -> str:
    """Render log entries as the spec's Settings → "CUI Audit" CSV download.

    Timestamps are ISO-8601 UTC (CLAUDE.md §5), not locale-formatted: this is a
    machine-readable compliance artefact, not a German-locale display surface.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for entry in entries:
        writer.writerow(
            [
                entry.occurred_at.isoformat(),
                str(entry.action),
                str(entry.subject_type),
                str(entry.subject_id),
                str(entry.actor_user_id) if entry.actor_user_id else "",
                str(entry.regime),
                entry.ip_address or "",
                entry.user_agent or "",
                # Compact JSON so one entry stays one CSV row.
                _compact_json(entry.detail),
            ]
        )
    return buf.getvalue()


def _compact_json(detail: dict[str, Any]) -> str:
    import json

    return json.dumps(detail, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
