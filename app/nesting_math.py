"""M4.3 — estimation-grade sheet-nesting math (spec ``#nesting``).

Pure, deterministic area packing — NOT a true 2D bin-packing layout (the v1
ceiling, INTERROGATION-ENGINE-SPEC §6). The spec pseudocode is followed
verbatim where it speaks:

    parts_area   = sum(flat_area * make_qty)
    usable_area  = (sheet_L * sheet_W) * utilization_factor   # from buffers/kerf
    sheets_needed = parts_area / usable_area                  # fractional
    material_cost = ceil_or_frac(sheets_needed) * sheet_cost
    # distributed back to parts by the chosen method (Area of parts)
    # Drop Threshold = % below which a partial sheet is "dropped"/not charged

Where it is silent the derivation is pinned here (ASSUMED, cheap to reverse —
recomputable from ``config``, nothing baked into schema):

- effective part footprint = ``(flat_x + clearance + kerf) x (flat_y + clearance
  + kerf)`` — each part carries its clearance + one kerf allowance;
- usable sheet = ``(L - 2*edge_buffer) x (W - 2*edge_buffer)``;
- ``parts_per_sheet`` (per component, integer — DemoJ/05 "25 Parts/Sheet")
  = ``floor(usable_area / effective_area)``;
- drop rule: with last-sheet used fraction ``f = net - floor(net)``, a partial
  sheet whose ``f`` is *below* the threshold is "dropped"/not charged in full →
  charge the fractional net; otherwise the remnant is scrap the customer pays →
  charge ``ceil(net)``. (Matches the build-plan's fractional 0.0966 example at
  the seeded 25 % threshold and DemoJ/08's 15 full sheets.)
- grain direction is recorded in the nest config but does not alter the area
  estimate (orientation-free math);
- metrics partition the gross cut stock: ``used + scrap + drop == gross area``
  (DemoJ/08 percentages sum to 100).

Money follows the repo convention: ``Decimal`` quantized to 4 dp,
``ROUND_HALF_UP`` (the ``kalk_output_to_calc`` pattern); geometry stays float
mm/mm². Allocation gives the largest-weight component the rounding remainder
so the per-component costs sum *exactly* to the material cost (no drift, and a
0 %-share component can never go negative).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT4 = Decimal("0.0001")


@dataclass(frozen=True)
class NestComponent:
    """One component's share of the nest (per quantity break)."""

    key: str
    flat_x_mm: float
    flat_y_mm: float
    flat_area_mm2: float
    contour_length_mm: float
    make_qty: int
    cost_distribution_pct: Decimal | None = None


@dataclass(frozen=True)
class NestStock:
    length_mm: float
    width_mm: float
    sheet_cost: Decimal


@dataclass(frozen=True)
class NestSettings:
    edge_buffer_mm: float
    clearance_mm: float
    kerf_mm: float
    drop_threshold_pct: float


@dataclass(frozen=True)
class ComponentResult:
    key: str
    parts_per_sheet: int
    effective_area_mm2: float
    used_area_mm2: float
    cost_share_pct: Decimal
    allocated_cost: Decimal


@dataclass(frozen=True)
class NestResult:
    net_sheet_used: float
    # a count of sheets, not money (the money is material_cost below)
    charged_sheets: float  # nosemgrep: semgrep.money-float-in-pydantic
    gross_sheets: int
    material_cost: Decimal
    used_area_mm2: float
    scrap_area_mm2: float
    drop_area_mm2: float
    # geometry (mm), not money
    total_contour_length_mm: float  # nosemgrep: semgrep.money-float-in-pydantic
    components: list[ComponentResult]


def _effective_area(comp: NestComponent, settings: NestSettings) -> float:
    pad = settings.clearance_mm + settings.kerf_mm
    return (comp.flat_x_mm + pad) * (comp.flat_y_mm + pad)


def _snap_net(net: float) -> float:
    """Snap float dust off a near-integral net sheet count — an accumulated
    2.0000000000000004 must not ceil into a third charged sheet."""
    if math.isclose(net, round(net), rel_tol=1e-12, abs_tol=1e-12):
        return float(round(net))
    return net


