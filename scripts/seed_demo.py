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

from app.config import get_settings
from app.db import make_engine, make_sessionmaker
from app.logging import configure_logging
from app.seed import DEFAULT_SEEDS_DIR, apply_seeds, load_seeds
from app.services.org_service import OrgResult, OrgSpec

logger = logging.getLogger("scripts.seed_demo")


async def _run(database_url: str, specs: list[OrgSpec]) -> list[OrgResult]:
    engine = make_engine(database_url)
    try:
        return await apply_seeds(make_sessionmaker(engine), specs)
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    specs = load_seeds(DEFAULT_SEEDS_DIR)
    if not specs:
        logger.warning(
            "seed_demo: no seed files found", extra={"seeds_dir": str(DEFAULT_SEEDS_DIR)}
        )
        return

    results = asyncio.run(_run(settings.database_url, specs))

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
    logger.info("seed complete", extra={"orgs": len(results)})


if __name__ == "__main__":
    main()
