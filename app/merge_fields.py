"""Email-template merge fields (M5.5).

Spec ``#settings`` Email Templates: the composer's subject/body carry ``%%FIELD%%``
placeholders — ``%%QUOTE_NUMBER%%``, ``%%QUOTE_LINK%%``, … — that resolve against
the quote at send. Two halves, split so the substitution is unit-testable without a
database:

* :func:`render_merge` — **pure** ``%%NAME%%`` → value substitution. A known token
  with no value blanks to ``""``; an *unknown* token is also blanked (customer-facing
  safety — a stray ``%%TYPO%%`` must never reach the buyer, and a value is **never
  invented**: the never-hallucinate invariant, CLAUDE.md §5).
* :func:`build_merge_values` — resolves the catalog against the DB (quote number, the
  minted portal link, contact/estimator/salesperson identities, org facility name).

The server runs :func:`render_merge` on the final (human-edited) body at send with the
authentic context, so ``%%QUOTE_LINK%%`` always becomes the real minted ``/q/:token``
URL — the client cannot forge it.
"""

from __future__ import annotations

import html as _htmllib
import json
import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Component, Contact, Organization, Part, Quote, QuoteItem

#: The supported merge-field catalog (spec ``#settings`` / block M5.5 scope).
MERGE_FIELDS: frozenset[str] = frozenset(
    {
        "QUOTE_NUMBER",
        "QUOTE_LINK",
        "RFQ_NUMBER",
        "PART_NUMBERS",
        "CUSTOMER_FIRST_NAME",
        "CUSTOMER_LAST_NAME",
        "ESTIMATOR_FIRST_NAME",
        "ESTIMATOR_LAST_NAME",
        "ESTIMATOR_EMAIL",
        "SALESPERSON_FIRST_NAME",
        "SALESPERSON_LAST_NAME",
        "SALESPERSON_EMAIL",
        "FACILITY_NAME",
        "FACILITY_PHONE",
    }
)

# Match ANY %%…%% token shape (upper/lower/digits/hyphen), not just the catalog's
# UPPER_SNAKE — so a stray %%typo%% / %%quote-number%% is *blanked*, never leaked
# verbatim to the customer. Catalog membership is checked in render_merge.
_TOKEN = re.compile(r"%%([A-Za-z0-9_-]+)%%")


def render_merge(template: str, values: Mapping[str, str], *, escape_html: bool = False) -> str:
    """Replace every ``%%NAME%%`` in ``template`` with ``values[NAME]``.

    A token not in :data:`MERGE_FIELDS`, or one with no supplied value, resolves to
    the empty string — never the literal ``%%…%%`` and never an invented value.

    ``escape_html=True`` HTML-escapes each substituted **value** (not the template's
    own markup) — required when merging into an HTML body, because a value can carry
    customer-supplied text (``%%PART_NUMBERS%%``, ``%%RFQ_NUMBER%%``, names) that
    would otherwise be a stored-XSS sink in the estimator's preview and the buyer's
    email. The subject is plain text and merges unescaped."""

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in MERGE_FIELDS:
            return ""
        value = values.get(name, "")
        return _htmllib.escape(value) if escape_html else value

    return _TOKEN.sub(_sub, template)


def _name_parts(member: dict[str, Any] | None) -> tuple[str, str, str]:
    if member is None:
        return "", "", ""
    return (
        member.get("first_name") or "",
        member.get("last_name") or "",
        member.get("email") or "",
    )


async def _org_members_by_id(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """The active org's members keyed by id — read through the ``app_org_members()``
    scoped ``SECURITY DEFINER`` view (M0.2), the ONLY ``app_user`` path the restricted
    role may use; it keys on the ``app.current_org_id`` GUC, so no other org leaks."""
    raw = (await session.execute(text("SELECT app_org_members()"))).scalar_one()
    members = json.loads(raw) if isinstance(raw, str) else raw
    return {str(m["id"]): m for m in (members or [])}


async def build_merge_values(
    session: AsyncSession,
    org: Organization,
    quote: Quote,
    *,
    quote_link: str,
) -> dict[str, str]:
    """Resolve the full merge catalog for ``quote`` (never hallucinating — an
    absent source resolves to ``""``)."""
    # Customer identity from the assigned contact.
    first = last = ""
    if quote.contact_id is not None:
        contact = await session.get(Contact, quote.contact_id)
        if contact is not None:
            first = contact.first_name or ""
            last = contact.last_name or ""

    members = await _org_members_by_id(session)
    est_first, est_last, est_email = _name_parts(
        members.get(str(quote.estimator_id)) if quote.estimator_id is not None else None
    )
    sales_first, sales_last, sales_email = _name_parts(
        members.get(str(quote.salesperson_id)) if quote.salesperson_id is not None else None
    )

    # Distinct part numbers across the quote's line items, in position order.
    part_numbers: list[str] = []
    rows = (
        await session.execute(
            select(Part.part_number)
            .join(
                Component,
                (Component.part_id == Part.id) & (Component.org_id == Part.org_id),
            )
            .join(
                QuoteItem,
                (QuoteItem.root_component_id == Component.id)
                & (QuoteItem.org_id == Component.org_id),
            )
            .where(QuoteItem.quote_id == quote.id)
            .order_by(QuoteItem.position)
        )
    ).all()
    for (number,) in rows:
        if number and number not in part_numbers:
            part_numbers.append(number)

    return {
        "QUOTE_NUMBER": quote.number or "",
        "QUOTE_LINK": quote_link,
        "RFQ_NUMBER": quote.rfq_number or "",
        "PART_NUMBERS": ", ".join(part_numbers),
        "CUSTOMER_FIRST_NAME": first,
        "CUSTOMER_LAST_NAME": last,
        "ESTIMATOR_FIRST_NAME": est_first,
        "ESTIMATOR_LAST_NAME": est_last,
        "ESTIMATOR_EMAIL": est_email,
        "SALESPERSON_FIRST_NAME": sales_first,
        "SALESPERSON_LAST_NAME": sales_last,
        "SALESPERSON_EMAIL": sales_email,
        "FACILITY_NAME": org.name or "",
        # No facility-phone field until M5.8 — resolve empty, never invent.
        "FACILITY_PHONE": "",
    }
