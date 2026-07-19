"""Idempotent Supplier Directory seed — the pilot's outside-process vendors (M6.3).

The Supplier Directory is only meaningful with vendors in it: the M6.4 batch-send
modal ranks and pre-checks them, and the M6.3 checkpoint review clicks through a
populated list. So each demo org gets a small, deterministic set of DACH vendors
covering the three outside processes the block's test plan names — anodize /
plating / heat treat — across aluminium, titanium and steel.

Idempotent under **sequential** re-runs, exactly like ``app.crm_seed``: each vendor
is matched on its natural key ``(org_id, name)`` among live rows and either
inserted or reconciled back to spec, so re-running never duplicates. Runs on the
**owner** connection (bypasses RLS); the explicit ``org_id`` filter scopes the
writes. ``vendor.name`` is deliberately not a DB unique key (multiple sites may
share a name), so this cannot be a single atomic upsert.

These are **placeholder demo values** — plausible German suppliers, not real
companies — until the anonymised Fechner packages land. Capability tags are stored
lowercase to match the normalization ``app.vendors`` applies on write, so the
directory filter finds them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vendor, VendorContact, VendorStatus


@dataclass(frozen=True)
class _VendorSpec:
    name: str
    address: str
    vat_id: str
    processes: tuple[str, ...]
    materials: tuple[str, ...]
    contact_name: str
    contact_email: str


#: The pilot vendor set — one per outside process the block's fixtures exercise.
VENDOR_SPECS: tuple[_VendorSpec, ...] = (
    _VendorSpec(
        name="Eloxal Werk Ost GmbH",
        address="Ostweg 12\n04347 Leipzig",
        vat_id="DE811234567",
        processes=("anodize", "polish"),
        materials=("aluminium",),
        contact_name="Ute Mann",
        contact_email="angebot@eloxal-ost.example",
    ),
    _VendorSpec(
        name="Galvanik Süd GmbH",
        address="Südring 9\n70565 Stuttgart",
        vat_id="DE812345678",
        processes=("plating", "passivate"),
        materials=("steel", "titanium"),
        contact_name="Bernd Klose",
        contact_email="angebot@galvanik-sued.example",
    ),
    _VendorSpec(
        name="Härterei Nord GmbH",
        address="Industriestraße 4\n21079 Hamburg",
        vat_id="DE813456789",
        processes=("heat treat",),
        materials=("steel",),
        contact_name="Anke Vogt",
        contact_email="angebot@haerterei-nord.example",
    ),
)


@dataclass(frozen=True)
class VendorSeedResult:
    """Outcome of seeding the directory (ids + how many were newly created). No
    contact email is carried — vendor contacts are personal data (CLAUDE.md §5)."""

    vendor_ids: tuple[uuid.UUID, ...]
    vendors_created: int
    contacts_created: int


async def seed_vendors(session: AsyncSession, *, org_id: uuid.UUID) -> VendorSeedResult:
    """Idempotently ensure the demo vendors + their quoting contacts exist."""
    vendor_ids: list[uuid.UUID] = []
    vendors_created = 0
    contacts_created = 0

    for spec in VENDOR_SPECS:
        vendor = await session.scalar(
            select(Vendor).where(
                Vendor.org_id == org_id,
                Vendor.name == spec.name,
                Vendor.deleted_at.is_(None),
            )
        )
        if vendor is None:
            vendor = Vendor(org_id=org_id, name=spec.name)
            session.add(vendor)
            vendors_created += 1
        # Reconcile back to spec on every run (see module docstring).
        vendor.address = spec.address
        vendor.vat_id = spec.vat_id
        vendor.status = VendorStatus.active
        vendor.capabilities = {
            "processes": list(spec.processes),
            "materials": list(spec.materials),
        }
        await session.flush()
        vendor_ids.append(vendor.id)

        contact = await session.scalar(
            select(VendorContact).where(
                VendorContact.org_id == org_id,
                VendorContact.vendor_id == vendor.id,
                VendorContact.email == spec.contact_email,
                VendorContact.deleted_at.is_(None),
            )
        )
        if contact is None:
            contact = VendorContact(
                org_id=org_id,
                vendor_id=vendor.id,
                email=spec.contact_email,
            )
            session.add(contact)
            contacts_created += 1
        contact.name = spec.contact_name
        contact.is_primary = True
        await session.flush()

    return VendorSeedResult(
        vendor_ids=tuple(vendor_ids),
        vendors_created=vendors_created,
        contacts_created=contacts_created,
    )
