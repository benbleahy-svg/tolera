"""M1.2 — File upload & storage.

Exercises the acceptance criteria (upload→download byte-identical; PRIMARY swap;
disallowed types rejected; files org-scoped) and the DECISIONS.md 2026-06-25 M1.2
rulings: files attach to a Part, auto-PRIMARY by geometric rank, one PRIMARY per
part, hard delete with a PRIMARY-delete guard. All requests run through the
restricted (RLS-bound) ``app_client`` over the in-memory storage backend; cross-org
rows are planted via the owner-connection ``seeder``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import create_app
from app.models import FileRole, MembershipRole
from app.storage import MemoryStorage
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings


def _memory_storage(client: TestClient) -> MemoryStorage:
    """The in-memory object store backing the test app (for blob-level assertions)."""
    return cast(MemoryStorage, cast(FastAPI, client.app).state.storage)


ADMIN = [MembershipRole.admin]
ESTIMATOR = [MembershipRole.estimator]
VIEWER = [MembershipRole.viewer]

# Minimal valid file bodies. STEP/PDF start with the magic tokens the sniff checks.
STEP_BYTES = b"ISO-10303-21;\nHEADER;\nFILE_NAME('bracket.step');\nENDSEC;\nEND-ISO-10303-21;\n"
PDF_BYTES = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _step(name: str = "bracket.step") -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, STEP_BYTES, "application/step"))


def _pdf(name: str = "drawing.pdf") -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, PDF_BYTES, "application/pdf"))


def _create_part(client: TestClient) -> str:
    created = client.post("/api/parts")
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


# --------------------------------------------------------------------------- #
# Upload → download round-trip + auto-PRIMARY
# --------------------------------------------------------------------------- #
def test_upload_download_round_trip_byte_identical(app_client: TestClient, seeder: Seeder) -> None:
    """The headline acceptance: a file uploaded then downloaded is byte-identical,
    and a CAD file uploaded alongside a print is auto-tagged PRIMARY."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)

        # Upload a STEP + a PDF in one request (the test-plan fixtures).
        resp = app_client.post(f"/api/parts/{part_id}/files", files=[_step(), _pdf()])
        assert resp.status_code == 201, resp.text
        by_name = {f["filename"]: f for f in resp.json()}
        # CAD wins → PRIMARY; print → supporting (DECISIONS.md 2026-06-25).
        assert by_name["bracket.step"]["role"] == "primary"
        assert by_name["bracket.step"]["file_type"] == "brep_cad"
        assert by_name["drawing.pdf"]["role"] == "supporting"
        assert by_name["bracket.step"]["size_bytes"] == len(STEP_BYTES)

        # The part now points at the STEP as its PRIMARY.
        part = app_client.get(f"/api/parts/{part_id}").json()
        assert part["primary_file_id"] == by_name["bracket.step"]["id"]

        # Download round-trips byte-identical.
        step_id = by_name["bracket.step"]["id"]
        dl = app_client.get(f"/api/parts/{part_id}/files/{step_id}/download")
        assert dl.status_code == 200
        assert dl.content == STEP_BYTES
        assert "bracket.step" in dl.headers["content-disposition"]


