"""M4.3 — estimation-grade nesting math (spec #nesting pseudocode).

The hand-calc below IS the acceptance golden ("nest math matches a hand-calc",
M4 exit criterion). Worked example, metric (DACH delta: mm / EUR):

Stock sheet 3000 x 1500 mm, cost EUR 250.00/sheet.
Settings: edge buffer 3.0 mm, part-to-part clearance 3.0 mm, kerf 0.25 mm,
drop threshold 25 %.

  usable_area = (3000 - 2*3) * (1500 - 2*3) = 2994 * 1494 = 4_473_036 mm2

Component A: unfolded 200 x 100 mm, true flat area 18_000 mm2, contour 620 mm
Component B: unfolded 150 x 80 mm,  true flat area 11_400 mm2, contour 500 mm

  eff_A = (200 + 3.25) * (100 + 3.25) = 203.25 * 103.25 = 20_985.5625 mm2
  eff_B = (150 + 3.25) * (80 + 3.25)  = 153.25 * 83.25  = 12_758.0625 mm2

  parts_per_sheet_A = floor(4_473_036 / 20_985.5625) = 213
  parts_per_sheet_B = floor(4_473_036 / 12_758.0625) = 350

Break (A x100, B x40):
  net_sheet_used = (20_985.5625*100 + 12_758.0625*40) / 4_473_036
                 = 2_608_878.75 / 4_473_036 = 0.58324656...
  fraction 0.5832 >= drop threshold 0.25 -> remnant is charged: ceil -> 1 sheet
  material_cost = 1 * 250.00 = 250.0000

  Area-of-parts distribution (true areas): A 1_800_000 : B 456_000
  allocated_A = 250 * 1_800_000/2_256_000 = 199.4681
  allocated_B = 250 - 199.4681           =  50.5319   (remainder keeps the sum exact)

Break (A alone x10):
  net_sheet_used = 209_855.625 / 4_473_036 = 0.04691570...
  fraction < 0.25 -> partial sheet is "dropped"/not charged in full:
  charged = 0.04691570 (fractional), material_cost = 11.7289
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from app.nesting_math import (
    NestComponent,
    NestSettings,
    NestStock,
    compute_nest,
)

STOCK = NestStock(length_mm=3000.0, width_mm=1500.0, sheet_cost=Decimal("250.00"))
SETTINGS = NestSettings(
    edge_buffer_mm=3.0,
    clearance_mm=3.0,
    kerf_mm=0.25,
    drop_threshold_pct=25.0,
)
COMP_A = NestComponent(
    key="A",
    flat_x_mm=200.0,
    flat_y_mm=100.0,
    flat_area_mm2=18_000.0,
    contour_length_mm=620.0,
    make_qty=100,
)
COMP_B = NestComponent(
    key="B",
    flat_x_mm=150.0,
    flat_y_mm=80.0,
    flat_area_mm2=11_400.0,
    contour_length_mm=500.0,
    make_qty=40,
)


class TestHandCalcGolden:
    """The worked example above, assertion by assertion."""

    def test_parts_per_sheet(self) -> None:
        result = compute_nest([COMP_A, COMP_B], STOCK, SETTINGS)
        by_key = {c.key: c for c in result.components}
        assert by_key["A"].parts_per_sheet == 213
        assert by_key["B"].parts_per_sheet == 350

    def test_net_sheet_used_fractional(self) -> None:
        result = compute_nest([COMP_A, COMP_B], STOCK, SETTINGS)
        assert result.net_sheet_used == pytest.approx(0.58324656, abs=1e-6)

    def test_full_sheet_charged_above_drop_threshold(self) -> None:
        result = compute_nest([COMP_A, COMP_B], STOCK, SETTINGS)
        assert result.charged_sheets == pytest.approx(1.0)
        assert result.material_cost == Decimal("250.0000")

    def test_area_of_parts_distribution_sums_exactly(self) -> None:
        result = compute_nest([COMP_A, COMP_B], STOCK, SETTINGS)
        by_key = {c.key: c for c in result.components}
        assert by_key["A"].allocated_cost == Decimal("199.4681")
        assert by_key["B"].allocated_cost == Decimal("50.5319")
        assert sum(c.allocated_cost for c in result.components) == result.material_cost

    def test_fractional_charge_below_drop_threshold(self) -> None:
        small = NestComponent(
            key="A",
            flat_x_mm=200.0,
            flat_y_mm=100.0,
            flat_area_mm2=18_000.0,
            contour_length_mm=620.0,
            make_qty=10,
        )
        result = compute_nest([small], STOCK, SETTINGS)
        assert result.net_sheet_used == pytest.approx(0.04691570, abs=1e-6)
        assert result.charged_sheets == pytest.approx(result.net_sheet_used)
        assert result.material_cost == Decimal("11.7289")
        # the single component carries the whole cost
        assert result.components[0].allocated_cost == Decimal("11.7289")

    def test_metrics_partition_gross_area(self) -> None:
        """used + scrap + drop == gross sheet area (DemoJ/08 percentages sum to 100)."""
        result = compute_nest([COMP_A, COMP_B], STOCK, SETTINGS)
        assert result.gross_sheets == 1
        gross = 1 * 3000.0 * 1500.0
        assert result.used_area_mm2 == pytest.approx(2_256_000.0)
        assert result.drop_area_mm2 == pytest.approx(0.0)  # remnant charged -> scrap
        assert result.used_area_mm2 + result.scrap_area_mm2 + result.drop_area_mm2 == (
            pytest.approx(gross)
        )

    def test_dropped_remnant_is_drop_not_scrap(self) -> None:
        small = NestComponent(
            key="A",
            flat_x_mm=200.0,
            flat_y_mm=100.0,
            flat_area_mm2=18_000.0,
            contour_length_mm=620.0,
            make_qty=10,
        )
        result = compute_nest([small], STOCK, SETTINGS)
        gross = 1 * 3000.0 * 1500.0
        assert result.gross_sheets == 1
        assert result.drop_area_mm2 == pytest.approx((1 - result.net_sheet_used) * gross)
        assert result.used_area_mm2 == pytest.approx(180_000.0)
        assert result.used_area_mm2 + result.scrap_area_mm2 + result.drop_area_mm2 == (
            pytest.approx(gross)
        )

    def test_total_contour_length(self) -> None:
        result = compute_nest([COMP_A, COMP_B], STOCK, SETTINGS)
        assert result.total_contour_length_mm == pytest.approx(620.0 * 100 + 500.0 * 40)


class TestDistributionOverrides:
    def test_manual_cost_distribution_pct(self) -> None:
        a = NestComponent(
            key="A",
            flat_x_mm=200.0,
            flat_y_mm=100.0,
            flat_area_mm2=18_000.0,
            contour_length_mm=620.0,
            make_qty=100,
            cost_distribution_pct=Decimal("60"),
        )
        b = NestComponent(
            key="B",
            flat_x_mm=150.0,
            flat_y_mm=80.0,
            flat_area_mm2=11_400.0,
            contour_length_mm=500.0,
            make_qty=40,
            cost_distribution_pct=Decimal("40"),
        )
        result = compute_nest([a, b], STOCK, SETTINGS)
        by_key = {c.key: c for c in result.components}
        assert by_key["A"].allocated_cost == Decimal("150.0000")
        assert by_key["B"].allocated_cost == Decimal("100.0000")

    def test_partial_pcts_are_normalised(self) -> None:
        # pcts that do not sum to 100 are normalised over their sum
        a = NestComponent(
            key="A",
            flat_x_mm=200.0,
            flat_y_mm=100.0,
            flat_area_mm2=18_000.0,
            contour_length_mm=620.0,
            make_qty=100,
            cost_distribution_pct=Decimal("30"),
        )
        b = NestComponent(
            key="B",
            flat_x_mm=150.0,
            flat_y_mm=80.0,
            flat_area_mm2=11_400.0,
            contour_length_mm=500.0,
            make_qty=40,
            cost_distribution_pct=Decimal("10"),
        )
        result = compute_nest([a, b], STOCK, SETTINGS)
        by_key = {c.key: c for c in result.components}
        assert by_key["A"].allocated_cost == Decimal("187.5000")
        assert by_key["B"].allocated_cost == Decimal("62.5000")


class TestValidation:
    def test_no_components_rejected(self) -> None:
        with pytest.raises(ValueError, match="component"):
            compute_nest([], STOCK, SETTINGS)

    def test_zero_make_qty_rejected(self) -> None:
        bad = NestComponent(
            key="A",
            flat_x_mm=200.0,
            flat_y_mm=100.0,
            flat_area_mm2=18_000.0,
            contour_length_mm=620.0,
            make_qty=0,
        )
        with pytest.raises(ValueError, match="make_qty"):
            compute_nest([bad], STOCK, SETTINGS)

    def test_part_larger_than_usable_sheet_rejected(self) -> None:
        huge = NestComponent(
            key="A",
            flat_x_mm=3200.0,
            flat_y_mm=100.0,
            flat_area_mm2=320_000.0,
            contour_length_mm=6_600.0,
            make_qty=1,
        )
        with pytest.raises(ValueError, match="does not fit"):
            compute_nest([huge], STOCK, SETTINGS)

    def test_part_too_wide_in_both_orientations_rejected(self) -> None:
        # 2000 x 2000 has area headroom on a 3000 x 1500 sheet but exceeds the
        # usable width whichever way it is rotated
        square = NestComponent(
            key="A",
            flat_x_mm=2000.0,
            flat_y_mm=2000.0,
            flat_area_mm2=4_000_000.0,
            contour_length_mm=8_000.0,
            make_qty=1,
        )
        with pytest.raises(ValueError, match="does not fit"):
            compute_nest([square], STOCK, SETTINGS)

    def test_non_positive_sheet_dims_rejected(self) -> None:
        with pytest.raises(ValueError, match="sheet"):
            compute_nest(
                [COMP_A],
                NestStock(length_mm=0.0, width_mm=1500.0, sheet_cost=Decimal("250.00")),
                SETTINGS,
            )

    def test_negative_sheet_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost"):
            compute_nest(
                [COMP_A],
                NestStock(length_mm=3000.0, width_mm=1500.0, sheet_cost=Decimal("-1")),
                SETTINGS,
            )


class TestBoundaries:
    def test_exact_integer_sheets_charge_exactly(self) -> None:
        """net exactly integral -> no partial sheet, charge == net (no drop, no extra)."""
        # engineer an effective footprint that divides the usable area exactly:
        # eff = 499 x 747 mm -> usable 2994 x 1494 holds exactly 12; qty 24 = 2 sheets
        # (dyadic offsets keep the float arithmetic exact)
        comp = NestComponent(
            key="A",
            flat_x_mm=499.0 - 3.25,
            flat_y_mm=747.0 - 3.25,
            flat_area_mm2=300_000.0,
            contour_length_mm=2_500.0,
            make_qty=24,
        )
        result = compute_nest([comp], STOCK, SETTINGS)
        assert result.net_sheet_used == pytest.approx(2.0, abs=1e-9)
        assert result.charged_sheets == pytest.approx(2.0)
        assert result.material_cost == Decimal("500.0000")

    def test_drop_threshold_zero_always_charges_full_sheets(self) -> None:
        """threshold 0: no fraction is ever below it -> always ceil."""
        small = NestComponent(
            key="A",
            flat_x_mm=200.0,
            flat_y_mm=100.0,
            flat_area_mm2=18_000.0,
            contour_length_mm=620.0,
            make_qty=10,
        )
        settings = NestSettings(
            edge_buffer_mm=3.0, clearance_mm=3.0, kerf_mm=0.25, drop_threshold_pct=0.0
        )
        result = compute_nest([small], STOCK, settings)
        assert result.charged_sheets == pytest.approx(1.0)
        assert result.material_cost == Decimal("250.0000")

    def test_multi_sheet_partial_drop(self) -> None:
        """5.1 net sheets, threshold 25 % -> fraction 0.1 dropped, charge 5.1 fractional."""
        usable = (3000.0 - 6.0) * (1500.0 - 6.0)
        eff = 20_985.5625  # COMP_A effective area
        qty = math.floor(5.1 * usable / eff)  # net just under 5.1
        comp = NestComponent(
            key="A",
            flat_x_mm=200.0,
            flat_y_mm=100.0,
            flat_area_mm2=18_000.0,
            contour_length_mm=620.0,
            make_qty=qty,
        )
        result = compute_nest([comp], STOCK, SETTINGS)
        assert 5.0 < result.net_sheet_used < 5.25
        assert result.charged_sheets == pytest.approx(result.net_sheet_used)
        assert result.gross_sheets == 6
