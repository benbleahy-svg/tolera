"""Object storage for uploaded part files (M1.2).

A thin seam over an S3-compatible object store so the provider is swappable
(DECISIONS.md 2026-06-25): dev/CI run **MinIO**, production runs an EU-resident
S3 bucket (provider OPEN — EU data residency). Object keys are **tenant-scoped**
(``org/<org_id>/part/<part_id>/<file_id>/<filename>``) so storage layout mirrors
the RLS isolation the DB enforces.

Two implementations behind one :class:`ObjectStorage` protocol:
  * :class:`MemoryStorage` — an in-process dict; the default, used by tests and a
    bare local boot (no external dependency to round-trip a file).
  * :class:`S3Storage` — ``aioboto3``; streams uploads from the spooled request
    body (never holds a whole 200 MB file in memory) and streams downloads back.

Stored bytes are raw and unmodified — upload→download is byte-identical
(M1.2 acceptance).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import IO, Any, Protocol, runtime_checkable

from .config import Settings

#: Download/stream chunk size (1 MiB) — bounds per-request memory on read.
STREAM_CHUNK_BYTES = 1024 * 1024


def object_key(org_id: uuid.UUID, part_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> str:
    """Build the tenant-scoped object key (DECISIONS.md 2026-06-25).

    The ``org_id`` prefix is defence-in-depth alongside ``part_file`` RLS; the
    ``file_id`` segment guarantees uniqueness even when two files share a name.
    Callers pass an already-sanitised filename (``parts._safe_filename``); we
    additionally take the basename here so a stray path component can never break
    out of the per-file prefix even if a caller forgets."""
    return f"org/{org_id}/part/{part_id}/{file_id}/{os.path.basename(filename)}"


@runtime_checkable
class ObjectStorage(Protocol):
    """The storage contract every file route depends on."""

    async def put(self, key: str, fileobj: IO[bytes], *, content_type: str | None = None) -> int:
        """Stream ``fileobj`` to ``key``; return the number of bytes written."""
        ...

    def stream(self, key: str) -> AsyncIterator[bytes]:
        """Yield the object's bytes in chunks (for a streaming download)."""
        ...

    async def delete(self, key: str) -> None:
        """Delete the object. Idempotent — deleting a missing key is not an error."""
        ...


class MemoryStorage:
    """In-process object store (dict). Default backend for tests + bare local boot.

    Not for production — bytes live in the process. The spooled request file is
    read fully here (test fixtures are tiny); the S3 backend is the one that must
    stream large files."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put(self, key: str, fileobj: IO[bytes], *, content_type: str | None = None) -> int:
        fileobj.seek(0)
        data = fileobj.read()
        self._objects[key] = data
        return len(data)

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        data = self._objects[key]  # KeyError → surfaced as a 500 (a missing blob is a bug)
        for start in range(0, len(data), STREAM_CHUNK_BYTES):
            yield data[start : start + STREAM_CHUNK_BYTES]

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)


class S3Storage:
    """S3-compatible backend (``aioboto3``) — MinIO in dev, an EU bucket in prod.

    A new client is opened per operation (cheap; ``aioboto3`` clients are async
    context managers and are not safe to share across tasks). Uploads stream from
    the spooled request body via ``upload_fileobj``; downloads stream the response
    body in chunks."""

    def __init__(self, settings: Settings) -> None:
        import aioboto3  # local import: only needed when the S3 backend is selected

        self._bucket = settings.s3_bucket
        self._session = aioboto3.Session()
        # MinIO (and most S3-compatibles) require path-style addressing + explicit
        # endpoint; AWS S3 accepts both. Credentials/endpoint come from settings.
        self._client_kwargs = {
            "endpoint_url": settings.s3_endpoint or None,
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key or None,
            "aws_secret_access_key": settings.s3_secret_key or None,
        }

    def _client(self) -> Any:  # aioboto3 async client is untyped
        return self._session.client("s3", **self._client_kwargs)

    async def put(self, key: str, fileobj: IO[bytes], *, content_type: str | None = None) -> int:
        fileobj.seek(0)
        extra = {"ContentType": content_type} if content_type else {}
        async with self._client() as s3:
            await s3.upload_fileobj(fileobj, self._bucket, key, ExtraArgs=extra)
            head = await s3.head_object(Bucket=self._bucket, Key=key)
        size: int = head["ContentLength"]
        return size

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        # Keep the client open for the life of the generator so the connection
        # stays live while chunks are streamed. ``resp["Body"]`` is the aiobotocore
        # StreamingBody (NOT the result of entering it as a context manager, which
        # hands back the raw aiohttp response that lacks ``iter_chunks``).
        async with self._client() as s3:
            resp = await s3.get_object(Bucket=self._bucket, Key=key)
            async for chunk in resp["Body"].iter_chunks(STREAM_CHUNK_BYTES):
                yield chunk

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)


def make_storage(settings: Settings) -> ObjectStorage:
    """Build the configured backend (DECISIONS.md 2026-06-25 — memory in dev/test).

    Validates first and fails closed on an unknown backend, so a typo'd/missing
    ``STORAGE_BACKEND`` in production can't silently accept uploads into process
    memory and lose them on restart (it would have to pass ``validate_storage``,
    which already forbids ``memory`` outside dev/test)."""
    settings.validate_storage()
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    if settings.storage_backend == "memory":
        return MemoryStorage()
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend!r}")
