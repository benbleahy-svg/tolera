"""HubSpot CRM adapter (M6.8) — mock-first against ``fixtures/hubspot/crm.json``.

Structure mirrors ``app.services.suppliers.wuerth`` exactly, because the seam is
the same one: a **client Protocol** is the only thing that differs between the
fixture and the live endpoint, so promoting to real HubSpot is config
(``HUBSPOT_MODE=live`` + base URL + token) and nothing else.

HubSpot specifics worth knowing while reading:

* Its objects are *companies* and *contacts*; Tolera's are Accounts and
  Contacts. The mapping lives in ``_account_from`` / ``_contact_from`` and
  nowhere else.
* Every field sits under a ``properties`` sub-object, and HubSpot writes
  ``null`` rather than omitting. Both are handled by :func:`_prop`.
* A deal ``amount`` is a **decimal string** ("12345.67"). It is converted to
  integer minor units at this boundary (:func:`_amount_to_minor` /
  :func:`_minor_to_amount`) so no float ever reaches the domain — the money
  invariant in CLAUDE.md §5.
* The free HubSpot tier has no API access; spec ``#crm`` records that PP steers
  customers to CRM Starter for exactly this reason. Nothing to enforce in code,
  but it is why a "credentials present but 403" live failure is expected enough
  to degrade rather than crash.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .base import (
    CrmAccount,
    CrmContact,
    CrmDeal,
    CrmPullResult,
    CrmUnavailable,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import Request

    from app.config import Settings

logger = logging.getLogger(__name__)

PROVIDER = "hubspot"
SCHEMA_VERSION = "1.0"
#: The recorded response that IS the contract (see fixtures/hubspot/README.md).
FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "hubspot" / "crm.json"

#: HubSpot money is a decimal string in **major** units; ours is integer minor.
_MINOR_UNITS = Decimal(100)


# --------------------------------------------------------------------------- #
# Wire-format helpers (the only place HubSpot's shape is known)
# --------------------------------------------------------------------------- #


def _prop(record: dict[str, Any], key: str) -> str | None:
    """Read one HubSpot property, treating ``null`` and ``""`` as absent."""
    value = (record.get("properties") or {}).get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_ts(raw: str | None) -> datetime | None:
    """HubSpot's ``hs_lastmodifieddate`` (ISO-8601, ``Z``-suffixed)."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _amount_to_minor(raw: str | None) -> int | None:
    """HubSpot decimal-string amount → integer minor units.

    Delegates to ``app.tax.to_minor_units`` rather than rounding here, so the
    CRM boundary uses the same **kaufmännische Rundung** (ROUND_HALF_UP) as
    every other money path in the product. Python's default is banker's
    rounding, which would put a half-cent on the wrong side of the cent
    relative to the quote the deal is mirroring."""
    if raw is None:
        return None
    from app.tax import to_minor_units

    try:
        return to_minor_units(Decimal(str(raw)))
    except (InvalidOperation, ValueError):
        return None


