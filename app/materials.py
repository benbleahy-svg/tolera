"""Materials catalog + processes API (M1.7, spec ``#partview`` Materials).

The nested material picker reads the org's Class → Family → Material tree
(``GET /api/materials/tree``) and type-ahead searches hierarchical paths
(``GET /api/materials?q=`` — "Metall / Aluminium / EN AW-6061", matching German
names, aliases, Werkstoffnummer, EN name and AISI alias, case-insensitive
substring per the ``#oplibrary`` picker behaviour). "Edit Material Properties"
edits the org-library row (``PATCH``); estimators can add a custom material to a
family on the fly (``POST``). Class/family management UI is M1.12 — the tree is
seed-provisioned here.

Reads need an authenticated org session (``view_all``); library writes are
``config_edit`` (they change org pricing config, not one quote)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import Material, MaterialClass, MaterialFamily, Process

materials_router = APIRouter(prefix="/api", tags=["materials"])

#: Type-ahead result page — the picker shows a bounded list (search-to-narrow).
SEARCH_LIMIT = 50


class MaterialOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    display_name: str
    werkstoffnummer: str | None
    en_name: str | None
    aisi_alias: str | None
    density: Decimal | None
    cost_per_volume: Decimal | None
    cost_per_area: Decimal | None
    added_lead_time_days: int


class MaterialSearchHit(MaterialOut):
    """A search hit carries the hierarchical path the picker renders
    ("Metall / Aluminium / EN AW-6061")."""

    class_name: str
    family_name: str
    path: str


class FamilyNode(BaseModel):
    id: uuid.UUID
    name: str
    alias: str | None
    materials: list[MaterialOut]


class ClassNode(BaseModel):
    id: uuid.UUID
    name: str
    families: list[FamilyNode]


class MaterialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: uuid.UUID
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    werkstoffnummer: Annotated[str | None, Field(max_length=50)] = None
    en_name: Annotated[str | None, Field(max_length=100)] = None
    aisi_alias: Annotated[str | None, Field(max_length=50)] = None
    density: Annotated[Decimal | None, Field(gt=0)] = None
    cost_per_volume: Annotated[Decimal | None, Field(ge=0)] = None
    cost_per_area: Annotated[Decimal | None, Field(ge=0)] = None
    added_lead_time_days: Annotated[int, Field(ge=0)] = 0


class MaterialUpdate(BaseModel):
    """Edit Material Properties — partial update; absent fields stay untouched.
    ``display_name`` renames; costs/density/lead-time are the editable properties."""

    model_config = ConfigDict(extra="forbid")

    display_name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    werkstoffnummer: Annotated[str | None, Field(max_length=50)] = None
    en_name: Annotated[str | None, Field(max_length=100)] = None
    aisi_alias: Annotated[str | None, Field(max_length=50)] = None
    density: Annotated[Decimal | None, Field(gt=0)] = None
    cost_per_volume: Annotated[Decimal | None, Field(ge=0)] = None
    cost_per_area: Annotated[Decimal | None, Field(ge=0)] = None
    added_lead_time_days: Annotated[int | None, Field(ge=0)] = None


class ProcessOut(BaseModel):
    id: uuid.UUID
    name: str
    external_name: str | None


def _material_out(material: Material) -> MaterialOut:
    return MaterialOut(
        id=material.id,
        family_id=material.family_id,
        display_name=material.display_name,
        werkstoffnummer=material.werkstoffnummer,
        en_name=material.en_name,
        aisi_alias=material.aisi_alias,
        density=material.density,
        cost_per_volume=material.cost_per_volume,
        cost_per_area=material.cost_per_area,
        added_lead_time_days=material.added_lead_time_days,
    )


@materials_router.get("/materials/tree")
async def material_tree(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[ClassNode]:
    """The full nested-picker tree, ordered by seeded position then name."""
    classes = (
        await session.scalars(
            select(MaterialClass).order_by(MaterialClass.position, MaterialClass.name)
        )
    ).all()
    families = (
        await session.scalars(
            select(MaterialFamily).order_by(MaterialFamily.position, MaterialFamily.name)
        )
    ).all()
    materials = (await session.scalars(select(Material).order_by(Material.display_name))).all()

    material_nodes: dict[uuid.UUID, list[MaterialOut]] = {}
    for material in materials:
        material_nodes.setdefault(material.family_id, []).append(_material_out(material))
    family_nodes: dict[uuid.UUID, list[FamilyNode]] = {}
    for family in families:
        family_nodes.setdefault(family.class_id, []).append(
            FamilyNode(
                id=family.id,
                name=family.name,
                alias=family.alias,
                materials=material_nodes.get(family.id, []),
            )
        )
    return [
        ClassNode(id=cls.id, name=cls.name, families=family_nodes.get(cls.id, []))
        for cls in classes
    ]


@materials_router.get("/materials")
async def search_materials(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> list[MaterialSearchHit]:
    """Type-ahead over hierarchical paths (case-insensitive substring; the spec's
    "Material is a type-ahead over hierarchical paths (Metal / Aluminum / …)")."""
    pattern = f"%{q}%"
    rows = (
        await session.execute(
            select(Material, MaterialFamily, MaterialClass)
            .join(MaterialFamily, Material.family_id == MaterialFamily.id)
            .join(MaterialClass, MaterialFamily.class_id == MaterialClass.id)
            .where(
                or_(
                    Material.display_name.ilike(pattern),
                    Material.werkstoffnummer.ilike(pattern),
                    Material.en_name.ilike(pattern),
                    Material.aisi_alias.ilike(pattern),
                    MaterialFamily.name.ilike(pattern),
                    MaterialFamily.alias.ilike(pattern),
                    MaterialClass.name.ilike(pattern),
                )
            )
            .order_by(MaterialClass.name, MaterialFamily.name, Material.display_name)
            .limit(SEARCH_LIMIT)
        )
    ).all()
    return [
        MaterialSearchHit(
            **_material_out(material).model_dump(),
            class_name=cls.name,
            family_name=family.name,
            path=f"{cls.name} / {family.name} / {material.display_name}",
        )
        for material, family, cls in rows
    ]


@materials_router.post("/materials", status_code=status.HTTP_201_CREATED)
async def create_material(
    payload: MaterialCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> MaterialOut:
    family = await session.get(MaterialFamily, payload.family_id)
    if family is None:
        raise AppError(
            "not_found", "Material family not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    duplicate = await session.scalar(
        select(Material.id).where(
            Material.family_id == family.id, Material.display_name == payload.display_name
        )
    )
    if duplicate is not None:
        raise AppError(
            "duplicate_material",
            "A material with this name already exists in the family.",
            status_code=status.HTTP_409_CONFLICT,
        )
    material = Material(org_id=principal.active_org_id, **payload.model_dump())
    session.add(material)
    await session.flush()
    return _material_out(material)


@materials_router.patch("/materials/{material_id}")
async def update_material(
    material_id: uuid.UUID,
    payload: MaterialUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> MaterialOut:
    """Edit Material Properties (org-library row; RLS scopes the lookup)."""
    material = await session.get(Material, material_id)
    if material is None:
        raise AppError("not_found", "Material not found.", status_code=status.HTTP_404_NOT_FOUND)
    changes = payload.model_dump(exclude_unset=True)
    if "display_name" in changes:
        duplicate = await session.scalar(
            select(Material.id).where(
                Material.family_id == material.family_id,
                Material.display_name == changes["display_name"],
                Material.id != material.id,
            )
        )
        if duplicate is not None:
            raise AppError(
                "duplicate_material",
                "A material with this name already exists in the family.",
                status_code=status.HTTP_409_CONFLICT,
            )
    for field, value in changes.items():
        setattr(material, field, value)
    await session.flush()
    return _material_out(material)


@materials_router.get("/processes")
async def list_processes(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[ProcessOut]:
    """Live processes (Change Process targets). Templates/routers arrive M1.12/M4."""
    processes = (
        await session.scalars(
            select(Process).where(Process.deleted_at.is_(None)).order_by(Process.name)
        )
    ).all()
    return [
        ProcessOut(id=process.id, name=process.name, external_name=process.external_name)
        for process in processes
    ]
