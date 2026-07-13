"""Resources a Celery task needs outside a request (M2.5).

A worker has no ``app.state``, so tasks resolve their database URL and object
storage here. ``create_app`` registers its own (so an eagerly-run task in tests
shares the app's in-memory storage and restricted-role DSN); a real worker
process falls back to building both from :func:`get_settings`.

Tasks get a *URL*, not the app's engine: asyncpg connections are bound to the
event loop that created them, and an eager task runs its coroutine on its own
loop — sharing the app engine would hand it another loop's connections. Storage
instances have no loop affinity (MemoryStorage is a dict; S3Storage opens a
client per call), so the instance itself is shared.
"""

from __future__ import annotations

from .config import get_settings
from .storage import ObjectStorage, make_storage

_registered: tuple[str, ObjectStorage] | None = None
_fallback: tuple[str, ObjectStorage] | None = None


def register(app_db_url: str, storage: ObjectStorage) -> None:
    """Called by ``create_app`` so in-process (eager) tasks share its resources."""
    global _registered
    _registered = (app_db_url, storage)


def resolve() -> tuple[str, ObjectStorage]:
    """The (restricted-role DB URL, object storage) for the current process."""
    global _fallback
    if _registered is not None:
        return _registered
    if _fallback is None:  # worker process: build once from the environment
        settings = get_settings()
        _fallback = (settings.effective_app_database_url, make_storage(settings))
    return _fallback
