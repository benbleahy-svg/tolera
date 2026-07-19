"""M6.5 — the vendor email channel's pure core: reference matching, money, the guard.

A vendor may answer an RFQ by replying to the email instead of using the M6.2 portal,
and the spec treats both channels as equally valid (``#vendor-rfq`` → "Email-channel
ingest (Lens)"). Three decisions live here, deliberately free of any database or
network so they can be pinned by fast tests:

**Matching is by RFQ reference number, never by sender.** The spec is explicit: a
vendor may reply from a shared inbox or a different address. ``vendor_rfq.number`` is a
bare per-org integer, so mailing it raw would make "12" match a date, a part count or a
signature; :func:`rfq_reference` mints the greppable wire form ``RFQ-12`` that
:func:`find_rfq_reference` looks for. Because M6.4 creates **one batch per vendor**, the
reference identifies the vendor too — there is nothing left to infer from the sender.

**We parse the vendor's money ourselves.** The model locates a price and quotes it
verbatim; :func:`parse_money` turns that quote into an exact :class:`~decimal.Decimal`.
A model's own "normalised" number is never trusted — that would be an AI doing
arithmetic on money (CLAUDE.md §5). German and English conventions both appear in DACH
inboxes (``1.234,56 €`` and ``1,234.56``), and in the German one ``1.234`` is one
thousand two hundred thirty-four, so the separator rules are worth being explicit about.

**Nothing survives that is not verbatim in the reply.** :func:`vendor_reply_guard`
mirrors ``parts_list_guard`` (M3.4): every number the model reports must carry a
citation that appears in the email body or the attached PDF's text layer, or it is
dropped. This is the never-hallucinate rule from ``AI-LENS-ENGINE-SPEC.md`` — an
invented vendor price is worse than a missing one, because a missing one is visible.

Everything extracted here is a **suggestion**: it lands on the response flagged
``ai_extracted``/not ``verified`` and M6.6's estimator confirmation is what lets it
reach costing.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field

#: Scale of ``vendor_rfq_response_price.unit_price`` — a quote with more precision than
#: the column holds is refused rather than silently rounded (the portal's ``_parse_price``
#: makes the same call).
MAX_PRICE_DECIMALS = 4

#: Upper bound mirroring the portal channel: a vendor unit price beyond this is a
#: transcription error, not a quote.
MAX_UNIT_PRICE = Decimal("99999999.9999")

#: Currency tokens recognised in a price citation. DACH only (EUR/CHF) — deliberately a
#: small closed set, so that stripping cannot eat part of a number (e.g. the ``e`` of
#: ``1e5``), and so an unknown symbol is a *refusal* rather than a silent assumption.
_CURRENCY_RE = re.compile(r"(?i)(?:\bEUR\b|\bCHF\b|€)")
_CURRENCY_CODES = {"eur": "EUR", "€": "EUR", "chf": "CHF"}

#: ``RFQ-12``, ``RFQ 12``, ``RFQ #12``, ``RFQ:12`` — with any dash a mail client may
#: substitute. A bare number never matches: the ``RFQ`` token is mandatory.
_REFERENCE_RE = re.compile(
    "\\bRFQ[\\s\u00a0]*[-\u2013\u2014#:]?[\\s\u00a0]*(\\d{1,12})\\b", re.IGNORECASE
)


def rfq_reference(number: str) -> str:
    """The wire form of an RFQ number — what goes in the subject and the email body.

    This is the *only* place the format is defined; :func:`find_rfq_reference` is its
    inverse, and the pair is what makes the reply matching in the spec work at all."""
    return f"RFQ-{number}"


def find_rfq_reference(subject: str | None, body: str | None = None) -> str | None:
    """Recover an RFQ number from a reply, subject first.

    Subject wins because it is the thread's identity: a vendor quoting our own footer
    can drag an older reference into the body. Leading zeros are stripped so
    ``RFQ-0012`` and ``RFQ-12`` are the same batch."""
    for haystack in (subject, body):
        if not haystack:
            continue
        match = _REFERENCE_RE.search(haystack)
        if match:
            return match.group(1).lstrip("0") or "0"
    return None


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
def _split_number(core: str) -> tuple[str, str] | None:
    """Split a separator-bearing numeric string into (integer digits, decimal digits).

    Returns ``None`` when the separators cannot be read as a consistent
    grouping/decimal convention — we refuse rather than pick one."""
    dots = core.count(".")
    commas = core.count(",")

    if dots and commas:
        # Both present: the *last* one is the decimal separator, the other groups.
        decimal_sep = "." if core.rfind(".") > core.rfind(",") else ","
        group_sep = "," if decimal_sep == "." else "."
        int_part, _, dec_part = core.rpartition(decimal_sep)
        if decimal_sep in int_part or not dec_part:
            return None
        return _ungroup(int_part, group_sep), dec_part

    if commas:
        # **A lone comma is always the decimal separator.** This is the German-first
        # reading and the only safe one: treating "2,750" as a thousands group would
        # turn a 2,75 € unit price into 2750 € — a 1000x error on a number a human is
        # about to apply to a quote, which nothing downstream could catch. A second
        # comma therefore cannot be grouping either; it is malformed ("12,50,60").
        if commas > 1:
            return None
        head, _, tail = core.rpartition(",")
        if not head or not tail:
            return None
        return head, tail

    if not dots:
        return core, ""

    head, _, tail = core.rpartition(".")
    # A lone dot with exactly three digits after it and a plausible group head is a
    # thousands separator — "1.234" is 1234 € in a German quote. A leading zero rules
    # that out: "0.500" can only be a decimal point.
    if dots == 1 and len(tail) == 3 and 1 <= len(head) <= 3 and head.isdigit():
        if not head.startswith("0"):
            return head + tail, ""
        return head, tail
    if dots > 1:
        # Several of the same separator can only be grouping: 1.234.567
        return _ungroup(core, "."), ""
    if not head or not tail:
        return None
    return head, tail


def _ungroup(text: str, sep: str) -> str:
    """Strip a thousands separator, refusing malformed groups (``12,50,60``)."""
    if sep not in text:
        return text
    head, *groups = text.split(sep)
    if not head or len(head) > 3 or not all(len(g) == 3 for g in groups):
        return ""  # invalid → caller's Decimal() raises → None
    return head + "".join(groups)


def parse_price(raw: str | None) -> tuple[Decimal, str | None] | None:
    """Parse a vendor's verbatim price text into ``(amount, currency)``, or ``None``.

    The currency is whatever the vendor actually wrote (``None`` when they wrote none,
    in which case the response's own currency stands). Carrying it out of here is what
    keeps a Swiss supplier's ``CHF 89.90`` from being stored as 89,90 **EUR** on a
    response whose currency column says EUR — a silent ~6% error on a cost an estimator
    is about to apply.

    Refuses anything it cannot read unambiguously — a negative amount, a percentage, a
    malformed grouping, or more precision than the column holds. ``None`` means "no
    price", which the estimator sees as a blank cell; it never means zero."""
    if not raw:
        return None
    found = {_CURRENCY_CODES[m.group(0).lower()] for m in _CURRENCY_RE.finditer(raw)}
    if len(found) > 1:
        return None  # "12,50 EUR / CHF" names no single price
    currency = next(iter(found), None)
    core = _CURRENCY_RE.sub("", raw)
    core = core.replace("\u00a0", " ").replace("\u202f", " ").strip()
    core = core.replace(" ", "")
    if not core or not re.fullmatch(r"[0-9.,]+", core) or not any(c.isdigit() for c in core):
        return None

    split = _split_number(core)
    if split is None:
        return None
    int_part, dec_part = split
    if not int_part.isdigit() or (dec_part and not dec_part.isdigit()):
        return None
    if len(dec_part) > MAX_PRICE_DECIMALS:
        return None
    try:
        value = Decimal(f"{int_part}.{dec_part}" if dec_part else int_part)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > MAX_UNIT_PRICE:
        return None
    return value, currency


def parse_money(raw: str | None) -> Decimal | None:
    """The amount alone — for callers that already know the currency."""
    parsed = parse_price(raw)
    return parsed[0] if parsed else None


# --------------------------------------------------------------------------- #
# What the model is allowed to say
# --------------------------------------------------------------------------- #
class RawVendorPrice(BaseModel):
    """One (quantity break → price, lead time) cell as the model reports it.

    ``*_raw`` are the model's **citations** — the characters it claims to have read out
    of the reply. The guard checks them against the reply text; the parsed values are
    ours, not the model's."""

    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(gt=0)
    unit_price_raw: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    lead_time_raw: str | None = None
    #: Filled by :func:`vendor_reply_guard` from ``unit_price_raw``; never by the model.
    unit_price: Decimal | None = None


class RawVendorQuoteLine(BaseModel):
    """The model's reading of one part's answer in a vendor reply."""

    model_config = ConfigDict(extra="forbid")

    part_number: str | None = None
    cannot_quote: bool = False
    notes: str | None = None
    prices: list[RawVendorPrice] = Field(default_factory=list)


def _normalize(text: str) -> str:
    """Fold a text into the shape citations are compared in.

    Mail clients rewrite spacing freely — NBSP before a currency sign, a line break
    mid-sentence, doubled spaces from quoted replies — so whitespace is collapsed and
    the comparison is case-insensitive. Nothing else is altered: digits and separators
    must still match exactly, which is the point of the guard."""
    folded = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", folded).strip().casefold()


def vendor_reply_guard(
    lines: list[RawVendorQuoteLine],
    body_text: str,
    pdf_text: str | None = None,
    *,
    currency: str | None = None,
    allowed_quantities: set[int] | None = None,
) -> tuple[list[RawVendorQuoteLine], int]:
    """Drop every fact the model did not cite verbatim in the reply.

    Returns the surviving lines and a count of dropped facts. A *dropped* fact is one
    the model **cited** and whose citation could not be found, could not be parsed, or
    contradicts the RFQ; a value the model reported without a citation is simply absent,
    never invented into existence. A line left with no prices and no ``cannot_quote``
    carries no information and is removed.

    Two checks here are not citation checks, because a citation cannot establish them:

    * ``currency`` — a price whose citation names a *different* currency from the one
      the response is recorded in is dropped rather than silently re-denominated.
    * ``allowed_quantities`` — the batch's own quantity breaks. The quantity is the one
      field the model reports that has no verbatim form of its own, so a correctly
      cited price could otherwise land on an invented break; the portal channel
      validates the same way."""
    corpus = _normalize(f"{body_text}\n{pdf_text or ''}")
    kept: list[RawVendorQuoteLine] = []
    dropped = 0

    for line in lines:
        clean_prices: list[RawVendorPrice] = []
        for price in line.prices:
            if allowed_quantities is not None and price.quantity not in allowed_quantities:
                dropped += 1
                continue

            unit_price: Decimal | None = None
            if price.unit_price_raw:
                if _normalize(price.unit_price_raw) in corpus:
                    parsed = parse_price(price.unit_price_raw)
                    # A currency the RFQ is not in is not this response's money.
                    if parsed is not None and not (
                        currency and parsed[1] and parsed[1] != currency
                    ):
                        unit_price = parsed[0]
                if unit_price is None:
                    dropped += 1

            lead_days: int | None = None
            if price.lead_time_raw:
                if _normalize(price.lead_time_raw) in corpus:
                    lead_days = price.lead_time_days
                if lead_days is None:
                    dropped += 1

            if unit_price is None and lead_days is None:
                continue
            clean_prices.append(
                price.model_copy(update={"unit_price": unit_price, "lead_time_days": lead_days})
            )

        notes = line.notes
        if notes and _normalize(notes) not in corpus:
            notes = None
            dropped += 1

        if not clean_prices and not line.cannot_quote:
            continue
        kept.append(line.model_copy(update={"prices": clean_prices, "notes": notes}))

    return kept, dropped