def test_list_files_primary_first(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        app_client.post(f"/api/parts/{part_id}/files", files=[_step(), _pdf()])

        listed = app_client.get(f"/api/parts/{part_id}/files").json()
        assert [f["role"] for f in listed] == ["primary", "supporting"]
        assert listed[0]["filename"] == "bracket.step"


def test_first_file_becomes_primary_even_if_not_cad(app_client: TestClient, seeder: Seeder) -> None:
    """A part with no PRIMARY adopts the (only) uploaded file as PRIMARY — a lone
    print becomes the source of truth until a better file is added/swapped."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        resp = app_client.post(f"/api/parts/{part_id}/files", files=[_pdf()])
        assert resp.json()[0]["role"] == "primary"


def test_later_upload_is_supporting_when_primary_exists(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        app_client.post(f"/api/parts/{part_id}/files", files=[_step()])
        # A second upload (even another CAD) is supporting — no auto-takeover.
        resp = app_client.post(f"/api/parts/{part_id}/files", files=[_step("v2.step")])
        assert resp.json()[0]["role"] == "supporting"


# --------------------------------------------------------------------------- #
# PRIMARY swap
# --------------------------------------------------------------------------- #
def test_swap_primary(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        uploaded = app_client.post(f"/api/parts/{part_id}/files", files=[_step(), _pdf()]).json()
        by_name = {f["filename"]: f for f in uploaded}
        pdf_id = by_name["drawing.pdf"]["id"]
        step_id = by_name["bracket.step"]["id"]

        swapped = app_client.post(f"/api/parts/{part_id}/files/{pdf_id}/primary")
        assert swapped.status_code == 200
        assert swapped.json()["role"] == "primary"

        # Exactly one PRIMARY, and it's the PDF now.
        listed = {f["filename"]: f for f in app_client.get(f"/api/parts/{part_id}/files").json()}
        assert listed["drawing.pdf"]["role"] == "primary"
        assert listed["bracket.step"]["role"] == "supporting"
        assert app_client.get(f"/api/parts/{part_id}").json()["primary_file_id"] == pdf_id

        # Idempotent: setting the current primary again is a no-op 200.
        assert app_client.post(f"/api/parts/{part_id}/files/{pdf_id}/primary").status_code == 200
        # Swap back works too.
        app_client.post(f"/api/parts/{part_id}/files/{step_id}/primary")
        assert app_client.get(f"/api/parts/{part_id}").json()["primary_file_id"] == step_id


# --------------------------------------------------------------------------- #
# Delete (hard) + PRIMARY-delete guard
# --------------------------------------------------------------------------- #
def test_delete_supporting_file_then_primary_last(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    storage = _memory_storage(app_client)
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        uploaded = app_client.post(f"/api/parts/{part_id}/files", files=[_step(), _pdf()]).json()
        by_name = {f["filename"]: f for f in uploaded}
        step_id, pdf_id = by_name["bracket.step"]["id"], by_name["drawing.pdf"]["id"]
        assert len(storage._objects) == 2  # both blobs stored

        # Deleting the PRIMARY while a supporting file remains is blocked.
        blocked = app_client.delete(f"/api/parts/{part_id}/files/{step_id}")
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "primary_delete_blocked"

        # Delete the supporting file: the BLOB is purged (not just the row), and a
        # subsequent download 404s. The purge runs in the post-response background task.
        assert app_client.delete(f"/api/parts/{part_id}/files/{pdf_id}").status_code == 204
        assert len(storage._objects) == 1  # blob actually gone, not just the DB row
        assert app_client.get(f"/api/parts/{part_id}/files/{pdf_id}/download").status_code == 404

        # Now the PRIMARY is the last file → deletable; the pointer is nulled.
        assert app_client.delete(f"/api/parts/{part_id}/files/{step_id}").status_code == 204
        assert len(storage._objects) == 0  # last blob purged
        assert app_client.get(f"/api/parts/{part_id}").json()["primary_file_id"] is None
        assert app_client.get(f"/api/parts/{part_id}/files").json() == []


# --------------------------------------------------------------------------- #
# Type allow-list + magic-byte sniff + size cap
# --------------------------------------------------------------------------- #
def test_disallowed_extension_rejected(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        resp = app_client.post(
            f"/api/parts/{part_id}/files",
            files=[("files", ("malware.exe", b"MZ\x90\x00", "application/octet-stream"))],
        )
        assert resp.status_code == 415
        assert resp.json()["code"] == "unsupported_file_type"


def test_spoofed_pdf_rejected_by_magic_sniff(app_client: TestClient, seeder: Seeder) -> None:
    """A non-PDF renamed .pdf is caught by the content sniff (DECISIONS.md 2026-06-25)."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        resp = app_client.post(
            f"/api/parts/{part_id}/files",
            files=[("files", ("evil.pdf", b"MZ\x90\x00 not a pdf", "application/pdf"))],
        )
        assert resp.status_code == 415
        assert resp.json()["code"] == "file_type_mismatch"


def test_bad_file_in_batch_rejects_whole_request(app_client: TestClient, seeder: Seeder) -> None:
    """One invalid file rejects the batch and stores nothing (no orphan blobs)."""
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        part_id = _create_part(app_client)
        resp = app_client.post(
            f"/api/parts/{part_id}/files",
            files=[_step(), ("files", ("x.exe", b"MZ", "application/octet-stream"))],
        )
        assert resp.status_code == 415
        assert app_client.get(f"/api/parts/{part_id}/files").json() == []


