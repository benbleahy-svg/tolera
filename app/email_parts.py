"""Email-body parts-list parse → Bulk Create prefill (M3.4 — spec ``#wingman``
pipeline 1, ``#smart-rfq`` shares the path).

The text-LLM reads the ingested RFQ's plain-text body (+ the attachment
filenames) and suggests a parts list — part number, revision, quantities,
requested date — that pre-fills the **Bulk Create Line Items** dialog
(AI-LENS §3). Everything here is a *suggestion* (AI-Governor): the guarded
result is persisted on the ``request_for_quote`` row and line items are
created only by the explicit Accept in :mod:`app.bulk_create` — never
automatically, and never fed into Kalk costing (CLAUDE.md §5).

Never-hallucinate (spec ``#lens-models``): a suggested part number must occur
verbatim in the email body or match an attachment filename; each suggested
quantity must occur in the body; revision/description/date claims that have no
verbatim source are cleared. "A wrong existing string" may survive — an
invented one may not (the :mod:`app.lens` guard's contract, applied to email
text instead of a print's text layer).

The parse runs as its own Celery task (enqueued post-commit by the M3.3 ingest
task): long work never blocks ingest, and a parse failure degrades to an empty
dialog, never a lost RFQ.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from celery.result import AsyncResult
from sqlalchemy import select

from .celery_app import celery_app
from .db import make_engine, make_sessionmaker, org_scoped_session
from .lens import RawLineItem
from .lens_extract import _run_on_own_loop
from .lens_provider import PARTS_PROMPT_VERSION, LensProviderError, resolve
from .models import PartFile, RequestForQuote
from .part_index import normalize_filename
from .tasks import BaseTask

logger = logging.getLogger("app.email_parts")

__all__ = [
    "EmailPartsListProvider",
    "RawLineItem",
    "email_parts_parse_task",
    "match_rows_to_parts",
    "parts_list_guard",
    "run_email_parts_parse",
]


class EmailPartsListProvider(Protocol):
    """The parts-list slice of the Lens provider seam (kept separate from
    :class:`app.lens.LensProvider` so the M3.1 document-extraction fakes keep
    type-checking without this method)."""

    async def parse_email_parts_list(
        self, body_text: str, attachment_filenames: list[str]
    ) -> list[RawLineItem]: ...


def _text_key(text: str) -> str:
    """Whitespace-collapsed, casefolded — presence checks tolerant of wrapping."""
    return " ".join(text.split()).casefold()


def _contains_verbatim(body_key: str, claim: str) -> bool:
    """Token-bounded presence of ``claim`` in the normalized body. A bare
    substring test would make the guard a no-op for short claims — a
    one-letter revision "B" occurs inside almost any German sentence
    (fresh-eyes review 🔴1) — so the match must not sit inside a longer
    alphanumeric run."""
    key = _text_key(claim)
    if not key:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", body_key) is not None


def _part_key(part_number: str) -> str:
    """The filename-match key: same tokenization as ``normalize_filename``
    (spec#partlib "strip extension, lowercase, tokenize") so ``PP-3635-001``
    agrees with ``PP-3635-001_TUBE.step``."""
    return re.sub(r"[^a-z0-9]+", "_", part_number.casefold()).strip("_")


def _key_in_filename(part_key: str, file_key: str) -> bool:
    """Token-bounded containment of a part-number key in a filename key
    (both ``_``-tokenized): ``pp_3635_001`` matches ``pp_3635_001_tube`` but
    ``635`` does not — a fragment must line up with whole tokens."""
    if not part_key:
        return False
    return re.search(rf"(?:^|_){re.escape(part_key)}(?:_|$)", file_key) is not None


#: Body-quantity extraction accepts the German/Swiss grouped integer forms —
#: "1.000 Stk." / "1'000" — alongside plain digit runs; a plain ``\d+`` scan
#: would tokenize "1.000" as {1, 0} and the guard would silently drop a
#: legitimate 1000 (fresh-eyes review 🟡3, DACH delta).
_NUMBER_RE = re.compile(r"\d{1,3}(?:[.']\d{3})+|\d+")


def _body_numbers(body_text: str) -> set[str]:
    return {match.replace(".", "").replace("'", "") for match in _NUMBER_RE.findall(body_text)}


#: Deterministic date forms a DACH RFQ body actually uses.
_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y")


def _iso_from_raw(raw: str) -> str | None:
    """Derive the ISO date from the *guarded* verbatim snippet — the model's
    own ISO field is untrusted (raw "31.12.2026" must never ship with ISO
    "2026-01-01"; CodeRabbit minor)."""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parts_list_guard(
    items: list[RawLineItem], body_text: str, attachment_filenames: list[str]
) -> tuple[list[RawLineItem], list[RawLineItem]]:
    """The never-hallucinate constraint over an email (M3.4 AC: "a part not in
    the email/attachments is not added"). Returns ``(kept, dropped)``.

    * ``part_number`` must occur in the body (text-normalized) or match an
      attachment filename (token-normalized) — else the whole row drops.
    * each quantity must occur as a number in the body — invented ones drop
      (the row survives; blank quantities default to 1 at Accept, per the
      dialog's own copy — DemoB/04).
    * ``revision`` / ``description`` / ``requested_date_raw`` claims without a
      verbatim source are cleared, never shown.
    """
    body_key = _text_key(body_text)
    file_keys = [key for f in attachment_filenames if (key := normalize_filename(f))]
    body_numbers = _body_numbers(body_text)

    kept: list[RawLineItem] = []
    dropped: list[RawLineItem] = []
    for item in items:
        part_key = _part_key(item.part_number)
        in_body = _contains_verbatim(body_key, item.part_number)
        in_files = any(_key_in_filename(part_key, file_key) for file_key in file_keys)
        if not (in_body or in_files):
            dropped.append(item)
            continue
        if item.revision and not _contains_verbatim(body_key, item.revision):
            item.revision = None
        if item.description and not _contains_verbatim(body_key, item.description):
            item.description = None
        if not item.requested_date_raw or not _contains_verbatim(body_key, item.requested_date_raw):
            item.requested_date = None
            item.requested_date_raw = None
        else:
            # The ISO form is DERIVED from the guarded snippet, never taken
            # from the model — raw "31.12.2026" must not ship as "2026-01-01".
            item.requested_date = _iso_from_raw(item.requested_date_raw)
        item.quantities = sorted({q for q in item.quantities if q >= 1 and str(q) in body_numbers})
        kept.append(item)
    if dropped:
        # counts only — part numbers are customer content (§5 logging).
        logger.warning(
            "email_parts_hallucination_dropped",
            extra={"dropped": len(dropped), "kept": len(kept)},
        )
    return kept, dropped


def match_rows_to_parts(
    part_numbers: list[str],
    candidates: list[tuple[uuid.UUID, list[str]]],
) -> dict[int, uuid.UUID]:
    """Deterministic file→part distribution (no LLM): row *i* binds the first
    unconsumed candidate part one of whose filenames contains the row's
    part-number key (the M2.12 ``normalize_filename`` convention). Each part is
    consumed at most once; unmatched rows get no entry (Accept creates a fresh
    file-less part — the ``#wingman`` §6 "line items without files" gap case,
    surfaced by M3.9 triage)."""
    consumed: set[uuid.UUID] = set()
    matches: dict[int, uuid.UUID] = {}
    for index, part_number in enumerate(part_numbers):
        key = _part_key(part_number)
        if not key:
            continue
        for part_id, filenames in candidates:
            if part_id in consumed:
                continue
            file_keys = (normalize_filename(f) or "" for f in filenames)
            if any(_key_in_filename(key, file_key) for file_key in file_keys):
                matches[index] = part_id
                consumed.add(part_id)
                break
    return matches


# --------------------------------------------------------------------------- #
# The parse task — body + filenames → guarded suggestions on the RFQ row
# --------------------------------------------------------------------------- #
def _payload(
    status: str,
    *,
    items: list[RawLineItem] | None = None,
    dropped: int = 0,
    error_code: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "prompt_version": PARTS_PROMPT_VERSION,
        "parsed_at": datetime.now(UTC).isoformat(),
        "dropped": dropped,
        "error_code": error_code,
        "items": [item.model_dump() for item in (items or [])],
    }


async def _store_payload(
    sessionmaker: Any, org_id: uuid.UUID, rfq_id: uuid.UUID, payload: dict[str, Any]
) -> bool:
    """Persist under a short row lock. Returns False when the RFQ vanished."""
    async with org_scoped_session(sessionmaker, org_id) as session:
        rfq = await session.get(RequestForQuote, rfq_id, with_for_update=True)
        if rfq is None:
            return False
        rfq.suggested_line_items = payload
        return True


async def run_email_parts_parse(
    db_url: str, *, org_id: uuid.UUID, rfq_id: uuid.UUID
) -> dict[str, Any]:
    """The task core — idempotent (a re-run simply overwrites
    ``suggested_line_items`` with a fresh parse; concurrent re-runs converge
    last-writer-wins on identical input, since body/filenames are immutable
    after ingest).

    Two SHORT transactions bracket the provider call: reading the input, then
    persisting the result. Holding the RFQ row lock (and its pooled
    connection) across an external LLM round-trip would let a degraded
    provider exhaust the pool and block ingest (CodeRabbit major)."""
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        async with org_scoped_session(sessionmaker, org_id) as session:
            rfq = await session.get(RequestForQuote, rfq_id)
            if rfq is None:
                return {"failed": True, "error_code": "rfq_gone"}
            body_text = rfq.description or ""
            # M3.9: the draft quote the Triage Brief chains onto after this parse.
            quote_id = str(rfq.quote_id) if rfq.quote_id is not None else None
            filenames = list(
                (
                    await session.scalars(
                        select(PartFile.filename).where(PartFile.rfq_id == rfq_id)
                    )
                ).all()
            )

        if not body_text.strip():
            await _store_payload(sessionmaker, org_id, rfq_id, _payload("completed"))
            return {"items": 0, "dropped": 0, "quote_id": quote_id}
        try:
            provider = cast("EmailPartsListProvider", resolve())
            raw_items = await provider.parse_email_parts_list(body_text, filenames)
        except (LensProviderError, RuntimeError, AttributeError) as exc:
            # Deterministic non-answers (refusal, bad JSON, provider not
            # configured): record and stop — retries would burn identical
            # calls, and a parse failure must degrade to an empty dialog,
            # never fail the ingested quote. Triage still runs (files/compliance/
            # need-by don't need the parts list).
            code = exc.code if isinstance(exc, LensProviderError) else "provider_unavailable"
            await _store_payload(sessionmaker, org_id, rfq_id, _payload("failed", error_code=code))
            return {"failed": True, "error_code": code, "quote_id": quote_id}
        kept, dropped_items = parts_list_guard(raw_items, body_text, filenames)
        stored = await _store_payload(
            sessionmaker,
            org_id,
            rfq_id,
            _payload("completed", items=kept, dropped=len(dropped_items)),
        )
        if not stored:
            return {"failed": True, "error_code": "rfq_gone"}
        return {"items": len(kept), "dropped": len(dropped_items), "quote_id": quote_id}
    finally:
        await engine.dispose()


@celery_app.task(
    base=BaseTask, name="app.email_parts_parse", bind=True, soft_time_limit=120, time_limit=180
)
def email_parts_parse_task(self: Any, org_id: str, rfq_id: str) -> dict[str, Any]:
    """Celery wrapper around :func:`run_email_parts_parse` (idempotent, §5)."""
    binding = {"org_id": org_id, "rfq_id": rfq_id}
    task_id = self.request.id
    # Redelivery guard (M3.1 precedent): worker died after commit, before ack.
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    from .task_resources import resolve as resolve_task_resources

    db_url, _storage = resolve_task_resources()
    result = _run_on_own_loop(
        run_email_parts_parse(db_url, org_id=uuid.UUID(org_id), rfq_id=uuid.UUID(rfq_id))
    )
    out = cast("dict[str, Any]", result)
    # M3.9 — chain the RFQ Triage Brief after the email-parse job (spec
    # #ai-triage: "chains after the Lens email-parse Celery job"). Post-work,
    # fire-and-forget: the parts list is now committed, so the brief reads it.
    quote_id = out.get("quote_id")
    if quote_id:
        from .triage import enqueue_triage_brief

        enqueue_triage_brief(uuid.UUID(org_id), uuid.UUID(quote_id))
    # counts only — parts lists are customer content (§5 logging).
    logger.info(
        "email_parts_parse_completed",
        extra={
            "task_id": task_id,
            "items": out.get("items"),
            "dropped": out.get("dropped"),
            "failed": out.get("failed", False),
            **binding,
        },
    )
    return {**out, **binding}
