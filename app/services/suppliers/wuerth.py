"""Würth ("Tolera Source") material adapter — M6.7.

The fastener / C-parts sourcing lane: availability + price-by-quantity for a
purchased-component part number, and a sourcing RFQ back to the supplier.
Public copy always says **Tolera Source** (``DECISIONS.md`` 2026-06-19 *Partner
integration names*); "Würth" survives only in config keys and this module.

**Mock-first.** ``fixtures/wuerth/catalog.json`` is a recorded response and *is*
the contract (``DECISIONS.md`` 2026-06-14 *Würth API access*: build against a
fixture, real credentials slot in without code changes, do not block M6 on
procurement). The fixture→live swap is pure config — ``WUERTH_MODE=live`` plus
``WUERTH_BASE_URL`` / ``WUERTH_API_KEY`` — and no credential or endpoint is ever
written into this source, logged, or returned to a client.

Errors never escape as themselves: any transport/parse failure becomes
:class:`SupplierUnavailable`, which the API layer turns into a *degraded*
200 response so costing is never blocked (spec ``#sourcing-adapters``).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from fastapi import Request

from ...config import Settings
from .base import (
    AvailabilityItem,
    AvailabilityResult,
    QuantityQuote,
    SourcingRfqRequest,
    SourcingRfqResult,
    SupplierCapability,
    SupplierUnavailable,
    classify_stock,
)

logger = logging.getLogger("app.suppliers.wuerth")

SUPPLIER = "wuerth"
SCHEMA_VERSION = "1.0"

#: The recorded response that documents the contract (see fixtures/wuerth/README.md).
FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "wuerth" / "catalog.json"


def normalize_part_number(part_number: str) -> str:
    """The lookup key: case- and whitespace-insensitive.

    Würth part numbers are written with grouping spaces (``0057 8 30``) that
    nobody types consistently, and a shop's library entry may hold either form.
    """
    return "".join(part_number.split()).upper()


class WuerthClient(Protocol):
    """The transport seam — the ONLY thing that differs between fixture and live."""

    async def fetch_catalog(self) -> dict[str, Any]:
        """The raw availability/pricing document (see the fixture README §1)."""
        ...

    async def send_rfq(self, request: dict[str, Any]) -> dict[str, Any]:
        """POST one sourcing RFQ; returns the supplier's acknowledgement."""
        ...


class FixtureWuerthClient:
    """Serves the recorded response from ``fixtures/wuerth/catalog.json``.

    The default in development, test and (until procurement lands) the pilot.
    It also records the last RFQ request so the documented outbound shape is
    assertable without a network.
    """

    def __init__(self, fixture_path: Path | None = None) -> None:
        self._path = fixture_path or FIXTURE_PATH
        self.last_rfq_request: dict[str, Any] | None = None

    async def fetch_catalog(self) -> dict[str, Any]:
        return _load_fixture(self._path)

    async def send_rfq(self, request: dict[str, Any]) -> dict[str, Any]:
        self.last_rfq_request = request
        # The recorded acknowledgement: the supplier echoes our reference and
        # answers within one working day (fixtures/wuerth/README.md §2).
        return {
            "reference": request["reference"],
            "accepted": True,
            "supplier_reference": f"WUE-{request['reference']}",
            "estimated_response_hours": 24,
        }


