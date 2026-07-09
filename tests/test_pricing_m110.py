"""Tests for M1.10 — costing roll-up + pricing (markup / margin / target-margin)
+ discounts.

Three layers:

* **Pure math** — the pricing-item arithmetic (`app.pricing`): markup off cost,
  margin `cost x pct/(1-pct)` (DECISIONS.md 2026-06-14), the target-margin
  back-solve + unreachable state (DECISIONS.md 2026-07-09), the 2-dp half-up
  price boundary. Mandatory per CLAUDE.md §9 (pricing math is test-first).
* **The six Demo E goldens** (real RLS-bound Postgres, through the API): each
  reproduces its verified figure exactly — 2.160,84 / 1.837,10 / 2.028,72 /
  1.957,74 / 2.124,51 / 928,64 + 857,20 (EUR; DemoE frames 07-15, DECISIONS.md
  2026-07-09 rounding model). Fixture inputs are the reverse-engineered 4-dp
  internals documented per example.
* **Behavior** — discounts after markup on the rounded unit (`unit x qty =
  total`); manual `pct`/unit-price overrides surviving reprice; target-margin
  single-item validation; def snapshot-on-attach + Refresh Pricing (E4-d).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole, ObtainMethod, OpCategory
from app.pricing import margin_amount, markup_amount, round_price, target_margin_amount
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]


# --------------------------------------------------------------------------- #
# Pure math
# --------------------------------------------------------------------------- #
def test_markup_amount_off_cost() -> None:
    # Demo E Ex1: 60% on 674.208 → 404.5248 (never compounds on a running price)
    assert markup_amount(Decimal("674.208"), Decimal("60")) == Decimal("404.5248")
    assert markup_amount(Decimal("0"), Decimal("60")) == Decimal("0.0000")


def test_margin_amount_nets_pct_on_slice() -> None:
    # Sell = Cost/(1-pct) ⇒ amount = cost x pct/(1-pct)  (DECISIONS.md 2026-06-14)
    assert margin_amount(Decimal("100"), Decimal("20")) == Decimal("25.0000")
    assert margin_amount(Decimal("100"), Decimal("50")) == Decimal("100.0000")


def test_margin_at_or_over_100_is_unpriceable() -> None:
    assert margin_amount(Decimal("100"), Decimal("100")) is None
    assert margin_amount(Decimal("100"), Decimal("120")) is None


def test_target_margin_back_solve() -> None:
    # profit/total = m ⇒ amount = m/(1-m) x cost - Σ others  (holding others fixed)
    amount, unreachable = target_margin_amount(Decimal("1000"), Decimal("20"), Decimal("100"))
    assert (amount, unreachable) == (Decimal("150.0000"), False)
    # check: total = 1000+100+150 = 1250; profit = 250; 250/1250 = 20% ✓


def test_target_margin_unreachable_contributes_zero() -> None:
    # other items already exceed the target → flag, never a negative amount
    amount, unreachable = target_margin_amount(Decimal("1000"), Decimal("5"), Decimal("100"))
    assert (amount, unreachable) == (Decimal("0.0000"), True)
    # a target ≥ 100% can never be met by a finite price
    amount, unreachable = target_margin_amount(Decimal("1000"), Decimal("100"), Decimal("0"))
    assert (amount, unreachable) == (Decimal("0.0000"), True)


def test_price_boundary_rounds_half_up() -> None:
    # kaufmännische Rundung at the 2-dp unit-price boundary (DECISIONS.md 2026-07-09)
    assert round_price(Decimal("2160.8396")) == Decimal("2160.84")
    assert round_price(Decimal("2160.8349")) == Decimal("2160.83")
    assert round_price(Decimal("0.005")) == Decimal("0.01")


# --------------------------------------------------------------------------- #
# API choreography helpers
# --------------------------------------------------------------------------- #
def _org_admin(seeder: Seeder, slug: str = "org-a") -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _new_component(client: TestClient, quantities: list[int] | None = None) -> str:
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    if quantities:
        res = client.put(
            f"/api/quotes/{qid}/items/{item['id']}/quantities", json={"quantities": quantities}
        )
        assert res.status_code == 200, res.text
    return str(item["root_component_id"])


def _add_manual_op(
    client: TestClient, component_id: str, name: str, cost: str, quantity: int = 1, **extra: Any
) -> str:
    """A router row whose effective cost is a fixed 4-dp figure (manual cell)."""
    created = client.post(
        f"/api/components/{component_id}/operations", json={"name": name, **extra}
    )
    assert created.status_code == 201, created.text
    op = next(o for o in created.json()["operations"] if o["name"] == name)
    res = client.patch(f"/api/operations/{op['id']}/cells/{quantity}", json={"manual_cost": cost})
    assert res.status_code == 200, res.text
    return str(op["id"])


def _add_pricing_item(client: TestClient, component_id: str, **payload: Any) -> dict[str, Any]:
    res = client.post(f"/api/components/{component_id}/pricing-items", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _pricing(client: TestClient, component_id: str) -> dict[str, Any]:
    res = client.get(f"/api/components/{component_id}/pricing")
    assert res.status_code == 200, res.text
    return res.json()


def _total_row(pricing: dict[str, Any], quantity: int) -> dict[str, Any]:
    return next(t for t in pricing["totals"] if t["quantity"] == quantity)


def _costing_row(pricing: dict[str, Any], quantity: int) -> dict[str, Any]:
    return next(c for c in pricing["costing"] if c["quantity"] == quantity)


def _item_cell(pricing: dict[str, Any], item_name: str, quantity: int) -> dict[str, Any]:
    item = next(i for i in pricing["pricing_items"] if i["name"] == item_name)
    return next(c for c in item["cells"] if c["quantity"] == quantity)


DIFFICULT_MATERIAL_FORMULA = """\
total = 0
for component in get_components():
    m = component.part.material
    if m and is_a_in_b('Titan', m):
        for mat in get_material_operations(component):
            total += mat.cost
