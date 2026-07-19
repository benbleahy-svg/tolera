"""Antivirus scanning of customer uploads (M3.13).

Customers — and, since M3.3 opened the untrusted path, anyone who can email the
org's ingest address — upload arbitrary files that staff download and forward to
vendors. `DECISIONS.md` (2026-06-25, RESOLVED 2026-07-17) settles the shape:
**ClamAV in our own infrastructure, scanned asynchronously after store**, with a
quarantine flag on ``part_file`` and download/forward blocked until ``clean``. A
cloud scanning API was rejected on GDPR grounds — shipping a customer's print to
a third-party scanner adds a subprocessor.

This module is the seam only: the wire protocol client, the verdict type, and
the read gate. The Celery task that drives it lives in :mod:`app.av_scan`.

Configuration mirrors the storage seam (:mod:`app.storage`): ``AV_SCANNER=none``
is the default so tests and a bare local boot need no sidecar, docker-compose
and every real deployment set ``clamav`` (enforced outside development/test by
``Settings.validate_av``).
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import IO, Protocol, runtime_checkable

from fastapi import status

from .config import Settings
from .errors import AppError

#: Bytes per INSTREAM frame. clamd caps a single frame at its ``StreamMaxLength``;
#: 64 KiB is the conventional frame size and keeps worker memory flat.
CHUNK_BYTES = 64 * 1024


class ScanStatus(StrEnum):
    """The lifecycle of one file's malware verdict (``part_file.scan_status``).

    ``pending`` → ``clean`` | ``infected`` | ``error``. ``clean`` and ``infected``
    are **terminal**; ``error`` is retryable (a clamd outage, never a verdict).
    """

    pending = "pending"
    clean = "clean"
    infected = "infected"
    error = "error"


@dataclass(frozen=True, slots=True)
class Verdict:
    """A completed scan. ``signature`` is clamd's malware name when infected."""

    status: ScanStatus
    signature: str | None = None


class ScannerUnavailableError(RuntimeError):
    """The scan could not be completed (connection refused, timeout, clamd ERROR).

    Deliberately distinct from a verdict: an unreachable scanner must never be
    mistaken for ``clean``. The task maps this to ``error`` + a retry.
    """


@runtime_checkable
class VirusScanner(Protocol):
    """The contract the scan task depends on (fake it in tests, no daemon needed)."""

    async def scan_chunks(self, chunks: AsyncIterator[bytes]) -> Verdict:
        """Scan a streamed payload. Raises :class:`ScannerUnavailableError`."""
        ...


class ClamdScanner:
    """Speaks clamd's ``INSTREAM`` protocol over TCP.

    INSTREAM is used rather than ``SCAN <path>`` because the daemon runs in its
    own container and shares no filesystem with the worker — the bytes come from
    object storage, so they are streamed over the socket in length-prefixed
    frames and never staged on local disk.

    Wire format: ``zINSTREAM\\0``, then ``<uint32 big-endian length><data>`` per
    frame, terminated by a zero-length frame; the reply is one NUL-terminated
    line — ``stream: OK``, ``stream: <Signature> FOUND``, or ``... ERROR``.
    """

    def __init__(self, *, host: str, port: int = 3310, timeout_seconds: float = 120.0) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    async def scan_chunks(self, chunks: AsyncIterator[bytes]) -> Verdict:
        try:
            return await asyncio.wait_for(self._scan(chunks), timeout=self.timeout_seconds)
        except ScannerUnavailableError:
            raise
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as exc:
            # Connection refused / reset / half-closed / timed out — infrastructure,
            # not a verdict.
            raise ScannerUnavailableError(f"clamd unreachable: {exc.__class__.__name__}") from exc

    async def scan(self, fileobj: IO[bytes]) -> Verdict:
        """Convenience wrapper for an already-materialised (small) payload."""

        async def _chunks() -> AsyncIterator[bytes]:
            while data := fileobj.read(CHUNK_BYTES):
                yield data

        return await self.scan_chunks(_chunks())

    async def _scan(self, chunks: AsyncIterator[bytes]) -> Verdict:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(b"zINSTREAM\0")
            async for chunk in chunks:
                if not chunk:
                    continue  # a zero-length frame would terminate the stream early
                writer.write(len(chunk).to_bytes(4, "big") + chunk)
                await writer.drain()
            writer.write(b"\0\0\0\0")
            await writer.drain()
            raw = await reader.readuntil(b"\0")
        finally:
            writer.close()
            with _suppress_close_errors():
                await writer.wait_closed()
        return _parse_reply(raw)


