"""FastAPI application factory — the M0.1 walking skeleton.

Wires the cross-cutting scaffolding every later block inherits: structured JSON
logging, the request-context middleware, the single error envelope, baseline
metrics, and the health/readiness probes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .accounts import accounts_router, contacts_router
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker
from .errors import register_exception_handlers
from .health import router as health_router
from .logging import configure_logging
from .me import router as me_router
from .metrics import register_metrics
from .middleware import RequestContextMiddleware
from .notes import router as notes_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Pass ``settings`` to override config in tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The app serves requests as the restricted, RLS-bound role (M0.2);
        # migrations run separately as the owner role.
        app.state.engine = make_engine(settings.effective_app_database_url)
        app.state.sessionmaker = make_sessionmaker(app.state.engine)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="Tolera API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    register_metrics(app)
    app.include_router(health_router)
    app.include_router(notes_router)
    app.include_router(me_router)
    app.include_router(accounts_router)
    app.include_router(contacts_router)

    return app


app = create_app()
