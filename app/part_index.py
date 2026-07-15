"""Part-Library match-index fields (M2.12 — spec `#partlib` "How matching works").

Every uploaded file gets deterministic index fields at ingest:

* ``file_hash`` — SHA-256 of the raw bytes (Exact File Match key), computed
  before any processing;
* ``filename_normalized`` — extension-stripped, lowercased, tokenized filename
  (File Name Match key; also the auto-bundling key);
* ``part_number_extracted`` — the STEP ``PRODUCT`` id (Part Number Match key).
  Deterministic CAD-metadata read only: the PDF title-block path is Lens (M3),
  and a value not present in the file is never invented (CLAUDE.md §5);
* ``pdf_text`` — full text of a PDF (the global Parts-Library search index;
  spec#partlib: "hard requirement for repeat-part discovery"). Extraction is
  long work → a Celery task (CLAUDE.md §5), idempotent and retry-safe: it
  recomputes from the stored blob and overwrites, so re-runs converge.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

from pypdf import PdfReader

from .celery_app import celery_app
from .db import make_engine, make_sessionmaker, org_scoped_session
from .models import PartFile
from .storage import ObjectStorage
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger("app.part_index")

# Cap the stored text: a print's title block + notes are what matching needs;
# a pathological text-dump PDF must not bloat the row (same bounded-internals
# posture as the M2.2 annotation caps, DECISIONS.md 2026-07-12).
PDF_TEXT_MAX_CHARS = 500_000

# How much of a STEP file the PRODUCT scan reads. The HEADER + first PRODUCT
# entities sit at the top; scanning megabytes of tessellated geometry for a
# part number is waste. Ingest captures this many head bytes while hashing.
STEP_SCAN_BYTES = 512 * 1024

# ``#164=PRODUCT('id','name',...)`` — anchored on the entity assignment so
# PRODUCT_CONTEXT / PRODUCT_DEFINITION / *_RELATIONSHIP never match.
_STEP_PRODUCT_RE = re.compile(rb"=\s*PRODUCT\s*\(\s*'([^']*)'")

_PART_NUMBER_MAX_CHARS = 255


def normalize_filename(filename: str) -> str | None:
    """The File Name Match / auto-bundling key: stem, lowercased, tokenized.

    spec#partlib: "strip extension, lowercase, tokenize" — runs of non-alphanumeric
    characters collapse to ``_`` so ``5-X-9__B.pdf`` and ``5-x-9 B.step`` agree.
    Returns ``None`` when nothing survives (an empty key must never join).

    Must stay equivalent to the SQL backfill in migration 0018.
    """
    stem, _, _ext = filename.rpartition(".")
    if not stem:  # no dot, or dot-first ("README", ".hidden")
        stem = filename
    normalized = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return normalized or None


def file_sha256(data: bytes) -> str:
    """SHA-256 hex digest of the raw uploaded bytes (Exact File Match key)."""
    return hashlib.sha256(data).hexdigest()


def extract_step_part_number(data: bytes) -> str | None:
    """The first STEP ``PRODUCT`` entity id — deterministic CAD metadata.

    Returns ``None`` for non-STEP bytes, an absent PRODUCT record, or an empty
    id. Never guesses: this is a read, not an inference (CLAUDE.md §5).
    """
    if not data.startswith(b"ISO-10303"):
        return None
    match = _STEP_PRODUCT_RE.search(data[:STEP_SCAN_BYTES])
    if match is None:
        return None
    value = match.group(1).decode("utf-8", errors="replace").strip()
    return value[:_PART_NUMBER_MAX_CHARS] or None


def extract_pdf_text(data: bytes) -> str | None:
    """All extractable text of a PDF, page order, newline-joined, capped.

    Returns ``None`` for non-PDF/corrupt/encrypted bytes and for PDFs with no
    text layer (scanned rasters) — a NULL ``pdf_text`` simply never matches.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return None
        chunks: list[str] = []
        total = 0
        for page in reader.pages:
            text = page.extract_text()
            if not text:
                continue
            chunks.append(text)
            total += len(text) + 1
            if total >= PDF_TEXT_MAX_CHARS:
                break
        joined = "\n".join(chunks)[:PDF_TEXT_MAX_CHARS].strip()
    except Exception:  # pypdf raises a zoo of parse errors — all mean "no text"
        return None
    return joined or None


async def _read_blob(storage: ObjectStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.stream(key)])


async def run_pdf_text_extraction(
    db_url: str,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    file_id: uuid.UUID,
) -> dict[str, Any]:
    """Extract and persist ``pdf_text`` for one stored file — the task's core.

    Idempotent: recomputes from the blob and overwrites. A vanished row/blob is
    a clean no-op (the file was deleted between enqueue and run — not an error).
    Runs under the caller's org via ``org_scoped_session`` (RLS holds in the
    worker exactly as in a request).
    """
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        async with org_scoped_session(sessionmaker, org_id) as session:
            pf = await session.get(PartFile, file_id)
            if pf is None:
                return {"skipped": "file_gone", "file_id": str(file_id)}
            try:
                data = await _read_blob(storage, pf.storage_key)
            except Exception:
                return {"skipped": "blob_gone", "file_id": str(file_id)}
            text = extract_pdf_text(data)
            pf.pdf_text = text
            return {"file_id": str(file_id), "chars": len(text or "")}
    finally:
        await engine.dispose()


def _run_on_own_loop(coro: Any) -> Any:
    """Run ``coro`` whether or not a loop is running (worker vs eager-in-request);
    same seam as ``app.file_split._run_on_own_loop``."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@celery_app.task(base=BaseTask, name="app.extract_pdf_text", bind=True)
def extract_pdf_text_task(self: Any, org_id: str, file_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_pdf_text_extraction`."""
    result = _run_on_own_loop(
        run_pdf_text_extraction(
            *resolve_task_resources(),
            org_id=uuid.UUID(org_id),
            file_id=uuid.UUID(file_id),
        )
    )
    out = cast("dict[str, Any]", result)
    # Structured completion log — ids only, never filenames/text (CLAUDE.md §5).
    logger.info(
        "pdf_text_indexed",
        extra={"org_id": org_id, "file_id": file_id, **out},
    )
    return out
