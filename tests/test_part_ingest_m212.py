"""M2.12 — ingest wiring: every stored file gets its match-index fields.

Covers the upload path (hash + normalized name + STEP part number inline,
``pdf_text`` via the eager Celery task), the derived-file paths (split pages,
redacted copies), the SQL↔Python equivalence of the 0018 backfill expression,
and the library-level multi-file upload with auto-bundling (same stem → one
part, CAD primary — KB `uploading-parts-to-your-part-library`).
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import MembershipRole
from app.part_index import normalize_filename
from tests.conftest import Seeder, authed

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
STEP_BYTES = (FIXTURES / "cad" / "cube-20mm.step").read_bytes()
PDF_BYTES = (FIXTURES / "drawings" / "halter-4711-rev-b.pdf").read_bytes()

ADMIN = [MembershipRole.admin]


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[Any, Any]:
    org = seeder.org(slug)
    user = seeder.user(f"{slug}-admin")
    seeder.membership(user, org, roles=ADMIN)
    return org, user


def _db_row(db_url: str, table: str, row_id: Any) -> dict[str, Any]:
    async def _fetch() -> dict[str, Any]:
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(f"SELECT * FROM {table} WHERE id = :id"), {"id": row_id}
                )
                row = result.mappings().one()
                return dict(row)
        finally:
            await engine.dispose()

    return asyncio.run(_fetch())


def _upload(
    client: TestClient, part_id: str, files: list[tuple[str, bytes, str]]
) -> list[dict[str, Any]]:
    resp = client.post(
        f"/api/parts/{part_id}/files",
        files=[("files", (name, body, ctype)) for name, body, ctype in files],
    )
    assert resp.status_code == 201, resp.text
    return list(resp.json())


class TestUploadIndexFields:
    def test_step_upload_gets_hash_name_and_part_number(
        self, app_client: TestClient, seeder: Seeder, tenancy_db: str
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-ing1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = app_client.post("/api/parts").json()["id"]
            [out] = _upload(app_client, part, [("Cube-20mm.step", STEP_BYTES, "application/step")])
        row = _db_row(tenancy_db, "part_file", out["id"])
        assert row["file_hash"] == hashlib.sha256(STEP_BYTES).hexdigest()
        assert row["filename_normalized"] == "cube_20mm"
        # Deterministic STEP PRODUCT read (the Lens/PDF path is M3).
        assert row["part_number_extracted"] == "cube-20mm"
        assert row["pdf_text"] is None

    def test_pdf_upload_extracts_text_via_task(
        self,
        app_client: TestClient,
        seeder: Seeder,
        tenancy_db: str,
        eager_celery: None,
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-ing2")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = app_client.post("/api/parts").json()["id"]
            [out] = _upload(
                app_client, part, [("Halter-4711-Rev-B.pdf", PDF_BYTES, "application/pdf")]
            )
        row = _db_row(tenancy_db, "part_file", out["id"])
        assert row["file_hash"] == hashlib.sha256(PDF_BYTES).hexdigest()
        assert row["filename_normalized"] == "halter_4711_rev_b"
        assert row["part_number_extracted"] is None
        assert row["pdf_text"] is not None
        assert "Halter 4711" in row["pdf_text"]

    def test_backfill_sql_equivalent_to_python(self, tenancy_db: str) -> None:
        """The 0018 backfill expression and normalize_filename must agree."""
        samples = [
            "Bracket.stp",
            "5-X-9__B.pdf",
            "3601215 _ OFFSET CONNECTOR.STEP",
            "halter.4711.step",
            "README",
            "---.pdf",
        ]

        async def _sql(name: str) -> str | None:
            engine = create_async_engine(tenancy_db)
            try:
                async with engine.connect() as conn:
                    result = await conn.execute(
                        text(
                            r"""
                            SELECT NULLIF(
                                trim(BOTH '_' FROM lower(
                                    regexp_replace(
                                        CASE WHEN :f ~ '.\.[^.]*$'
                                             THEN regexp_replace(:f, '\.[^.]*$', '')
                                             ELSE :f END,
                                        '[^a-zA-Z0-9]+', '_', 'g')
                                )), '')
                            """
                        ),
                        {"f": name},
                    )
                    return result.scalar()
            finally:
                await engine.dispose()

        for name in samples:
            assert asyncio.run(_sql(name)) == normalize_filename(name), name


class TestDerivedFilesGetIndexFields:
    def test_split_pages_carry_index_fields(
        self,
        app_client: TestClient,
        seeder: Seeder,
        tenancy_db: str,
        eager_celery: None,
    ) -> None:
        three_page = (FIXTURES / "drawings" / "halter-4711-blaetter.pdf").read_bytes()
        org, admin = _org_with_admin(seeder, "org-ing3")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part = app_client.post("/api/parts").json()["id"]
            [src] = _upload(app_client, part, [("blaetter.pdf", three_page, "application/pdf")])
            resp = app_client.post(f"/api/parts/{part}/files/{src['id']}/split")
            assert resp.status_code == 202, resp.text
            pages = [
                f
                for f in app_client.get(f"/api/parts/{part}/files").json()
                if f["source_file_id"] == src["id"]
            ]
        assert len(pages) == 3
        for n, page in enumerate(sorted(pages, key=lambda f: f["filename"]), start=1):
            row = _db_row(tenancy_db, "part_file", page["id"])
            assert row["file_hash"] is not None
            assert row["filename_normalized"] == f"blaetter_p{n}"
            assert row["pdf_text"] is not None and f"BLATT {n}" in row["pdf_text"]


class TestLibraryUploadAutoBundling:
    def test_same_stem_bundles_into_one_part_cad_primary(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-ing4")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                "/api/parts/upload",
                files=[
                    ("files", ("Bracket.pdf", PDF_BYTES, "application/pdf")),
                    ("files", ("Bracket.step", STEP_BYTES, "application/step")),
                ],
            )
            assert resp.status_code == 201, resp.text
            parts = resp.json()
            assert len(parts) == 1
            files = app_client.get(f"/api/parts/{parts[0]['id']}/files").json()
        by_name = {f["filename"]: f for f in files}
        assert by_name["Bracket.step"]["role"] == "primary"  # CAD wins PRIMARY
        assert by_name["Bracket.pdf"]["role"] == "supporting"

    def test_different_stems_create_separate_parts(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-ing5")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                "/api/parts/upload",
                files=[
                    ("files", ("5-X-9.step", STEP_BYTES, "application/step")),
                    ("files", ("5-X-9__B.pdf", PDF_BYTES, "application/pdf")),
                    ("files", ("Deckel.step", STEP_BYTES, "application/step")),
                ],
            )
            assert resp.status_code == 201, resp.text
            parts = resp.json()
        # 5-X-9 and 5-X-9__B normalize differently (KB: names must MATCH to
        # bundle — the mismatched print is merged manually later).
        assert len(parts) == 3

    def test_bundled_part_takes_stem_as_name(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with_admin(seeder, "org-ing6")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            resp = app_client.post(
                "/api/parts/upload",
                files=[("files", ("Offset Connector.step", STEP_BYTES, "application/step"))],
            )
            assert resp.status_code == 201, resp.text
            [part] = resp.json()
            assert part["name"] == "Offset Connector"
            # The extracted STEP PRODUCT id stays file-level (part_number_extracted);
            # the canonical library part# is manual (spec#partlib: two number types).
            assert part["part_number"] is None
