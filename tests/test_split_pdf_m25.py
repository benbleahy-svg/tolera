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

import io
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
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
        for key in ("task_always_eager", "task_store_eager_result", "task_eager_propagates")
    }
    celery_app.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
        # Task errors must surface via the status endpoint, not blow up the POST.
        task_eager_propagates=False,
        result_backend="cache+memory://",
    )
    yield
    celery_app.conf.update(saved)


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
