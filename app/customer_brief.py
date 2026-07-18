"""Customer Intelligence Brief — AI Feature 5 (spec ``#ai-customer-brief``; M5.10).

Governing question: *"Before I send this quote, what do I know about this
customer that should change my approach?"*

Unlike the RFQ Triage Brief (M3.9) this is **generated on demand and NOT
persisted** (spec: "Not stored; generated on demand") — there is no cache
column and no Celery task. When the send-quote composer mounts it calls the
endpoint, which runs a **deterministic per-account DB aggregate** and then a
**single Claude call** that writes **2-3 German bullets** — editorial: it
*selects and phrases* what is unusual/decision-relevant, it does not dump the
data and it never invents a fact not in the aggregate (never-hallucinate;
folded AI-LENS spec).

Graceful degradation — the composer simply shows **no card** (never an empty
state) when: the quote has no account, the AI toggle (master **or**
``customer_brief``) is off, the account has **< 3 prior quotes**, or the model
call fails. The brief is pure information: the estimator reads it, applies their
own judgement, and sends. It never feeds Kalk costing (tier-1 invariant).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import statistics
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .ai_settings import get_ai_flags
from .config import Settings, get_settings
from .models import (
    Account,
    ComponentQuantity,
    Quote,
    QuoteItem,
    QuoteStatus,
    QuoteStatusEvent,
)

logger = logging.getLogger("app.customer_brief")

#: Bump when the assembled brief JSON shape changes (frontend keys off it).
BRIEF_VERSION = 1
#: Versioned prompt id (repeatability, eval alignment — mirrors triage-v1).
BRIEF_PROMPT_VERSION = "brief-v1"

#: The card fires only at/above this many prior quotes (spec: "≥ 3 prior
#: quotes"). Below it the brief is omitted entirely — no empty state.
MIN_PRIOR_QUOTES = 3
#: The trailing window for the win-rate trend (spec: "last 12 months").
TREND_MONTHS = 12
#: Claude writes at most this many bullets (spec: "2-3 bullets maximum").
MAX_BULLETS = 3
#: Account Notes are advisory free text — cap what we hand the model.
NOTES_MAX_CHARS = 2000

_ZERO = Decimal("0")
_DECIDED = (QuoteStatus.won, QuoteStatus.lost)


# --------------------------------------------------------------------------- #
# Deterministic per-account aggregate (no AI — pure DB reads)
# --------------------------------------------------------------------------- #


def _to_minor(value: Decimal | None) -> int | None:
    """A resolved 2-dp EUR/CHF ``total_price`` → integer minor units (tier-1
    money convention). ``None`` stays ``None`` (value unknown)."""
    if value is None:
        return None
    return int((value * 100).quantize(_ZERO, rounding=ROUND_HALF_UP))


async def quote_values(
    session: AsyncSession, quote_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int | None]:
    """A representative monetary value per quote, in minor units.

    No canonical quote-total column exists (value is per-quantity-break; the
    buyer selects a quantity only at checkout). ASSUMED (advisory-only, never
    persisted, never feeds Kalk): value = Σ over the quote's line items of
    ``component_quantity.total_price`` at each line's **highest-quantity break**
    (``DISTINCT ON (quote_item.id) … ORDER BY quantity DESC``). Every quote in an
    account is measured identically, so the *comparison* (is this one unusually
    large) is consistent even though the absolute figure is one of several
    defensible totals. A quote with no priced line → ``None`` (excluded from the
    range so the model never sees a fabricated zero)."""
    if not quote_ids:
        return {}
    # One row per line item: the total_price of its largest-quantity break.
    per_item = (
        select(
            QuoteItem.quote_id.label("quote_id"),
            ComponentQuantity.total_price.label("total_price"),
        )
        .join(ComponentQuantity, ComponentQuantity.component_id == QuoteItem.root_component_id)
        .where(QuoteItem.quote_id.in_(quote_ids))
        .distinct(QuoteItem.id)
        .order_by(QuoteItem.id, ComponentQuantity.quantity.desc())
        .subquery()
    )
    rows = (
        await session.execute(
            select(per_item.c.quote_id, func.sum(per_item.c.total_price)).group_by(
                per_item.c.quote_id
            )
        )
    ).all()
    summed: dict[uuid.UUID, Decimal | None] = {row[0]: row[1] for row in rows}
    # Quotes with no line item at all never appear above — surface them as None.
    return {qid: _to_minor(summed.get(qid)) for qid in quote_ids}


async def _decision_dates(
    session: AsyncSession, quote_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """The most-recent won/lost transition time per quote (the audit trail is
    the truth for *when* a quote was decided). Callers fall back to
    ``quote.created_at`` for quotes without a recorded transition (legacy/seed)."""
    if not quote_ids:
        return {}
    rows = (
        await session.execute(
            select(
                QuoteStatusEvent.quote_id,
                func.max(QuoteStatusEvent.created_at),
            )
            .where(
                QuoteStatusEvent.quote_id.in_(quote_ids),
                QuoteStatusEvent.to_status.in_(_DECIDED),
            )
            .group_by(QuoteStatusEvent.quote_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


@dataclasses.dataclass(frozen=True, slots=True)
class _PriorQuote:
    id: uuid.UUID
    status: QuoteStatus
    revision: int
    created_at: datetime


async def build_account_aggregate(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    current_quote_id: uuid.UUID,
    currency: str,
    now: datetime,
) -> dict[str, Any] | None:
    """Deterministic signal aggregate for one Account, or ``None`` when the
    account is gone or has fewer than :data:`MIN_PRIOR_QUOTES` prior quotes.

    "Prior" = the account's other (non-trashed) quotes, excluding the one being
    sent. Only signals that can be computed are populated; anything unknown is
    left ``None`` so the prompt (and therefore the model) never sees an invented
    value. Reads run inside the caller's org-scoped (RLS) session."""
    account = await session.get(Account, account_id)
    if account is None:
        return None

    prior_rows = (
        await session.execute(
            select(Quote.id, Quote.status, Quote.revision, Quote.created_at).where(
                Quote.account_id == account_id,
                Quote.id != current_quote_id,
                Quote.deleted_at.is_(None),
            )
        )
    ).all()
    if len(prior_rows) < MIN_PRIOR_QUOTES:
        return None
    prior = [
        _PriorQuote(id=r[0], status=r[1], revision=int(r[2]), created_at=r[3]) for r in prior_rows
    ]

    won = [q for q in prior if q.status == QuoteStatus.won]
    lost = [q for q in prior if q.status == QuoteStatus.lost]
    decided = len(won) + len(lost)
    win_rate_pct = round(100 * len(won) / decided, 1) if decided else None

    # 12-month trend: classify each decided quote by its decision date (audit
    # trail, else created_at) into the trailing window.
    prior_ids = [q.id for q in prior]
    decided_at = await _decision_dates(session, prior_ids)
    cutoff = now - timedelta(days=int(TREND_MONTHS * 365.25 / 12))

    def _in_window(q: _PriorQuote) -> bool:
        when = decided_at.get(q.id, q.created_at)
        return when >= cutoff

    won_recent = sum(1 for q in won if _in_window(q))
    lost_recent = sum(1 for q in lost if _in_window(q))
    decided_recent = won_recent + lost_recent
    win_rate_recent_pct = round(100 * won_recent / decided_recent, 1) if decided_recent else None

    # Value range across the account's history vs this quote (see quote_values).
    values = await quote_values(session, [current_quote_id, *prior_ids])
    this_value = values.get(current_quote_id)
    prior_values = sorted(
        v for qid, v in values.items() if qid != current_quote_id and v is not None
    )
    prior_min = prior_values[0] if prior_values else None
    prior_max = prior_values[-1] if prior_values else None
    prior_median = int(statistics.median(prior_values)) if prior_values else None
    is_largest = this_value is not None and prior_max is not None and this_value > prior_max
    outside_range = (
        this_value is not None
        and prior_min is not None
        and (this_value > prior_max or this_value < prior_min)  # type: ignore[operator]
    )

    # Revision (negotiation) pattern among won quotes (Quote.revision > 0 ⇒ the
    # quote went through at least one revision before it was won).
    won_with_rev = sum(1 for q in won if q.revision > 0)
    won_without_rev = len(won) - won_with_rev
    never_first_accept = len(won) > 0 and won_without_rev == 0

    notes = (account.notes or "").strip()

    return {
        "account_name": account.name,
        "currency": currency,
        "prior_quote_count": len(prior),
        "won": len(won),
        "lost": len(lost),
        "win_rate_pct": win_rate_pct,
        "won_last_12mo": won_recent,
        "lost_last_12mo": lost_recent,
        "win_rate_last_12mo_pct": win_rate_recent_pct,
        "this_quote_value_minor": this_value,
        "prior_value_min_minor": prior_min,
        "prior_value_max_minor": prior_max,
        "prior_value_median_minor": prior_median,
        "this_quote_is_largest": is_largest,
        "this_quote_outside_range": outside_range,
        "won_with_revision": won_with_rev,
        "won_without_revision": won_without_rev,
        "never_accepts_without_revision": never_first_accept,
        "account_notes": notes[:NOTES_MAX_CHARS] or None,
    }