def test_oversize_upload_rejected(seeder: Seeder, tenancy_db: str) -> None:
    """A file over the cap is rejected 413. Uses a 1 MB cap so the test stays cheap."""
    settings = build_settings(
        database_url=tenancy_db, app_database_url=app_role_url(tenancy_db), max_upload_mb=1
    )
    org, admin = _org_with_admin(seeder, "org-a")
    with (
        TestClient(create_app(settings)) as client,
        authed(client, user_id=admin, org_id=org, roles=ADMIN),
    ):
        part_id = _create_part(client)
        big = b"\x00" * (1024 * 1024 + 1024)  # just over 1 MB
        resp = client.post(
            f"/api/parts/{part_id}/files",
            files=[("files", ("big.stl", big, "model/stl"))],
        )
        assert resp.status_code == 413
        assert resp.json()["code"] == "file_too_large"


# --------------------------------------------------------------------------- #
# Org isolation (RLS)
# --------------------------------------------------------------------------- #
def test_cross_org_isolation(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, _admin_b = _org_with_admin(seeder, "org-b")
    part_b = seeder.part(org_b)
    file_b = seeder.part_file(org_b, part_b, role=FileRole.primary)

    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        assert app_client.get("/api/parts").json() == []
        # RLS makes another org's part a 404, not a 403.
        assert app_client.get(f"/api/parts/{part_b}").status_code == 404
        assert app_client.get(f"/api/parts/{part_b}/files").status_code == 404
        assert app_client.get(f"/api/parts/{part_b}/files/{file_b}/download").status_code == 404


def test_part_file_rls_enforced_at_the_database(tenancy_db: str, seeder: Seeder) -> None:
    """The restricted role sees ZERO part files with no org GUC set (DB guarantee)."""
    org = seeder.org("org-a")
    part = seeder.part(org)
    seeder.part_file(org, part, role=FileRole.primary)

    async def _counts() -> tuple[int, int]:
        app_engine = create_async_engine(app_role_url(tenancy_db))
        owner_engine = create_async_engine(tenancy_db)
        try:
            async with app_engine.connect() as conn:  # no set_config → GUC unset
                restricted = (
                    await conn.execute(text("SELECT count(*) FROM part_file"))
                ).scalar_one()
            async with owner_engine.connect() as conn:
                owner = (await conn.execute(text("SELECT count(*) FROM part_file"))).scalar_one()
        finally:
            await app_engine.dispose()
            await owner_engine.dispose()
        return restricted, owner

    restricted_count, owner_count = asyncio.run(_counts())
    assert restricted_count == 0
    assert owner_count == 1


# --------------------------------------------------------------------------- #
# RBAC + auth
# --------------------------------------------------------------------------- #
def test_rbac_upload_gates(app_client: TestClient, seeder: Seeder) -> None:
    """Writes need quote_edit; reads need only an authed session (DECISIONS.md
    2026-06-25 — file management is editing the quote's content)."""
    org = seeder.org("org-a")
    viewer = seeder.user("viewer@org-a.example")
    estimator = seeder.user("est@org-a.example")
    seeder.membership(viewer, org, VIEWER)
    seeder.membership(estimator, org, ESTIMATOR)

    # viewer cannot create a part or upload, but can read.
    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        assert app_client.post("/api/parts").status_code == 403

    # estimator: full file management.
    with authed(app_client, user_id=estimator, org_id=org, roles=ESTIMATOR):
        part_id = _create_part(app_client)
        up = app_client.post(f"/api/parts/{part_id}/files", files=[_step()])
        assert up.status_code == 201
        file_id = up.json()[0]["id"]

    # viewer can read/list/download but not mutate (delete OR swap PRIMARY).
    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        assert app_client.get(f"/api/parts/{part_id}/files").status_code == 200
        assert app_client.get(f"/api/parts/{part_id}/files/{file_id}/download").status_code == 200
        assert app_client.delete(f"/api/parts/{part_id}/files/{file_id}").status_code == 403
        # Every file-management write route is gated — including set-PRIMARY.
        assert app_client.post(f"/api/parts/{part_id}/files/{file_id}/primary").status_code == 403


def test_upload_to_missing_part_is_404(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.post(f"/api/parts/{uuid.uuid4()}/files", files=[_step()])
    assert resp.status_code == 404


def test_unauthenticated_request_is_rejected(app_client: TestClient) -> None:
    assert app_client.get("/api/parts").status_code == 401
