"""GeometryService — the CAD-interrogation engine boundary (M4.1).

Public surface: the contract types plus :func:`get_engine`. The OCCT
implementation imports OCP (worker-image-only dependency), so it is loaded
lazily on first :func:`get_engine` call — importing :mod:`app.geometry` from
API code stays safe on an image without OCP.
"""

from __future__ import annotations

from .contract import (
    FAMILY_LATHE,
    FAMILY_MILLING,
    FAMILY_SHEET_METAL,
    RECOGNIZED_FAMILIES,
    SIGNATURE_VERSION,
    AnalysisResult,
    Dimensions,
    GeometryError,
    GeometryService,
    MultiBodyError,
    StepParseError,
)

__all__ = [
    "FAMILY_LATHE",
    "FAMILY_MILLING",
    "FAMILY_SHEET_METAL",
    "RECOGNIZED_FAMILIES",
    "SIGNATURE_VERSION",
    "AnalysisResult",
    "Dimensions",
    "GeometryError",
    "GeometryService",
    "MultiBodyError",
    "StepParseError",
    "get_engine",
]

_engine: GeometryService | None = None


def get_engine() -> GeometryService:
    """The process-wide engine (OCCT v1; Spatial swaps in behind the same
    contract — DECISIONS.md 2026-06-14). Lazy: OCP loads on first use."""
    global _engine
    if _engine is None:
        from .occt import OcctGeometryService

        _engine = OcctGeometryService()
    return _engine
