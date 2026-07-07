"""Request-context middleware: request-id propagation, access logging, metrics.

Implemented as pure ASGI (not ``BaseHTTPMiddleware``) so the ``request_id``
context variable set here is visible inside route handlers and their log lines.
"""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import error_envelope
from .logging import request_id_var
from .metrics import http_request_duration_seconds, http_requests_total

logger = logging.getLogger("app.access")

_REQUEST_ID_HEADER = b"x-request-id"
_REQUEST_ID_MAX_LEN = 128
_CONTENT_LENGTH_HEADER = b"content-length"


class MaxBodySizeMiddleware:
    """Reject a request whose declared ``Content-Length`` exceeds the upload cap,
    **before** the multipart parser spools the body to disk/memory (CodeRabbit
    PR #8 — defence against disk/memory exhaustion).

    This is a cheap in-app guard for honest clients; the primary control against a
    spoofed/absent Content-Length or chunked upload is the reverse proxy's body-size
    limit (e.g. nginx ``client_max_body_size``) in front of the app."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            raw = dict(scope.get("headers", [])).get(_CONTENT_LENGTH_HEADER)
            if raw is not None:
                try:
                    declared = int(raw)
                except ValueError:
                    declared = -1
                if declared > self.max_bytes:
                    body = json.dumps(
                        error_envelope(
                            "file_too_large", "Request body exceeds the upload size limit."
                        )
                    ).encode()
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 413,
                            "headers": [
                                (b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                            ],
                        }
                    )
                    await send({"type": "http.response.body", "body": body})
                    return
        await self.app(scope, receive, send)


class RequestContextMiddleware:
    """Attach a request id, time the request, and emit one structured access log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming = headers.get(_REQUEST_ID_HEADER)
        # Tolerate a malformed header rather than 500 on bad UTF-8, and don't
        # trust the client with unbounded input: an oversized value would be
        # echoed into the response header and stamped on every log line for the
        # request (log inflation / junk trace ids).
        request_id = incoming.decode("utf-8", errors="replace") if incoming else uuid4().hex
        if len(request_id) > _REQUEST_ID_MAX_LEN:
            request_id = uuid4().hex
        token = request_id_var.set(request_id)

        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((_REQUEST_ID_HEADER, request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start
            method = scope.get("method", "")
            route = scope.get("route")
            path = getattr(route, "path", "unmatched")
            http_request_duration_seconds.labels(method, path).observe(elapsed)
            http_requests_total.labels(method, path, str(status_code)).inc()
            logger.info(
                "request",
                extra={
                    "http_method": method,
                    "http_path": path,
                    "http_status": status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
            request_id_var.reset(token)
