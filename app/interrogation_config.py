"""Configure -> Interrogations (M4.7) — the org's DFM profiles.

Serves the pinned warning catalogue (dfm.CATALOGUE — names, threshold fields,
seed defaults, v1/"v2-Spatial" flags) alongside the org's
``CustomInterrogation`` rows, and lets ``config_edit`` update a profile's
``inputs`` (thresholds + ``should_detect_*`` toggles).

Always-on enforcement (DFM-WARNINGS §Implementation 3) is structural: an
always-on warning has NO toggle key in the family's allowed-input set, so any
attempt to write one (e.g. ``should_detect_uncut_faces``) is rejected as an
unknown key — server-side, not a UI convention. Material-specific profile
binding and most-specific resolution are M4.8; M4.7 exposes the org defaults
seeded by ``configure_seed``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .geometry.dfm import CATALOGUE, WarningDef, dfm_default_inputs
from .models import CustomInterrogation

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
    inputs: dict[str, Any]


class InterrogationsConfigOut(BaseModel):
    catalog: list[FamilyCatalogOut]
    profiles: list[ProfileOut]


class ProfileUpdateIn(BaseModel):
    inputs: dict[str, Any]


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


@interrogation_config_router.get("/interrogations", response_model=InterrogationsConfigOut)
async def get_interrogations_config(
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InterrogationsConfigOut:
    profiles = (
        await session.scalars(select(CustomInterrogation).order_by(CustomInterrogation.family))
    ).all()
    return InterrogationsConfigOut(
        catalog=[
            FamilyCatalogOut(
                family=family,
                warnings=[_def_out(d) for d in defs],
                defaults=dfm_default_inputs(family),
            )
            for family, defs in CATALOGUE.items()
        ],
        profiles=[
            ProfileOut(id=p.id, name=p.name, family=p.family.value, inputs=p.inputs)
            for p in profiles
        ],
    )


@interrogation_config_router.put("/interrogations/{profile_id}", response_model=ProfileOut)
async def update_interrogation_profile(
    profile_id: uuid.UUID,
    body: ProfileUpdateIn,
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileOut:
    profile = await session.get(CustomInterrogation, profile_id)
    if profile is None:
        raise AppError(
            code="not_found", message="Interrogation profile not found.", status_code=404
        )
    profile.inputs = validate_profile_inputs(profile.family.value, body.inputs)
    await session.flush()
    return ProfileOut(
        id=profile.id, name=profile.name, family=profile.family.value, inputs=profile.inputs
    )