# --------------------------------------------------------------------------- #
# AI synthesis seam (single Claude call → 2-3 bullets) — mirrors triage
# --------------------------------------------------------------------------- #


class BriefSynthError(Exception):
    """A deterministic synthesis outcome (refusal / truncation / bad JSON) — not
    an infra failure. The caller degrades to *no card* rather than retrying."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class BriefSynthesizer(Protocol):
    """The AI seam: one Claude call over the deterministic aggregate → 2-3
    German bullets. Returns ``{"bullets": [str, ...]}``; the caller treats it as
    advisory and never lets it fabricate history."""

    async def synthesize(self, aggregate: dict[str, Any]) -> dict[str, Any]: ...


_registered: BriefSynthesizer | None = None


def register(synthesizer: BriefSynthesizer | None) -> None:
    """Install (or clear) the process-wide synthesizer — tests/``create_app``."""
    global _registered
    _registered = synthesizer


def resolve() -> BriefSynthesizer:
    """The synthesizer for this process (registered, else built from settings)."""
    if _registered is not None:
        return _registered
    return make_synthesizer(get_settings())


def make_synthesizer(settings: Settings) -> BriefSynthesizer:
    """Build the settings-configured synthesizer (reuses the Lens provider seam:
    same Claude account/model/EU routing, DECISIONS 2026-07-15)."""
    if settings.lens_provider != "anthropic":
        raise RuntimeError(f"Unknown LENS_PROVIDER {settings.lens_provider!r}")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — live customer brief needs it.")
    return AnthropicBriefSynthesizer(
        api_key=settings.anthropic_api_key,
        model=settings.lens_model,
        inference_geo=settings.lens_inference_geo or None,
    )


_BULLETS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": MAX_BULLETS,
        },
    },
    "required": ["bullets"],
    "additionalProperties": False,
}

_PROMPT = (
    f"[{BRIEF_PROMPT_VERSION}] Du bist ein Vertriebsassistent für einen "
    "Fertigungsbetrieb. Aus den folgenden aggregierten Kundendaten formulierst du "
    "2-3 kurze, entscheidungsrelevante Stichpunkte auf DEUTSCH, die der Kalkulator "
    "VOR dem Versand des Angebots kennen sollte. Wähle nur das Ungewöhnliche oder "
    "Handlungsrelevante aus (Gewinnquote/Trend, ob dieses Angebot außerhalb der "
    "bisherigen Wertspanne liegt, Verhandlungs-/Revisionsmuster, relevante "
    "Kundennotizen) — KEINE vollständige Datenaufzählung. Erfinde KEINE Werte, die "
    "nicht in den Daten stehen; lasse fehlende Werte weg. Beträge sind in "
    "Minor-Units (Cent) angegeben — nenne sie als runde Euro-/CHF-Beträge. Gib NUR "
    'JSON zurück: {"bullets": ["…"]}. Daten:\n'
)


class AnthropicBriefSynthesizer:
    """Text-only Claude synthesis (structured JSON), mirroring
    :class:`app.triage.AnthropicTriageEnricher` — same ``inference_geo`` routing;
    only the derived aggregate (no drawing/print bytes) is ever sent."""

    def __init__(self, *, api_key: str, model: str, inference_geo: str | None) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._inference_geo = inference_geo

    async def synthesize(self, aggregate: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 512,
            "output_config": {"format": {"type": "json_schema", "schema": _BULLETS_SCHEMA}},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _PROMPT + json.dumps(aggregate, ensure_ascii=False),
                        }
                    ],
                }
            ],
        }
        if self._inference_geo:
            params["inference_geo"] = self._inference_geo
        response = await self._client.messages.create(**params)
        if response.stop_reason == "refusal":
            raise BriefSynthError("provider_refusal")
        if response.stop_reason == "max_tokens":
            raise BriefSynthError("provider_truncated")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise BriefSynthError("provider_empty_response")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BriefSynthError("provider_invalid_json") from exc
        if not isinstance(payload, dict):
            raise BriefSynthError("provider_invalid_json")
        return payload


# --------------------------------------------------------------------------- #
# Orchestration: gate → aggregate → synthesise (on demand, not stored)
# --------------------------------------------------------------------------- #


def _omit(reason: str) -> dict[str, Any]:
    """The uniform "no card" response — the composer renders nothing."""
    return {"brief": None, "reason": reason}


async def generate_customer_brief(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    quote_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the on-demand brief for the send composer, or omit it.

    Order matters for cost: the cheap gates (missing quote/account, AI toggle
    off, below the prior-quote threshold) short-circuit **before** any Claude
    call. Nothing is persisted."""
    now = now or datetime.now(UTC)

    quote = await session.get(Quote, quote_id)
    if quote is None or quote.deleted_at is not None:
        return _omit("quote_not_found")
    if quote.account_id is None:
        return _omit("no_account")

    flags = await get_ai_flags(session, org_id)
    if not flags.customer_brief_active:
        return _omit("ai_disabled")

    aggregate = await build_account_aggregate(
        session,
        account_id=quote.account_id,
        current_quote_id=quote_id,
        currency=quote.currency,
        now=now,
    )
    if aggregate is None:
        return _omit("insufficient_data")

    try:
        result = await resolve().synthesize(aggregate)
    except (BriefSynthError, RuntimeError, AttributeError) as exc:
        code = exc.code if isinstance(exc, BriefSynthError) else "provider_unavailable"
        logger.info("customer_brief_skipped", extra={"code": code, "quote_id": str(quote_id)})
        return _omit(f"error:{code}")

    raw = result.get("bullets") if isinstance(result, dict) else None
    raw = raw if isinstance(raw, list) else []
    bullets = [b.strip() for b in raw if isinstance(b, str) and b.strip()][:MAX_BULLETS]
    if not bullets:
        return _omit("empty")

    return {
        "brief": {
            "version": BRIEF_VERSION,
            "prompt_version": BRIEF_PROMPT_VERSION,
            "generated_at": now.isoformat(),
            "account_name": aggregate["account_name"],
            "bullets": bullets,
            "signals": aggregate,
        },
        "reason": "ok",
    }
