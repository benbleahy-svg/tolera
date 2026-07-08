"""Idempotent per-org material catalog + Core-4 process seed (M1.7).

The nested material picker needs a browsable Class → Family → Material tree from
day one, so provisioning seeds the **Metall** class with the 11 hubs.com-derived
CNC metal families and their standard DIN/EN variants (DECISIONS.md 2026-07-07
"M1.7 material catalog content"; `SEED-AND-FIXTURES.md` Part 1 §2 mirrors this).
M1.12 extends the same seed with the remaining classes (Polymer, Holz, Sonstige, …),
the 54-op library and full process templates.

Conventions (DACH-DELTA §4): German-first family display names with the English/
hubs name as ``alias``; materials keyed Werkstoffnummer + EN short name + AISI
alias; ``density`` in g/cm³ (standard published values). **No costs are seeded** —
``cost_per_volume``/``cost_per_area`` stay NULL until the shop configures rates
(the M1.14 missing-rates guard flags exactly this state).

Idempotency follows ``app.crm_seed``: natural-key match (class/family/material
names per org) then insert-or-reconcile, sequential provisioning only. Runs on the
owner connection (bypasses RLS); the explicit ``org_id`` scopes every write.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Material, MaterialClass, MaterialFamily, Process

METAL_CLASS_NAME = "Metall"

# One material variant: (display, wnr, en_name, aisi, density g/cm3).
_Variant = tuple[str, str | None, str | None, str | None, str]

# (German display name, English/hubs alias, variants). Variants are the standard
# DIN EN designations for each family's common CNC grades (hubs.com subpage sets,
# keyed to DIN/EN per the 2026-07-07 decision — not a scrape).
_METAL_FAMILIES: list[tuple[str, str, list[_Variant]]] = [
    (
        "Aluminium",
        "Aluminum",
        [
            ("EN AW-6061", "3.3211", "AlMg1SiCu", "6061", "2.70"),
            ("EN AW-6082", "3.2315", "AlSi1MgMn", "6082", "2.70"),
            ("EN AW-7075", "3.4365", "AlZn5.5MgCu", "7075", "2.81"),
            ("EN AW-5083", "3.3547", "AlMg4.5Mn0.7", "5083", "2.66"),
        ],
    ),
    (
        "Nichtrostender Stahl",
        "Stainless steel",
        [
            ("1.4301", "1.4301", "X5CrNi18-10", "304", "7.90"),
            ("1.4307", "1.4307", "X2CrNi18-9", "304L", "7.90"),
            ("1.4401", "1.4401", "X5CrNiMo17-12-2", "316", "8.00"),
            ("1.4404", "1.4404", "X2CrNiMo17-12-2", "316L", "8.00"),
            ("1.4305", "1.4305", "X8CrNiS18-9", "303", "7.90"),
            ("1.4021", "1.4021", "X20Cr13", "420", "7.70"),
            ("1.4462", "1.4462", "X2CrNiMoN22-5-3", "2205", "7.80"),
        ],
    ),
    (
        "Baustahl",
        "Mild steel",
        [
            ("S235JR", "1.0038", "S235JR", "A36", "7.85"),
            ("S355J2", "1.0570", "S355J2", None, "7.85"),
            ("C45", "1.0503", "C45", "1045", "7.85"),
            ("C15E", "1.1141", "C15E", "1018", "7.85"),
        ],
    ),
    (
        "Legierter Stahl",
        "Alloy steel",
        [
            ("42CrMo4", "1.7225", "42CrMo4", "4140", "7.85"),
            ("36CrNiMo4", "1.6511", "36CrNiMo4", "4340", "7.85"),
            ("16MnCr5", "1.7131", "16MnCr5", "5115", "7.85"),
        ],
    ),
    (
        "Werkzeugstahl",
        "Tool steel",
        [
            ("X153CrMoV12", "1.2379", "X153CrMoV12", "D2", "7.70"),
            ("X100CrMoV5", "1.2363", "X100CrMoV5", "A2", "7.70"),
            ("100MnCrW4", "1.2510", "100MnCrW4", "O1", "7.85"),
            ("X40CrMoV5-1", "1.2344", "X40CrMoV5-1", "H13", "7.80"),
        ],
    ),
    (
        "Messing",
        "Brass",
        [
            ("CuZn39Pb3", "2.0401", "CuZn39Pb3", None, "8.47"),
            ("CuZn37", "2.0321", "CuZn37", None, "8.44"),
        ],
    ),
    (
        "Bronze",
        "Bronze",
        [
            ("CuSn8", "2.1030", "CuSn8", "C52100", "8.80"),
            ("CuSn7Zn4Pb7", "2.1090", "CuSn7Zn4Pb7", "C93200", "8.80"),
        ],
    ),
    (
        "Kupfer",
        "Copper",
        [
            ("Cu-ETP", "2.0060", "Cu-ETP", "C11000", "8.94"),
            ("Cu-OF", "2.0040", "Cu-OF", "C10200", "8.94"),
        ],
    ),
    (
        "Titan",
        "Titanium",
        [
            ("Ti Grade 2", "3.7035", "Ti Grade 2", None, "4.51"),
            ("Ti6Al4V (Grade 5)", "3.7164", "Ti6Al4V", None, "4.43"),
        ],
    ),
    (
        "Inconel",
        "Inconel",
        [
            ("Inconel 718", "2.4668", "NiCr19Fe19Nb5Mo3", "718", "8.19"),
            ("Inconel 625", "2.4856", "NiCr22Mo9Nb", "625", "8.44"),
        ],
    ),
    (
        "Invar",
        "Invar 36",
        [
            ("Invar 36", "1.3912", "Ni36", "36", "8.05"),
        ],
    ),
]

#: Core-4 process names (SEED §4). M1.7 seeds the bare entities so "Change
#: Process" has real targets; templates/routers/interrogations arrive with M1.12.
CORE_PROCESS_NAMES = ("Sheet Metal", "Milling", "Lathe", "Tube Laser")


@dataclass(frozen=True)
class CatalogSeedResult:
    """Outcome counts of one org's catalog seed (idempotent: created counts are 0
    on a re-run)."""

    classes_created: int
    families_created: int
    materials_created: int
    processes_created: int


async def seed_material_catalog(session: AsyncSession, *, org_id: uuid.UUID) -> CatalogSeedResult:
    """Seed (or reconcile) the Metall tree + Core-4 processes for one org."""
    classes_created = families_created = materials_created = processes_created = 0

    metal = await session.scalar(
        select(MaterialClass).where(
            MaterialClass.org_id == org_id, MaterialClass.name == METAL_CLASS_NAME
        )
    )
    if metal is None:
        metal = MaterialClass(org_id=org_id, name=METAL_CLASS_NAME, position=0)
        session.add(metal)
        await session.flush()
        classes_created += 1

    existing_families = {
        family.name: family
        for family in (
            await session.scalars(
                select(MaterialFamily).where(
                    MaterialFamily.org_id == org_id, MaterialFamily.class_id == metal.id
                )
            )
        ).all()
    }
    for position, (name, alias, variants) in enumerate(_METAL_FAMILIES):
        family = existing_families.get(name)
        if family is None:
            family = MaterialFamily(
                org_id=org_id, class_id=metal.id, name=name, alias=alias, position=position
            )
            session.add(family)
            await session.flush()
            families_created += 1
        elif family.alias != alias or family.position != position:
            family.alias = alias
            family.position = position

        existing_materials = {
            material.display_name
            for material in (
                await session.scalars(
                    select(Material).where(
                        Material.org_id == org_id, Material.family_id == family.id
                    )
                )
            ).all()
        }
        for display, wnr, en_name, aisi, density in variants:
            if display in existing_materials:
                continue
            session.add(
                Material(
                    org_id=org_id,
                    family_id=family.id,
                    display_name=display,
                    werkstoffnummer=wnr,
                    en_name=en_name,
                    aisi_alias=aisi,
                    density=Decimal(density),
                )
            )
            materials_created += 1

    existing_processes = {
        process.name
        for process in (
            await session.scalars(select(Process).where(Process.org_id == org_id))
        ).all()
    }
    for name in CORE_PROCESS_NAMES:
        if name in existing_processes:
            continue
        session.add(Process(org_id=org_id, name=name))
        processes_created += 1

    await session.flush()
    return CatalogSeedResult(
        classes_created=classes_created,
        families_created=families_created,
        materials_created=materials_created,
        processes_created=processes_created,
    )
