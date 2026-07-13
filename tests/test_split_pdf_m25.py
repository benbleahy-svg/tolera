"""M2.5 — Split PDF into single-page files.

Exercises the block's acceptance criteria (a 3-page fixture PDF splits into 3
single-page supporting files; the original stays byte-identical and listed) and
the grill-decided edge policy (DECISIONS.md 2026-07-13): 1-page / non-PDF /
corrupt / encrypted / over-the-ceiling PDFs are rejected with a 422 envelope and
nothing is persisted; page files are named ``<stem>-p<N>.pdf``, carry
``source_file_id`` provenance, and re-running a split is allowed.

Seams under test (agreed in the grill):
* the pure splitter ``app.pdf_split.split_pdf_pages`` (bytes → page bytes),
* the HTTP contract ``POST …/files/{id}/split`` (202 + task id) and
  ``GET …/files/{id}/split/{task_id}`` (status/progress/file_ids),
* the public file list/download API, used to observe the split's results.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from app.celery_app import celery_app
from app.models import MembershipRole
from app.pdf_split import (
    EncryptedPdfError,
    InvalidPdfError,
    SinglePageError,
    TooManyPagesError,
    split_pdf_pages,
)
from tests.conftest import Seeder, authed

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "drawings"
THREE_PAGE_PDF = (FIXTURES / "halter-4711-blaetter.pdf").read_bytes()
ONE_PAGE_PDF = (FIXTURES / "cube-20mm-print.pdf").read_bytes()


def _encrypted_pdf() -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(THREE_PAGE_PDF))
    writer.encrypt("geheim")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Pure splitter
# --------------------------------------------------------------------------- #
class TestSplitPdfPages:
    def test_three_page_fixture_yields_three_single_page_pdfs(self) -> None:
        parts = split_pdf_pages(THREE_PAGE_PDF)
        assert len(parts) == 3
        for n, page_bytes in enumerate(parts, start=1):
            reader = PdfReader(io.BytesIO(page_bytes))
            assert len(reader.pages) == 1
            # Page identity: the fixture stamps each sheet with its number.
            assert f"BLATT {n}" in reader.pages[0].extract_text()

    def test_single_page_pdf_is_nothing_to_split(self) -> None:
        with pytest.raises(SinglePageError):
            split_pdf_pages(ONE_PAGE_PDF)

    def test_garbage_bytes_are_invalid(self) -> None:
        with pytest.raises(InvalidPdfError):
            split_pdf_pages(b"ISO-10303-21; this is a STEP file, not a PDF")

    def test_truncated_pdf_is_invalid(self) -> None:
        with pytest.raises(InvalidPdfError):
            split_pdf_pages(THREE_PAGE_PDF[:120])

    def test_encrypted_pdf_is_rejected(self) -> None:
        writer = PdfWriter(clone_from=io.BytesIO(THREE_PAGE_PDF))
        writer.encrypt("geheim")
        buf = io.BytesIO()
        writer.write(buf)
        with pytest.raises(EncryptedPdfError):
            split_pdf_pages(buf.getvalue())

    def test_page_ceiling_is_enforced(self) -> None:
        with pytest.raises(TooManyPagesError):
            split_pdf_pages(THREE_PAGE_PDF, max_pages=2)


# --------------------------------------------------------------------------- #
# HTTP contract (Celery runs eagerly in-process; results land in a memory
# backend so the status endpoint reads real task state)
# --------------------------------------------------------------------------- #
ADMIN = [MembershipRole.admin]


@pytest.fixture
def eager_celery() -> Iterator[None]:
    """Run split tasks inline and store results in an in-process backend."""
    saved = {
        key: celery_app.conf[key]
        for key in (
            "task_always_eager",
            "task_store_eager_result",
            "task_eager_propagates",
            "result_backend",
        )
    }
    celery_app.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
        # Task errors must surface via the status endpoint, not blow up the POST.
        task_eager_propagates=False,
        result_backend="cache+memory://",
    )
    # The backend is a cached property — drop any cached instance so the config
    # change takes effect now and can't leak into later tests after restore.
    celery_app.__dict__.pop("backend", None)
    yield
    celery_app.conf.update(saved)
    celery_app.__dict__.pop("backend", None)


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _create_part(client: TestClient) -> str:
    created = client.post("/api/parts")
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _upload_pdf(client: TestClient, part_id: str, name: str, data: bytes) -> str:
    resp = client.post(
        f"/api/parts/{part_id}/files", files=[("files", (name, data, "application/pdf"))]
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()[0]["id"])


class TestSplitEndpoint:
    def test_split_creates_one_supporting_file_per_page(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        """The headline acceptance: 3-page fixture → 3 single-page supporting
        files with provenance; the original stays byte-identical and primary."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)

            resp = app_client.post(f"/api/parts/{part_id}/files/{file_id}/split")
            assert resp.status_code == 202, resp.text
            task_id = resp.json()["task_id"]

            status = app_client.get(f"/api/parts/{part_id}/files/{file_id}/split/{task_id}")
            assert status.status_code == 200, status.text
            body = status.json()
            assert body["state"] == "succeeded"
            assert body["progress"] == {"done": 3, "total": 3}
            assert len(body["file_ids"]) == 3

            listed = app_client.get(f"/api/parts/{part_id}/files").json()
            assert len(listed) == 4
            pages = [f for f in listed if f["id"] in body["file_ids"]]
            # Page files: named <stem>-p<N>.pdf, supporting, provenance-linked.
            assert sorted(f["filename"] for f in pages) == [
                f"halter-4711-blaetter-p{n}.pdf" for n in (1, 2, 3)
            ]
            assert all(f["role"] == "supporting" for f in pages)
            assert all(f["source_file_id"] == file_id for f in pages)

            # The original is untouched: still listed, still primary, byte-identical.
            original = next(f for f in listed if f["id"] == file_id)
            assert original["role"] == "primary"
            assert original["source_file_id"] is None
            download = app_client.get(f"/api/parts/{part_id}/files/{file_id}/download")
            assert download.content == THREE_PAGE_PDF

            # Each page file is a 1-page PDF holding exactly its sheet.
            by_name = {f["filename"]: f["id"] for f in pages}
            for n in (1, 2, 3):
                page_id = by_name[f"halter-4711-blaetter-p{n}.pdf"]
                dl = app_client.get(f"/api/parts/{part_id}/files/{page_id}/download")
                reader = PdfReader(io.BytesIO(dl.content))
                assert len(reader.pages) == 1
                assert f"BLATT {n}" in reader.pages[0].extract_text()

    def test_rerun_creates_a_second_set(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        """Re-splitting is allowed and simply adds another set (DECISIONS.md
        2026-07-13) — the user acted twice, they can delete extras."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)
            for _ in range(2):
                resp = app_client.post(f"/api/parts/{part_id}/files/{file_id}/split")
                assert resp.status_code == 202, resp.text
            listed = app_client.get(f"/api/parts/{part_id}/files").json()
            assert len(listed) == 7  # original + 2 x 3 pages
            assert sum(f["source_file_id"] == file_id for f in listed) == 6

    @pytest.mark.parametrize(
        ("name", "data", "expected_code"),
        [
            ("cube-20mm-print.pdf", ONE_PAGE_PDF, "nothing_to_split"),
            ("truncated.pdf", THREE_PAGE_PDF[:120], "invalid_pdf"),
            ("geheim.pdf", _encrypted_pdf(), "encrypted_pdf"),
        ],
    )
    def test_unsplittable_pdf_is_a_422_and_persists_nothing(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        name: str,
        data: bytes,
        expected_code: str,
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, name, data)
            resp = app_client.post(f"/api/parts/{part_id}/files/{file_id}/split")
            assert resp.status_code == 422, resp.text
            assert resp.json()["code"] == expected_code
            # Nothing was persisted — the original is still the only file.
            assert len(app_client.get(f"/api/parts/{part_id}/files").json()) == 1

    def test_non_pdf_file_is_a_422(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        step = b"ISO-10303-21;\nHEADER;\nFILE_NAME('bracket.step');\nENDSEC;\nEND-ISO-10303-21;\n"
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            resp = app_client.post(
                f"/api/parts/{part_id}/files",
                files=[("files", ("bracket.step", step, "application/step"))],
            )
            file_id = resp.json()[0]["id"]
            split = app_client.post(f"/api/parts/{part_id}/files/{file_id}/split")
            assert split.status_code == 422
            assert split.json()["code"] == "invalid_pdf"

    def test_viewer_role_cannot_split(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-a")
        viewer = seeder.user("viewer@org-a.example")
        seeder.membership(viewer, org, [MembershipRole.viewer])
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)
        with authed(app_client, user_id=viewer, org_id=org, roles=[MembershipRole.viewer]):
            resp = app_client.post(f"/api/parts/{part_id}/files/{file_id}/split")
            assert resp.status_code == 403

    def test_cross_org_split_and_status_are_404(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        """Tenancy: neither the split action, the status of another org's task,
        nor its very existence is visible across orgs."""
        org_a, admin_a = _org_with_admin(seeder, "org-a")
        org_b, admin_b = _org_with_admin(seeder, "org-b")
        with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
            part_a = _create_part(app_client)
            file_a = _upload_pdf(app_client, part_a, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)
            task_a = app_client.post(f"/api/parts/{part_a}/files/{file_a}/split").json()["task_id"]
        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            # Org B can't split A's file (RLS: the file doesn't exist for B) …
            assert app_client.post(f"/api/parts/{part_a}/files/{file_a}/split").status_code == 404
            # … nor read A's task status via A's paths …
            status = app_client.get(f"/api/parts/{part_a}/files/{file_a}/split/{task_a}")
            assert status.status_code == 404
            # … nor bind A's task id to a file of their own (meta names A's file).
            part_b = _create_part(app_client)
            file_b = _upload_pdf(app_client, part_b, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)
            hijack = app_client.get(f"/api/parts/{part_b}/files/{file_b}/split/{task_a}")
            assert hijack.status_code == 404

    def test_mid_split_failure_persists_nothing(
        self, app_client: TestClient, seeder: Seeder, tenancy_db: str
    ) -> None:
        """All-or-nothing (DECISIONS.md 2026-07-13): if page 3 of 3 fails, no
        rows are committed and the blobs written for pages 1-2 are discarded."""
        from app.file_split import run_split
        from app.storage import MemoryStorage
        from tests.conftest import app_role_url

        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)

        storage = cast(MemoryStorage, cast(FastAPI, app_client.app).state.storage)
        blobs_before = dict(storage._objects)

        class ThirdPutFails:
            """Delegates to the real storage; the 3rd put blows up mid-split."""

            def __init__(self) -> None:
                self.puts = 0

            async def put(self, key: str, fileobj: Any, *, content_type: str | None = None) -> int:
                self.puts += 1
                if self.puts == 3:
                    raise OSError("object store went away")
                return await storage.put(key, fileobj, content_type=content_type)

            def stream(self, key: str) -> Any:
                return storage.stream(key)

            async def delete(self, key: str) -> None:
                await storage.delete(key)

        with pytest.raises(OSError):
            asyncio.run(
                run_split(
                    app_role_url(tenancy_db),
                    ThirdPutFails(),
                    org_id=org,
                    part_id=uuid.UUID(part_id),
                    file_id=uuid.UUID(file_id),
                )
            )

        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            listed = app_client.get(f"/api/parts/{part_id}/files").json()
        assert len(listed) == 1  # no rows committed
        assert storage._objects == blobs_before  # pages 1-2 blobs discarded

    def test_redelivered_task_returns_stored_result_without_rerunning(
        self, eager_celery: None
    ) -> None:
        """Idempotency net (CLAUDE.md §5): with acks_late, a worker crash after
        commit-before-ack redelivers the task under the SAME id — the guard
        returns the stored result instead of splitting again."""
        from app.file_split import split_pdf_task

        stored = {
            "file_ids": ["a", "b", "c"],
            "done": 3,
            "total": 3,
            "org_id": str(uuid.uuid4()),
            "file_id": str(uuid.uuid4()),
        }
        task_id = str(uuid.uuid4())
        celery_app.backend.store_result(task_id, stored, "SUCCESS")
        # Would blow up in run_split (no such org/part/file) if it re-ran.
        result = split_pdf_task.apply(
            task_id=task_id,
            args=(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())),
        )
        assert result.result == stored

    def test_deleted_source_surfaces_as_bound_failure(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        """A deterministic task-side rejection (file gone by run time) returns a
        *bound* failure dict — the status GET reports failed with its code."""
        from app.file_split import split_pdf_task

        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)
            # Run the task against a file id that doesn't exist (deleted between
            # enqueue and run); resources are the test app's (registered).
            ghost = str(uuid.uuid4())
            result = split_pdf_task.apply(args=(str(org), part_id, ghost))
            assert result.result["failed"] is True
            assert result.result["error_code"] == "source_file_gone"

            # Mapped through the status endpoint (bound to the ghost's id via
            # meta, so poll with the real file path + this task id → 404, and
            # with a synthetic bound-to-this-file failure → failed + code).
            tid = str(uuid.uuid4())
            celery_app.backend.store_result(
                tid,
                {
                    "failed": True,
                    "error_code": "source_file_gone",
                    "org_id": str(org),
                    "file_id": file_id,
                },
                "SUCCESS",
            )
            resp = app_client.get(f"/api/parts/{part_id}/files/{file_id}/split/{tid}")
            assert resp.status_code == 200
            assert resp.json()["state"] == "failed"
            assert resp.json()["error"]["code"] == "source_file_gone"

            # A failure dict bound to ANOTHER file must not be readable here.
            other = str(uuid.uuid4())
            celery_app.backend.store_result(
                tid + "x",
                {
                    "failed": True,
                    "error_code": "source_file_gone",
                    "org_id": str(org),
                    "file_id": other,
                },
                "SUCCESS",
            )
            hijack = app_client.get(f"/api/parts/{part_id}/files/{file_id}/split/{tid}x")
            assert hijack.status_code == 404

    def test_infra_failure_state_is_generic(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        """Celery FAILURE (transient/infra death) carries no binding, so the
        status GET exposes nothing beyond a generic failure — no exception
        text, no specific code."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)
            tid = str(uuid.uuid4())
            celery_app.backend.store_result(tid, ValueError("boom secret"), "FAILURE")
            resp = app_client.get(f"/api/parts/{part_id}/files/{file_id}/split/{tid}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["state"] == "failed"
            assert body["error"] == {"code": "split_failed", "message": "Split failed."}
            assert "boom" not in resp.text

    def test_unknown_task_id_reads_as_queued(
        self, app_client: TestClient, seeder: Seeder, eager_celery: None
    ) -> None:
        """Celery can't distinguish 'not yet started' from 'never existed' —
        an unknown id reads as queued (documented contract)."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-blaetter.pdf", THREE_PAGE_PDF)
            resp = app_client.get(f"/api/parts/{part_id}/files/{file_id}/split/{uuid.uuid4()}")
            assert resp.status_code == 200
            assert resp.json() == {
                "state": "queued",
                "progress": None,
                "file_ids": None,
                "error": None,
            }