@lru_cache(maxsize=4)
def _load_fixture(path: Path) -> dict[str, Any]:
    """Read + cache the recorded response (a file read per request would be silly)."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


class LiveWuerthClient:
    """The production client. Base URL and key come from settings, never source.

    Deliberately thin: it speaks the fixture's JSON shape, so promoting it is a
    config change (``WUERTH_MODE=live``) rather than a code change. Any HTTP or
    decode failure propagates to the adapter, which converts it into
    :class:`SupplierUnavailable`.
    """

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}

    async def fetch_catalog(self) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # The recorded contract is a whole-catalogue document, so this is a
            # faithful mock swap. A live endpoint with a part-number filter should
            # narrow it here (the shape stays identical) rather than pull it all.
            resp = await client.get(f"{self._base_url}/catalog", headers=self._headers())
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        return body

    async def send_rfq(self, request: dict[str, Any]) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/rfq", headers=self._headers(), json=request)
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        return body


class WuerthMaterialPricingAdapter:
    """``SupplierAdapter`` for Würth — availability/pricing + sourcing RFQ."""

    supplier = SUPPLIER
    capabilities = frozenset(
        {SupplierCapability.availability_pricing, SupplierCapability.sourcing_rfq}
    )

    def __init__(self, client: WuerthClient, *, mode: str = "fixture") -> None:
        self.client = client
        #: ``fixture`` | ``live`` — surfaced to the caller so a mock send is never
        #: reported (or audited) as though it reached the supplier.
        self.mode = mode

    async def availability(
        self, oem_part_numbers: list[str], *, quantities: list[int]
    ) -> AvailabilityResult:
        try:
            document = await self.client.fetch_catalog()
        except Exception:
            # Log for operations; never re-raise the client's message — it can
            # carry the endpoint URL (CLAUDE.md §5: nothing leaks to a client).
            logger.warning("wuerth availability lookup failed", exc_info=True)
            raise SupplierUnavailable(SUPPLIER) from None

        # Parsing lives inside the guard too: live-API drift (a renamed key, a
        # string where a number belongs) is likelier than an outage, and it must
        # degrade exactly the same way rather than 500 the estimating page.
        try:
            currency = str(document["currency"])
            by_part = {
                normalize_part_number(str(raw["oem_part_number"])): raw
                for raw in document.get("items", [])
            }
            wanted = sorted({int(q) for q in quantities if int(q) > 0})
            items = tuple(
                _build_item(
                    part_number,
                    by_part.get(normalize_part_number(part_number)),
                    currency,
                    wanted,
                )
                for part_number in oem_part_numbers
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("wuerth returned an unusable document: %s", type(exc).__name__)
            raise SupplierUnavailable(SUPPLIER) from None

        return AvailabilityResult(supplier=SUPPLIER, items=items)

    async def send_rfq(self, request: SourcingRfqRequest) -> SourcingRfqResult:
        payload = _rfq_payload(request)
        try:
            body = await self.client.send_rfq(payload)
        except Exception:
            logger.warning("wuerth rfq send failed", exc_info=True)
            raise SupplierUnavailable(SUPPLIER) from None

        # Same reasoning as the lookup: an acknowledgement we cannot parse is a
        # failed send (clean 503), never a 500.
        try:
            return SourcingRfqResult(
                reference=str(body.get("reference", request.reference)),
                accepted=bool(body.get("accepted", False)),
                supplier_reference=body.get("supplier_reference"),
                estimated_response_hours=body.get("estimated_response_hours"),
                mode=self.mode,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("wuerth returned an unusable ack: %s", type(exc).__name__)
            raise SupplierUnavailable(SUPPLIER) from None


def _build_item(
    part_number: str,
    raw: dict[str, Any] | None,
    currency: str,
    quantities: list[int],
) -> AvailabilityItem:
    """One answered part. A part the supplier does not carry is ``found=False``."""
    if raw is None:
        return AvailabilityItem(oem_part_number=part_number, found=False, currency=currency)

    stock = raw.get("quantity_available")
    stock_int = int(stock) if stock is not None else None
    breaks = sorted(raw.get("price_breaks", []), key=lambda b: int(b["min_quantity"]))

    quotes = [
        QuantityQuote(
            quantity=quantity,
            # None = carried, but not quoted at this quantity (see QuantityQuote).
            unit_price_minor=_price_for(breaks, quantity),
            status=classify_stock(stock_int, quantity),
        )
        for quantity in quantities
    ]

    return AvailabilityItem(
        oem_part_number=part_number,
        found=True,
        currency=currency,
        description=raw.get("description"),
        brand=raw.get("brand"),
        quantity_available=stock_int,
        lead_time_days=raw.get("lead_time_days"),
        quotes=tuple(quotes),
    )


def _price_for(breaks: list[dict[str, Any]], quantity: int) -> int | None:
    """The unit price (minor units) of the highest break at or below ``quantity``."""
    price: int | None = None
    for row in breaks:
        if int(row["min_quantity"]) <= quantity:
            price = int(row["unit_price_minor"])
        else:
            break
    return price


def _rfq_payload(request: SourcingRfqRequest) -> dict[str, Any]:
    """The documented outbound RFQ shape (fixtures/wuerth/README.md §2).

    Optional keys are omitted rather than sent as ``null``, and no file/CAD key
    exists at all: this lane carries part numbers and quantities only, which is
    why the M6.7c external-send gate does not apply to it.
    """
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "supplier": SUPPLIER,
        "reference": request.reference,
        "requested_by": request.requested_by,
    }
    if request.reply_to:
        payload["reply_to"] = request.reply_to
    if request.message:
        payload["message"] = request.message

    lines: list[dict[str, Any]] = []
    for line in request.lines:
        row: dict[str, Any] = {
            "oem_part_number": line.oem_part_number,
            "quantities": [int(q) for q in line.quantities],
        }
        if line.description:
            row["description"] = line.description
        lines.append(row)
    payload["lines"] = lines
    return payload


def build_wuerth_adapter(settings: Settings) -> WuerthMaterialPricingAdapter:
    """The adapter for the configured mode — the whole fixture→live swap."""
    if settings.wuerth_mode.strip().lower() == "live":
        return WuerthMaterialPricingAdapter(
            LiveWuerthClient(
                settings.wuerth_base_url,
                settings.wuerth_api_key,
                timeout_seconds=settings.wuerth_timeout_seconds,
            ),
            mode="live",
        )
    return WuerthMaterialPricingAdapter(FixtureWuerthClient(), mode="fixture")


def get_sourcing_adapter(request: Request) -> WuerthMaterialPricingAdapter:
    """FastAPI dependency: the org's sourcing adapter for this app instance.

    Settings come off ``app.state`` (the ``get_app_settings`` convention), so a
    test that overrides config is honoured; tests override *this* dependency to
    simulate a supplier outage.
    """
    return build_wuerth_adapter(request.app.state.settings)
