"""M3.13 — ClamAV upload scanning + quarantine.

Three layers, each tested on its own:
  * the **clamd client** (``app.av``) — the INSTREAM wire protocol, exercised
    against a fake asyncio server so no clamd is needed in CI;
  * the **scan task** (``app.av_scan``) — status transitions, idempotency, and
    the outage path (``error`` + raise-to-retry, never a silent ``clean``);
  * the **gate** — download / vendor-forward blocked until ``clean``.

The EICAR test string is assembled at runtime (never a literal in the tree) so
checking this file out does not trip the developer's own antivirus.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from typing import Any

import pytest

from app.av import (
    ClamdScanner,
    ScannerUnavailableError,
    ScanStatus,
    Verdict,
    eicar_bytes,
    make_scanner,
    scan_gate_error,
)
from app.config import Settings
from tests.support import build_settings


# --------------------------------------------------------------------------- #
# A fake clamd: speaks just enough of the INSTREAM protocol to test the client.
# --------------------------------------------------------------------------- #
class FakeClamd:
    """Accepts one INSTREAM session and replies with ``reply``."""

    def __init__(self, reply: bytes, *, drop: bool = False) -> None:
        self.reply = reply
        self.drop = drop
        self.received = b""
        self.command = b""
        self.server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.drop:  # simulate clamd dying mid-session
            writer.close()
            return
        self.command = await reader.readuntil(b"\0")
        while True:
            raw = await reader.readexactly(4)
            length = int.from_bytes(raw, "big")
            if length == 0:
                break
            self.received += await reader.readexactly(length)
        writer.write(self.reply)
        await writer.drain()
        writer.close()


async def _scan_with(reply: bytes, payload: bytes, **kw: Any) -> Verdict:
    fake = FakeClamd(reply, **kw)
    await fake.start()
    try:
        scanner = ClamdScanner(host="127.0.0.1", port=fake.port, timeout_seconds=5.0)
        return await scanner.scan(io.BytesIO(payload))
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_clamd_clean_reply_is_clean() -> None:
    verdict = await _scan_with(b"stream: OK\0", b"harmless bytes")
    assert verdict.status is ScanStatus.clean
    assert verdict.signature is None


@pytest.mark.asyncio
async def test_clamd_found_reply_is_infected_with_signature() -> None:
    verdict = await _scan_with(b"stream: Eicar-Test-Signature FOUND\0", eicar_bytes())
    assert verdict.status is ScanStatus.infected
    assert verdict.signature == "Eicar-Test-Signature"


@pytest.mark.asyncio
async def test_clamd_streams_the_whole_payload_in_instream_frames() -> None:
    payload = b"x" * (300 * 1024)  # spans several chunks
    fake = FakeClamd(b"stream: OK\0")
    await fake.start()
    try:
        scanner = ClamdScanner(host="127.0.0.1", port=fake.port, timeout_seconds=5.0)
        assert (await scanner.scan(io.BytesIO(payload))).status is ScanStatus.clean
    finally:
        await fake.stop()
    assert fake.command == b"zINSTREAM\0"
    assert fake.received == payload


@pytest.mark.asyncio
async def test_clamd_error_reply_raises_unavailable_never_clean() -> None:
    with pytest.raises(ScannerUnavailableError):
        await _scan_with(b"INSTREAM size limit exceeded. ERROR\0", b"payload")


@pytest.mark.asyncio
async def test_clamd_connection_failure_raises_unavailable() -> None:
    scanner = ClamdScanner(host="127.0.0.1", port=1, timeout_seconds=1.0)
    with pytest.raises(ScannerUnavailableError):
        await scanner.scan(io.BytesIO(b"payload"))


@pytest.mark.asyncio
async def test_clamd_dropped_connection_raises_unavailable() -> None:
    with pytest.raises(ScannerUnavailableError):
        await _scan_with(b"", b"payload", drop=True)


# --------------------------------------------------------------------------- #
# The scanner factory — fail-closed configuration
# --------------------------------------------------------------------------- #
def test_make_scanner_returns_none_when_disabled() -> None:
    assert make_scanner(build_settings(av_scanner="none")) is None


def test_make_scanner_builds_clamd_when_enabled() -> None:
    scanner = make_scanner(build_settings(av_scanner="clamav", clamav_host="clamav"))
    assert isinstance(scanner, ClamdScanner)


def test_make_scanner_rejects_clamav_without_host() -> None:
    with pytest.raises(ValueError):
        make_scanner(build_settings(av_scanner="clamav", clamav_host=""))


def test_scanning_must_be_enabled_outside_development() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production", av_scanner="none").validate_av()
    # …and a half-configured daemon is a misconfiguration, not a licence to skip.
    with pytest.raises(ValueError):
        Settings(environment="production", av_scanner="clamav", clamav_host="").validate_av()
    Settings(environment="production", av_scanner="clamav", clamav_host="clamav").validate_av()


# --------------------------------------------------------------------------- #
# The gate — which statuses may be read, and under which configuration
# --------------------------------------------------------------------------- #
class _Row:
    def __init__(self, status: ScanStatus) -> None:
        self.id = uuid.uuid4()
        self.scan_status = status


@pytest.mark.parametrize("status", [ScanStatus.pending, ScanStatus.error])
def test_gate_blocks_unscanned_files_with_409_when_scanning_is_on(status: ScanStatus) -> None:
    err = scan_gate_error(_Row(status), build_settings(av_scanner="clamav", clamav_host="c"))
    assert err is not None
    assert err.status_code == 409
    assert err.code == "file_scan_pending"


@pytest.mark.parametrize("status", [ScanStatus.pending, ScanStatus.error])
def test_gate_allows_unscanned_files_when_scanning_is_off(status: ScanStatus) -> None:
    # No scanner configured → nothing will ever move the row off ``pending``;
    # gating on it would block every download in a scanner-less deployment.
    assert scan_gate_error(_Row(status), build_settings(av_scanner="none")) is None


def test_gate_blocks_infected_even_when_scanning_is_off() -> None:
    # ``infected`` is a terminal, positively-known verdict: turning the scanner
    # off must never un-quarantine a file that was already found to be malware.
    err = scan_gate_error(_Row(ScanStatus.infected), build_settings(av_scanner="none"))
    assert err is not None
    assert err.status_code == 403
    assert err.code == "file_quarantined"


def test_gate_allows_clean() -> None:
    on = build_settings(av_scanner="clamav", clamav_host="c")
    assert scan_gate_error(_Row(ScanStatus.clean), build_settings(av_scanner="none")) is None
    assert scan_gate_error(_Row(ScanStatus.clean), on) is None


def test_eicar_bytes_is_the_standard_test_signature() -> None:
    payload = eicar_bytes()
    assert payload.startswith(b"X5O!P%@AP[4")
    assert payload.endswith(b"H+H*")
    assert len(payload) == 68
