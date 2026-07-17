"""Idempotent per-org Configure seed (M1.12) — SEED-AND-FIXTURES Part 1 §2-§7.

Extends the M1.7 material/process seed (``app.catalog_seed``) with everything
else the pricing engine quotes against:

* **§2** — the non-metal material classes (Kunststoff with POM/PA6/PEEK
  leaves, Verbundwerkstoff, Sand, Wachs, Additiv, plus Holz and Sonstige per
  DECISIONS.md 2026-07-07 "Foreign materials"). The Metall tree stays
  M1.7-owned.
* **§3** — the 54-op German library from spec ``#oplibrary`` (the numbered
  tables are authoritative: rows 1-32 machine_plus_operator, 33-54
  labour_only), plus the §3/§4 router-support entries (material lines,
  PC piece price, assembly/shipping-prep, hardware insert, outside service,
  engineering). ``is_pre_installed=true``; **rates stay NULL** — the spec is
  explicit: "Rates are not pre-seeded — every shop configures their own."
* **§4** — Core-4 router templates (``process_operation`` rows) +
  ``Assembly | Parent-Level`` + the default purchased-component process.
* **§6** — pricing defaults: Standardaufschlag, the Zuschlagskalkulation
  items (spec ``#zuschlagskalkulation`` / ``#dach-costing`` — seeded when
  DACH Costing Mode is on, which DACH orgs are provisioned with), a sample
  Kalk volume discount, the six ``#addons`` AddOnType defs, and the org's
  default expedite tiers.
* **§7 partial** — workflow steps, the three example custom tables, German
  email templates. The starter rule library waits for M3's rules engine.

Idempotency follows ``app.catalog_seed``: natural-key match per org, then
insert-or-reconcile. Re-seeding never overwrites user edits — existing rows
keep their configured rates/percentages ("Defaults are starting points, not
prescriptions"). Runs on the owner connection; ``org_id`` scopes every write.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AddOnDef,
    CalcType,
    CalculationMode,
    CostCategory,
    CustomInterrogation,
    CustomTable,
    DiscountDef,
    EmailTemplate,
    Material,
    MaterialClass,
    MaterialFamily,
    OpCategory,
    OperationDef,
    Organization,
    PricingItemDef,
    Process,
    ProcessFamily,
    ProcessOperation,
    Rule,
    WorkflowStepDef,
)
from app.rules_schema import RuleSchema

# ---------------------------------------------------------------------------
# §2 — non-metal classes (German-first; Metall is M1.7's)
# ---------------------------------------------------------------------------
# (class name, position). Metall holds position 0 from M1.7.
_EXTRA_CLASSES: tuple[tuple[str, int], ...] = (
    ("Kunststoff", 1),
    ("Verbundwerkstoff", 2),
    ("Sand", 3),
    ("Wachs", 4),
    ("Additiv", 5),
    ("Holz", 6),
    ("Sonstige", 7),
)

# The §2 polymers as leaves under Kunststoff (standard densities, costs NULL).
_POLYMER_FAMILY = ("Thermoplaste", "Polymers")
_POLYMERS: tuple[tuple[str, str], ...] = (  # (display name, density g/cm3)
    ("POM", "1.41"),
    ("PA6", "1.14"),
    ("PEEK", "1.32"),
)

# ---------------------------------------------------------------------------
# §3 — the 54-op German library (spec #oplibrary, numbered tables verbatim)
# ---------------------------------------------------------------------------
_MACHINE_OPERATOR_OPS: tuple[str, ...] = (
    "Fräsen/Drehen",
    "Fräsen",
    "Drehen",
    "Bohren",
    "Senken",
    "Schleifen 1",
    "Schleifen 2",
    "Honen",
    "Zerspanen",
    "Sägen/Schneiden",
    "Auf Gehrung",
    "V-Cut",
    "Kanten",
    "Biegen",
    "Walzen",
    "Richten",
    "Verformen",
    "Strahlen",
    "Bürsten",
    "Gewindefräsen",
    "Verzahnen",
    "Laserschneiden Blech",
    "Laserschneiden Rohr",
    "Plasmaschneiden",
    "Brennschneiden",
    "Wasserstrahlschneiden",
    "Erodieren Senk",
    "Drahterodieren",
    "Punktschweißen",
    "Roboterschweißen",
    "Lackieren",
    "Pulverbeschichten",
)

_LABOUR_ONLY_OPS: tuple[str, ...] = (
    "Schweißen",
    "MAG/MIG Schweißen",
    "WIG/TIG Schweißen",
    "Heften",
    "Löten",
    "Kleben",
    "Schrauben",
    "Nieten",
    "Polieren 1",
    "Polieren 2",
    "Nachpolieren",
    "Entgraten",
    "Gewinde",
    "Anpassen",
    "Abziehen",
    "Montage",
    "Zusammenbauen",
    "Nacharbeiten",
    "Kommissionieren",
    "Verpacken/Kontrollieren",
    "Sonstiges",
    "Reserve",
)

# §3/§4 router-support entries with no German-54 counterpart (doc names
# verbatim; pre-installed ops are renameable, so German polish is a rename).
# (name, category, calculation_mode, is_outside_service)
_SUPPORT_OPS: tuple[tuple[str, OpCategory, CalculationMode, bool], ...] = (
    ("Material | Bar (Round)", OpCategory.material, CalculationMode.machine_plus_operator, False),
    (
        "Material | Bar (Rectangular)",
        OpCategory.material,
        CalculationMode.machine_plus_operator,
        False,
    ),
    ("Material | Bar (I-Beam)", OpCategory.material, CalculationMode.machine_plus_operator, False),
    (
        "Material | Sheet (Nesting)",
        OpCategory.material,
        CalculationMode.machine_plus_operator,
        False,
    ),
    ("PC Piece Price", OpCategory.operation, CalculationMode.labour_only, False),
    ("Assembly | Manufactured", OpCategory.operation, CalculationMode.labour_only, False),
    ("Generic | Shipping Prep", OpCategory.operation, CalculationMode.labour_only, False),
    ("Hardware Insert", OpCategory.operation, CalculationMode.labour_only, False),
    ("Engineering", OpCategory.operation, CalculationMode.labour_only, False),
    ("Outside Service | General", OpCategory.operation, CalculationMode.outside_process, True),
)

# ---------------------------------------------------------------------------
# §4 — processes + routers (op names reference the library above / German 54)
# ---------------------------------------------------------------------------
# (process name, family, smart_rfq, default_pc, router rows)
# router row: (op name, per_setup, is_assembly, root_component_only)
_RouterRow = tuple[str, bool, bool, bool]
_PROCESSES: tuple[tuple[str, ProcessFamily, bool, bool, tuple[_RouterRow, ...]], ...] = (
    (
        "Milling",
        ProcessFamily.MILLING,
        True,
        False,
        (
            ("Material | Bar (Round)", False, False, False),
            ("Fräsen", True, False, False),
            ("Entgraten", False, False, False),
            ("Verpacken/Kontrollieren", False, False, False),
        ),
    ),
    (
        "Lathe",
        ProcessFamily.LATHE,
        True,
        False,
        (
            ("Material | Bar (Round)", False, False, False),
            ("Drehen", True, False, False),
            ("Entgraten", False, False, False),
            ("Verpacken/Kontrollieren", False, False, False),
        ),
    ),
    (
        "Sheet Metal",
        ProcessFamily.SHEET_METAL,
        True,
        False,
        (
            ("Material | Sheet (Nesting)", False, False, False),
            ("Laserschneiden Blech", False, False, False),
            ("Kanten", False, False, False),
            ("Entgraten", False, False, False),
        ),
    ),
    (
        "Tube Laser",
        ProcessFamily.TUBE_LASER,
        True,
        False,
        (
            ("Material | Bar (Round)", False, False, False),
            ("Laserschneiden Rohr", False, False, False),
            ("Entgraten", False, False, False),
        ),
    ),
    (
        "Assembly | Parent-Level",
        ProcessFamily.ASSEMBLY,
        False,
        False,
        (
            ("Assembly | Manufactured", False, True, True),
            ("Generic | Shipping Prep", False, False, True),
        ),
    ),
    (
        "Purchased Component",
        ProcessFamily.GENERIC,
        False,
        True,
        (("PC Piece Price", False, False, False),),
    ),
)

# ---------------------------------------------------------------------------
# §6 — pricing defaults (spec #zuschlagskalkulation table; editable defaults)
# ---------------------------------------------------------------------------
# Zuschlagskalkulation (spec #zuschlagskalkulation defaults: MGK 10 %, VwGK
# 8 %, VtGK 6 %, Gewinn 10 %) — Gewinn sits LAST so get_selbstkosten() sees
# the other Zuschlag amounts ("Selbstkosten = everything before Gewinn").
# (name, custom category (None = plain markup on `category`), formula, pct, position)
_ZUSCHLAG_ITEMS: tuple[tuple[str, str | None, str | None, Decimal | None, int], ...] = (
    ("Materialgemeinkosten (MGK)", None, None, Decimal("10"), 1),
    (
        "Verwaltungsgemeinkosten (VwGK)",
        "Herstellkosten",
        "set_custom_cost(get_herstellkosten())\nPERCENTAGE = 8",
        None,
        2,
    ),
    (
        "Vertriebsgemeinkosten (VtGK)",
        "Herstellkosten",
        "set_custom_cost(get_herstellkosten())\nPERCENTAGE = 6",
        None,
        3,
    ),
    (
        "Gewinnzuschlag",
        "Selbstkosten",
        "set_custom_cost(get_selbstkosten())\nPERCENTAGE = 10",
        None,
        4,
    ),
)

_DISCOUNT_DEF = (
    "Mengenrabatt",
    "PERCENTAGE = 5 if REQUESTED_QUANTITY > 100 else 0",
)

# The six spec #addons AddOnType entries (dropdown, admin-configurable).
_ADD_ON_DEFS: tuple[tuple[str, bool], ...] = (
    ("Manual Add-On", False),
    ("Certificate of Conformance", False),
    ("Non-Recurring Engineering (NRE)", True),
    ("Tooling Charge", True),
    ("Special Packaging", False),
    ("First Article Inspection (FAI)", False),
    ("Minimum Order Charge", True),
)

# §6 expedite default set — monotonic (faster costs more; the skeleton's
# inverted pair reads as a typo, noted in the M1.12 PR).
_DEFAULT_EXPEDITE_TIERS = [
    {"days_faster": 5, "markup_pct": "7"},
    {"days_faster": 10, "markup_pct": "15"},
]

# ---------------------------------------------------------------------------
# §7 partial — workflow steps, custom tables, email templates
# ---------------------------------------------------------------------------
_WORKFLOW_STEPS = ("Not Started", "In Progress", "On Hold", "Completed", "No Quote")

_CUSTOM_TABLES: tuple[tuple[str, list[dict[str, str]]], ...] = (
    (
        "material_inventory",
        [
            {"name": "material", "type": "string"},
            {"name": "diameter", "type": "numeric"},
            {"name": "length", "type": "numeric"},
            {"name": "bar_cost", "type": "numeric"},
        ],
    ),
    (
        "laser_cut_rates",
        [
            {"name": "material_family", "type": "string"},
            {"name": "thickness", "type": "numeric"},
            {"name": "cut_rate", "type": "numeric"},
            {"name": "pierce_time", "type": "numeric"},
        ],
    ),
    (
        "punch_tooling",
        [
            {"name": "tool_name", "type": "string"},
            {"name": "setup_time", "type": "numeric"},
            {"name": "hit_time", "type": "numeric"},
        ],
    ),
)

_EMAIL_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("quote_sent", "de-DE", "Ihr Angebot {{quote_number}}"),
    ("rfq_received", "de-DE", "Anfrage erhalten"),
    ("follow_up", "de-DE", "Erinnerung: Ihr Angebot {{quote_number}}"),
)


@dataclass(frozen=True)
class ConfigureSeedResult:
    """Created-row counts (zero across the board on a re-run)."""

    classes_created: int
    materials_created: int
    operation_defs_created: int
    processes_created: int
    router_rows_created: int
    pricing_item_defs_created: int
    discount_defs_created: int
    add_on_defs_created: int
    workflow_steps_created: int
    custom_tables_created: int
    email_templates_created: int
    rules_created: int
    interrogation_profiles_created: int


async def seed_configure_catalog(
    session: AsyncSession, *, org_id: uuid.UUID
) -> ConfigureSeedResult:
    """Seed (or reconcile) the §2-§7 Configure catalog for one org."""
    org = await session.get(Organization, org_id)
    assert org is not None  # provisioning always precedes the catalog seed

    # First-ever configure seed? (no library yet). Org-level switches are only
    # provisioned then — a re-seed must never undo an admin's explicit choice
    # (spec #dach-costing: turning the mode off is a deliberate user action).
    is_first_seed = (
        await session.scalar(select(OperationDef.id).where(OperationDef.org_id == org_id).limit(1))
    ) is None
    if is_first_seed:
        # DACH orgs are provisioned with the mode ON (#dach-costing);
        # OrgCountry is DE/AT/CH-only, so every seeded org qualifies.
        org.dach_costing_mode = True
        if org.default_expedite_tiers is None:
            org.default_expedite_tiers = _DEFAULT_EXPEDITE_TIERS

    classes_created = await _seed_classes(session, org_id)
    materials_created = await _seed_polymers(session, org_id)
    operation_defs_created = await _seed_operation_defs(session, org_id)
    processes_created, router_rows_created = await _seed_processes(session, org_id)
    pricing_created = await _seed_pricing_item_defs(session, org_id, org.dach_costing_mode)
    discount_created = await _seed_discount_defs(session, org_id)
    add_on_created = await _seed_add_on_defs(session, org_id)
    steps_created = await _seed_workflow_steps(session, org_id)
    tables_created = await _seed_custom_tables(session, org_id)
    templates_created = await _seed_email_templates(session, org_id)
    rules_created = await _seed_rules(session, org_id)
    interrogation_profiles_created = await _seed_interrogation_profiles(session, org_id)

    await session.flush()
    return ConfigureSeedResult(
        classes_created=classes_created,
        materials_created=materials_created,
        operation_defs_created=operation_defs_created,
        processes_created=processes_created,
        router_rows_created=router_rows_created,
        pricing_item_defs_created=pricing_created,
        discount_defs_created=discount_created,
        add_on_defs_created=add_on_created,
        workflow_steps_created=steps_created,
        custom_tables_created=tables_created,
        email_templates_created=templates_created,
        rules_created=rules_created,
        interrogation_profiles_created=interrogation_profiles_created,
    )


async def _seed_classes(session: AsyncSession, org_id: uuid.UUID) -> int:
    existing = {
        row.name
        for row in (
            await session.scalars(select(MaterialClass).where(MaterialClass.org_id == org_id))
        ).all()
    }
    created = 0
    for name, position in _EXTRA_CLASSES:
        if name in existing:
            continue
        session.add(MaterialClass(org_id=org_id, name=name, position=position))
        created += 1
    await session.flush()
    return created


async def _seed_polymers(session: AsyncSession, org_id: uuid.UUID) -> int:
    kunststoff = await session.scalar(
        select(MaterialClass).where(
            MaterialClass.org_id == org_id, MaterialClass.name == "Kunststoff"
        )
    )
    assert kunststoff is not None  # _seed_classes runs first
    family_name, family_alias = _POLYMER_FAMILY
    family = await session.scalar(
        select(MaterialFamily).where(
            MaterialFamily.org_id == org_id,
            MaterialFamily.class_id == kunststoff.id,
            MaterialFamily.name == family_name,
        )
    )
    if family is None:
        family = MaterialFamily(
            org_id=org_id, class_id=kunststoff.id, name=family_name, alias=family_alias, position=0
        )
        session.add(family)
        await session.flush()
    existing = {
        material.display_name
        for material in (
            await session.scalars(
                select(Material).where(Material.org_id == org_id, Material.family_id == family.id)
            )
        ).all()
    }
    created = 0
    for display_name, density in _POLYMERS:
        if display_name in existing:
            continue
        session.add(
            Material(
                org_id=org_id,
                family_id=family.id,
                display_name=display_name,
                density=Decimal(density),
            )
        )
        created += 1
    return created


async def _seed_operation_defs(session: AsyncSession, org_id: uuid.UUID) -> int:
    existing = {
        row.name
        for row in (
            await session.scalars(select(OperationDef).where(OperationDef.org_id == org_id))
        ).all()
    }
    created = 0
    sort_order = 0
    for name in _MACHINE_OPERATOR_OPS:
        if name not in existing:
            session.add(
                OperationDef(
                    org_id=org_id,
                    name=name,
                    category=OpCategory.operation,
                    calculation_mode=CalculationMode.machine_plus_operator,
                    is_pre_installed=True,
                    sort_order=sort_order,
                )
            )
            created += 1
        sort_order += 1
    for name in _LABOUR_ONLY_OPS:
        if name not in existing:
            session.add(
                OperationDef(
                    org_id=org_id,
                    name=name,
                    category=OpCategory.operation,
                    calculation_mode=CalculationMode.labour_only,
                    is_pre_installed=True,
                    sort_order=sort_order,
                )
            )
            created += 1
        sort_order += 1
    for name, category, mode, outside in _SUPPORT_OPS:
        if name not in existing:
            session.add(
                OperationDef(
                    org_id=org_id,
                    name=name,
                    category=category,
                    calculation_mode=mode,
                    is_outside_service=outside,
                    is_pre_installed=True,
                    sort_order=sort_order,
                )
            )
            created += 1
        sort_order += 1
    await session.flush()
    return created


async def _seed_processes(session: AsyncSession, org_id: uuid.UUID) -> tuple[int, int]:
    defs_by_name = {
        row.name: row
        for row in (
            await session.scalars(select(OperationDef).where(OperationDef.org_id == org_id))
        ).all()
    }
    processes_by_name = {
        row.name: row
        for row in (await session.scalars(select(Process).where(Process.org_id == org_id))).all()
    }
    processes_created = 0
    router_rows_created = 0
    for name, family, smart_rfq, default_pc, router in _PROCESSES:
        process = processes_by_name.get(name)
        if process is None:
            process = Process(org_id=org_id, name=name)
            session.add(process)
            await session.flush()
            processes_created += 1
        # reconcile the M1.12 config columns (idempotent; not user-editable yet)
        process.family = family
        process.available_in_smart_rfq = smart_rfq
        process.is_default_purchased_component_process = default_pc

        existing_rows = {
            (row.operation_def_id, row.position)
            for row in (
                await session.scalars(
                    select(ProcessOperation).where(ProcessOperation.process_id == process.id)
                )
            ).all()
        }
        if existing_rows:
            continue  # router already present — never reshape a configured one
        for position, (op_name, per_setup, is_assembly, root_only) in enumerate(router):
            op_def = defs_by_name[op_name]
            session.add(
                ProcessOperation(
                    org_id=org_id,
                    process_id=process.id,
                    operation_def_id=op_def.id,
                    position=position,
                    per_setup=per_setup,
                    is_assembly=is_assembly,
                    root_component_only=root_only,
                )
            )
            router_rows_created += 1
    await session.flush()
    return processes_created, router_rows_created


async def _seed_pricing_item_defs(
    session: AsyncSession, org_id: uuid.UUID, dach_costing_mode: bool
) -> int:
    existing = {
        row.name
        for row in (
            await session.scalars(select(PricingItemDef).where(PricingItemDef.org_id == org_id))
        ).all()
    }
    created = 0
    if not dach_costing_mode and "Standardaufschlag" not in existing:
        # §6 standard markup — the NON-DACH default. With DACH Costing Mode on
        # the Zuschlagskalkulation chain IS the pricing default: its Gewinn
        # item carries the profit, and a general markup on top would both
        # double-count profit and pollute get_selbstkosten()'s "everything
        # before Gewinn" base (the chain must price 261,80 for the spec's
        # 100 € + 100 € example, not 305,80).
        session.add(
            PricingItemDef(
                org_id=org_id,
                name="Standardaufschlag",
                calc_type=CalcType.markup,
                category=CostCategory.general,
                default_pct=Decimal("20"),
                position=0,
            )
        )
        created += 1
    if dach_costing_mode:
        for name, custom_category, formula, default_pct, position in _ZUSCHLAG_ITEMS:
            if name in existing:
                continue
            if custom_category is None:
                # MGK: a plain markup on the material cost category (MEK)
                session.add(
                    PricingItemDef(
                        org_id=org_id,
                        name=name,
                        calc_type=CalcType.markup,
                        category=CostCategory.material,
                        default_pct=default_pct,
                        position=position,
                    )
                )
            else:
                # VwGK/VtGK/Gewinn: custom categories off the Kalk helpers
                session.add(
                    PricingItemDef(
                        org_id=org_id,
                        name=name,
                        calc_type=CalcType.markup,
                        category=CostCategory.general,
                        is_custom=True,
                        custom_category_name=custom_category,
                        formula=formula,
                        position=position,
                    )
                )
            created += 1
    await session.flush()
    return created


async def _seed_discount_defs(session: AsyncSession, org_id: uuid.UUID) -> int:
    name, formula = _DISCOUNT_DEF
    existing = await session.scalar(
        select(DiscountDef).where(DiscountDef.org_id == org_id, DiscountDef.name == name)
    )
    if existing is not None:
        return 0
    session.add(DiscountDef(org_id=org_id, name=name, formula=formula, position=0))
    return 1


async def _seed_add_on_defs(session: AsyncSession, org_id: uuid.UUID) -> int:
    existing = {
        row.name
        for row in (await session.scalars(select(AddOnDef).where(AddOnDef.org_id == org_id))).all()
    }
    created = 0
    for position, (name, required) in enumerate(_ADD_ON_DEFS):
        if name in existing:
            continue
        session.add(
            AddOnDef(
                org_id=org_id,
                name=name,
                default_is_required=required,
                position=position,
            )
        )
        created += 1
    return created


async def _seed_workflow_steps(session: AsyncSession, org_id: uuid.UUID) -> int:
    existing = {
        row.name
        for row in (
            await session.scalars(select(WorkflowStepDef).where(WorkflowStepDef.org_id == org_id))
        ).all()
    }
    created = 0
    for position, name in enumerate(_WORKFLOW_STEPS):
        if name in existing:
            continue
        session.add(WorkflowStepDef(org_id=org_id, name=name, position=position))
        created += 1
    return created


async def _seed_custom_tables(session: AsyncSession, org_id: uuid.UUID) -> int:
    existing = {
        row.name
        for row in (
            await session.scalars(select(CustomTable).where(CustomTable.org_id == org_id))
        ).all()
    }
    created = 0
    for name, columns in _CUSTOM_TABLES:
        if name in existing:
            continue
        session.add(CustomTable(org_id=org_id, name=name, columns=columns))
        created += 1
    return created


async def _seed_email_templates(session: AsyncSession, org_id: uuid.UUID) -> int:
    existing = {
        (row.key, row.locale)
        for row in (
            await session.scalars(select(EmailTemplate).where(EmailTemplate.org_id == org_id))
        ).all()
    }
    created = 0
    for key, locale, subject in _EMAIL_TEMPLATES:
        if (key, locale) in existing:
            continue
        session.add(EmailTemplate(org_id=org_id, key=key, locale=locale, subject=subject))
        created += 1
    return created


# --------------------------------------------------------------------------- #
# §7 — starter rule library
# --------------------------------------------------------------------------- #
#: Tolerance collections the tight-tolerance rule ORs over (RULES-ENGINE-SPEC §4).
_TIGHT_TOLERANCE_PATHS = (
    "length_tolerances",
    "diameter_tolerances",
    "radius_tolerances",
    "angular_tolerances",
)

#: PP's 5-thou tight-tolerance threshold, re-unit'd (§7 DACH: "PP 5-thou →
#: 0.13 mm"). **Linear paths only.**
_TIGHT_TOLERANCE_MM = 0.13

#: The angular threshold is a SEPARATE number, not the linear one reused. §7
#: re-units PP's 5 thou to 0.13 mm and says nothing about angles, so sharing the
#: scalar would be a coincidence of digits rather than a decision — and it would
#: print "0.13 mm" in the rule's description while comparing degrees.
#: 0.5° is the seeded default: ISO 2768-m's angular general tolerance is ±1° for
#: the shortest leg, so half of it means "tighter than the general tolerance the
#: shop already assumes", which is what the rule is for. ASSUMED — the ladder is
#: silent on an angular threshold; shop-specific and cheap to retune, and
#: Fechner's real numbers arrive with the starter-rule review (DECISIONS
#: 2026-07-12).
_TIGHT_ANGLE_DEG = 0.5

#: Stable identities so a re-seed reconciles the same rows rather than minting
#: duplicates (``rule.uuid`` is the portable upsert key, M3.6).
_RULE_UUIDS = {
    "dual_use": uuid.UUID("6f1f6a3e-0b8e-4a5a-9c21-2a1d1f0a0001"),
    "tight_tolerance": uuid.UUID("6f1f6a3e-0b8e-4a5a-9c21-2a1d1f0a0002"),
    "missing_file": uuid.UUID("6f1f6a3e-0b8e-4a5a-9c21-2a1d1f0a0003"),
    "deburr": uuid.UUID("6f1f6a3e-0b8e-4a5a-9c21-2a1d1f0a0004"),
}


def _text_keyword_signal(keywords: list[str]) -> dict[str, Any]:
    return {
        "logical_operator": "AND",
        "groups": [
            {
                "document_path": "text",
                "logical_operator": "AND",
                "queries": [
                    {
                        "field_name": ["raw_text"],
                        "operator": "includesCaseInsensitive",
                        "value": keywords,
                        "value_type": "string",
                        "filter_type": "string",
                        "units": None,
                    }
                ],
                "count_query": None,
            }
        ],
    }


def _files_signal(field: str) -> dict[str, Any]:
    return {
        "logical_operator": "AND",
        "groups": [
            {
                "document_path": "files",
                "logical_operator": "AND",
                "queries": [
                    {
                        "field_name": [field],
                        "operator": "equals",
                        "value": False,
                        "value_type": "boolean",
                        "filter_type": "boolean",
                        "units": None,
                    }
                ],
                "count_query": None,
            }
        ],
    }


def _tolerance_signal(document_path: str) -> dict[str, Any]:
    angular = document_path == "angular_tolerances"
    return {
        "logical_operator": "AND",
        "groups": [
            {
                "document_path": document_path,
                "logical_operator": "AND",
                "queries": [
                    {
                        "field_name": ["smallest_delta"],
                        "operator": "lessThanOrEqual",
                        "value": _TIGHT_ANGLE_DEG if angular else _TIGHT_TOLERANCE_MM,
                        "value_type": "angle" if angular else "distance",
                        "filter_type": "numeric",
                        "units": "deg" if angular else "mm",
                    }
                ],
                "count_query": None,
            }
        ],
    }


def _starter_rules(deburr_op_def_id: uuid.UUID | None) -> list[dict[str, Any]]:
    """The §7 starter library, German-first (DECISIONS 2026-07-16: Claude-
    generated German, Fechner reviews later).

    §7 names five starters; four are expressible against M3.6's ``document_path``
    catalogue and are seeded here. The fifth — *no material specified → block
    send* — has **no addressable path**: the catalogue exposes no line-item or
    material collection (M3.7's ``line_item``/``quote`` context fields are inert
    for exactly this reason). Cataloguing one is an M3.6 schema change, logged in
    DECISIONS.md (2026-07-16) rather than guessed at here.
    """
    rules: list[dict[str, Any]] = [
        {
            "uuid": str(_RULE_UUIDS["dual_use"]),
            "name": "Ausfuhrkontrolle prüfen (Dual-Use)",
            "description": (
                "Hinweis auf Ausfuhrkontrolle/Dual-Use in den Dokumenten — "
                "Einstufung durch die Leitung bestätigen lassen."
            ),
            "logical_operator": "OR",
            "signals": [
                _text_keyword_signal(
                    [
                        "dual-use",
                        "dual use",
                        "ausfuhrgenehmigung",
                        "ausfuhrliste",
                        "ausfuhrkontrolle",
                        "eg 428/2009",
                        "eu 2021/821",
                        "export control",
                    ]
                )
            ],
            "resolutions": [
                {"type": "RESOLVE", "parameters": [], "custom_label": "Von Leitung freigegeben"},
                {"type": "RESOLVE", "parameters": [], "custom_label": "Einstufung bestätigt"},
                {"type": "NO_QUOTE", "parameters": [], "custom_label": None},
            ],
            "default_assignee_id": None,
        },
        {
            "uuid": str(_RULE_UUIDS["tight_tolerance"]),
            "name": "Enge Toleranz — Senior-Schätzer",
            "description": (
                f"Mindestens eine Toleranz ≤ {_TIGHT_TOLERANCE_MM} mm "
                f"(bzw. ≤ {_TIGHT_ANGLE_DEG}° bei Winkeln) — "
                "vor der Kalkulation von einem Senior-Schätzer prüfen lassen."
            ),
            "logical_operator": "OR",
            "signals": [_tolerance_signal(path) for path in _TIGHT_TOLERANCE_PATHS],
            "resolutions": [
                {
                    "type": "RESOLVE",
                    "parameters": [],
                    "custom_label": "Von Senior-Schätzer geprüft",
                },
                {"type": "RESOLVE", "parameters": [], "custom_label": "Fremdvergabe"},
                {"type": "NO_QUOTE", "parameters": [], "custom_label": None},
            ],
            "default_assignee_id": None,
        },
        {
            "uuid": str(_RULE_UUIDS["missing_file"]),
            "name": "Fehlendes Modell oder fehlende Zeichnung",
            "description": "Zum Bauteil fehlt das 3D-Modell oder die Zeichnung.",
            "logical_operator": "OR",
            "signals": [_files_signal("has_print"), _files_signal("has_model")],
            "resolutions": [
                {"type": "RESOLVE", "parameters": [], "custom_label": "Kunde kontaktiert"},
                {"type": "RESOLVE", "parameters": [], "custom_label": "Ohne Datei kalkuliert"},
            ],
            "default_assignee_id": None,
        },
    ]
    if deburr_op_def_id is not None:
        rules.append(
            {
                "uuid": str(_RULE_UUIDS["deburr"]),
                "name": "Entgraten gefordert",
                "description": (
                    "Die Zeichnung fordert Entgraten/Kantenbruch — "
                    "Operation in den Arbeitsplan aufnehmen."
                ),
                "logical_operator": "OR",
                "signals": [
                    _text_keyword_signal(
                        [
                            "entgrat",
                            "kanten brechen",
                            "kantenbruch",
                            "gratfrei",
                            "deburr",
                            "break all edges",
                            "remove all burrs",
                        ]
                    )
                ],
                "resolutions": [
                    {
                        "type": "ADD_OPERATION",
                        "parameters": [{"name": "op_def_ids", "value": [str(deburr_op_def_id)]}],
                        "custom_label": None,
                    },
                    {"type": "RESOLVE", "parameters": [], "custom_label": "Nicht zutreffend"},
                ],
                "default_assignee_id": None,
            }
        )
    return rules


async def _seed_rules(session: AsyncSession, org_id: uuid.UUID) -> int:
    """Seed the §7 starter rule library (spec ``#rules``: "Starter rule library
    ships seeded").

    Reconciling, not overwriting: a rule the shop has since edited keeps its
    edits — re-seeding must never silently revert an admin's tuning (the
    config-freeze posture the rest of this module takes). Only absent rules are
    created.
    """
    deburr = await session.scalar(
        select(OperationDef).where(
            OperationDef.org_id == org_id,
            OperationDef.name == "Entgraten",
            OperationDef.deleted_at.is_(None),
        )
    )
    existing = {
        row.uuid for row in (await session.scalars(select(Rule).where(Rule.org_id == org_id))).all()
    }
    created = 0
    for payload in _starter_rules(deburr.id if deburr is not None else None):
        rule = RuleSchema.model_validate(payload)
        if rule.uuid in existing:
            continue
        dumped = rule.model_dump(mode="json")
        session.add(
            Rule(
                org_id=org_id,
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
    await session.flush()
    return created


#: Default interrogation-profile names per Core-4 family — German-first (the
#: tier-1 UI rule + the seeded German op-library precedent outrank the folded
#: sub-spec's PP-English example "Default Sheet Metal (Laser)", which is an
#: "e.g.", not a pinned name).
_INTERROGATION_PROFILE_NAMES: dict[ProcessFamily, str] = {
    ProcessFamily.SHEET_METAL: "Standard Blech (Laser)",
    ProcessFamily.MILLING: "Standard CNC-Fräsen",
    ProcessFamily.LATHE: "Standard CNC-Drehen",
    ProcessFamily.TUBE_LASER: "Standard Rohrlaser",
}


async def _seed_interrogation_profiles(session: AsyncSession, org_id: uuid.UUID) -> int:
    """M4.7: one org-default ``CustomInterrogation`` per Core-4 family, its
    ``inputs`` the DFM-WARNINGS seed defaults (thresholds + toggles, metric).
    Natural key = (org, family, no material link) — a re-seed never touches an
    existing default, so edited thresholds survive (the catalog_seed rule)."""
    from app.geometry.dfm import dfm_default_inputs

    existing = {
        row.family
        for row in (
            await session.scalars(
                select(CustomInterrogation).where(
                    CustomInterrogation.org_id == org_id,
                    CustomInterrogation.material_class_id.is_(None),
                    CustomInterrogation.material_family_id.is_(None),
                    CustomInterrogation.material_id.is_(None),
                )
            )
        ).all()
    }
    created = 0
    for family, name in _INTERROGATION_PROFILE_NAMES.items():
        if family in existing:
            continue
        session.add(
            CustomInterrogation(
                org_id=org_id,
                name=name,
                family=family,
                inputs=dfm_default_inputs(family.value),
            )
        )
        created += 1
    return created
