"""Structured JSON logging carries request/org context."""

from __future__ import annotations

import json
import logging
import sys

from app.logging import JsonFormatter, configure_logging, request_id_var


def test_formatter_emits_json_with_context() -> None:
    formatter = JsonFormatter()
    token = request_id_var.set("req-123")
    try:
        record = logging.makeLogRecord(
            {
                "name": "test",
                "levelno": logging.INFO,
                "levelname": "INFO",
                "msg": "hello %s",
                "args": ("world",),
                "custom_field": "x",
            }
        )
        rendered = formatter.format(record)
    finally:
        request_id_var.reset(token)

    data = json.loads(rendered)
    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["request_id"] == "req-123"
    assert data["org_id"] is None
    assert data["custom_field"] == "x"
    assert "timestamp" in data


def test_formatter_includes_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )
    data = json.loads(formatter.format(record))
    assert "exc_info" in data
    assert "ValueError" in data["exc_info"]


def test_configure_logging_installs_json_handler() -> None:
    root = logging.getLogger()
    saved_level, saved_handlers = root.level, root.handlers[:]
    try:
        configure_logging("DEBUG")
        assert root.level == logging.DEBUG
        assert any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers)
    finally:
        # Restore the process-wide root logger — leaving it at DEBUG changes
        # the log output of every test that runs after this one.
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
