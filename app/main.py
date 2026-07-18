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
from .addons import addons_router
from .bom_builder import bom_router
from .bulk_create import bulk_create_router
from .buyer_portal import buyer_router
from .checkout import checkout_router
from .collab import collab_router
from .config import Settings, get_settings
from .config_completeness import config_completeness_router
from .custom_tables import custom_tables_router
from .db import make_engine, make_sessionmaker
from .email_connections import router as email_connections_router
from .email_ingest import ingest_router
from .email_templates import email_templates_router
from .email_threads import router as email_threads_router
from .errors import register_exception_handlers
from .file_split import split_router
from .health import router as health_router
from .interrogation import interrogation_router
from .interrogation_config import interrogation_config_router
from .lens_extract import extract_router
from .lens_findings import findings_router
from .logging import configure_logging
from .materials import materials_router
from .me import router as me_router
from .metrics import register_metrics
from .middleware import MaxBodySizeMiddleware, RequestContextMiddleware
from .nesting import nesting_router
from .notes import router as notes_router
from .operations import operations_router
from .part_library import library_router as part_library_router
from .parts import parts_router
from .pdf_api import pdf_router
from .pricing import pricing_router
from .quote_assembly import assembly_router
from .quote_send import quote_send_router
from .quotes import quotes_router
from .requote_diff import requote_router
from .review_items import review_items_router
from .rule_suggest_api import rule_suggest_router
from .rules import rules_router
from .saved_views import saved_views_router
from .storage import make_storage
from .task_resources import register as register_task_resources


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Pass ``settings`` to override config in tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    settings.validate_storage()  # fail closed on a misconfigured object store

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The app serves requests as the restricted, RLS-bound role (M0.2);
        # migrations run separately as the owner role.
        app.state.engine = make_engine(settings.effective_app_database_url)
        app.state.sessionmaker = make_sessionmaker(app.state.engine)
        app.state.storage = make_storage(settings)  # object store for part files (M1.2)
        # Eagerly-run Celery tasks (tests) share the app's storage + restricted DSN (M2.5).
        register_task_resources(settings.effective_app_database_url, app.state.storage)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="Tolera API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    # Order matters: RequestContextMiddleware is added last so it stays the
    # outermost wrapper (it logs/meters every response, including the 413 below).
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_upload_bytes)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    register_metrics(app)
    app.include_router(health_router)
    app.include_router(notes_router)
    app.include_router(me_router)
    app.include_router(accounts_router)
    app.include_router(contacts_router)
    app.include_router(parts_router)
    app.include_router(interrogation_router)
    app.include_router(interrogation_config_router)
    app.include_router(nesting_router)
    app.include_router(part_library_router)
    app.include_router(split_router)
    app.include_router(extract_router)
    app.include_router(findings_router)
    app.include_router(quotes_router)
    app.include_router(bom_router)
    app.include_router(bulk_create_router)
    app.include_router(saved_views_router)
    app.include_router(materials_router)
    app.include_router(operations_router)
    app.include_router(pricing_router)
    app.include_router(addons_router)
    app.include_router(custom_tables_router)
    app.include_router(config_completeness_router)
    app.include_router(collab_router)
    app.include_router(ingest_router)
    app.include_router(email_connections_router)
    app.include_router(email_threads_router)
    app.include_router(email_templates_router)
    app.include_router(quote_send_router)
    app.include_router(rules_router)
    app.include_router(review_items_router)
    app.include_router(rule_suggest_router)
    app.include_router(requote_router)
    app.include_router(assembly_router)
    app.include_router(buyer_router)
    app.include_router(checkout_router)
    app.include_router(pdf_router)

    return app


app = create_app()