set_custom_cost(total)
PERCENTAGE = 10
"""


# --------------------------------------------------------------------------- #
# Demo E goldens (frames 07-15; DECISIONS.md 2026-07-09 fixture internals)
# --------------------------------------------------------------------------- #
def test_golden_ex1_difficult_material(app_client: TestClient, seeder: Seeder) -> None:
    """Ex1 — custom category over the titanium slice of an assembly's material.

    Internals: Top (Titan Grade 5) material 539.3680 + Base (Alu) material
    134.8400 → Raw Material 674.2080; root inside 1019.8000; purchased child
    8.3700 → Total Estimated Cost 1702.3780. Raw Material Markup 60% (404.5248)
    + Difficult Material Markup 10% of the titanium slice (53.9368) →
    Total = 2160.8396 → **2.160,84 €** (frame 07)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "CNC Bearbeitung", "1019.8000")

        top = seeder.bom_child(org, uuid.UUID(component), material_display="Titan Grade 5 (3.7165)")
        seeder.operation(
            org,
            top,
            "Titan Rohmaterial",
            category=OpCategory.material,
            cost_formula="COST = 539.368\nDAYS = 0\n",
        )
        base = seeder.bom_child(org, uuid.UUID(component), material_display="Aluminium 6061")
        seeder.operation(
            org,
            base,
            "Alu Rohmaterial",
            category=OpCategory.material,
            cost_formula="COST = 134.84\nDAYS = 0\n",
        )
        seeder.bom_child(
            org,
            uuid.UUID(component),
            obtain_method=ObtainMethod.purchased,
            piece_price=Decimal("8.3700"),
        )

        _add_pricing_item(
            app_client,
            component,
            name="Raw Material Markup",
            calc_type="markup",
            category="material",
            default_pct="60",
        )
        _add_pricing_item(
            app_client,
            component,
            name="Difficult Material Markup",
            calc_type="markup",
            is_custom=True,
            custom_category_name="Difficult Material",
            color="#8b1e3f",
            formula=DIFFICULT_MATERIAL_FORMULA,
        )

        pricing = _pricing(app_client, component)
        costing = _costing_row(pricing, 1)
        assert Decimal(costing["material"]) == Decimal("674.2080")
        assert Decimal(costing["inside"]) == Decimal("1019.8000")
        assert Decimal(costing["purchased_component"]) == Decimal("8.3700")
        assert Decimal(costing["total"]) == Decimal("1702.3780")
        custom_row = costing["custom_rows"][0]
        assert custom_row["name"] == "Difficult Material"
        assert Decimal(custom_row["cost"]) == Decimal("539.3680")

        assert Decimal(_item_cell(pricing, "Raw Material Markup", 1)["amount"]) == Decimal(
            "404.5248"
        )
        assert Decimal(_item_cell(pricing, "Difficult Material Markup", 1)["amount"]) == Decimal(
            "53.9368"
        )
        total = _total_row(pricing, 1)
        assert Decimal(total["unit_price"]) == Decimal("2160.84")
        assert Decimal(total["total_price"]) == Decimal("2160.84")


