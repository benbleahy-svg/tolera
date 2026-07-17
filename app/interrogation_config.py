"""Configure -> Interrogations (M4.7/M4.8) — the org's DFM profiles.

Serves the pinned warning catalogue (dfm.CATALOGUE — names, threshold fields,
seed defaults, v1/"v2-Spatial" flags) alongside the org's
``CustomInterrogation`` rows, and lets ``config_edit`` author them: create
(inputs prefilled with the engine defaults, the KB ``custom-interrogations``
flow), update thresholds/toggles, bind to material class/family/material
and/or operation defs, delete (the seeded default is undeletable — PP keeps
the default interrogation "always available"). The most-specific resolution
over these rows lives in :mod:`app.interrogation`.

Always-on enforcement (DFM-WARNINGS §Implementation 3) is structural: an
always-on warning has NO toggle key in the family's allowed-input set, so any
attempt to write one (e.g. ``should_detect_uncut_faces``) is rejected as an
unknown key — server-side, not a UI convention.

The duplicate-dispatch ⚠️ (KB "Be careful with how you link your
interrogations...") is advisory: saving op-def links reports every other
same-family profile that is op-linked into a shared process — PP dispatches
one interrogation per applicable profile there, doubling wait times — but
never blocks the save.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .geometry.dfm import CATALOGUE, WarningDef, dfm_default_inputs
from .models import (
    CustomInterrogation,
    CustomInterrogationOperationDef,
    Material,
    MaterialClass,
    MaterialFamily,
    OperationDef,
    Process,
    ProcessFamily,
    ProcessOperation,
)

interrogation_config_router = APIRouter(prefix="/api/configure", tags=["interrogations-config"])


class WarningDefOut(BaseModel):
    type: str
    detects: str
    threshold_fields: list[str]
    toggle: str | None
    toggle_default: bool
    v1_supported: bool
    always_on: bool


class FamilyCatalogOut(BaseModel):
    family: str
    warnings: list[WarningDefOut]
    defaults: dict[str, Any]


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    family: str
    is_default: bool
    inputs: dict[str, Any]
    material_class_id: uuid.UUID | None
    material_family_id: uuid.UUID | None
    material_id: uuid.UUID | None
    operation_def_ids: list[uuid.UUID]


class DispatchWarningOut(BaseModel):
    """One advisory duplicate-dispatch finding (never blocks the save)."""

    code: str = "duplicate_dispatch"
    process_id: uuid.UUID
    process_name: str
    other_profile_id: uuid.UUID
    other_profile_name: str


class ProfileWithWarningsOut(ProfileOut):
    warnings: list[DispatchWarningOut] = Field(default_factory=list)


class InterrogationsConfigOut(BaseModel):
    catalog: list[FamilyCatalogOut]
    profiles: list[ProfileOut]


class ProfileCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    family: str
    #: Overrides onto the engine-default prefill (KB: a new interrogation
    #: starts with every task input at its default).
    inputs: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdateIn(BaseModel):
    """Partial update — only the provided fields change; an explicit null
    clears a material link (``model_fields_set`` distinguishes the two)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    inputs: dict[str, Any] | None = None
    material_class_id: uuid.UUID | None = None
    material_family_id: uuid.UUID | None = None
    material_id: uuid.UUID | None = None
    operation_def_ids: list[uuid.UUID] | None = None


def _def_out(d: WarningDef) -> WarningDefOut:
    return WarningDefOut(
        type=d.type,
        detects=d.detects,
        threshold_fields=list(d.threshold_fields),
        toggle=d.toggle,
        toggle_default=d.toggle_default,
        v1_supported=d.v1_supported,
        always_on=d.always_on,
    )


