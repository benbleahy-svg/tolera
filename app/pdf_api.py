"""Quote / order-confirmation PDF download endpoints (M5.4).

Shop-side, Clerk-authenticated downloads of the white-label document:

* ``GET /api/quotes/{quote_id}/pdf`` — the quote as an *Angebot* (net). Rendered
  **live** from the current Display Settings (a preview; the send-time snapshot is
  M5.5). Also stored so the artifact is re-fetchable (AC).
* ``GET /api/orders/{order_id}/pdf`` — the order-confirmation variant used by the
  Orders list's "Download order PDF" (M5.6); rendered from the Order's persisted
  §14-UStG breakdown.

Both open the caller's org-scoped session (RLS), so a cross-org id 404s. The
rendered bytes are streamed inline and mirrored into object storage under a
tenant-scoped key (``pdf_object_key`` on the row). A 503 is returned when the
WeasyPrint native libs are unavailable (a deploy/config fault, never a client
error)."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .buyer_portal import load_display_settings
from .deps import get_session
from .errors import AppError
from .models import Order, Organization, Quote
from .pdf import (
    assemble_order_context,
    assemble_quote_context,
    html_to_pdf,
    load_quote_content,
    render_document_html,
    weasyprint_available,
)

pdf_router = APIRouter(prefix="/api", tags=["pdf"])


def _pdf_response(pdf: bytes, filename: str) -> Response:
    """An inline ``application/pdf`` response (opens in-browser; the filename is
    used on Save)."""
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _require_weasyprint() -> None:
    if not weasyprint_available():
        # A missing native lib is a server/deploy fault, not a client error.
        raise AppError(
            "pdf_unavailable",
            "PDF rendering is temporarily unavailable.",
            status_code=503,
        )


async def _load_org(session: AsyncSession, principal: Principal) -> Organization:
    org = await session.get(Organization, principal.active_org_id)
    if org is None:  # RLS breakage — never invent shop identity
        raise AppError("org_not_found", "Organization not found.", status_code=404)
    return org


@pdf_router.get("/quotes/{quote_id}/pdf")
async def download_quote_pdf(
    quote_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Response:
    """Render + return the white-label quote PDF (Angebot). 404 on a missing or
    trashed quote in the caller's org."""
    _require_weasyprint()
    quote = await session.get(Quote, quote_id)
    if quote is None or quote.deleted_at is not None:
        raise AppError("quote_not_found", "Quote not found.", status_code=404)
    org = await _load_org(session, principal)

    settings = await load_display_settings(session, org.id)
    content = await load_quote_content(session, org.id)
    storage = request.app.state.storage
    ctx = await assemble_quote_context(
        session, org, quote, settings, content, storage, datetime.now(UTC)
    )
    pdf = html_to_pdf(render_document_html(ctx))
    # A live preview only — it must NOT persist ``quote.pdf_object_key``. That key
    # is the send-time *snapshot* (M5.5): a preview download before send must not
    # point it at a non-snapshot render (fresh-eyes review, M5.4).
    return _pdf_response(pdf, f"Angebot-{quote.number}.pdf")


@pdf_router.get("/orders/{order_id}/pdf")
async def download_order_pdf(
    order_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
) -> Response:
    """Render + return the order-confirmation PDF (Auftragsbestätigung), with the
    persisted §14-UStG tax block. 404 on a missing order in the caller's org."""
    _require_weasyprint()
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError("order_not_found", "Order not found.", status_code=404)
    org = await _load_org(session, principal)

    settings = await load_display_settings(session, org.id)
    content = await load_quote_content(session, org.id)
    storage = request.app.state.storage
    ctx = await assemble_order_context(session, org, order, settings, content, storage)
    pdf = html_to_pdf(render_document_html(ctx))

    key = f"org/{org.id}/order/{order.id}/order.pdf"
    await storage.put(key, io.BytesIO(pdf), content_type="application/pdf")
    order.pdf_object_key = key
    return _pdf_response(pdf, f"Auftragsbestaetigung-{order.number}.pdf")