def test_golden_ex2_laser_workcenter(app_client: TestClient, seeder: Seeder) -> None:
    """Ex2 — one work center inside Inside Processing carries extra margin.

    Internals: material 566.3340; Laser Workcenter 178.1690 + CNC Fräsen
    841.6395 → Inside 1019.8085; purchased 8.7800 → cost 1594.9225. Inside 22%
    (224.3579) + Laser 10% (17.8169) → 1837.0973 → **1.837,10 €** (frame 08);
    the laser slice carries 32%, the rest 22% — additive, never double-counted."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "Rohmaterial", "566.3340", category="material")
        _add_manual_op(app_client, component, "Laser Workcenter", "178.1690")
        _add_manual_op(app_client, component, "CNC Fräsen", "841.6395")
        seeder.bom_child(
            org,
            uuid.UUID(component),
            obtain_method=ObtainMethod.purchased,
            piece_price=Decimal("8.7800"),
        )
        _add_pricing_item(
            app_client,
            component,
            name="Inside Operations Markup",
            calc_type="markup",
            category="inside",
            default_pct="22",
        )
        _add_pricing_item(
            app_client,
            component,
            name="Laser Workcenter Markup",
            calc_type="markup",
            is_custom=True,
            custom_category_name="Laser Workcenter",
            color="#4b3f72",
            formula=(
                "total = 0\n"
                "for component in get_components():\n"
                "    for op in get_operations(component):\n"
                "        if op.name == 'Laser Workcenter':\n"
                "            total += op.cost\n"
                "set_custom_cost(total)\n"
                "PERCENTAGE = 10\n"
            ),
        )

        pricing = _pricing(app_client, component)
        costing = _costing_row(pricing, 1)
        assert Decimal(costing["inside"]) == Decimal("1019.8085")
        assert Decimal(costing["total"]) == Decimal("1594.9225")
        assert Decimal(costing["custom_rows"][0]["cost"]) == Decimal("178.1690")
        assert Decimal(_item_cell(pricing, "Inside Operations Markup", 1)["amount"]) == Decimal(
            "224.3579"
        )
        assert Decimal(_item_cell(pricing, "Laser Workcenter Markup", 1)["amount"]) == Decimal(
            "17.8169"
        )
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("1837.10")


def test_golden_ex3_labor_vs_overhead(app_client: TestClient, seeder: Seeder) -> None:
    """Ex3 — Inside split into Labor vs Overhead, each marked up on top of the
    whole-Inside markup.

    Internals: material 674.2010; Montage (Lohn) 632.6790 + Gemeinkosten
    387.1290 → Inside 1019.8080; purchased 8.3700 → cost 1702.3790. Inside 22%
    (224.3578) + Labor 10% (63.2679) + Overhead 10% (38.7129) → 2028.7176 →
    **2.028,72 €** (frame 09)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "Rohmaterial", "674.2010", category="material")
        _add_manual_op(app_client, component, "Montage (Lohn)", "632.6790")
        _add_manual_op(app_client, component, "Gemeinkosten", "387.1290")
        seeder.bom_child(
            org,
            uuid.UUID(component),
            obtain_method=ObtainMethod.purchased,
            piece_price=Decimal("8.3700"),
        )
        _add_pricing_item(
            app_client,
            component,
            name="Inside Operations Markup",
            calc_type="markup",
            category="inside",
            default_pct="22",
        )
        for item_name, op_name, color, category_name in (
            ("Labor Markup (Exclude Overhead)", "Montage (Lohn)", "#3d2b56", "Inside Labor"),
            ("Overhead Markup (Exclude Labor)", "Gemeinkosten", "#2f5d50", "Inside Overhead"),
        ):
            _add_pricing_item(
                app_client,
                component,
                name=item_name,
                calc_type="markup",
                is_custom=True,
                custom_category_name=category_name,
                color=color,
                formula=(
                    "total = 0\n"
                    "for component in get_components():\n"
                    "    for op in get_operations(component):\n"
                    f"        if op.name == '{op_name}':\n"
                    "            total += op.cost\n"
                    "set_custom_cost(total)\n"
                    "PERCENTAGE = 10\n"
                ),
            )

        pricing = _pricing(app_client, component)
        assert Decimal(_costing_row(pricing, 1)["total"]) == Decimal("1702.3790")
        by_name = {c["name"]: c for c in _costing_row(pricing, 1)["custom_rows"]}
        assert Decimal(by_name["Inside Labor"]["cost"]) == Decimal("632.6790")
        assert Decimal(by_name["Inside Overhead"]["cost"]) == Decimal("387.1290")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("2028.72")