def _minor_to_amount(amount_minor: int) -> str:
    """Integer minor units → the decimal string HubSpot expects on write.

    Exact: minor units are already whole cents, so the division only moves the
    decimal point — no rounding decision is taken here."""
    return str(
        (Decimal(amount_minor) / _MINOR_UNITS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _account_from(record: dict[str, Any]) -> CrmAccount:
    website = _prop(record, "domain")
    return CrmAccount(
        external_id=str(record["id"]),
        name=_prop(record, "name") or "",
        email=_prop(record, "email"),
        phone=_prop(record, "phone"),
        website=f"https://{website}" if website else None,
        updated_at=_parse_ts(_prop(record, "hs_lastmodifieddate")),
    )


def _contact_from(record: dict[str, Any]) -> CrmContact:
    return CrmContact(
        external_id=str(record["id"]),
        email=_prop(record, "email") or "",
        account_external_id=_prop(record, "associatedcompanyid"),
        first_name=_prop(record, "firstname"),
        last_name=_prop(record, "lastname"),
        phone=_prop(record, "phone"),
        updated_at=_parse_ts(_prop(record, "hs_lastmodifieddate")),
    )


# --------------------------------------------------------------------------- #
# The transport seam
# --------------------------------------------------------------------------- #


class HubSpotClient(Protocol):
    """The ONLY thing that differs between fixture and live."""

    async def fetch_crm(self) -> dict[str, Any]:
        """Companies + contacts, in the recorded document's shape."""
        ...

    async def upsert(self, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create-or-update one CRM object; returns at least ``{"id": ...}``."""
        ...


class FixtureHubSpotClient:
    """Serves the recorded document and records every write.

    ``last_writes`` makes the *outbound* payload assertable without a network,
    which is how the deal-on-send contract is tested."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self._path = fixture_path or FIXTURE_PATH
        self.last_writes: list[tuple[str, dict[str, Any]]] = []
        self._next_id = 1

    async def fetch_crm(self) -> dict[str, Any]:
        return _load_fixture(self._path)

    async def upsert(self, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_writes.append((object_type, payload))
        existing = payload.get("id")
        if existing:
            return {"id": str(existing), "updated": True}
        # Deterministic ids: no Math.random-style nondeterminism in a fixture.
        assigned = f"{object_type}-{self._next_id}"
        self._next_id += 1
        return {"id": assigned, "updated": False}


@lru_cache(maxsize=4)
def _load_fixture(path: Path) -> dict[str, Any]:
    import json

    return dict(json.loads(path.read_text(encoding="utf-8")))


class LiveHubSpotClient:
    """The real HubSpot CRM v3 API. No URL or credential literal lives here."""

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def fetch_crm(self) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            companies = await client.get(
                f"{self._base_url}/crm/v3/objects/companies",
                headers=self._headers(),
                params={"properties": "name,domain,phone,email,hs_lastmodifieddate"},
            )
            companies.raise_for_status()
            contacts = await client.get(
                f"{self._base_url}/crm/v3/objects/contacts",
                headers=self._headers(),
                params={
                    "properties": (
                        "email,firstname,lastname,phone,associatedcompanyid,hs_lastmodifieddate"
                    )
                },
            )
            contacts.raise_for_status()
        return {
            "schema_version": SCHEMA_VERSION,
            "results": {
                "companies": companies.json().get("results", []),
                "contacts": contacts.json().get("results", []),
            },
        }

    async def upsert(self, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        object_id = payload.get("id")
        url = f"{self._base_url}/crm/v3/objects/{object_type}"
        body = {"properties": payload.get("properties", {})}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if object_id:
                response = await client.patch(
                    f"{url}/{object_id}", headers=self._headers(), json=body
                )
            else:
                response = await client.post(url, headers=self._headers(), json=body)
            response.raise_for_status()
        return dict(response.json())


# --------------------------------------------------------------------------- #
# The adapter
# --------------------------------------------------------------------------- #


class HubSpotCrmAdapter:
    """Implements :class:`~app.services.crm.base.CrmAdapter` over HubSpot.

    Every client call **and its parsing** sits inside the guard: a drifted
    document is as much an outage as a refused connection, and both must reach
    the caller as :class:`CrmUnavailable` rather than an ``AttributeError`` from
    somewhere deep in a comprehension."""

    provider = PROVIDER

    def __init__(self, client: HubSpotClient, *, mode: str = "fixture") -> None:
        self._client = client
        self.mode = mode

    async def pull(self) -> CrmPullResult:
        try:
            document = await self._client.fetch_crm()
            results = document["results"]
            accounts = tuple(_account_from(rec) for rec in results["companies"])
            contacts = tuple(_contact_from(rec) for rec in results["contacts"])
        except Exception:
            logger.warning("hubspot_pull_failed", exc_info=True)
            raise CrmUnavailable(PROVIDER) from None
        # A company with no name or a contact with no email cannot be resolved
        # to a Tolera row; drop them here rather than writing a blank record.
        return CrmPullResult(
            accounts=tuple(a for a in accounts if a.name),
            contacts=tuple(c for c in contacts if c.email),
        )

    async def push_account(self, account: CrmAccount) -> str:
        payload: dict[str, Any] = {
            "properties": _drop_empty(
                {
                    "name": account.name,
                    "email": account.email,
                    "phone": account.phone,
                    "domain": _domain_of(account.website),
                }
            )
        }
        if account.external_id:
            payload["id"] = account.external_id
        return await self._upsert("companies", payload)

    async def push_contact(self, contact: CrmContact) -> str:
        payload: dict[str, Any] = {
            "properties": _drop_empty(
                {
                    "email": contact.email,
                    "firstname": contact.first_name,
                    "lastname": contact.last_name,
                    "phone": contact.phone,
                    "associatedcompanyid": contact.account_external_id,
                }
            )
        }
        if contact.external_id:
            payload["id"] = contact.external_id
        return await self._upsert("contacts", payload)

    async def push_deal(self, deal: CrmDeal) -> str:
        """Write/link the deal for a sent quote (spec ``#crm`` advanced tier).

        ``amount`` leaves as HubSpot's decimal string; ``tolera_quote_id`` is the
        back-reference that makes the link two-way without a join table."""
        payload: dict[str, Any] = {
            "properties": _drop_empty(
                {
                    "dealname": deal.name,
                    "amount": _minor_to_amount(deal.amount_minor),
                    "deal_currency_code": deal.currency,
                    "dealstage": deal.stage,
                    "tolera_quote_id": deal.quote_id,
                }
            )
        }
        if deal.external_id:
            payload["id"] = deal.external_id
        return await self._upsert("deals", payload)

    async def _upsert(self, object_type: str, payload: dict[str, Any]) -> str:
        try:
            response = await self._client.upsert(object_type, payload)
            return str(response["id"])
        except Exception:
            logger.warning("hubspot_upsert_failed", extra={"object_type": object_type})
            raise CrmUnavailable(PROVIDER) from None


def _drop_empty(properties: dict[str, Any]) -> dict[str, Any]:
    """Omit absent keys rather than sending ``null``.

    HubSpot treats an explicit ``null`` as "clear this field" — sending one for
    a value Tolera simply does not hold would *erase* CRM data, which is the one
    way a "Tolera wins" sync could still destroy something it did not own."""
    return {key: value for key, value in properties.items() if value not in (None, "")}


def _domain_of(website: str | None) -> str | None:
    """HubSpot keys companies on a bare ``domain``, not a URL."""
    if not website:
        return None
    return website.removeprefix("https://").removeprefix("http://").strip("/") or None


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def build_hubspot_adapter(settings: Settings) -> HubSpotCrmAdapter:
    """The whole fixture→live swap (build-plan M6 "Adapter posture")."""
    if settings.hubspot_mode.strip().lower() == "live":
        return HubSpotCrmAdapter(
            LiveHubSpotClient(
                settings.hubspot_base_url,
                settings.hubspot_api_key,
                timeout_seconds=settings.hubspot_timeout_seconds,
            ),
            mode="live",
        )
    return HubSpotCrmAdapter(FixtureHubSpotClient(), mode="fixture")


def get_crm_adapter(request: Request) -> HubSpotCrmAdapter:
    """FastAPI dependency — overridden in tests to simulate a CRM outage."""
    return build_hubspot_adapter(request.app.state.settings)
