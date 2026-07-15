"""Found-in-Files actions on Lens findings (M3.2 — spec ``#wingman`` §3,
``#lens-accept``; AI-LENS-ENGINE §4/§7).

The AI-Governor write path: a finding is a *suggestion* until the explicit
human action lands here — **accept** (optionally filling the matching part
field in the same transaction, so status and field can never diverge),
**reject** (= "Mark as inaccurate", a false-positive label), **replace**
(wrong-value label) and **add-missing** (false-negative label). Reject /
replace / add-missing each persist one ``extraction_correction`` row with the
``{predicted, corrected}`` pair + source region — per-tenant training data
(DECISIONS.md 2026-07-15). Nothing here touches costing: an accepted identity
or dimension write is exactly the M1.5/M1.7 manual-entry path, human-confirmed
(CLAUDE.md §5 — Lens is never auto-fed into Kalk).
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from functools import partial
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .dimensions import DimensionError, evaluate_length
from .errors import AppError
from .lens_extract import FindingOut, _get_part_and_file_or_404
from .models import (
    CorrectionType,
    ExtractionCorrection,
    ExtractionFinding,
    FindingCategory,
    FindingStatus,
    Part,
)
from .parts import _apply_dim, _get_or_create_geometry

findings_router = APIRouter(prefix="/api/parts", tags=["lens"])

# Click-to-fill targets (spec #wingman §2 NUM/REV click-fill; AI-LENS §4
# "apply part#/rev/desc; set X/Y/Z from dims").
ApplyTarget = Literal["part_number", "revision", "description", "size_x", "size_y", "size_z"]
_IDENTITY_TARGETS: dict[str, str] = {
    "part_number": "part_number",
    "revision": "revision",
    "description": "description",
}
_AXIS_TARGETS = ("size_x", "size_y", "size_z")


class AcceptIn(BaseModel):
    """``apply_to`` picks the fill target; omitted, it derives from the finding
    type (identity types self-target; a dimension needs its axis named)."""

    model_config = ConfigDict(extra="forbid")

    apply_to: ApplyTarget | None = None


class ReplaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    normalized_value: str | None = None
    units: str | None = None


class AddMissingIn(BaseModel):
    """A callout Lens missed — typed by the user, optionally with the drawn
    region (page + bbox in the unrotated pdf-unit convention)."""

    model_config = ConfigDict(extra="forbid")

    category: FindingCategory
    type: str = Field(min_length=1)
    value: str | None = None
    raw_text: str | None = None
    normalized_value: str | None = None
    units: str | None = None
    tolerance: dict[str, Any] | None = None
    role: str | None = None
    gdt: dict[str, Any] | None = None
    page: int | None = None
    bbox: dict[str, Any] | None = None


class FindingActionOut(BaseModel):
    finding: FindingOut
    applied_field: str | None = None


class CorrectionOut(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID | None
    source_file_id: uuid.UUID | None
    correction_type: str
    predicted: dict[str, Any] | None
    corrected: dict[str, Any] | None
    page: int | None
    bbox: dict[str, Any] | None


def _finding_out(row: ExtractionFinding) -> FindingOut:
    return FindingOut(
        id=row.id,
        source_file_id=row.source_file_id,
        component_id=row.component_id,
        page=row.page,
        category=row.category.value,
        type=row.type,
        raw_text=row.raw_text,
        value=row.value,
        normalized_value=row.normalized_value,
        units=row.units,
        tolerance=row.tolerance,
        role=row.role,
        gdt=row.gdt,
        bbox=row.bbox,
        confidence=float(row.confidence),
        status=row.status.value,
    )


def _predicted_snapshot(row: ExtractionFinding) -> dict[str, Any]:
    """The finding as the model emitted it — the durable half of the training
    pair (survives the finding row itself; see the 0021 SET NULL)."""
    return {
        "category": row.category.value,
        "type": row.type,
        "raw_text": row.raw_text,
        "value": row.value,
        "normalized_value": row.normalized_value,
        "units": row.units,
        "tolerance": row.tolerance,
        "role": row.role,
        "gdt": row.gdt,
        "confidence": float(row.confidence),
    }


async def _get_finding_or_404(
    session: AsyncSession, part_id: uuid.UUID, file_id: uuid.UUID, finding_id: uuid.UUID
) -> ExtractionFinding:
    """Resolve a finding through its file: the org gate (RLS + org-scoped file
    lookup) runs first, and the finding must belong to the addressed file —
    same 404 for cross-org, unknown and misaddressed ids."""
    await _get_part_and_file_or_404(session, part_id, file_id)
    finding = await session.get(ExtractionFinding, finding_id, with_for_update=True)
    if finding is None or finding.source_file_id != file_id:
        raise AppError("not_found", "Finding not found.", status_code=status.HTTP_404_NOT_FOUND)
    return finding


def _resolve_apply_target(finding: ExtractionFinding, apply_to: ApplyTarget | None) -> str | None:
    """Which field this accept fills, or None for a plain acknowledge.

    Explicit targets are validated against the finding (a part_number can't
    land in size_x); a bare accept derives the target from the type — and a
    dimension finding, having three possible axes, must name one (422).
    """
    if apply_to is None:
        if finding.type in _IDENTITY_TARGETS:
            return _IDENTITY_TARGETS[finding.type]
        if finding.category is FindingCategory.dimensions:
            raise AppError(
                "apply_target_required",
                "Eine Bemaßung braucht eine Zielachse (size_x/size_y/size_z).",
                status_code=422,
            )
        return None
    if apply_to in _IDENTITY_TARGETS:
        if finding.type != apply_to:
            raise AppError(
                "apply_mismatch",
                f"Ein Fund vom Typ '{finding.type}' kann nicht nach '{apply_to}' "
                "übernommen werden.",
                status_code=422,
            )
        return apply_to
    # Axis target: only a dimension finding carries a fillable length.
    if finding.category is not FindingCategory.dimensions:
        raise AppError(
            "apply_mismatch",
            f"Ein Fund vom Typ '{finding.type}' kann nicht nach '{apply_to}' übernommen werden.",
            status_code=422,
        )
    return apply_to


async def _apply_to_part(
    session: AsyncSession, part: Part, finding: ExtractionFinding, target: str
) -> None:
    """Write the accepted value where it belongs — the same paths the manual
    editors use (PATCH part / PATCH geometry), so calc-vs-override and the
    metric-storage contract hold identically."""
    value = finding.normalized_value or finding.value
    if value is None:
        raise AppError("empty_value", "Der Fund enthält keinen Wert.", status_code=422)
    if target in _IDENTITY_TARGETS:
        setattr(part, target, value)
        return
    # Geometry axis: evaluate with the finding's unit as default (mm fallback,
    # DACH) — stored metric, override provenance recorded (parts._apply_dim).
    unit = finding.units if finding.units in ("mm", "in") else "mm"
    geom = await _get_or_create_geometry(session, part)
    overrides = dict(geom.overrides or {})
    try:
        _apply_dim(
            geom, overrides, target, value, partial(evaluate_length, default_unit=unit), unit
        )
    except DimensionError as exc:
        raise AppError("invalid_dimension", str(exc), status_code=422) from exc
    geom.overrides = overrides


@findings_router.post("/{part_id}/files/{file_id}/findings/{finding_id}/accept")
async def accept_finding(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    finding_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
    payload: AcceptIn | None = None,
) -> FindingActionOut:
    """Explicit Accept: flip the suggestion to ``accepted`` and fill the target
    part field — one transaction, so the two can never diverge. Idempotent on
    an already-accepted finding; a rejected one is gone from the panel (409)."""
    finding = await _get_finding_or_404(session, part_id, file_id, finding_id)
    if finding.status is FindingStatus.rejected:
        raise AppError(
            "invalid_status",
            "Ein als ungenau markierter Fund kann nicht übernommen werden.",
            status_code=status.HTTP_409_CONFLICT,
        )
    target = _resolve_apply_target(finding, payload.apply_to if payload else None)
    if target is not None:
        part = await session.get(Part, part_id, with_for_update=True)
        assert part is not None  # gated by _get_finding_or_404
        await _apply_to_part(session, part, finding, target)
    if finding.status is FindingStatus.suggested:
        finding.status = FindingStatus.accepted
    await session.flush()
    return FindingActionOut(finding=_finding_out(finding), applied_field=target)


@findings_router.post("/{part_id}/files/{file_id}/findings/{finding_id}/reject")
async def reject_finding(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    finding_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> FindingActionOut:
    """ "Mark as inaccurate": remove the wrong finding and persist the
    false-positive label. Idempotent — a second reject adds no second label."""
    finding = await _get_finding_or_404(session, part_id, file_id, finding_id)
    if finding.status is not FindingStatus.rejected:
        session.add(
            ExtractionCorrection(
                id=uuid.uuid4(),
                org_id=principal.active_org_id,
                finding_id=finding.id,
                source_file_id=file_id,
                correction_type=CorrectionType.mark_inaccurate,
                predicted=_predicted_snapshot(finding),
                corrected=None,
                page=finding.page,
                bbox=finding.bbox,
                created_by=principal.user_id,
            )
        )
        finding.status = FindingStatus.rejected
        await session.flush()
    return FindingActionOut(finding=_finding_out(finding))


@findings_router.post("/{part_id}/files/{file_id}/findings/{finding_id}/replace")
async def replace_finding(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: ReplaceIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> FindingActionOut:
    """The user supplies the right value: persist the ``{predicted, corrected}``
    pair, then edit the finding in place (status ``edited`` — survives re-runs)."""
    finding = await _get_finding_or_404(session, part_id, file_id, finding_id)
    if finding.status is FindingStatus.rejected:
        raise AppError(
            "invalid_status",
            "Ein als ungenau markierter Fund kann nicht ersetzt werden.",
            status_code=status.HTTP_409_CONFLICT,
        )
    corrected = payload.model_dump(exclude_none=True)
    session.add(
        ExtractionCorrection(
            id=uuid.uuid4(),
            org_id=principal.active_org_id,
            finding_id=finding.id,
            source_file_id=file_id,
            correction_type=CorrectionType.replace,
            predicted=_predicted_snapshot(finding),
            corrected=corrected,
            page=finding.page,
            bbox=finding.bbox,
            created_by=principal.user_id,
        )
    )
    finding.value = payload.value
    finding.normalized_value = payload.normalized_value
    if payload.units is not None:
        finding.units = payload.units
    finding.status = FindingStatus.edited
    await session.flush()
    return FindingActionOut(finding=_finding_out(finding))


@findings_router.post("/{part_id}/files/{file_id}/findings", status_code=status.HTTP_201_CREATED)
async def add_missing_finding(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: AddMissingIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> FindingOut:
    """ "Add missing extraction": the false-negative label. The typed callout
    becomes a real finding — born ``accepted`` at confidence 1 (human ground
    truth: the M3.1 replace-suggested re-run can never wipe it)."""
    await _get_part_and_file_or_404(session, part_id, file_id)
    finding = ExtractionFinding(
        id=uuid.uuid4(),
        org_id=principal.active_org_id,
        source_file_id=file_id,
        page=payload.page,
        category=payload.category,
        type=payload.type,
        raw_text=payload.raw_text,
        value=payload.value,
        normalized_value=payload.normalized_value,
        units=payload.units,
        tolerance=payload.tolerance,
        role=payload.role,
        gdt=payload.gdt,
        bbox=payload.bbox,
        confidence=Decimal("1").quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        status=FindingStatus.accepted,
    )
    session.add(finding)
    # Flush the finding first: the correction FKs it, and with no ORM
    # relationship between the two mappers the unit of work won't order the
    # inserts itself.
    await session.flush()
    session.add(
        ExtractionCorrection(
            id=uuid.uuid4(),
            org_id=principal.active_org_id,
            finding_id=finding.id,
            source_file_id=file_id,
            correction_type=CorrectionType.add_missing,
            predicted=None,
            corrected=payload.model_dump(exclude_none=True),
            page=payload.page,
            bbox=payload.bbox,
            created_by=principal.user_id,
        )
    )
    await session.flush()
    return _finding_out(finding)


@findings_router.get("/{part_id}/files/{file_id}/corrections")
async def list_corrections(
    part_id: uuid.UUID,
    file_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CorrectionOut]:
    """The file's training labels — read surface for QA and the M3.11 eval
    harness. Org-scoped via RLS (per-tenant storage, never cross-org)."""
    await _get_part_and_file_or_404(session, part_id, file_id)
    rows = (
        (
            await session.execute(
                select(ExtractionCorrection)
                .where(ExtractionCorrection.source_file_id == file_id)
                .order_by(ExtractionCorrection.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        CorrectionOut(
            id=row.id,
            finding_id=row.finding_id,
            source_file_id=row.source_file_id,
            correction_type=row.correction_type.value,
            predicted=row.predicted,
            corrected=row.corrected,
            page=row.page,
            bbox=row.bbox,
        )
        for row in rows
    ]