def test_golden_ex4_piece_price_vs_tooling(app_client: TestClient, seeder: Seeder) -> None:
    """Ex4 — tooling separated from piece price; a General markup on top.

    Internals: material 674.2040; CNC 929.8050 + Werkzeugbau 90.0000 → Inside
    1019.8050; purchased 8.3700 → cost 1702.3790. General 5% (85.1190) + Piece
    Price 10% of (cost - tooling) (161.2379) + Tooling 10% (9.0000) →
    1957.7359 → **1.957,74 €** (frame 11)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "Rohmaterial", "674.2040", category="material")
        _add_manual_op(app_client, component, "CNC Bearbeitung", "929.8050")
        _add_manual_op(app_client, component, "Werkzeugbau", "90.0000")
        seeder.bom_child(
            org,
            uuid.UUID(component),
            obtain_method=ObtainMethod.purchased,
            piece_price=Decimal("8.3700"),
        )
        _add_pricing_item(
            app_client, component, name="General Markup", calc_type="markup", default_pct="5"
        )
        _add_pricing_item(
            app_client,
            component,
            name="Piece Price Markup",
            calc_type="markup",
            is_custom=True,
            custom_category_name="Piece Price",
            color="#333333",
            formula=(
                "tooling = 0\n"
                "for component in get_components():\n"
                "    for op in get_operations(component):\n"
                "        if op.name == 'Werkzeugbau':\n"
                "            tooling += op.cost\n"
                "set_custom_cost(TOTAL_COST - tooling)\n"
                "PERCENTAGE = 10\n"
            ),
        )
        _add_pricing_item(
            app_client,
            component,
            name="Tooling Markup",
            calc_type="markup",
            is_custom=True,
            custom_category_name="Tooling",
            color="#1d4ed8",
            formula=(
                "total = 0\n"
                "for component in get_components():\n"
                "    for op in get_operations(component):\n"
                "        if op.name == 'Werkzeugbau':\n"
                "            total += op.cost\n"
                "set_custom_cost(total)\n"
                "PERCENTAGE = 10\n"
            ),
        )

        pricing = _pricing(app_client, component)
        by_name = {c["name"]: c for c in _costing_row(pricing, 1)["custom_rows"]}
        assert Decimal(by_name["Piece Price"]["cost"]) == Decimal("1612.3790")
        assert Decimal(by_name["Tooling"]["cost"]) == Decimal("90.0000")
        assert Decimal(_item_cell(pricing, "General Markup", 1)["amount"]) == Decimal("85.1190")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("1957.74")


def test_golden_ex5_outside_finishes(app_client: TestClient, seeder: Seeder) -> None:
    """Ex5 — only the outside *finish* services carry the extra markup.

    Internals: material 566.3340; inside 1219.8040; Pulverbeschichten (outside
    finish) 300.0000; purchased 8.3700 → cost 2094.5080. Outside Finishes 10%
    (30.0000) → 2124.5080 → **2.124,51 €** (frame 12)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "Rohmaterial", "566.3340", category="material")
        _add_manual_op(app_client, component, "CNC Bearbeitung", "1219.8040")
        _add_manual_op(
            app_client,
            component,
            "Pulverbeschichten",
            "300.0000",
            is_outside_service=True,
            is_finish=True,
        )
        seeder.bom_child(
            org,
            uuid.UUID(component),
            obtain_method=ObtainMethod.purchased,
            piece_price=Decimal("8.3700"),
        )
        _add_pricing_item(
            app_client,
            component,
            name="Outside Finishes Markup",
            calc_type="markup",
            is_custom=True,
            custom_category_name="Outside Finishes",
            color="#8a6d1d",
            formula=(
                "total = 0\n"
                "for component in get_components():\n"
                "    for op in get_operations(component):\n"
                "        if op.is_outside_service and op.is_finish:\n"
                "            total += op.cost\n"
                "set_custom_cost(total)\n"
                "PERCENTAGE = 10\n"
            ),
        )

        pricing = _pricing(app_client, component)
        costing = _costing_row(pricing, 1)
        assert Decimal(costing["outside"]) == Decimal("300.0000")
        assert Decimal(costing["total"]) == Decimal("2094.5080")
        assert Decimal(costing["custom_rows"][0]["cost"]) == Decimal("300.0000")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("2124.51")