def validate_profile_inputs(family: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Whitelist + type-check a profile's inputs against the family catalogue.

    Unknown keys are rejected outright — that single rule is what makes the
    always-on warnings non-disableable (their toggles are not in the set).
    Thresholds must be positive finite numbers, toggles strict booleans.
    """
    allowed = dfm_default_inputs(family)
    cleaned: dict[str, Any] = {}
    for key, value in inputs.items():
        if key not in allowed:
            raise AppError(
                code="unknown_interrogation_input",
                message=f"'{key}' is not a configurable input for {family}.",
                status_code=422,
            )
        if isinstance(allowed[key], bool):
            if not isinstance(value, bool):
                raise AppError(
                    code="invalid_interrogation_input",
                    message=f"'{key}' must be a boolean.",
                    status_code=422,
                )
            cleaned[key] = value
        else:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise AppError(
                    code="invalid_interrogation_input",
                    message=f"'{key}' must be a number.",
                    status_code=422,
                )
            try:
                number = float(value)
            except OverflowError:  # a valid-but-astronomical JSON int -> 422, not 500
                number = float("inf")
            if not number > 0 or number != number or number in (float("inf"), float("-inf")):
                raise AppError(
                    code="invalid_interrogation_input",
                    message=f"'{key}' must be a positive finite number.",
                    status_code=422,
                )
            cleaned[key] = number
    return cleaned


async def _op_links(
    session: AsyncSession, profile_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    if not profile_ids:
        return {}
    rows = (
        await session.execute(
            select(
                CustomInterrogationOperationDef.custom_interrogation_id,
                CustomInterrogationOperationDef.operation_def_id,
            )
            .where(CustomInterrogationOperationDef.custom_interrogation_id.in_(profile_ids))
            .order_by(CustomInterrogationOperationDef.created_at)
        )
    ).all()
    links: dict[uuid.UUID, list[uuid.UUID]] = {}
    for profile_id, op_def_id in rows:
        links.setdefault(profile_id, []).append(op_def_id)
    return links


def _profile_out(profile: CustomInterrogation, op_def_ids: list[uuid.UUID]) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        family=profile.family.value,
        is_default=profile.is_default,
        inputs=profile.inputs,
        material_class_id=profile.material_class_id,
        material_family_id=profile.material_family_id,
        material_id=profile.material_id,
        operation_def_ids=op_def_ids,
    )


async def _get_profile_or_404(session: AsyncSession, profile_id: uuid.UUID) -> CustomInterrogation:
    profile = await session.get(CustomInterrogation, profile_id)
    if profile is None:
        raise AppError(
            code="not_found", message="Interrogation profile not found.", status_code=404
        )
    return profile


async def _check_unique_name(
    session: AsyncSession, name: str, exclude_id: uuid.UUID | None = None
) -> None:
    query = select(CustomInterrogation.id).where(CustomInterrogation.name == name)
    if exclude_id is not None:
        query = query.where(CustomInterrogation.id != exclude_id)
    if await session.scalar(query) is not None:
        raise AppError(
            code="duplicate_interrogation_name",
            message="A custom interrogation with this name already exists.",
            status_code=422,
        )


async def _duplicate_dispatch_warnings(
    session: AsyncSession, profile: CustomInterrogation, op_def_ids: list[uuid.UUID]
) -> list[DispatchWarningOut]:
    """KB custom-interrogations: two same-family profiles op-linked into one
    process make the system dispatch two interrogations of that type."""
    if not op_def_ids:
        return []
    shared_processes = (
        select(ProcessOperation.process_id)
        .join(OperationDef, OperationDef.id == ProcessOperation.operation_def_id)
        .where(
            ProcessOperation.operation_def_id.in_(op_def_ids),
            OperationDef.deleted_at.is_(None),
        )
    )
    rows = (
        await session.execute(
            select(CustomInterrogation.id, CustomInterrogation.name, Process.id, Process.name)
            .join(
                CustomInterrogationOperationDef,
                CustomInterrogationOperationDef.custom_interrogation_id == CustomInterrogation.id,
            )
            .join(
                ProcessOperation,
                ProcessOperation.operation_def_id
                == CustomInterrogationOperationDef.operation_def_id,
            )
            .join(
                OperationDef,
                OperationDef.id == CustomInterrogationOperationDef.operation_def_id,
            )
            .join(Process, Process.id == ProcessOperation.process_id)
            .where(
                CustomInterrogation.family == profile.family,
                CustomInterrogation.id != profile.id,
                ProcessOperation.process_id.in_(shared_processes),
                Process.deleted_at.is_(None),
                OperationDef.deleted_at.is_(None),
            )
            .distinct()
        )
    ).all()
    return [
        DispatchWarningOut(
            other_profile_id=other_id,
            other_profile_name=other_name,
            process_id=process_id,
            process_name=process_name,
        )
        for other_id, other_name, process_id, process_name in rows
    ]


@interrogation_config_router.get("/interrogations", response_model=InterrogationsConfigOut)
async def get_interrogations_config(
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InterrogationsConfigOut:
    profiles = (
        await session.scalars(
            select(CustomInterrogation).order_by(
                CustomInterrogation.family, CustomInterrogation.created_at
            )
        )
    ).all()
    links = await _op_links(session, [p.id for p in profiles])
    return InterrogationsConfigOut(
        catalog=[
            FamilyCatalogOut(
                family=family,
                warnings=[_def_out(d) for d in defs],
                defaults=dfm_default_inputs(family),
            )
            for family, defs in CATALOGUE.items()
        ],
        profiles=[_profile_out(p, links.get(p.id, [])) for p in profiles],
    )


@interrogation_config_router.post(
    "/interrogations", response_model=ProfileOut, status_code=status.HTTP_201_CREATED
)
async def create_interrogation_profile(
    body: ProfileCreateIn,
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileOut:
    if body.family not in CATALOGUE:
        raise AppError(
            code="unknown_family",
            message=f"family must be one of {', '.join(sorted(CATALOGUE))}.",
            status_code=422,
        )
    await _check_unique_name(session, body.name)
    overrides = validate_profile_inputs(body.family, body.inputs)
    inputs = {**dfm_default_inputs(body.family), **overrides}
    profile = CustomInterrogation(
        org_id=principal.active_org_id,
        name=body.name,
        family=ProcessFamily(body.family),
        inputs=inputs,
    )
    session.add(profile)
    await session.flush()
    return _profile_out(profile, [])


_MATERIAL_LINK_MODELS = {
    "material_class_id": MaterialClass,
    "material_family_id": MaterialFamily,
    "material_id": Material,
}


@interrogation_config_router.put(
    "/interrogations/{profile_id}", response_model=ProfileWithWarningsOut
)
async def update_interrogation_profile(
    profile_id: uuid.UUID,
    body: ProfileUpdateIn,
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileWithWarningsOut:
    profile = await _get_profile_or_404(session, profile_id)
    # The org default's rank-0 fallback slot is keyed on having no links —
    # binding it to a material or op would silently remove the fallback for
    # every other material (fresh-eyes review). Clearing (null) stays legal.
    wants_links = any(
        field in body.model_fields_set and getattr(body, field) is not None
        for field in _MATERIAL_LINK_MODELS
    ) or bool(body.operation_def_ids)
    if profile.is_default and wants_links:
        raise AppError(
            code="default_profile_unlinkable",
            message="The default interrogation profile cannot be linked to materials or"
            " operations — create a named profile for that.",
            status_code=422,
        )
    if "name" in body.model_fields_set and body.name is not None:
        await _check_unique_name(session, body.name, exclude_id=profile.id)
        profile.name = body.name
    if body.inputs is not None:
        # Merge, don't replace: a sparse PUT must never silently reset the
        # keys it omits to engine defaults — profiles stay full input sets
        # (create prefills them), and resetting a key = sending its default.
        overrides = validate_profile_inputs(profile.family.value, body.inputs)
        profile.inputs = {
            **dfm_default_inputs(profile.family.value),
            **profile.inputs,
            **overrides,
        }
    for field, model in _MATERIAL_LINK_MODELS.items():
        if field not in body.model_fields_set:
            continue
        link_id = getattr(body, field)
        if link_id is not None and await session.get(model, link_id) is None:
            # RLS scopes the lookup — another org's id looks nonexistent.
            raise AppError(
                code="unknown_material_link",
                message=f"{field} does not reference a material entry of this organization.",
                status_code=422,
            )
        setattr(profile, field, link_id)
    if body.operation_def_ids is not None:
        op_def_ids = list(dict.fromkeys(body.operation_def_ids))
        for op_def_id in op_def_ids:
            op_def = await session.get(OperationDef, op_def_id)
            if op_def is None or op_def.deleted_at is not None:
                raise AppError(
                    code="unknown_operation_def",
                    message="operation_def_ids references no live operation of this organization.",
                    status_code=422,
                )
        await session.execute(
            delete(CustomInterrogationOperationDef).where(
                CustomInterrogationOperationDef.custom_interrogation_id == profile.id
            )
        )
        for op_def_id in op_def_ids:
            session.add(
                CustomInterrogationOperationDef(
                    org_id=profile.org_id,
                    custom_interrogation_id=profile.id,
                    operation_def_id=op_def_id,
                )
            )
    await session.flush()
    links = await _op_links(session, [profile.id])
    op_def_ids = links.get(profile.id, [])
    warnings = await _duplicate_dispatch_warnings(session, profile, op_def_ids)
    base = _profile_out(profile, op_def_ids)
    return ProfileWithWarningsOut(**base.model_dump(), warnings=warnings)


@interrogation_config_router.delete(
    "/interrogations/{profile_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_interrogation_profile(
    profile_id: uuid.UUID,
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    profile = await _get_profile_or_404(session, profile_id)
    if profile.is_default:
        raise AppError(
            code="default_profile_undeletable",
            message="The seeded default interrogation profile cannot be deleted.",
            status_code=422,
        )
    await session.delete(profile)  # op-def links cascade (migration 0032)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
