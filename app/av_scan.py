"""The scan-on-store Celery task (M3.13).

Every stored ``part_file`` — direct upload, Part-Library bulk upload, or an
attachment off an ingested RFQ email (M3.3) — is enqueued here post-commit and
scanned asynchronously, so the upload request never waits on clamd. The verdict
lands on ``part_file.scan_status``; :func:`app.av.scan_gate_error` is what turns
it into a download/forward block.

Task discipline (CLAUDE.md §5): **idempotent** — a terminal verdict is never
re-scanned, so a double-enqueue or an acks_late redelivery converges; **retried
with backoff** and **dead-lettered** via ``BaseTask``; **never silently clean** —
an unreachable daemon writes ``error`` and re-raises so the retry ladder runs.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from .av import ScannerUnavailableError, ScanStatus, VirusScanner, make_scanner, scanning_enabled
from .celery_app import celery_app
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker, org_scoped_session, run_after_commit
from .models import PartFile
from .storage import ObjectStorage
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger(__name__)

#: Verdicts that are final — re-scanning them would be work without an answer.
TERMINAL = frozenset({ScanStatus.clean, ScanStatus.infected})


async def run_scan(
    db_url: str,
    storage: ObjectStorage,
    *,
    org_id: uuid.UUID,
    file_id: uuid.UUID,
    scanner: VirusScanner,
) -> dict[str, Any]:
    """Scan one stored file and record the verdict — the task's core.

    Runs under the file's org via ``org_scoped_session`` (RLS holds in the worker
    exactly as in a request). Returns the resulting status; raises
    :class:`~app.av.ScannerUnavailableError` after stamping ``error`` so the
    caller's retry ladder gets its chance and the row never reads ``clean`` on a
    scan that did not actually happen.
    """
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        async with org_scoped_session(sessionmaker, org_id) as session:
            row = await session.get(PartFile, file_id)
            if row is None:
                # Deleted between enqueue and run — nothing to quarantine.
                return {"file_id": str(file_id), "status": "gone"}
            if ScanStatus(row.scan_status) in TERMINAL:
                return {"file_id": str(file_id), "status": row.scan_status, "skipped": True}
            key, part_id = row.storage_key, row.part_id
            try:
                verdict = await scanner.scan_chunks(_stream(storage, key))
            except ScannerUnavailableError as exc:
                await _record_error(session, row)
                logger.warning(
                    "av_scan_unavailable",
                    extra={
                        "org_id": str(org_id),
                        "part_id": str(part_id),
                        "file_id": str(file_id),
                        "reason": str(exc),
                    },
                )
                raise
            row.scan_status = verdict.status
            infected = verdict.status is ScanStatus.infected
            row.scan_signature = verdict.signature if infected else None
            row.scanned_at = datetime.now(UTC)
            if infected:
                # Structured quarantine log: tenant ids + the signature only —
                # never the filename or a byte of the file (CLAUDE.md §5).
                logger.warning(
                    "upload_quarantined",
                    extra={
                        "org_id": str(org_id),
                        "part_id": str(part_id),
                        "file_id": str(file_id),
                        "signature": verdict.signature,
                    },
                )
        return {"file_id": str(file_id), "status": verdict.status.value}
    finally:
        await engine.dispose()


async def _record_error(session: AsyncSession, row: PartFile) -> None:
    """Stamp ``error`` and commit it independently of the failure that follows.

    The enclosing ``org_scoped_session`` rolls back when we re-raise, so the flag
    would be lost; committing here is what makes an outage visible (and keeps the
    row out of ``clean``) while the task retries."""
    row.scan_status = ScanStatus.error
    row.scan_signature = None
    row.scanned_at = datetime.now(UTC)
    await session.commit()


async def _stream(storage: ObjectStorage, key: str) -> AsyncIterator[bytes]:
    async for chunk in storage.stream(key):
        yield chunk


def _run_on_own_loop(coro: Any) -> Any:
    """Run ``coro`` whether or not a loop is already running (the M2.5 pattern)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@celery_app.task(base=BaseTask, name="app.scan_part_file", bind=True)
def scan_part_file_task(self: Any, org_id: str, file_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_scan`.

    A scanner-less deployment (``AV_SCANNER=none``) is a no-op rather than an
    error: the row stays ``pending`` and the gate ignores ``pending`` there."""
    scanner = make_scanner(get_settings())
    if scanner is None:
        return {"file_id": file_id, "status": "skipped", "reason": "scanning_disabled"}
    result = _run_on_own_loop(
        run_scan(
            *resolve_task_resources(),
            org_id=uuid.UUID(org_id),
            file_id=uuid.UUID(file_id),
            scanner=scanner,
        )
    )
    return cast("dict[str, Any]", result)


def enqueue_scan(
    session: AsyncSession, settings: Settings, org_id: uuid.UUID, file_id: uuid.UUID
) -> None:
    """Queue ``file_id`` for scanning once the storing transaction commits.

    Post-commit only (the worker re-reads the committed row), and a no-op when no
    scanner is configured. Mirrors ``parts._enqueue_pdf_text``."""
    if not scanning_enabled(settings):
        return
    run_after_commit(session, partial(_enqueue, org_id, file_id))


def _enqueue(org_id: uuid.UUID, file_id: uuid.UUID) -> None:
    """Never raises: the commit already happened, so a broker outage must not turn
    a succeeded upload into a 500. The file stays ``pending`` — which the gate
    treats as *not downloadable* — and the partial index on un-verdicted rows is
    the backlog sweep's entry point."""
    try:
        scan_part_file_task.delay(str(org_id), str(file_id))
    except Exception:
        logger.warning(
            "av_scan_enqueue_failed",
            extra={"org_id": str(org_id), "file_id": str(file_id)},
            exc_info=True,
        )
