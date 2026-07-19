"""ERP-push payload stub — the "Export Quote/Order" contract (M6.8).

Build-plan M6.8 scopes this precisely: *"a documented Integration Action
'Export Quote/Order' request shape — DATEV/ERP export contract defined,
transport stubbed"*. A real ERP connector is post-pilot (INTEGRATION-API-
CONTRACT §7 lists ProAlpha / abas / SAP B1 as managed connectors after the
pilot). What is built **now** is the payload, so that:

* the export contract is fixed and versioned before anyone builds against it;
* the Integration-Action log (``queued → in_progress → completed/failed``) and
  its export-failure notification are exercised end-to-end today;
* dropping in a transport later changes one function, not the contract.

**Money.** Every amount is ``{"amount_minor": int, "currency": "EUR"|"CHF"}`` —
integer minor units plus an explicit currency (CLAUDE.md §5). No float appears
anywhere in this payload, and no total is computed here: the caller passes the
already-computed quote total, exactly as the CRM deal path does.

**Safety.** The payload is data-out only. It carries no ACL, permission,
security-setting or funds-movement field, and the action ``type`` it is filed
under (``export_quote`` / ``export_order``) passes
:func:`app.integration_actions.assert_permitted` — the §5 prohibitions.
"""

from __future__ import annotations

import uuid
from typing import Any

#: Bumped when the payload shape changes in a way a consumer must notice.
EXPORT_SCHEMA_VERSION = "1.0"

#: The two capability keys this stub defines (`integration_action_definition.type`).
ACTION_EXPORT_QUOTE = "export_quote"
ACTION_EXPORT_ORDER = "export_order"

#: The integration these definitions hang off.
ERP_INTEGRATION_KEY = "erp_push"


def build_money(amount_minor: int, currency: str) -> dict[str, Any]:
    """The one money shape used throughout the export contract."""
    return {"amount_minor": int(amount_minor), "currency": currency}


def build_quote_export_payload(
    *,
    org_slug: str,
    quote_id: uuid.UUID,
    quote_number: str,
    currency: str,
    total_minor: int,
    account: dict[str, Any] | None = None,
    contact: dict[str, Any] | None = None,
    lines: list[dict[str, Any]] | None = None,
    issued_at: str | None = None,
) -> dict[str, Any]:
    """The documented "Export Quote" request body.

    ``lines`` entries are ``{"line_number", "part_number", "description",
    "quantity", "unit_price": <money>, "extended_price": <money>}`` — built by
    the caller from the quote's own already-priced items, never recomputed
    here."""
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "action": ACTION_EXPORT_QUOTE,
        "object": "quote",
        "org_slug": org_slug,
        "quote": {
            "id": str(quote_id),
            "number": quote_number,
            "issued_at": issued_at,
            "currency": currency,
            "total": build_money(total_minor, currency),
            "account": account,
            "contact": contact,
            "lines": lines or [],
        },
    }


def build_order_export_payload(
    *,
    org_slug: str,
    order_id: uuid.UUID,
    order_number: str,
    quote_number: str | None,
    currency: str,
    total_minor: int,
    account: dict[str, Any] | None = None,
    placed_at: str | None = None,
) -> dict[str, Any]:
    """The documented "Export Order" request body (same envelope as the quote)."""
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "action": ACTION_EXPORT_ORDER,
        "object": "order",
        "org_slug": org_slug,
        "order": {
            "id": str(order_id),
            "number": order_number,
            "quote_number": quote_number,
            "placed_at": placed_at,
            "currency": currency,
            "total": build_money(total_minor, currency),
            "account": account,
        },
    }


class ErpTransportStub:
    """The stubbed transport (build-plan: "transport stubbed").

    It records what *would* have been sent so the export contract is assertable,
    and can be told to fail — which is how the export-failure notification path
    is exercised without a real ERP to break."""

    def __init__(
        self, *, fail: bool = False, failure_message: str = "ERP nicht erreichbar"
    ) -> None:
        self.fail = fail
        self.failure_message = failure_message
        self.sent: list[dict[str, Any]] = []

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail:
            raise ErpExportFailed(self.failure_message)
        self.sent.append(payload)
        return {"accepted": True, "reference": f"ERP-{payload['action']}-{len(self.sent)}"}


class ErpExportFailed(Exception):
    """The stubbed (later: real) ERP refused or could not be reached."""
