"""M6.3 — Vendor Library & Directory.

Exercises the block's acceptance criteria (build-plan/M6-differentiators-hardening.md
§M6.3; spec ``#vendor-rfq`` → "Supplier Directory"):

  * CRUD round-trips a vendor + its quoting contacts;
  * the capabilities filter (process / material) narrows the directory;
  * **Notes never serialize into any vendor-facing payload** — asserted against the
    external DTO seam M6.4/M6.5 must reuse, since no portal exists yet;
  * vendors are org-scoped — cross-org denial holds at the API *and* at the DB;
  * an ERP-sourced vendor exposes ``erp_vendor_id`` and its **identity** fields are
    read-only (ERP is source of truth), while BF-only data (capabilities, notes)
    stays editable and never writes back.

All requests run through the restricted (RLS-bound) ``app_client``; cross-org rows
are planted over the owner connection via ``seeder``.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed

ADMIN = [MembershipRole.admin]
VIEWER = [MembershipRole.viewer]


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _plant_vendor(
    seeder: Seeder,
    org_id: uuid.UUID,
    name: str,
    *,
    erp_vendor_id: str | None = None,
) -> uuid.UUID:
    """Plant a vendor over the owner connection (bypasses RLS) — for cross-org rows
    the API of the *other* org must never see."""
    vendor_id = uuid.uuid4()
    seeder.sql(
        "INSERT INTO vendor (id, org_id, name, erp_vendor_id) VALUES (:id, :org_id, :name, :erp)",
        {"id": vendor_id, "org_id": org_id, "name": name, "erp": erp_vendor_id},
    )
    return vendor_id


# --------------------------------------------------------------------------- #
# CRUD round-trip
# --------------------------------------------------------------------------- #
def test_vendor_crud_round_trip(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        created = app_client.post(
            "/api/vendors",
            json={
                "name": "Härterei Nord GmbH",
                "address": "Industriestraße 4\n21079 Hamburg",
                "vat_id": "DE123456789",
                "capabilities": {"processes": ["heat treat"], "materials": ["steel"]},
                "notes": "Zahlungsziel 30 Tage — intern.",
                "primary_contact": {
                    "name": "Anke Vogt",
                    "email": "vogt@haerterei-nord.example",
                    "is_primary": True,
                },
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        vendor_id = body["id"]
        assert body["name"] == "Härterei Nord GmbH"
        assert body["status"] == "active"
        assert body["erp_vendor_id"] is None
        assert body["capabilities"] == {"processes": ["heat treat"], "materials": ["steel"]}
        # No vendor RFQs exist until M6.4 — the column ships, the count is honest.
        assert body["active_rfq_count"] == 0

        # The primary contact was created in the same transaction.
        contacts = app_client.get(f"/api/vendors/{vendor_id}/contacts").json()
        assert [c["email"] for c in contacts] == ["vogt@haerterei-nord.example"]
        assert contacts[0]["is_primary"] is True

        # Update: rename + flip to inactive.
        patched = app_client.patch(
            f"/api/vendors/{vendor_id}", json={"name": "Härterei Nord AG", "status": "inactive"}
        )
        assert patched.status_code == 200
        assert patched.json()["name"] == "Härterei Nord AG"
        assert patched.json()["status"] == "inactive"

        # Archive hides it from the default list but the row persists.
        assert app_client.post(f"/api/vendors/{vendor_id}/archive").status_code == 200
        assert app_client.get("/api/vendors").json() == []
        assert app_client.get(f"/api/vendors/{vendor_id}").json()["archived"] is True
        assert len(app_client.get("/api/vendors", params={"include_archived": True}).json()) == 1

        # Restore brings it back.
        assert app_client.post(f"/api/vendors/{vendor_id}/restore").status_code == 200
        assert len(app_client.get("/api/vendors").json()) == 1


def test_vendor_contact_crud_round_trip(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        vendor_id = app_client.post("/api/vendors", json={"name": "Galvanik Süd"}).json()["id"]

        created = app_client.post(
            f"/api/vendors/{vendor_id}/contacts",
            json={"name": "Bernd Klose", "email": "klose@galvanik-sued.example", "cc": True},
        )
        assert created.status_code == 201, created.text
        contact_id = created.json()["id"]
        assert created.json()["cc"] is True
        assert created.json()["is_primary"] is False

        patched = app_client.patch(
            f"/api/vendor-contacts/{contact_id}", json={"is_primary": True, "phone": "+49 711 1234"}
        )
        assert patched.status_code == 200
        assert patched.json()["is_primary"] is True
        assert patched.json()["phone"] == "+49 711 1234"

        assert app_client.delete(f"/api/vendor-contacts/{contact_id}").status_code == 204
        assert app_client.get(f"/api/vendors/{vendor_id}/contacts").json() == []


# --------------------------------------------------------------------------- #
# Directory list — search + capabilities filter
# --------------------------------------------------------------------------- #
def _seed_directory(app_client: TestClient) -> None:
    for name, processes, materials in (
        ("Eloxal Werk Ost", ["anodize"], ["aluminium"]),
        ("Galvanik Süd", ["plating"], ["steel", "titanium"]),
        ("Härterei Nord", ["heat treat"], ["steel"]),
    ):
        app_client.post(
            "/api/vendors",
            json={
                "name": name,
                "capabilities": {"processes": processes, "materials": materials},
            },
        )


def test_capabilities_filter_narrows_the_directory(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        _seed_directory(app_client)

        by_process = app_client.get("/api/vendors", params={"process": "anodize"}).json()
        assert [v["name"] for v in by_process] == ["Eloxal Werk Ost"]

        by_material = app_client.get("/api/vendors", params={"material": "steel"}).json()
        assert [v["name"] for v in by_material] == ["Galvanik Süd", "Härterei Nord"]

        # Process + material intersect (AND), not union.
        both = app_client.get(
            "/api/vendors", params={"process": "plating", "material": "titanium"}
        ).json()
        assert [v["name"] for v in both] == ["Galvanik Süd"]
        assert (
            app_client.get(
                "/api/vendors", params={"process": "anodize", "material": "titanium"}
            ).json()
            == []
        )

        # Tags match case-insensitively — chips are free text typed by humans.
        assert len(app_client.get("/api/vendors", params={"process": "ANODIZE"}).json()) == 1


def test_directory_search_and_status_filter(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        _seed_directory(app_client)

        found = app_client.get("/api/vendors", params={"q": "galvanik"}).json()
        assert [v["name"] for v in found] == ["Galvanik Süd"]

        vendor_id = found[0]["id"]
        app_client.patch(f"/api/vendors/{vendor_id}", json={"status": "inactive"})
        active = app_client.get("/api/vendors", params={"status": "active"}).json()
        assert "Galvanik Süd" not in [v["name"] for v in active]
        inactive = app_client.get("/api/vendors", params={"status": "inactive"}).json()
        assert [v["name"] for v in inactive] == ["Galvanik Süd"]


# --------------------------------------------------------------------------- #
# Notes never reach the vendor  (block AC)
# --------------------------------------------------------------------------- #
def test_notes_absent_from_vendor_facing_payload(app_client: TestClient, seeder: Seeder) -> None:
    """The internal DTO carries ``notes``; the vendor-facing one must not — the
    seam every outbound M6.4/M6.5 payload is required to serialize through."""
    from app.vendors import VendorExternalOut, vendor_external_out

    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        vendor_id = app_client.post(
            "/api/vendors",
            json={"name": "Galvanik Süd", "notes": "Streitfall 2025 — nie an Lieferant zeigen."},
        ).json()["id"]
        internal = app_client.get(f"/api/vendors/{vendor_id}").json()

    assert internal["notes"] == "Streitfall 2025 — nie an Lieferant zeigen."
    # The external contract cannot even express notes.
    assert "notes" not in VendorExternalOut.model_fields
    external = vendor_external_out(
        _StubVendor(id=uuid.UUID(vendor_id), name="Galvanik Süd", notes="secret")
    )
    assert "notes" not in external.model_dump()
    assert "secret" not in external.model_dump_json()


class _StubVendor:
    """Minimal duck-type for the external serializer (no DB round-trip needed)."""

    def __init__(self, *, id: uuid.UUID, name: str, notes: str) -> None:
        self.id = id
        self.name = name
        self.notes = notes
        # Annotated optional to match the Protocol exactly — a Protocol's mutable
        # attributes are invariant, so `str` would not satisfy `str | None`.
        self.address: str | None = "Industriestraße 4"
        self.vat_id: str | None = "DE123456789"


# --------------------------------------------------------------------------- #
# ERP-sourced vendors — identity read-only, BF-only data still editable
# --------------------------------------------------------------------------- #
def test_erp_sourced_vendor_identity_is_read_only(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    vendor_id = _plant_vendor(seeder, org, "SAP-Lieferant GmbH", erp_vendor_id="ERP-4711")

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        detail = app_client.get(f"/api/vendors/{vendor_id}").json()
        assert detail["erp_vendor_id"] == "ERP-4711"
        assert detail["erp_managed"] is True

        # Identity fields are owned by the ERP (one-way ERP → Tolera).
        rejected = app_client.patch(f"/api/vendors/{vendor_id}", json={"name": "Umbenannt GmbH"})
        assert rejected.status_code == 409
        assert rejected.json()["code"] == "vendor_erp_managed"
        assert app_client.get(f"/api/vendors/{vendor_id}").json()["name"] == "SAP-Lieferant GmbH"

        assert (
            app_client.patch(f"/api/vendors/{vendor_id}", json={"address": "Neue Str. 1"})
        ).status_code == 409

        # BF-only data is NOT ERP-owned and stays editable — it never writes back.
        ok = app_client.patch(
            f"/api/vendors/{vendor_id}",
            json={
                "capabilities": {"processes": ["laser osv"], "materials": ["steel"]},
                "notes": "Rahmenvertrag läuft bis 2027.",
                "status": "inactive",
            },
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["capabilities"]["processes"] == ["laser osv"]
        assert ok.json()["notes"] == "Rahmenvertrag läuft bis 2027."

        # Contact identity is ERP-owned too.
        assert (
            app_client.post(
                f"/api/vendors/{vendor_id}/contacts",
                json={"name": "Neu", "email": "neu@erp.example"},
            ).status_code
            == 409
        )


# --------------------------------------------------------------------------- #
# Tenancy — API denial + DB-level RLS proof
# --------------------------------------------------------------------------- #
def test_vendor_cross_org_isolation_both_directions(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, admin_b = _org_with_admin(seeder, "org-b")
    _plant_vendor(seeder, org_a, "A-Lieferant")
    vendor_b = _plant_vendor(seeder, org_b, "B-Lieferant")

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        a_list = app_client.get("/api/vendors").json()
        a_sees_b = app_client.get(f"/api/vendors/{vendor_b}")
        a_patches_b = app_client.patch(f"/api/vendors/{vendor_b}", json={"notes": "pwn"})
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        b_list = app_client.get("/api/vendors").json()

    assert [v["name"] for v in a_list] == ["A-Lieferant"]
    assert [v["name"] for v in b_list] == ["B-Lieferant"]
    # RLS makes a foreign row invisible — 404, never 403.
    assert a_sees_b.status_code == 404
    assert a_patches_b.status_code == 404


def test_vendor_rls_enforced_at_the_database(tenancy_db: str, seeder: Seeder) -> None:
    """The restricted role sees ZERO vendors/contacts with no org GUC set."""
    org = seeder.org("org-a")
    vendor_id = _plant_vendor(seeder, org, "Geheim GmbH")
    seeder.sql(
        "INSERT INTO vendor_contact (org_id, vendor_id, name, email) "
        "VALUES (:org_id, :vendor_id, 'Geheim', 'geheim@example.com')",
        {"org_id": org, "vendor_id": vendor_id},
    )

    async def _counts() -> tuple[int, int, int, int]:
        app_engine = create_async_engine(app_role_url(tenancy_db))
        owner_engine = create_async_engine(tenancy_db)
        try:
            async with app_engine.connect() as conn:  # no set_config → GUC unset
                r_v = (await conn.execute(text("SELECT count(*) FROM vendor"))).scalar_one()
                r_c = (await conn.execute(text("SELECT count(*) FROM vendor_contact"))).scalar_one()
            async with owner_engine.connect() as conn:
                o_v = (await conn.execute(text("SELECT count(*) FROM vendor"))).scalar_one()
                o_c = (await conn.execute(text("SELECT count(*) FROM vendor_contact"))).scalar_one()
        finally:
            await app_engine.dispose()
            await owner_engine.dispose()
        return int(r_v), int(r_c), int(o_v), int(o_c)

    restricted_v, restricted_c, owner_v, owner_c = asyncio.run(_counts())
    assert (restricted_v, restricted_c) == (0, 0)
    assert (owner_v, owner_c) == (1, 1)


def test_vendor_contact_cannot_be_attached_across_orgs(
    app_client: TestClient, seeder: Seeder
) -> None:
    """A contact must hang off a vendor in the SAME org (composite FK + RLS)."""
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, _ = _org_with_admin(seeder, "org-b")
    vendor_b = _plant_vendor(seeder, org_b, "B-Lieferant")

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        resp = app_client.post(
            f"/api/vendors/{vendor_b}/contacts",
            json={"name": "Eve", "email": "eve@evil.example"},
        )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #
def test_writes_require_config_edit(app_client: TestClient, seeder: Seeder) -> None:
    org = seeder.org("org-a")
    viewer = seeder.user("viewer@org-a.example")
    seeder.membership(viewer, org, VIEWER)
    vendor_id = _plant_vendor(seeder, org, "Galvanik Süd")

    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        assert app_client.get("/api/vendors").status_code == 200  # read is fine
        assert app_client.post("/api/vendors", json={"name": "Neu"}).status_code == 403
        assert app_client.patch(f"/api/vendors/{vendor_id}", json={"notes": "x"}).status_code == 403
        assert app_client.post(f"/api/vendors/{vendor_id}/archive").status_code == 403


# --------------------------------------------------------------------------- #
# RFQ History tab + CSV import
# --------------------------------------------------------------------------- #
def test_rfq_history_is_empty_until_m64(app_client: TestClient, seeder: Seeder) -> None:
    """The tab exists and is read-only here; M6.4+ populates it."""
    org, admin = _org_with_admin(seeder, "org-a")
    vendor_id = _plant_vendor(seeder, org, "Galvanik Süd")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.get(f"/api/vendors/{vendor_id}/rfq-history")
        assert resp.status_code == 200
        assert resp.json() == []


def test_csv_import_creates_vendors_and_contacts(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    csv_body = (
        "name,address,vat_id,processes,materials,contact_name,contact_email\n"
        "Eloxal Werk Ost,Ostweg 1,DE111111111,anodize;polish,aluminium,"
        "Ute Mann,ute@eloxal.example\n"
        "Galvanik Süd,Südring 9,,plating,steel;titanium,,\n"
    )
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.post(
            "/api/vendors/import",
            content=csv_body.encode("utf-8"),
            headers={"Content-Type": "text/csv"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["created"] == 2
        assert resp.json()["errors"] == []

        listed = app_client.get("/api/vendors").json()
        assert [v["name"] for v in listed] == ["Eloxal Werk Ost", "Galvanik Süd"]
        eloxal = listed[0]
        assert eloxal["capabilities"] == {
            "processes": ["anodize", "polish"],
            "materials": ["aluminium"],
        }
        contacts = app_client.get(f"/api/vendors/{eloxal['id']}/contacts").json()
        assert [c["email"] for c in contacts] == ["ute@eloxal.example"]
        assert contacts[0]["is_primary"] is True


def test_csv_import_reports_bad_rows_without_aborting(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    csv_body = (
        "name,contact_email\n"
        "Gute GmbH,gut@example.com\n"
        ",kein-name@example.com\n"
        "Schlechte GmbH,nicht-valide\n"
    )
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.post(
            "/api/vendors/import",
            content=csv_body.encode("utf-8"),
            headers={"Content-Type": "text/csv"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["created"] == 1
        assert len(body["errors"]) == 2
        assert {e["row"] for e in body["errors"]} == {2, 3}
        assert [v["name"] for v in app_client.get("/api/vendors").json()] == ["Gute GmbH"]


# --------------------------------------------------------------------------- #
# Demo seed
# --------------------------------------------------------------------------- #
def test_vendor_seed_is_idempotent(app_client: TestClient, seeder: Seeder, tenancy_db: str) -> None:
    """``seed_vendors`` runs on every ``seed_demo`` — re-running must reconcile,
    never duplicate (the ``app.crm_seed`` contract)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.vendor_seed import VENDOR_SPECS, seed_vendors

    org, admin = _org_with_admin(seeder, "org-a")

    async def _seed_twice() -> tuple[int, int]:
        # The seed runs on the OWNER connection (bypasses RLS), like seed_demo.
        engine = create_async_engine(tenancy_db)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session, session.begin():
                first = await seed_vendors(session, org_id=org)
            async with maker() as session, session.begin():
                second = await seed_vendors(session, org_id=org)
        finally:
            await engine.dispose()
        return first.vendors_created, second.vendors_created

    created_first, created_second = asyncio.run(_seed_twice())
    assert created_first == len(VENDOR_SPECS)
    assert created_second == 0  # reconciled, not duplicated

    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        listed = app_client.get("/api/vendors").json()
    assert len(listed) == len(VENDOR_SPECS)
    # The seeded capability tags are what the directory filter matches on.
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        anodize = app_client.get("/api/vendors", params={"process": "anodize"}).json()
    assert [v["name"] for v in anodize] == ["Eloxal Werk Ost GmbH"]
