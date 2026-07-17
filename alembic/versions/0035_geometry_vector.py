"""Part-Library similarity index (M4.11) — pgvector + ``part.geometry_vector``.

Spec ``#partlib`` (Similar Geometries): a deterministic scalar feature vector
per part, searched with pgvector nearest-neighbour, feeds the fuzzy match
bucket. The column lives on ``part`` next to its sibling index ``geom_hash``
(DECISIONS.md 2026-07-16 M4.1 froze the signature there; the spec's
``part_files.*`` placement is superseded).

* ``CREATE EXTENSION vector`` — first use of pgvector (compose/CI images
  moved to ``pgvector/pgvector:pg16`` with this block).
* ``part.geometry_vector vector(10)`` — nullable; populated by the
  interrogation task and backfilled below from ``part_geometry.raw`` (the
  persisted analysis result) so pre-M4.11 parts index without a re-run.
* HNSW L2 index — HNSW over IVFFlat because it needs no training rows
  (IVFFlat lists degrade on an empty/small table).

The ``gv1`` recipe is INLINED (not imported from ``app.geometry.vector``):
a migration must stay immutable when the app's builder moves to ``gv2``.

Downgrade drops the index, the column, and the extension (symmetric;
without CASCADE, so an unexpectedly shared extension fails loudly rather
than silently breaking a dependent).

Revision ID: 0035_geometry_vector
Revises: 0033_bom_draft
Create Date: 2026-07-17
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from math import log1p
from typing import Any

from sqlalchemy import text

from alembic import op

revision: str = "0035_geometry_vector"
down_revision: str | None = "0033_bom_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HOLE_FEATURES = {"hole", "circular_pocket"}


def _gv1(result: Mapping[str, Any]) -> list[float] | None:
    """Frozen copy of ``app.geometry.vector.build_geometry_vector`` (gv1)."""
    dims = result.get("dimensions") or {}
    size_x = dims.get("size_x")
    size_y = dims.get("size_y")
    size_z = dims.get("size_z")
    volume = dims.get("volume")
    area = dims.get("area")
    if any(v is None or v <= 0 for v in (size_x, size_y, size_z, volume, area)):
        return None
    scalars = result.get("family_scalars") or {}
    features = result.get("features") or []
    holes = sum(1 for f in features if f.get("name") in _HOLE_FEATURES)
    holes += int(scalars.get("pierce_count") or 0)
    bends = int(scalars.get("bend_count") or 0)
    max_dim = dims.get("max_dim") or size_x
    min_dim = dims.get("min_dim") or size_z
    aspect = max_dim / min_dim if min_dim > 0 else 0.0
    return [
        log1p(size_x),
        log1p(size_y),
        log1p(size_z),
        log1p(volume),
        log1p(area),
        log1p(float(holes)),
        log1p(float(bends)),
        log1p(aspect),
        volume / (size_x * size_y * size_z),
        log1p(area / volume),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE part ADD COLUMN geometry_vector vector(10)")
    # L2 to match the calibrated SIMILAR_L2_THRESHOLD; queries stay org-scoped
    # in the WHERE clause (the index itself is physically shared, like every
    # other index on an RLS table).
    op.execute(
        "CREATE INDEX ix_part_geometry_vector_hnsw ON part "
        "USING hnsw (geometry_vector vector_l2_ops)"
    )

    # Backfill from the persisted analysis results (deterministic — the same
    # arithmetic the worker now runs; parts without a clean interrogation
    # simply stay NULL and out of the similarity index). Runs as the OWNER
    # role (the repo's privileged migration path); every write is same-row —
    # the vector lands on exactly the part whose own part_geometry.raw
    # produced it, org_id pinned in the predicate as belt-and-braces.
    bind = op.get_bind()
    rows = bind.execute(
        text("SELECT part_id, org_id, raw FROM part_geometry WHERE raw IS NOT NULL")
    ).all()
    for part_id, org_id, raw in rows:
        payload = raw if isinstance(raw, dict) else json.loads(raw)
        vec = _gv1(payload)
        if vec is None:
            continue
        bind.execute(
            text("UPDATE part SET geometry_vector = :vec WHERE id = :pid AND org_id = :org"),
            {"vec": json.dumps(vec), "pid": part_id, "org": org_id},
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_part_geometry_vector_hnsw")
    op.execute("ALTER TABLE part DROP COLUMN geometry_vector")
    # Symmetric with upgrade(). No CASCADE: if a later revision grew another
    # dependent on the extension, this fails loudly instead of silently
    # breaking it (a full downgrade walk removes dependents first).
    op.execute("DROP EXTENSION IF EXISTS vector")
