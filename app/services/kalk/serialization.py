"""Canonical serialization — the determinism contract's byte form.

DECISIONS.md [2026-07-08]: JSON, sorted keys, compact separators, ASCII-only,
floats via ``repr`` (shortest round-trip, which is what ``json`` emits),
non-finite values rejected. Identical results must always yield identical
bytes; goldens compare these bytes.
"""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.kalk.evaluator import EvalResult


def canonical_bytes(result: EvalResult) -> bytes:
    payload = dataclasses.asdict(result)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
