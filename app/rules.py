"""Review-rules API (M3.6) — list + JSON import/export (spec ``#rules-schema``).

Surface (Configure → Rules; mutations need ``config_edit`` — rule building is
gated on the process-edit permission per RULES-ENGINE-SPEC §6 — reads
``view_all``):

* ``GET  /api/rules``          — list the org's rules (canonical fields +
  internal ``id``/``is_active``)
* ``GET  /api/rules/export``   — the whole set as ONE canonical JSON string
  (the portable, diffable paste-out)
* ``POST /api/rules/import``   — paste-in: validate the string against the
  canonical AST schema and upsert per ``uuid``. All-or-nothing: any invalid
  rule rejects the whole paste. Idempotent — re-importing an export is a
  byte-stable no-op.

``units``/``value_type`` are stored verbatim (normalization is the M3.7
evaluator's job); the AST itself is validated but never interpreted here.
"""

from __future__ import annotations

import uuid as uuid_mod
from typing import Annotated, Any

import pydantic
from fastapi import APIRouter, Depends
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import Rule
from .rules_schema import RuleSchema, parse_rules_json, serialize_rules

rules_router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid_mod.UUID
    uuid: uuid_mod.UUID
    name: str
    description: str
    logical_operator: str
    signals: list[dict[str, Any]]
    resolutions: list[dict[str, Any]]
    default_assignee_id: uuid_mod.UUID | None
    is_active: bool


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules_json: str


class ImportOut(BaseModel):
    created: int
    updated: int


class ExportOut(BaseModel):
    rules_json: str
    count: int


def _to_schema(row: Rule) -> RuleSchema:
    """Rebuild the canonical form from the persisted row (validated on the way
    in, so this cannot fail for stored data)."""
    return RuleSchema.model_validate(
        {
            "uuid": row.uuid,
            "name": row.name,
            "description": row.description,
            "logical_operator": row.logical_operator,
            "signals": row.signals,
            "resolutions": row.resolutions,
            "default_assignee_id": row.default_assignee_id,
        }
    )


@rules_router.get("", response_model=list[RuleOut])
async def list_rules(
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[RuleOut]:
    rows = (await session.execute(select(Rule).order_by(Rule.uuid))).scalars().all()
    return [
        RuleOut(
            id=row.id,
            uuid=row.uuid,
            name=row.name,
            description=row.description,
            logical_operator=row.logical_operator,
            signals=row.signals,
            resolutions=row.resolutions,
            default_assignee_id=row.default_assignee_id,
            is_active=row.is_active,
        )
        for row in rows
    ]


@rules_router.get("/export", response_model=ExportOut)
async def export_rules(
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExportOut:
    rows = (await session.execute(select(Rule))).scalars().all()
    schemas = [_to_schema(row) for row in rows]
    return ExportOut(rules_json=serialize_rules(schemas), count=len(schemas))


@rules_router.post("/import", response_model=ImportOut)
async def import_rules(
    payload: ImportIn,
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ImportOut:
    try:
        parsed = parse_rules_json(payload.rules_json)
    except pydantic.ValidationError as exc:
        raise AppError(
            code="invalid_rules_json",
            message="The pasted rules JSON does not match the canonical rule schema.",
            details=exc.errors(include_url=False, include_input=False),
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc
    except ValueError as exc:
        raise AppError(
            code="invalid_rules_json",
            message=str(exc),
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc

    # The same uuid twice in one paste would make the upsert order-dependent.
    seen: set[uuid_mod.UUID] = set()
    for rule in parsed:
        if rule.uuid in seen:
            raise AppError(
                code="invalid_rules_json",
                message=f"duplicate rule uuid in the pasted set: {rule.uuid}",
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        seen.add(rule.uuid)

    existing = {
        row.uuid: row
        for row in (
            (await session.execute(select(Rule).where(Rule.uuid.in_(seen)))).scalars()
            if seen
            else []
        )
    }
    created = updated = 0
    for rule in parsed:
        dumped = rule.model_dump(mode="json")
        row = existing.get(rule.uuid)
        if row is None:
            session.add(
                Rule(
                    org_id=principal.active_org_id,
                    uuid=rule.uuid,
                    name=rule.name,
                    description=rule.description,
                    logical_operator=rule.logical_operator,
                    signals=dumped["signals"],
                    resolutions=dumped["resolutions"],
                    default_assignee_id=rule.default_assignee_id,
                )
            )
            created += 1
        else:
            row.name = rule.name
            row.description = rule.description
            row.logical_operator = rule.logical_operator
            row.signals = dumped["signals"]
            row.resolutions = dumped["resolutions"]
            row.default_assignee_id = rule.default_assignee_id
            updated += 1
    await session.commit()
    return ImportOut(created=created, updated=updated)