class _suppress_close_errors:
    """``wait_closed`` may raise on an already-reset socket; that is not a scan failure."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: type[BaseException] | None, *_: object) -> bool:
        return exc_type is not None and issubclass(exc_type, (OSError, asyncio.IncompleteReadError))


def _parse_reply(raw: bytes) -> Verdict:
    """Map one clamd reply line to a :class:`Verdict`."""
    line = raw.rstrip(b"\0").decode("utf-8", "replace").strip()
    if line.endswith("ERROR"):
        raise ScannerUnavailableError(f"clamd error: {line}")
    if line.endswith("FOUND"):
        # ``stream: Eicar-Test-Signature FOUND`` → ``Eicar-Test-Signature``
        body = line.rsplit(" FOUND", 1)[0]
        signature = body.split(":", 1)[1].strip() if ":" in body else body.strip()
        return Verdict(ScanStatus.infected, signature or None)
    if line.endswith("OK"):
        return Verdict(ScanStatus.clean)
    raise ScannerUnavailableError(f"unparseable clamd reply: {line[:120]!r}")


def make_scanner(settings: Settings) -> VirusScanner | None:
    """Build the configured scanner; ``None`` when scanning is switched off.

    Fails closed on a half-configured daemon: ``AV_SCANNER=clamav`` without a
    host is a misconfiguration, not a licence to skip scanning.
    """
    choice = settings.av_scanner.strip().lower()
    if choice == "none":
        return None
    if choice != "clamav":
        raise ValueError(f"Unknown AV_SCANNER {settings.av_scanner!r} (expected 'none'|'clamav').")
    if not settings.clamav_host:
        raise ValueError("AV_SCANNER=clamav requires CLAMAV_HOST.")
    return ClamdScanner(
        host=settings.clamav_host,
        port=settings.clamav_port,
        timeout_seconds=settings.clamav_timeout_seconds,
    )


class _HasScanStatus(Protocol):
    scan_status: ScanStatus


def scan_gate_error(part_file: _HasScanStatus, settings: Settings) -> AppError | None:
    """The read gate: ``None`` when the bytes may leave the system, else the error.

    Applied to every path that hands a file's *contents* to anyone — the staff
    download, the vendor portal download, and the vendor-RFQ send that grants a
    vendor access. Listing files and reading their metadata stays open (the
    charter's "pending = allow internal view-metadata").

    Two rules, deliberately asymmetric:
      * ``infected`` is blocked **always** — a positively-identified piece of
        malware must not be released by switching the scanner off;
      * ``pending``/``error`` are blocked **only while scanning is enabled** —
        with no scanner configured nothing will ever move a row off ``pending``,
        so gating on it would block every download in that deployment.
    """
    current = ScanStatus(part_file.scan_status)
    if current is ScanStatus.infected:
        return AppError(
            "file_quarantined",
            "Diese Datei wurde als Schadsoftware eingestuft und ist gesperrt.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if current is ScanStatus.clean or not scanning_enabled(settings):
        return None
    return AppError(
        "file_scan_pending",
        "Die Datei wird noch auf Schadsoftware geprüft. Bitte gleich erneut versuchen.",
        status_code=status.HTTP_409_CONFLICT,
    )


def scanning_enabled(settings: Settings) -> bool:
    """Is a scanner configured for this deployment?"""
    return settings.av_scanner.strip().lower() != "none"


def eicar_bytes() -> bytes:
    """The 68-byte EICAR anti-malware test file (not malware; every AV flags it).

    Assembled at runtime from fragments so the literal signature never sits in
    the checked-out tree, where the developer's own antivirus would quarantine
    this source file.
    """
    return b"".join(
        [
            b"X5O!P%@AP[4\\PZX54(P^)7CC)7}",
            b"$EICAR-STANDARD-",
            b"ANTIVIRUS-TEST-FILE!",
            b"$H+H*",
        ]
    )


def eicar_upload() -> io.BytesIO:
    """The EICAR payload as a file object, for upload fixtures."""
    return io.BytesIO(eicar_bytes())
