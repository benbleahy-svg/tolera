"""``gv1`` — the Part-Library similarity feature vector (M4.11).

Spec ``#partlib`` (Similar Geometries): a numeric vector of manufacturing-
relevant geometric scalars — bbox dims, volume, surface area, hole count,
bend count, thinness, aspect ratio — searched with pgvector nearest-neighbour.
The decided v1 is this deterministic scalar vector; learned embeddings are
explicitly post-pilot.

Recipe (frozen as ``gv1`` — changing any slot or the scaling is a ``gv2``
and forces a column migration + backfill, like the ``gs1`` signature freeze):

====  =======================================================================
slot  value
====  =======================================================================
0-2   ``log1p(size_x/y/z)`` — OBB-sorted mm dims (descending, M4.1)
3     ``log1p(volume)`` mm³
4     ``log1p(area)`` mm²
5     ``log1p(hole count)`` — milling ``hole``/``circular_pocket`` features
      + sheet-metal ``pierce_count``
6     ``log1p(bend_count)`` (sheet metal; 0 elsewhere)
7     ``log1p(max_dim / min_dim)`` — aspect ratio
8     ``volume / bbox volume`` — fill ratio in (0, 1]
9     ``log1p(area / volume)`` — surface-to-volume thinness proxy
====  =======================================================================

Log scaling keeps the mm³-scale slots from dominating the L2 distance, and
slots 8/9 stand in for the build-plan's "thin-wall flags": DFM warnings are
org-threshold-configurable (M4.7/M4.8), so they can never feed a cross-part
index — only pure geometry is deterministic enough to store.

All inputs come from the persisted ``AnalysisResult`` dict (metric-native);
family scalars/features are optional so the vector enriches as recognizer
families land without ever failing a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite, log1p
from typing import Any

GV_VERSION = "gv1"
GV_DIM = 10

#: L2 cut-off for the Similar-Geometries bucket, calibrated on the fixture
#: corpus (M4.11): same-class variants (tube↔tube, block↔block) fall at
#: 0.06-0.9, cross-class pairs (cube↔tube, bracket↔plate) above ~1.5.
#: Pinned by the near/far engine tests; retune there if the recipe changes.
SIMILAR_L2_THRESHOLD = 1.0

#: Milling feature names that count as holes (a circular pocket is a hole
#: above the tool-diameter cutoff — same manufacturing intent).
_HOLE_FEATURES = {"hole", "circular_pocket"}


def build_geometry_vector(result: Mapping[str, Any]) -> list[float] | None:
    """The ``gv1`` vector for a persisted analysis result, or ``None``.

    ``None`` (no vector, part absent from the Similar-Geometries index) when
    the dims are missing or degenerate — a failed/partial run must never
    index as "similar to everything near the origin".
    """
    dims = result.get("dimensions") or {}
    raw = [dims.get(k) for k in ("size_x", "size_y", "size_z", "volume", "area")]
    # NaN fails every comparison, so test finiteness explicitly — pgvector
    # rejects non-finite elements at write time.
    if any(v is None or not isfinite(v) or v <= 0 for v in raw):
        return None
    size_x, size_y, size_z, volume, area = (float(v) for v in raw if v is not None)

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