COMPLEXITY_FORMULA = """\
level = 'Level 2'
for component in get_components():
    for op in get_operations(component):
        if is_a_in_b('PartLevel', op.name):
            level = op.get_variable('Part Level', 'Level 2')
PERCENTAGE = 20
if level == 'Level 3':
    PERCENTAGE = 30
set_profit_item_name('{} Markup'.format(level))
"""


def test_golden_ex6_complexity_driven_markup(app_client: TestClient, seeder: Seeder) -> None:
    """Ex6 — the markup % follows a PartLevel complexity operation; overriding
    L3→L2 instantly re-prices.

    Internals: material 102.0540 + CNC 612.2820 → cost 714.3360. Level 3 → 30%
    (214.3008) → 928.6368 → **928,64 €** (frame 14); override to Level 2 → 20%
    (142.8672) → 857.2032 → **857,20 €** (frame 15)."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "Rohmaterial", "102.0540", category="material")
        _add_manual_op(app_client, component, "CNC Bearbeitung", "612.2820")
        part_level_op = _add_manual_op(app_client, component, "PartLevel (Critical Info)", "0")
        res = app_client.put(
            f"/api/operations/{part_level_op}/variables",
            json={"overrides": {"Part Level": "Level 3"}},
        )
        assert res.status_code == 200, res.text

        _add_pricing_item(
            app_client,
            component,
            name="Part Level Markup",
            calc_type="markup",
            formula=COMPLEXITY_FORMULA,
        )

        pricing = _pricing(app_client, component)
        cell = _item_cell(pricing, "Part Level Markup", 1)
        assert Decimal(cell["pct"]) == Decimal("30.0000")
        assert Decimal(cell["amount"]) == Decimal("214.3008")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("928.64")

        # override the complexity op L3 → L2: the % follows the router data
        res = app_client.put(
            f"/api/operations/{part_level_op}/variables",
            json={"overrides": {"Part Level": "Level 2"}},
        )
        assert res.status_code == 200, res.text
        pricing = _pricing(app_client, component)
        cell = _item_cell(pricing, "Part Level Markup", 1)
        assert Decimal(cell["pct"]) == Decimal("20.0000")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("857.20")


# --------------------------------------------------------------------------- #
# Behavior — discounts, overrides, target margin, freeze/refresh
# --------------------------------------------------------------------------- #
def test_discounts_apply_after_markup_on_rounded_unit(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Spec #kalk-rollup: discounted_unit = rounded_unit x (1 - Σ pct/100);
    percentages sum (not compound); `unit x qty = total` holds exactly."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client, quantities=[3])
        _add_manual_op(app_client, component, "CNC", "100.0100", quantity=3)
        _add_pricing_item(
            app_client, component, name="General Markup", calc_type="markup", default_pct="20"
        )
        for name, pct in (("Treuerabatt", "5"), ("Aktionsrabatt", "10")):
            res = app_client.post(
                f"/api/components/{component}/discounts",
                json={"name": name, "default_pct": pct},
            )
            assert res.status_code == 201, res.text

        pricing = _pricing(app_client, component)
        total = _total_row(pricing, 3)
        # cost 100.01 → total excl. 120.012 → unit round2 = 40.00
        assert Decimal(total["calc_unit_price"]) == Decimal("40.00")
        # 15% off the ROUNDED unit: 40.00 x 0.85 = 34.00; invariant 34x3 = 102
        assert Decimal(total["unit_price"]) == Decimal("34.00")
        assert Decimal(total["total_price"]) == Decimal("102.00")
        assert Decimal(total["total_discount"]) == Decimal("18.00")
        assert Decimal(total["total_discount_pct"]) == Decimal("15.0000")


def test_margin_item_prices_the_slice(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "CNC", "100.0000")
        _add_pricing_item(
            app_client, component, name="Inside Margin", calc_type="margin", default_pct="20"
        )
        pricing = _pricing(app_client, component)
        # margin 20% on 100 → amount 25 → total 125; profit/total = 20% ✓
        total = _total_row(pricing, 1)
        assert Decimal(total["total_price"]) == Decimal("125.00")
        assert Decimal(total["profit_margin_pct"]) == Decimal("20.0000")


def test_target_margin_back_solves_and_flags_unreachable(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "CNC", "1000.0000")
        _add_pricing_item(
            app_client, component, name="General Markup", calc_type="markup", default_pct="10"
        )
        target = _add_pricing_item(
            app_client,
            component,
            name="Zielmarge",
            calc_type="target_margin",
            default_pct="20",
        )
        pricing = _pricing(app_client, component)
        cell = _item_cell(pricing, "Zielmarge", 1)
        assert Decimal(cell["amount"]) == Decimal("150.0000")
        assert cell["unreachable"] is False
        total = _total_row(pricing, 1)
        assert Decimal(total["total_price"]) == Decimal("1250.00")
        assert Decimal(total["profit_margin_pct"]) == Decimal("20.0000")

        # a second target-margin item is mathematically ill-defined → 422
        second = app_client.post(
            f"/api/components/{component}/pricing-items",
            json={"name": "Noch eine Zielmarge", "calc_type": "target_margin"},
        )
        assert second.status_code == 422
        assert second.json()["code"] == "duplicate_target_margin"

        # unreachable: the 10% markup alone already exceeds a 5% target
        res = app_client.patch(
            f"/api/pricing-items/{target['id']}/cells/1", json={"manual_pct": "5"}
        )
        assert res.status_code == 200, res.text
        pricing = _pricing(app_client, component)
        cell = _item_cell(pricing, "Zielmarge", 1)
        assert cell["unreachable"] is True
        assert Decimal(cell["amount"]) == Decimal("0.0000")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("1100.00")


def test_manual_pct_override_survives_reprice(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        op = _add_manual_op(app_client, component, "CNC", "100.0000")
        item = _add_pricing_item(
            app_client, component, name="General Markup", calc_type="markup", default_pct="10"
        )
        res = app_client.patch(
            f"/api/pricing-items/{item['id']}/cells/1", json={"manual_pct": "25"}
        )
        assert res.status_code == 200, res.text
        # reprice via a cost change — the override must survive and keep winning
        res = app_client.patch(f"/api/operations/{op}/cells/1", json={"manual_cost": "200.0000"})
        assert res.status_code == 200, res.text
        pricing = _pricing(app_client, component)
        cell = _item_cell(pricing, "General Markup", 1)
        assert Decimal(cell["manual_pct"]) == Decimal("25.0000")
        assert Decimal(cell["amount"]) == Decimal("50.0000")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("250.00")


def test_manual_unit_price_override(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        component = _new_component(app_client)
        _add_manual_op(app_client, component, "CNC", "100.0000")
        _add_pricing_item(
            app_client, component, name="General Markup", calc_type="markup", default_pct="20"
        )
        res = app_client.patch(
            f"/api/components/{component}/price/1", json={"manual_unit_price": "150.00"}
        )
        assert res.status_code == 200, res.text
        pricing = _pricing(app_client, component)
        total = _total_row(pricing, 1)
        # calc side retained beneath the override (calc-vs-override invariant)
        assert Decimal(total["calc_unit_price"]) == Decimal("120.00")
        assert Decimal(total["unit_price"]) == Decimal("150.00")
        assert Decimal(total["total_price"]) == Decimal("150.00")
        # clearing the override falls back to calculated
        res = app_client.patch(
            f"/api/components/{component}/price/1", json={"manual_unit_price": None}
        )
        assert res.status_code == 200, res.text
        assert Decimal(_total_row(_pricing(app_client, component), 1)["unit_price"]) == Decimal(
            "120.00"
        )


def test_defs_snapshot_on_attach_and_refresh_pricing(
    app_client: TestClient, seeder: Seeder
) -> None:
    """E4-d: config edits never touch existing drafts; Refresh Pricing
    re-snapshots `is_from_factory` rows and re-evaluates, preserving overrides."""
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/pricing-item-defs",
            json={"name": "General Markup", "calc_type": "markup", "default_pct": "10"},
        )
        assert res.status_code == 201, res.text
        def_id = res.json()["id"]

        qid = app_client.post("/api/quotes", json={}).json()["id"]
        item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][0]
        component = str(item["root_component_id"])
        _add_manual_op(app_client, component, "CNC", "100.0000")

        pricing = _pricing(app_client, component)
        attached = pricing["pricing_items"]
        assert [i["name"] for i in attached] == ["General Markup"]
        assert attached[0]["is_from_factory"] is True
        assert attached[0]["source_def_id"] == def_id
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("110.00")

        # editing the def never reprices the existing draft (freeze)
        res = app_client.patch(f"/api/pricing-item-defs/{def_id}", json={"default_pct": "30"})
        assert res.status_code == 200, res.text
        assert Decimal(_total_row(_pricing(app_client, component), 1)["total_price"]) == Decimal(
            "110.00"
        )

        # Refresh Pricing re-snapshots deliberately
        res = app_client.post(f"/api/quotes/{qid}/refresh-pricing")
        assert res.status_code == 200, res.text
        assert Decimal(_total_row(_pricing(app_client, component), 1)["total_price"]) == Decimal(
            "130.00"
        )


def test_refresh_pricing_preserves_manual_overrides(app_client: TestClient, seeder: Seeder) -> None:
    org, user = _org_admin(seeder)
    with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
        res = app_client.post(
            "/api/pricing-item-defs",
            json={"name": "General Markup", "calc_type": "markup", "default_pct": "10"},
        )
        def_id = res.json()["id"]
        qid = app_client.post("/api/quotes", json={}).json()["id"]
        item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][0]
        component = str(item["root_component_id"])
        _add_manual_op(app_client, component, "CNC", "100.0000")
        pricing = _pricing(app_client, component)
        attached_id = pricing["pricing_items"][0]["id"]
        res = app_client.patch(
            f"/api/pricing-items/{attached_id}/cells/1", json={"manual_pct": "50"}
        )
        assert res.status_code == 200, res.text
        app_client.patch(f"/api/pricing-item-defs/{def_id}", json={"default_pct": "30"})
        res = app_client.post(f"/api/quotes/{qid}/refresh-pricing")
        assert res.status_code == 200, res.text
        pricing = _pricing(app_client, component)
        cell = _item_cell(pricing, "General Markup", 1)
        # the re-snapshot updated the calc side; the estimator's 50% still wins
        assert Decimal(cell["calc_pct"]) == Decimal("30.0000")
        assert Decimal(cell["manual_pct"]) == Decimal("50.0000")
        assert Decimal(_total_row(pricing, 1)["total_price"]) == Decimal("150.00")


def test_pricing_isolated_across_orgs(app_client: TestClient, seeder: Seeder) -> None:
    org_a, user_a = _org_admin(seeder, "org-a")
    org_b, user_b = _org_admin(seeder, "org-b")
    with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
        component = _new_component(app_client)
        item = _add_pricing_item(
            app_client, component, name="General Markup", calc_type="markup", default_pct="10"
        )
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        assert app_client.get(f"/api/components/{component}/pricing").status_code == 404
        assert (
            app_client.patch(
                f"/api/pricing-items/{item['id']}", json={"default_pct": "99"}
            ).status_code
            == 404
        )
