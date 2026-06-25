"""M1.2 — S3 storage backend round-trip (against MinIO).

Skips unless ``TEST_S3_ENDPOINT`` is set (mirrors the ``TEST_DATABASE_URL`` gate),
so the default suite stays dependency-free while CI / a dev with MinIO running can
prove the real ``aioboto3`` upload→stream→delete path works byte-identically.

Run locally with:
    docker run -d -p 9100:9000 -e MINIO_ROOT_USER=minioadmin \\
        -e MINIO_ROOT_PASSWORD=minioadmin minio/minio server /data
    TEST_S3_ENDPOINT=http://localhost:9100 uv run pytest tests/test_storage_s3.py
"""

from __future__ import annotations

import contextlib
import io
import os

import pytest

from app.config import Settings
from app.storage import S3Storage, object_key

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_S3_ENDPOINT"),
    reason="TEST_S3_ENDPOINT not set — S3 backend round-trip skipped",
)

# Imported after the skip guard so a no-MinIO run doesn't fail at import time.
import uuid  # noqa: E402

from botocore.exceptions import ClientError  # noqa: E402


def _settings() -> Settings:
    return Settings(
        environment="test",
        storage_backend="s3",
        s3_endpoint=os.environ["TEST_S3_ENDPOINT"],
        s3_bucket="tolera-files",
        s3_region="eu-central-1",
        s3_access_key=os.environ.get("TEST_S3_ACCESS_KEY", "minioadmin"),
        s3_secret_key=os.environ.get("TEST_S3_SECRET_KEY", "minioadmin"),
    )


async def _ensure_bucket(storage: S3Storage) -> None:
    async with storage._client() as s3:
        # Only swallow the already-exists race, not arbitrary failures.
        with contextlib.suppress(ClientError):
            await s3.create_bucket(Bucket="tolera-files")


async def test_s3_round_trip_byte_identical() -> None:
    storage = S3Storage(_settings())
    await _ensure_bucket(storage)

    data = b"ISO-10303-21;\n" + b"\x00\x01\x02\x03" * 1000 + b"\nEND-ISO-10303-21;\n"
    key = object_key(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "bracket.step")

    try:
        size = await storage.put(key, io.BytesIO(data), content_type="application/step")
        assert size == len(data)

        chunks = [chunk async for chunk in storage.stream(key)]
        assert b"".join(chunks) == data  # byte-identical
    finally:
        # Always clean up the object, even if an assertion above failed.
        await storage.delete(key)
    await storage.delete(key)  # idempotent — deleting again is not an error
