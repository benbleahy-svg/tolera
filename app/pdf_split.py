"""Pure PDF page splitter (M2.5 — spec `#pdf-capabilities`, Pages → split).

Bytes in, per-page bytes out — no I/O, no ORM — so the split math is testable
without a broker or database (the same pattern as ``tasks.apply_idempotent``).
Validation policy per DECISIONS.md 2026-07-13: a 1-page PDF is nothing to
split, non-PDF / corrupt / encrypted input is rejected, and a page ceiling
bounds how many ``part_file`` rows + blobs one split may mint.
"""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter

#: Ceiling on pages per split (DECISIONS.md 2026-07-13) — a 500-page catalog
#: must not mint 500 part_file rows in one action.
MAX_SPLIT_PAGES = 200


class PdfSplitError(Exception):
    """Base for split rejections; ``code`` feeds the API error envelope."""

    code = "invalid_pdf"


class InvalidPdfError(PdfSplitError):
    """Not a PDF, or too corrupt to parse."""

    code = "invalid_pdf"


class EncryptedPdfError(PdfSplitError):
    """Password-protected PDFs are not split (we never guess keys)."""

    code = "encrypted_pdf"


class SinglePageError(PdfSplitError):
    """A 1-page PDF has nothing to split."""

    code = "nothing_to_split"


class TooManyPagesError(PdfSplitError):
    """Page count exceeds the per-split ceiling."""

    code = "too_many_pages"


def _read_for_split(data: bytes, max_pages: int) -> PdfReader:
    """Parse ``data`` and enforce the split policy; the shared validation core."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise EncryptedPdfError("PDF is password-protected")
        page_count = len(reader.pages)
    except PdfSplitError:
        raise
    except Exception as exc:  # pypdf raises many shapes on malformed input
        raise InvalidPdfError("file is not a readable PDF") from exc
    if page_count <= 1:
        raise SinglePageError("PDF has a single page — nothing to split")
    if page_count > max_pages:
        raise TooManyPagesError(f"PDF has {page_count} pages (ceiling {max_pages})")
    return reader


def validate_pdf_split(data: bytes, max_pages: int = MAX_SPLIT_PAGES) -> int:
    """Validate ``data`` as splittable and return its page count.

    The request-time check behind the 202: rejections must be a 422 on the POST,
    not a failed task (DECISIONS.md 2026-07-13)."""
    return len(_read_for_split(data, max_pages).pages)


def split_pdf_pages(data: bytes, max_pages: int = MAX_SPLIT_PAGES) -> list[bytes]:
    """Split ``data`` into one single-page PDF per page, in page order.

    Raises a :class:`PdfSplitError` subclass instead of persisting anything —
    callers map ``.code`` onto the 422 envelope.
    """
    reader = _read_for_split(data, max_pages)
    pages: list[bytes] = []
    for page in reader.pages:
        writer = PdfWriter()
        writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        pages.append(buf.getvalue())
    return pages