def compute_nest(
    components: list[NestComponent], stock: NestStock, settings: NestSettings
) -> NestResult:
    """One nest = one stock sheet type x one quantity break."""
    if not components:
        raise ValueError("a nest needs at least one component")
    numeric_settings = (
        stock.length_mm,
        stock.width_mm,
        settings.edge_buffer_mm,
        settings.clearance_mm,
        settings.kerf_mm,
        settings.drop_threshold_pct,
    )
    if not all(math.isfinite(v) for v in numeric_settings):
        raise ValueError("sheet and nest settings must be finite numbers")
    if settings.edge_buffer_mm < 0 or settings.clearance_mm < 0 or settings.kerf_mm < 0:
        raise ValueError("edge buffer, clearance and kerf must not be negative")
    if not 0 <= settings.drop_threshold_pct <= 100:
        raise ValueError("drop threshold must be between 0 and 100 percent")
    usable_x = stock.length_mm - 2 * settings.edge_buffer_mm
    usable_y = stock.width_mm - 2 * settings.edge_buffer_mm
    if usable_x <= 0 or usable_y <= 0:
        raise ValueError("sheet dimensions must exceed twice the edge buffer")
    if stock.sheet_cost < 0:
        raise ValueError("sheet cost must not be negative")
    usable_area = usable_x * usable_y
    pad = settings.clearance_mm + settings.kerf_mm
    for comp in components:
        if comp.make_qty <= 0:
            raise ValueError(f"make_qty must be positive (component {comp.key!r})")
        dims = (comp.flat_x_mm, comp.flat_y_mm, comp.flat_area_mm2, comp.contour_length_mm)
        if not all(math.isfinite(v) for v in dims):
            raise ValueError(f"component {comp.key!r} geometry must be finite")
        if comp.flat_x_mm <= 0 or comp.flat_y_mm <= 0 or comp.flat_area_mm2 <= 0:
            raise ValueError(f"component {comp.key!r} geometry must be positive")
        if comp.contour_length_mm < 0:
            raise ValueError(f"component {comp.key!r} contour must not be negative")
        # rotation-allowed fit: longer part side within the longer usable side,
        # shorter within the shorter
        fits = max(comp.flat_x_mm, comp.flat_y_mm) + pad <= max(usable_x, usable_y) and min(
            comp.flat_x_mm, comp.flat_y_mm
        ) + pad <= min(usable_x, usable_y)
        if not fits or _effective_area(comp, settings) > usable_area:
            raise ValueError(f"component {comp.key!r} does not fit the usable sheet")

    # spec pseudocode: fractional net sheets from effective (buffer/kerf-padded) area
    net = _snap_net(
        sum(_effective_area(c, settings) * c.make_qty for c in components) / usable_area
    )

    # ceil_or_frac via the drop threshold (module docstring pins the reading)
    fraction = net - math.floor(net)
    threshold = settings.drop_threshold_pct / 100.0
    dropped = 0.0 < fraction < threshold
    charged = net if dropped else float(math.ceil(net))
    gross = math.ceil(net) if net > 0 else 0

    material_cost = (Decimal(repr(charged)) * stock.sheet_cost).quantize(
        _CENT4, rounding=ROUND_HALF_UP
    )

    # cost distribution: explicit percentages (normalised over their sum) win;
    # default is the spec's "Area of parts" method on true flat areas.
    # Explicit pcts are all-or-none — mixing would silently zero the implicit
    # components (the API validates this too; belt and braces here).
    explicit = [c.cost_distribution_pct for c in components]
    if any(p is not None for p in explicit):
        if any(p is None for p in explicit):
            raise ValueError("cost distribution percentages must be set for all components or none")
        weights = [p if p is not None else Decimal(0) for p in explicit]
    else:
        weights = [Decimal(repr(c.flat_area_mm2 * c.make_qty)) for c in components]
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("cost distribution weights must sum to a positive value")
    if any(w < 0 for w in weights):
        raise ValueError("cost distribution weights must not be negative")

    # The largest-weight component takes the rounding remainder so the parts
    # sum EXACTLY to material_cost; pinning it to the largest (not the last)
    # keeps a 0 %-share component from absorbing negative rounding dust.
    remainder_index = max(range(len(components)), key=lambda i: weights[i])
    allocations = [
        (material_cost * (weights[i] / total_weight)).quantize(_CENT4, rounding=ROUND_HALF_UP)
        for i in range(len(components))
    ]
    allocations[remainder_index] = material_cost - sum(
        a for i, a in enumerate(allocations) if i != remainder_index
    )
    results: list[ComponentResult] = []
    for i, comp in enumerate(components):
        share = weights[i] / total_weight
        results.append(
            ComponentResult(
                key=comp.key,
                parts_per_sheet=math.floor(usable_area / _effective_area(comp, settings)),
                effective_area_mm2=_effective_area(comp, settings),
                used_area_mm2=comp.flat_area_mm2 * comp.make_qty,
                cost_share_pct=(share * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                allocated_cost=allocations[i],
            )
        )

    sheet_area = stock.length_mm * stock.width_mm
    gross_area = gross * sheet_area
    used_area = sum(c.flat_area_mm2 * c.make_qty for c in components)
    drop_area = (gross - net) * sheet_area if dropped else 0.0
    scrap_area = gross_area - used_area - drop_area

    return NestResult(
        net_sheet_used=net,
        charged_sheets=charged,
        gross_sheets=gross,
        material_cost=material_cost,
        used_area_mm2=used_area,
        scrap_area_mm2=scrap_area,
        drop_area_mm2=drop_area,
        total_contour_length_mm=sum(c.contour_length_mm * c.make_qty for c in components),
        components=results,
    )
