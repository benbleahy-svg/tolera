"""The ``GeometryService`` contract — the swappable engine boundary (M4.1).

This module defines what crosses the boundary and nothing else: STEP bytes in,
plain dataclasses out. **No OCP/OCCT type may appear here** — the engine
internals (OCCT v1, Spatial swap-in post-pilot) must be replaceable with zero
changes above the service layer (DECISIONS.md 2026-06-14). The output field
names and units are the geometry↔Kalk contract (PartGeometry-Attribute-Catalog
§1-§2): mm / mm² / mm³ / g, metric always.

M4.1 populates ``dimensions`` only. ``family_scalars`` / ``features`` /
``feedback`` / ``confidence`` are carried in the schema now (the contract is
pinned — INTERROGATION-ENGINE-SPEC §2) and stay empty until the per-family
recognizers land (M4.2 / M4.4-M4.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

#: Geometry-signature recipe version, prefixed onto every hash (``gs1:<hex>``)
#: so a future recipe change re-indexes instead of silently mismatching stored
#: hashes. gs1 = the M4.0-proven recipe: UnifySameDomain canonicalization →
#: quantized (volume, area, OBB-sorted dims, face/edge-type histograms,
#: per-type areas) at 6 significant digits → SHA-256 (GEOMETRY.md §2).
SIGNATURE_VERSION = "gs1"

#: Family values the engine recognizes (mirror ``app.models.ProcessFamily``
#: values without importing app models across the boundary). M4.2: sheet metal;
#: M4.4: milling; M4.5/M4.6 add the rest of the Core 4.
FAMILY_SHEET_METAL = "SHEET_METAL"
FAMILY_MILLING = "MILLING"

#: Families with a per-family recognizer behind :meth:`GeometryService.analyze`
#: — any other family degrades to the dims-only pass, never fabricated scalars.
RECOGNIZED_FAMILIES = frozenset({FAMILY_SHEET_METAL, FAMILY_MILLING})


class GeometryError(Exception):
    """Base for engine failures the caller can classify."""


class StepParseError(GeometryError):
    """The bytes are not a readable STEP body."""


class MultiBodyError(GeometryError):
    """More than one solid: assemblies are decomposed first (M4.9b), never
    interrogated directly (INTERROGATION-ENGINE-SPEC §5.1)."""

    def __init__(self, solid_count: int) -> None:
        super().__init__(f"expected a single solid body, found {solid_count}")
        self.solid_count = solid_count


@dataclass(frozen=True)
class Dimensions:
    """The catalog §1 core-dims block (+ §2 weight), metric.

    ``size_x/y/z`` here are the **raw extraction** — max/med/min of the winning
    bounding box (catalog §1: X = max dim of the optimal bbox …). The
    overwrite > optimal-bbox > AABB > manual precedence is resolved at the
    persistence layer against ``part_geometry.overrides``, never inside the
    engine. ``bbox_source`` records which box won the min-volume tie-break
    (``Bnd_OBB`` is approximate — GEOMETRY.md §1), keeping the extraction
    auditable.
    """

    size_x: float  # mm
    size_y: float  # mm
    size_z: float  # mm
    max_dim: float  # mm (== size_x)
    med_dim: float  # mm (== size_y)
    min_dim: float  # mm (== size_z)
    area: float  # mm²
    volume: float  # mm³
    weight: float | None  # g — volume x density; None when no density given
    bbox_source: Literal["obb", "aabb"]


@dataclass(frozen=True)
class AnalysisResult:
    """One body's interrogation output (INTERROGATION-ENGINE-SPEC §2)."""

    family: str | None
    dimensions: Dimensions
    family_scalars: dict[str, Any] = field(default_factory=dict)
    features: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"] | None = None


class GeometryService(Protocol):
    """The engine interface (INTERROGATION-ENGINE-SPEC §1) — v1 subset.

    ``family`` is optional in M4.1: the dimensions block is family-agnostic and
    the per-family recognizers don't exist yet; from M4.2 on a family selects
    its recognizer. ``density_g_cm3`` is the caller-resolved material density
    (density is a ``man`` attribute — the engine never invents it).
    """

    def analyze(
        self,
        step_bytes: bytes,
        family: str | None = None,
        density_g_cm3: float | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> AnalysisResult: ...

    def compute_signature(self, step_bytes: bytes) -> str: ...
