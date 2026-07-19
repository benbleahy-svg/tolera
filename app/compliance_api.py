"""Compliance admin API (M6.9) — export-control regime + the "CUI Audit" export.

Two surfaces from the spec's Settings tree
(``#company-settings-detail`` → Company Settings):

* **Export-control regime** — ``#dach-delta``: "Export-control regime = config,
  not hardcoded". Read/write the org's :class:`~app.models.ExportRegime`.
* **CUI Audit** — the spec lists it verbatim as *"CUI Audit: download CSV
  (compliance log)"*. Served both as JSON (for a Settings table) and as the
  ``text/csv`` download the spec names.

Both gate on :attr:`~app.authz.Permission.compliance_manage`, which is
**admin-only**: the audit names every actor who touched a flagged record, and
``settings_edit`` reaches managers too.

Note the asymmetry with :mod:`app.gdpr`: reading a compliance log is not a
destructive act, so there is no confirmation ceremony here — but it is still not
a manager-level surface.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .export_control import list_access, to_csv
from .models import ExportControlAccess, ExportRegime, Organization

compliance_router = APIRouter(prefix="/api/settings/export-control", tags=["settings"])

#: Hard ceiling on one audit export. Not a silent cap: both responses report
#: whether they truncated (CLAUDE.md engineering rules — "no silent caps").
MAX_AUDIT_ROWS = 5000


class RegimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    export_regime: ExportRegime


class RegimeUpdate(BaseModel):
    export_regime: ExportRegime


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    occurred_at: datetime
    action: str
    subject_type: str
    subject_id: str
    actor_user_id: str | None
    regime: str
    ip_address: str | None
    user_agent: str | None
    detail: dict[str, Any]


class AuditPage(BaseModel):
    entries: list[AuditEntryOut]
    #: True when the ceiling clipped the result — the caller must narrow the
    #: window rather than assume it holds the whole log.
    truncated: bool
    limit: int


async def _org_or_404(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise AppError("not_found", "Organisation nicht gefunden.", status_code=404)
    return org


@compliance_router.get("", response_model=RegimeOut)
async def get_regime(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.compliance_manage))],
) -> RegimeOut:
    """The org's configured export-control regime."""
    org = await _org_or_404(session, principal.active_org_id)
    return RegimeOut.model_validate(org)


@compliance_router.put("", response_model=RegimeOut)
async def set_regime(
    payload: RegimeUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.compliance_manage))],
) -> RegimeOut:
    """Set the regime. Changing it never rewrites past audit entries — each entry
    denormalises the regime in force when it was written."""
    org = await _org_or_404(session, principal.active_org_id)
    org.export_regime = payload.export_regime
    # ``get_session`` is transaction-scoped and commits on exit — flush, never
    # commit, is the house convention (a commit here closes the caller's txn).
    await session.flush()
    return RegimeOut.model_validate(org)


async def _load(
    session: AsyncSession,
    principal: Principal,
    since: datetime | None,
    until: datetime | None,
) -> list[ExportControlAccess]:
    return list(
        await list_access(
            session,
            org_id=principal.active_org_id,
            since=since,
            until=until,
            # +1 so we can tell "exactly at the ceiling" from "clipped".
            limit=MAX_AUDIT_ROWS + 1,
        )
    )


@compliance_router.get("/audit", response_model=AuditPage)
async def get_audit(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.compliance_manage))],
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> AuditPage:
    """The compliance log as JSON, newest first."""
    rows = await _load(session, principal, since, until)
    truncated = len(rows) > MAX_AUDIT_ROWS
    return AuditPage(
        entries=[
            AuditEntryOut(
                id=str(row.id),
                occurred_at=row.occurred_at,
                action=str(row.action),
                subject_type=str(row.subject_type),
                subject_id=str(row.subject_id),
                actor_user_id=str(row.actor_user_id) if row.actor_user_id else None,
                regime=str(row.regime),
                ip_address=row.ip_address,
                user_agent=row.user_agent,
                detail=row.detail,
            )
            for row in rows[:MAX_AUDIT_ROWS]
        ],
        truncated=truncated,
        limit=MAX_AUDIT_ROWS,
    )


@compliance_router.get("/audit.csv", response_class=PlainTextResponse)
async def get_audit_csv(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.compliance_manage))],
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> PlainTextResponse:
    """The spec's Settings → "CUI Audit: download CSV (compliance log)"."""
    rows = await _load(session, principal, since, until)
    truncated = len(rows) > MAX_AUDIT_ROWS
    body = to_csv(rows[:MAX_AUDIT_ROWS])
    return PlainTextResponse(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="export-control-audit.csv"',
            # Surfaced in a header so a truncated download is never mistaken for
            # a complete compliance record.
            "X-Audit-Truncated": "true" if truncated else "false",
        },
    )
