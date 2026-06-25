"""Load org seed files and apply them through :class:`OrgService`.

A seed file is one JSON object per org (``SEED-AND-FIXTURES.md`` Part 1 §1),
parsed and validated into an :class:`~app.services.org_service.OrgSpec`. Applying
runs one transaction per org so a bad org fails in isolation rather than rolling
back already-provisioned ones. The runner is idempotent because the service is.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.org_service import OrgResult, OrgService, OrgSpec

# Committed seeds live next to the CLI that loads them (``scripts/seeds/*.json``).
DEFAULT_SEEDS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "seeds"


def load_seeds(directory: Path) -> list[OrgSpec]:
    """Parse + validate every ``*.json`` in ``directory`` (sorted for determinism)."""
    specs: list[OrgSpec] = []
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        specs.append(OrgSpec.model_validate(raw))
    return specs


async def apply_seeds(
    sessionmaker: async_sessionmaker[AsyncSession], specs: Iterable[OrgSpec]
) -> list[OrgResult]:
    """Provision each spec in its own transaction; return the per-org results."""
    results: list[OrgResult] = []
    for spec in specs:
        async with sessionmaker() as session, session.begin():
            results.append(await OrgService(session).create_org(spec))
    return results
