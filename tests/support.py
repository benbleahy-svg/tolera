"""Shared test helpers."""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

from app.celery_app import celery_app
from app.config import Settings

DEFAULT_TEST_DB = "postgresql+asyncpg://tolera:tolera@localhost:5432/tolera_test"


@contextmanager
def eager_celery() -> Iterator[None]:
    """Run Celery tasks inline (the M2.5/M3.1 precedent) with the result
    backend swapped to the in-process cache (CI has no Redis service)."""
    previous = {
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
        task_eager_propagates=True,
        result_backend="cache+memory://",
    )
    celery_app.__dict__.pop("backend", None)
    try:
        yield
    finally:
        celery_app.conf.update(**previous)
        celery_app.__dict__.pop("backend", None)


def mailgun_fields(signing_key: str) -> dict[str, str]:
    """A fresh valid Mailgun signature triple (timestamp/token/signature)."""
    ts = str(int(time.time()))
    token = uuid.uuid4().hex
    sig = hmac.new(signing_key.encode(), (ts + token).encode(), hashlib.sha256).hexdigest()
    return {"timestamp": ts, "token": token, "signature": sig}


def post_mailgun_webhook(
    client: TestClient,
    raw_eml: bytes,
    *,
    recipient: str,
    sender: str,
    signing_key: str,
) -> Any:
    """POST a raw-MIME message to the Mailgun inbound route."""
    data = {
        **mailgun_fields(signing_key),
        "recipient": recipient,
        "sender": sender,
        "body-mime": raw_eml.decode("utf-8"),
    }
    return client.post("/webhooks/mailgun", data=data)


def build_settings(
    database_url: str = DEFAULT_TEST_DB,
    app_database_url: str | None = None,
    *,
    max_upload_mb: int = 200,
    **overrides: Any,
) -> Settings:
    """Construct deterministic test settings (init kwargs override any ``.env``).

    ``app_database_url`` is the restricted-role DSN the request-serving engine
    uses; when omitted the app falls back to the (owner) ``database_url``.
    ``max_upload_mb`` lets a test exercise the upload size cap cheaply, and
    ``**overrides`` sets any other field (e.g. ``av_scanner=`` for M3.13).
    """
    return Settings(
        **overrides,
        environment="test",
        database_url=database_url,
        app_database_url=app_database_url,
        redis_url="redis://localhost:6379/15",
        log_level="INFO",
        # Pin the backend so a globally-set STORAGE_BACKEND can't switch tests to S3.
        storage_backend="memory",
        max_upload_mb=max_upload_mb,
    )
