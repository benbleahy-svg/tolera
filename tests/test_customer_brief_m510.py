"""M5.10 — Customer Intelligence Brief (AI Feature 5).

Two tracks:

* Service integration — seed an account with a quote history, run the on-demand
  aggregate + a *registered fake* synthesizer, assert the signals (win rate,
  value range vs history, revision pattern) and the gates (< 3 prior quotes, AI
  toggle off, no account) omit the card with **no Claude call**.
* API route — ``GET /api/quotes/{id}/customer-brief`` returns the brief (fake
  bullets) and is org-scoped; the brief is never persisted.

The Claude call is mocked with a registered fake (``customer_brief.register``),
mirroring the M3.9 triage-enricher pattern — no HTTP/SDK stubbing.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import customer_brief
from app.customer_brief import build_account_aggregate, generate_customer_brief, quote_values
from app.db import make_engine, make_sessionmaker, org_scoped_session
from app.models import MembershipRole, QuoteStatus
from tests.conftest import Seeder, app_role_url, authed

ADMIN = [MembershipRole.admin]
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Fake synthesizer (the single Claude call) — registered per test
# --------------------------------------------------------------------------- #


class _FakeSynth:
    """Records the aggregate it was handed and returns fixed bullets."""

    def __init__(self, bullets: list[str] | None = None) -> None:
        self.calls = 0
        self.last_aggregate: dict[str, Any] | None = None
        self._bullets = bullets if bullets is not None else ["Bestandskunde mit hoher Gewinnquote."]

    async def synthesize(self, aggregate: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.last_aggregate = aggregate
        return {"bullets": self._bullets}


@pytest.fixture
def fake_synth() -> Iterator[_FakeSynth]:
    synth = _FakeSynth()
    customer_brief.register(synth)
    try:
        yield synth
    finally:
        customer_brief.register(None)


# --------------------------------------------------------------------------- #
# Seeding helpers (raw SQL — a priced line item needs part→component→qty chain)
# --------------------------------------------------------------------------- #


def _seed_priced_quote(
    seeder: Seeder,
    org_id: uuid.UUID,
    account_id: uuid.UUID,
    number: str,
    *,
    status: QuoteStatus = QuoteStatus.draft,
    revision: int = 0,
    line_totals: list[str] | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    """A quote with one priced line item per entry in ``line_totals`` (each a
    single ``component_quantity`` break carrying that ``total_price``)."""
    quote_id = seeder.quote(org_id, number, status=status, account_id=account_id)
    if revision or created_at is not None:
        seeder.sql(
            "UPDATE quote SET revision = :rev, "
            "created_at = COALESCE(:ca, created_at) WHERE id = :id AND org_id = :org",
            {"rev": revision, "ca": created_at, "id": str(quote_id), "org": str(org_id)},
        )
    for pos, total in enumerate(line_totals or []):
        part_id = seeder.part(org_id)
        comp_id = uuid.uuid4()
        seeder.sql(
            "INSERT INTO component (id, org_id, part_id, is_root_component) "
            "VALUES (:id, :org, :part, true)",
            {"id": str(comp_id), "org": str(org_id), "part": str(part_id)},
        )
        seeder.sql(
            "INSERT INTO quote_item (id, org_id, quote_id, root_component_id, position) "
            "VALUES (gen_random_uuid(), :org, :q, :c, :pos)",
            {"org": str(org_id), "q": str(quote_id), "c": str(comp_id), "pos": pos},
        )
        seeder.sql(
            "INSERT INTO component_quantity (id, org_id, component_id, quantity, total_price) "
            "VALUES (gen_random_uuid(), :org, :c, 1, :tp)",
            {"org": str(org_id), "c": str(comp_id), "tp": total},
        )
    return quote_id


def _run_aggregate(
    tenancy_db: str,
    org_id: uuid.UUID,
    account_id: uuid.UUID,
    current_quote_id: uuid.UUID,
    *,
    currency: str = "EUR",
    now: datetime = NOW,
) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        engine = make_engine(app_role_url(tenancy_db))
        try:
            sessionmaker = make_sessionmaker(engine)
            async with org_scoped_session(sessionmaker, org_id) as session:
                return await build_account_aggregate(
                    session,
                    account_id=account_id,
                    current_quote_id=current_quote_id,
                    currency=currency,
                    now=now,
                )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _run_quote_values(
    tenancy_db: str, org_id: uuid.UUID, quote_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int | None]:
    async def _run() -> dict[uuid.UUID, int | None]:
        engine = make_engine(app_role_url(tenancy_db))
        try:
            sm = make_sessionmaker(engine)
            async with org_scoped_session(sm, org_id) as session:
                return await quote_values(session, quote_ids)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _run_generate(
    tenancy_db: str, org_id: uuid.UUID, quote_id: uuid.UUID, *, now: datetime = NOW
) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        engine = make_engine(app_role_url(tenancy_db))
        try:
            sessionmaker = make_sessionmaker(engine)
            async with org_scoped_session(sessionmaker, org_id) as session:
                return await generate_customer_brief(
                    session, org_id=org_id, quote_id=quote_id, now=now
                )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Aggregate signals
# --------------------------------------------------------------------------- #


def test_aggregate_win_rate_value_range_and_revision(tenancy_db: str, seeder: Seeder) -> None:
    org_id = seeder.org("brief-agg")
    account_id = seeder.account(org_id, name="Arch Medial Solutions")
    # History: 5 won (all with a revision), 3 lost — win rate 62.5%; prior values
    # 1_200€ .. 12_000€. Current quote 31_000€ = largest, outside range.
    _seed_priced_quote(
        seeder,
        org_id,
        account_id,
        "H-1",
        status=QuoteStatus.won,
        revision=1,
        line_totals=["12000.00"],
    )
    _seed_priced_quote(
        seeder,
        org_id,
        account_id,
        "H-2",
        status=QuoteStatus.won,
        revision=2,
        line_totals=["8000.00"],
    )
    _seed_priced_quote(
        seeder,
        org_id,
        account_id,
        "H-3",
        status=QuoteStatus.won,
        revision=1,
        line_totals=["1200.00"],
    )
    _seed_priced_quote(
        seeder,
        org_id,
        account_id,
        "H-4",
        status=QuoteStatus.won,
        revision=1,
        line_totals=["3000.00"],
    )
    _seed_priced_quote(
        seeder,
        org_id,
        account_id,
        "H-5",
        status=QuoteStatus.won,
        revision=3,
        line_totals=["5000.00"],
    )
    _seed_priced_quote(
        seeder, org_id, account_id, "L-1", status=QuoteStatus.lost, line_totals=["4000.00"]
    )
    _seed_priced_quote(
        seeder, org_id, account_id, "L-2", status=QuoteStatus.lost, line_totals=["2000.00"]
    )
    _seed_priced_quote(
        seeder, org_id, account_id, "L-3", status=QuoteStatus.lost, line_totals=["9000.00"]
    )
    current = _seed_priced_quote(
        seeder,
        org_id,
        account_id,
        "CUR",
        status=QuoteStatus.draft,
        line_totals=["25000.00", "6000.00"],
    )

    agg = _run_aggregate(tenancy_db, org_id, account_id, current)
    assert agg is not None
    assert agg["account_name"] == "Arch Medial Solutions"
    assert agg["prior_quote_count"] == 8
    assert agg["won"] == 5 and agg["lost"] == 3
    assert agg["win_rate_pct"] == 62.5
    # Money in minor units (tier-1 convention).
    assert agg["this_quote_value_minor"] == 3_100_000  # 25_000 + 6_000 €
    assert agg["prior_value_max_minor"] == 1_200_000  # 12_000 €
    assert agg["prior_value_min_minor"] == 120_000  # 1_200 €
    assert agg["this_quote_is_largest"] is True
    assert agg["this_quote_outside_range"] is True
    # Every won quote had a revision → never first-accept.
    assert agg["never_accepts_without_revision"] is True
    assert agg["won_with_revision"] == 5 and agg["won_without_revision"] == 0


def test_aggregate_first_accept_pattern(tenancy_db: str, seeder: Seeder) -> None:
    org_id = seeder.org("brief-firstaccept")
    account_id = seeder.account(org_id, name="Direct Buyer GmbH")
    for n in range(3):
        _seed_priced_quote(
            seeder,
            org_id,
            account_id,
            f"W-{n}",
            status=QuoteStatus.won,
            revision=0,
            line_totals=["1000.00"],
        )
    current = seeder.quote(org_id, "CUR2", status=QuoteStatus.draft, account_id=account_id)
    agg = _run_aggregate(tenancy_db, org_id, account_id, current)
    assert agg is not None
    assert agg["never_accepts_without_revision"] is False
    assert agg["won_without_revision"] == 3
    # No priced line on the current quote → value unknown, not fabricated.
    assert agg["this_quote_value_minor"] is None
    assert agg["this_quote_is_largest"] is False


def test_aggregate_value_range_scoped_to_current_currency(tenancy_db: str, seeder: Seeder) -> None:
    """A CHF quote's value must be ranged only against the account's other CHF
    quotes — EUR history must never enter the band (tier-1 money rule)."""
    org_id = seeder.org("brief-currency")
    account_id = seeder.account(org_id, name="Mixed Currency AG")
    # Two EUR priors at 50_000€ and one CHF prior at 1_000 CHF.
    for n, total in enumerate(["50000.00", "50000.00"]):
        q = _seed_priced_quote(
            seeder, org_id, account_id, f"EUR-{n}", status=QuoteStatus.won, line_totals=[total]
        )
        seeder.sql(
            "UPDATE quote SET currency = 'EUR' WHERE id = :id AND org_id = :org",
            {"id": str(q), "org": str(org_id)},
        )
    chf_prior = _seed_priced_quote(
        seeder, org_id, account_id, "CHF-1", status=QuoteStatus.lost, line_totals=["1000.00"]
    )
    seeder.sql(
        "UPDATE quote SET currency = 'CHF' WHERE id = :id AND org_id = :org",
        {"id": str(chf_prior), "org": str(org_id)},
    )
    # Current quote is CHF at 2_000 CHF — largest CHF, but far below the EUR figures.
    current = _seed_priced_quote(
        seeder, org_id, account_id, "CUR-CHF", status=QuoteStatus.draft, line_totals=["2000.00"]
    )
    seeder.sql(
        "UPDATE quote SET currency = 'CHF' WHERE id = :id AND org_id = :org",
        {"id": str(current), "org": str(org_id)},
    )
    agg = _run_aggregate(tenancy_db, org_id, account_id, current, currency="CHF")
    assert agg is not None
    # Only the single CHF prior (1_000 CHF) is in range — the EUR 50k are excluded.
    assert agg["prior_value_max_minor"] == 100_000  # 1_000 CHF, not 50_000 €
    assert agg["this_quote_is_largest"] is True  # 2_000 > 1_000 CHF


def test_aggregate_below_threshold_returns_none(tenancy_db: str, seeder: Seeder) -> None:
    org_id = seeder.org("brief-thresh")
    account_id = seeder.account(org_id, name="Sparse Corp")
    seeder.quote(org_id, "P-1", status=QuoteStatus.won, account_id=account_id)
    seeder.quote(org_id, "P-2", status=QuoteStatus.lost, account_id=account_id)
    current = seeder.quote(org_id, "CUR3", status=QuoteStatus.draft, account_id=account_id)
    # Only 2 prior quotes < MIN_PRIOR_QUOTES → omitted (no empty state).
    assert _run_aggregate(tenancy_db, org_id, account_id, current) is None


def test_aggregate_excludes_trashed_prior_quotes(tenancy_db: str, seeder: Seeder) -> None:
    org_id = seeder.org("brief-trash")
    account_id = seeder.account(org_id, name="Trashy Ltd")
    for n in range(3):
        seeder.quote(org_id, f"K-{n}", status=QuoteStatus.won, account_id=account_id)
    trashed = seeder.quote(org_id, "TRASH", status=QuoteStatus.won, account_id=account_id)
    seeder.sql(
        "UPDATE quote SET deleted_at = now() WHERE id = :id AND org_id = :org",
        {"id": str(trashed), "org": str(org_id)},
    )
    current = seeder.quote(org_id, "CUR4", status=QuoteStatus.draft, account_id=account_id)
    agg = _run_aggregate(tenancy_db, org_id, account_id, current)
    assert agg is not None
    assert agg["prior_quote_count"] == 3  # trashed one not counted


def test_twelve_month_trend_uses_recent_window(tenancy_db: str, seeder: Seeder) -> None:
    org_id = seeder.org("brief-trend")
    account_id = seeder.account(org_id, name="Trending AG")
    # Old wins (>12mo ago) + a recent loss: overall 3-1, but recent window 0-1.
    old = NOW - timedelta(days=500)
    for n in range(3):
        _seed_priced_quote(
            seeder, org_id, account_id, f"OLD-{n}", status=QuoteStatus.won, created_at=old
        )
    _seed_priced_quote(
        seeder,
        org_id,
        account_id,
        "RECENT",
        status=QuoteStatus.lost,
        created_at=NOW - timedelta(days=30),
    )
    current = seeder.quote(org_id, "CUR5", status=QuoteStatus.draft, account_id=account_id)
    agg = _run_aggregate(tenancy_db, org_id, account_id, current)
    assert agg is not None
    assert agg["won"] == 3 and agg["lost"] == 1
    assert agg["won_last_12mo"] == 0 and agg["lost_last_12mo"] == 1


# --------------------------------------------------------------------------- #
# quote_values — the representative per-quote total
# --------------------------------------------------------------------------- #


def test_quote_values_sums_highest_break_per_line(tenancy_db: str, seeder: Seeder) -> None:
    org_id = seeder.org("brief-values")
    account_id = seeder.account(org_id, name="Val Co")
    quote_id = seeder.quote(org_id, "V-1", status=QuoteStatus.draft, account_id=account_id)
    # One line item with two breaks — value must use the highest-quantity break.
    part_id = seeder.part(org_id)
    comp_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO component (id, org_id, part_id, is_root_component) "
        "VALUES (:id, :org, :part, true)",
        {"id": str(comp_id), "org": str(org_id), "part": str(part_id)},
    )
    seeder.sql(
        "INSERT INTO quote_item (id, org_id, quote_id, root_component_id, position) "
        "VALUES (gen_random_uuid(), :org, :q, :c, 0)",
        {"org": str(org_id), "q": str(quote_id), "c": str(comp_id)},
    )
    seeder.sql(
        "INSERT INTO component_quantity (id, org_id, component_id, quantity, total_price) "
        "VALUES (gen_random_uuid(), :org, :c, 1, '500.00')",
        {"org": str(org_id), "c": str(comp_id)},
    )
    seeder.sql(
        "INSERT INTO component_quantity (id, org_id, component_id, quantity, total_price) "
        "VALUES (gen_random_uuid(), :org, :c, 10, '4200.00')",
        {"org": str(org_id), "c": str(comp_id)},
    )

    values = _run_quote_values(tenancy_db, org_id, [quote_id])
    assert values[quote_id] == 420_000  # 4_200 € (qty-10 break), not the qty-1 break


def _add_line(
    seeder: Seeder, org_id: uuid.UUID, quote_id: uuid.UUID, pos: int, total: str | None
) -> None:
    """One line item on ``quote_id``; ``total`` None seeds a line with NO break."""
    part_id = seeder.part(org_id)
    comp_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO component (id, org_id, part_id, is_root_component) "
        "VALUES (:id, :org, :p, true)",
        {"id": str(comp_id), "org": str(org_id), "p": str(part_id)},
    )
    seeder.sql(
        "INSERT INTO quote_item (id, org_id, quote_id, root_component_id, position) "
        "VALUES (gen_random_uuid(), :org, :q, :c, :pos)",
        {"org": str(org_id), "q": str(quote_id), "c": str(comp_id), "pos": pos},
    )
    if total is not None:
        seeder.sql(
            "INSERT INTO component_quantity (id, org_id, component_id, quantity, total_price) "
            "VALUES (gen_random_uuid(), :org, :c, 1, :tp)",
            {"org": str(org_id), "c": str(comp_id), "tp": total},
        )


def test_quote_values_partial_pricing_is_unknown_not_understated(
    tenancy_db: str, seeder: Seeder
) -> None:
    """A quote with one priced line and one UNPRICED line (no break) must read as
    None — never the priced line's total alone, which would understate it and
    corrupt the value-range signal."""
    org_id = seeder.org("brief-partial")
    account_id = seeder.account(org_id, name="Partial Co")
    quote_id = seeder.quote(org_id, "PP-1", status=QuoteStatus.draft, account_id=account_id)
    _add_line(seeder, org_id, quote_id, 0, "500.00")  # priced
    _add_line(seeder, org_id, quote_id, 1, None)  # no break → unpriced
    values = _run_quote_values(tenancy_db, org_id, [quote_id])
    assert values[quote_id] is None  # unknown, not 50_000


# --------------------------------------------------------------------------- #
# Orchestration gates (generate_customer_brief) — no Claude call when gated
# --------------------------------------------------------------------------- #


def test_generate_calls_model_and_returns_bullets(
    tenancy_db: str, seeder: Seeder, fake_synth: _FakeSynth
) -> None:
    org_id = seeder.org("brief-gen")
    account_id = seeder.account(org_id, name="Gen Co")
    for n in range(3):
        seeder.quote(org_id, f"G-{n}", status=QuoteStatus.won, account_id=account_id)
    current = seeder.quote(org_id, "GCUR", status=QuoteStatus.draft, account_id=account_id)
    out = _run_generate(tenancy_db, org_id, current)
    assert out["reason"] == "ok"
    assert out["brief"]["bullets"] == ["Bestandskunde mit hoher Gewinnquote."]
    assert out["brief"]["account_name"] == "Gen Co"
    assert fake_synth.calls == 1


def test_generate_omits_below_threshold_without_model_call(
    tenancy_db: str, seeder: Seeder, fake_synth: _FakeSynth
) -> None:
    org_id = seeder.org("brief-gen-thresh")
    account_id = seeder.account(org_id, name="Thin Co")
    seeder.quote(org_id, "T-1", status=QuoteStatus.won, account_id=account_id)
    current = seeder.quote(org_id, "TCUR", status=QuoteStatus.draft, account_id=account_id)
    out = _run_generate(tenancy_db, org_id, current)
    assert out["brief"] is None and out["reason"] == "insufficient_data"
    assert fake_synth.calls == 0  # cheap gate short-circuits before Claude


def test_generate_omits_when_ai_disabled_without_model_call(
    tenancy_db: str, seeder: Seeder, fake_synth: _FakeSynth
) -> None:
    org_id = seeder.org("brief-gen-off")
    account_id = seeder.account(org_id, name="Quiet Co")
    for n in range(3):
        seeder.quote(org_id, f"Q-{n}", status=QuoteStatus.won, account_id=account_id)
    current = seeder.quote(org_id, "QCUR", status=QuoteStatus.draft, account_id=account_id)
    seeder.sql(
        "INSERT INTO org_ai_settings (org_id, master_enabled) VALUES (:org, false) "
        "ON CONFLICT (org_id) DO UPDATE SET master_enabled = false",
        {"org": str(org_id)},
    )
    out = _run_generate(tenancy_db, org_id, current)
    assert out["brief"] is None and out["reason"] == "ai_disabled"
    assert fake_synth.calls == 0


def test_generate_omits_per_feature_toggle_off(
    tenancy_db: str, seeder: Seeder, fake_synth: _FakeSynth
) -> None:
    org_id = seeder.org("brief-gen-feat")
    account_id = seeder.account(org_id, name="Feature Co")
    for n in range(3):
        seeder.quote(org_id, f"F-{n}", status=QuoteStatus.won, account_id=account_id)
    current = seeder.quote(org_id, "FCUR", status=QuoteStatus.draft, account_id=account_id)
    seeder.sql(
        "INSERT INTO org_ai_settings (org_id, customer_brief_enabled) VALUES (:org, false) "
        "ON CONFLICT (org_id) DO UPDATE SET customer_brief_enabled = false",
        {"org": str(org_id)},
    )
    out = _run_generate(tenancy_db, org_id, current)
    assert out["brief"] is None and out["reason"] == "ai_disabled"
    assert fake_synth.calls == 0


def test_generate_omits_when_no_account(
    tenancy_db: str, seeder: Seeder, fake_synth: _FakeSynth
) -> None:
    org_id = seeder.org("brief-gen-noacct")
    current = seeder.quote(org_id, "NCUR", status=QuoteStatus.draft, account_id=None)
    out = _run_generate(tenancy_db, org_id, current)
    assert out["brief"] is None and out["reason"] == "no_account"
    assert fake_synth.calls == 0


def test_generate_omits_on_model_error(tenancy_db: str, seeder: Seeder) -> None:
    class _Boom:
        async def synthesize(self, aggregate: dict[str, Any]) -> dict[str, Any]:
            raise customer_brief.BriefSynthError("provider_refusal")

    customer_brief.register(_Boom())
    try:
        org_id = seeder.org("brief-gen-boom")
        account_id = seeder.account(org_id, name="Boom Co")
        for n in range(3):
            seeder.quote(org_id, f"B-{n}", status=QuoteStatus.won, account_id=account_id)
        current = seeder.quote(org_id, "BCUR", status=QuoteStatus.draft, account_id=account_id)
        out = _run_generate(tenancy_db, org_id, current)
        assert out["brief"] is None and out["reason"] == "error:provider_refusal"
    finally:
        customer_brief.register(None)


def test_generate_truncates_to_three_bullets(tenancy_db: str, seeder: Seeder) -> None:
    customer_brief.register(_FakeSynth(bullets=["a", "b", "c", "d", "e"]))
    try:
        org_id = seeder.org("brief-gen-trunc")
        account_id = seeder.account(org_id, name="Verbose Co")
        for n in range(3):
            seeder.quote(org_id, f"X-{n}", status=QuoteStatus.won, account_id=account_id)
        current = seeder.quote(org_id, "XCUR", status=QuoteStatus.draft, account_id=account_id)
        out = _run_generate(tenancy_db, org_id, current)
        assert out["brief"]["bullets"] == ["a", "b", "c"]  # capped at MAX_BULLETS
    finally:
        customer_brief.register(None)


# --------------------------------------------------------------------------- #
# API route — GET /api/quotes/{id}/customer-brief (org-scoped, not persisted)
# --------------------------------------------------------------------------- #


def test_endpoint_returns_brief(
    app_client: TestClient, seeder: Seeder, fake_synth: _FakeSynth
) -> None:
    org_id = seeder.org("brief-api")
    user = seeder.user("u@brief-api.example")
    seeder.membership(user, org_id, ADMIN)
    account_id = seeder.account(org_id, name="API Kunde")
    for n in range(3):
        seeder.quote(org_id, f"A-{n}", status=QuoteStatus.won, account_id=account_id)
    current = seeder.quote(org_id, "ACUR", status=QuoteStatus.draft, account_id=account_id)
    with authed(app_client, user_id=user, org_id=org_id, roles=ADMIN):
        res = app_client.get(f"/api/quotes/{current}/customer-brief")
    assert res.status_code == 200
    body = res.json()
    assert body["reason"] == "ok"
    assert body["brief"]["account_name"] == "API Kunde"
    assert body["brief"]["bullets"]


def test_endpoint_is_org_scoped(
    app_client: TestClient, seeder: Seeder, fake_synth: _FakeSynth
) -> None:
    org_a = seeder.org("brief-a")
    org_b = seeder.org("brief-b")
    user_b = seeder.user("u@brief-b.example")
    seeder.membership(user_b, org_b, ADMIN)
    account_a = seeder.account(org_a, name="A Kunde")
    quote_a = seeder.quote(org_a, "QA", status=QuoteStatus.draft, account_id=account_a)
    with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
        res = app_client.get(f"/api/quotes/{quote_a}/customer-brief")
    body = res.json()
    # RLS hides org A's quote from org B → the brief is omitted, never leaked.
    assert res.status_code == 200
    assert body["brief"] is None and body["reason"] == "quote_not_found"
