"""Celery base task policy + the idempotent example."""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY

from app import tasks
from app.tasks import BaseTask, apply_idempotent, example_idempotent


def test_apply_idempotent_does_not_duplicate_on_repeat() -> None:
    store: dict[str, dict[str, Any]] = {}

    first = apply_idempotent("k1", "hello", store)
    assert first == {"item_id": "k1", "value": "HELLO", "created": True}

    second = apply_idempotent("k1", "hello", store)
    assert second["created"] is False
    assert second["value"] == "HELLO"
    assert len(store) == 1


def test_example_task_is_idempotent_on_retry() -> None:
    tasks._STORE.clear()
    first = example_idempotent("a", "x")
    second = example_idempotent("a", "x")
    assert first["created"] is True
    assert second["created"] is False
    assert len(tasks._STORE) == 1


class _ProbeTask(BaseTask):
    name = "probe_task"


def _state_count(state: str) -> float:
    value = REGISTRY.get_sample_value("celery_tasks_total", {"task": "probe_task", "state": state})
    return value or 0.0


def test_basetask_callbacks_record_metrics() -> None:
    task = _ProbeTask()
    success0, retry0, failure0 = (
        _state_count("success"),
        _state_count("retry"),
        _state_count("failure"),
    )

    task.on_success({"ok": 1}, "id1", (), {})
    task.on_retry(Exception("e"), "id1", (), {}, None)
    task.on_failure(Exception("e"), "id1", (), {}, None)

    assert _state_count("success") == success0 + 1
    assert _state_count("retry") == retry0 + 1
    assert _state_count("failure") == failure0 + 1


def test_basetask_retry_policy_is_set() -> None:
    assert BaseTask.autoretry_for == (Exception,)
    assert BaseTask.retry_backoff is True
    assert BaseTask.max_retries == 5
