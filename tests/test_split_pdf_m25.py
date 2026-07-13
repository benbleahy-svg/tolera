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
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from app.pdf_split import (
    EncryptedPdfError,
    InvalidPdfError,
    SinglePageError,
    TooManyPagesError,
    split_pdf_pages,
)

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
