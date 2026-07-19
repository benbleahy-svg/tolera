"""``python -m scripts.seed_demo`` — idempotent org-provisioning seed (M0.5).

Provisions the orgs declared in ``scripts/seeds/*.json`` (the ``fechner`` pilot
plus a second org) and is safe to re-run. Connects as the **owner** role
(``Settings.database_url``): provisioning writes the RLS-self-isolated
``organization`` table and across orgs, which only the owner/superuser may do —
the request-serving restricted role deliberately cannot.

Run inside the app container: ``docker compose exec app python -m scripts.seed_demo``.
"""

from __future__ import annotations

import asyncio
import logging

from app.catalog_seed import CatalogSeedResult, seed_material_catalog
from app.config import get_settings
from app.configure_seed import ConfigureSeedResult, seed_configure_catalog
from app.crm_seed import FECHNER_SLUG, CrmSeedResult, seed_pilot_crm
from app.db import make_engine, make_sessionmaker
from app.logging import configure_logging
from app.seed import DEFAULT_SEEDS_DIR, apply_seeds, load_seeds
from app.services.org_service import OrgResult, OrgSpec
from app.vendor_seed import VendorSeedResult, seed_vendors

logger = logging.getLogger("scripts.seed_demo")


async def _run(
    database_url: str, specs: list[OrgSpec]
) -> tuple[list[OrgResult], CrmSeedResult | None]:
    engine = make_engine(database_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        results = await apply_seeds(sessionmaker, specs)
        # Every org gets the material catalog + Core-4 processes (M1.7) — its own
        # transaction per org so a catalog hiccup can't undo provisioning.
        for result in results:
            async with sessionmaker() as session, session.begin():
                catalog = await seed_material_catalog(session, org_id=result.org_id)
            _log_catalog(result.slug, catalog)
            # M1.12: the full Configure catalog (54-op library, routers,
            # pricing defaults, …) — its own transaction per org as well.
            async with sessionmaker() as session, session.begin():
                configure = await seed_configure_catalog(session, org_id=result.org_id)
            _log_configure(result.slug, configure)
            # M6.3: the Supplier Directory's demo vendors — every org, own
            # transaction, so the Suppliers nav is never an empty screen.
            async with sessionmaker() as session, session.begin():
                vendors = await seed_vendors(session, org_id=result.org_id)
            _log_vendors(result.slug, vendors)
        # Seed the golden-thread CRM (Fechner account + contact) once the pilot org
        # exists — its own transaction so a CRM hiccup can't undo provisioning.
        crm: CrmSeedResult | None = None
        fechner = next((r for r in results if r.slug == FECHNER_SLUG), None)
        if fechner is not None:
            async with sessionmaker() as session, session.begin():
                crm = await seed_pilot_crm(session, org_id=fechner.org_id)
        return results, crm
    finally:
        await engine.dispose()


def _log_vendors(slug: str, vendors: VendorSeedResult) -> None:
    logger.info(
        "seeded vendors",
        extra={
            "slug": slug,
            "vendors_total": len(vendors.vendor_ids),
            "vendors_created": vendors.vendors_created,
            "contacts_created": vendors.contacts_created,
        },
    )


def _log_catalog(slug: str, catalog: CatalogSeedResult) -> None:
    logger.info(
        "seeded material catalog",
        extra={
            "slug": slug,
            "classes_created": catalog.classes_created,
            "families_created": catalog.families_created,
            "materials_created": catalog.materials_created,
            "processes_created": catalog.processes_created,
        },
    )


def _log_configure(slug: str, configure: ConfigureSeedResult) -> None:
    logger.info(
        "seeded configure catalog",
        extra={
            "slug": slug,
            "classes_created": configure.classes_created,
            "materials_created": configure.materials_created,
            "operation_defs_created": configure.operation_defs_created,
            "processes_created": configure.processes_created,
            "router_rows_created": configure.router_rows_created,
            "pricing_item_defs_created": configure.pricing_item_defs_created,
            "discount_defs_created": configure.discount_defs_created,
            "add_on_defs_created": configure.add_on_defs_created,
            "workflow_steps_created": configure.workflow_steps_created,
            "custom_tables_created": configure.custom_tables_created,
            "email_templates_created": configure.email_templates_created,
        },
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    specs = load_seeds(DEFAULT_SEEDS_DIR)
    if not specs:
        logger.warning(
            "seed_demo: no seed files found", extra={"seeds_dir": str(DEFAULT_SEEDS_DIR)}
        )
        return

    results, crm = asyncio.run(_run(settings.database_url, specs))

    # Log slugs + counts only — never the seeded emails (PII; CLAUDE.md §5).
    for result in results:
        logger.info(
            "seeded org",
            extra={
                "slug": result.slug,
                "org_created": result.org_created,
                "rfq_ingest": result.rfq_ingest,
                "users_total": len(result.users),
                "users_created": sum(member.user_created for member in result.users),
                "memberships_created": sum(member.membership_created for member in result.users),
            },
        )
    if crm is not None:
        logger.info(
            "seeded pilot CRM",
            extra={
                "slug": FECHNER_SLUG,
                "account_created": crm.account_created,
                "contact_created": crm.contact_created,
            },
        )
    logger.info("seed complete", extra={"orgs": len(results)})


if __name__ == "__main__":
    main()
