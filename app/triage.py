"""RFQ Triage Brief — AI Feature 1 (spec ``#ai-triage``; M3.9).

Governing question: *"Should I work on this RFQ now, and am I the right
person?"* Chains after the Lens email-parse job when an ingested RFQ creates a
draft quote; the result is cached as ``quote.triage_brief`` (JSONB) and rendered
as the dashboard notification card + the quote-header Triage chip.

Design — a **deterministic core** + a **gated AI enrichment**:

* The deterministic core (parts/file summary, missing-file blocker, compliance
  flags, est-time-to-quote, need-by, customer known/new) is computed with **no
  AI** and is *always* populated. This is what makes "compliance flags are
  never suppressible" and "est-time-to-quote is deterministic (not AI)" hold
  together with "AI-disabled skips briefs": when AI is off, the core still
  renders and the card shows an "AI processing disabled" state for the enriched
  fields only.
* The AI enrichment is a **single Claude call** that only *adds* inferred
  process hints (never-hallucinate: it cannot drop a deterministic process, and
  it never overwrites the deterministic customer one-liner, est-time, or
  compliance — those are facts). It is skipped when AI is disabled *or* any part
  is export-controlled (DECISIONS 2026-07-15: a dual-use-flagged part's content
  never reaches ANY provider).

The est-time figure is deterministic -- ``part_count * per-process base
minutes * +/-band`` -- identical across runs and independent of the AI call
(spec: "not AI. Feeds workload planning.").
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from celery.result import AsyncResult
from sqlalchemy import func, select

from .celery_app import celery_app
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker, org_scoped_session
from .export_control import record_ai_skip
from .lens_extract import _run_on_own_loop
from .lens_provider import LensProviderError
from .models import ExportControlSubject
from .tasks import BaseTask

logger = logging.getLogger("app.triage")

#: Bump when the assembled JSON shape changes (readers key off it).
TRIAGE_BRIEF_VERSION = 1
#: Versioned prompt id (repeatability, M3.11 eval-harness alignment).
TRIAGE_PROMPT_VERSION = "triage-v1"

# --------------------------------------------------------------------------- #
# Deterministic signal builders (no AI — pure, repeatable)
# --------------------------------------------------------------------------- #

#: File extensions grouped into the classes the summary reports.
_CAD_EXTS = ("step", "stp", "iges", "igs", "x_t", "x_b", "sldprt", "ipt", "3dm", "sat")
_SHEET_EXTS = ("dxf", "dwg")
_PRINT_EXTS = ("pdf", "tif", "tiff")


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _part_key(part_number: str) -> str:
    """Normalise a part number to a filename-comparable key (mirrors
    ``email_parts._part_key`` so missing-file detection matches ingest)."""
    return re.sub(r"[^a-z0-9]+", "_", (part_number or "").casefold()).strip("_")


def _file_key(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return re.sub(r"[^a-z0-9]+", "_", stem.casefold()).strip("_")


def summarize_files(filenames: list[str]) -> dict[str, Any]:
    """Count received files by class → ``{step,dxf,pdf,other,total}`` +
    a German one-line summary (spec example "7 parts · 5 STEP + 3 PDF")."""
    counts: dict[str, Any] = {"step": 0, "dxf": 0, "pdf": 0, "other": 0}
    for name in filenames:
        ext = _ext(name)
        if ext in _CAD_EXTS:
            counts["step"] += 1
        elif ext in _SHEET_EXTS:
            counts["dxf"] += 1
        elif ext in _PRINT_EXTS:
            counts["pdf"] += 1
        else:
            counts["other"] += 1
    counts["total"] = len(filenames)
    parts = []
    if counts["step"]:
        parts.append(f"{counts['step']} STEP")
    if counts["dxf"]:
        parts.append(f"{counts['dxf']} DXF")
    if counts["pdf"]:
        parts.append(f"{counts['pdf']} PDF")
    if counts["other"]:
        parts.append(f"{counts['other']} weitere")
    counts["summary"] = " + ".join(parts) if parts else "keine Dateien"
    return counts


def detect_missing_files(part_numbers: list[str], filenames: list[str]) -> list[str]:
    """Expected parts (from the parsed line items) that arrived with **no**
    matching file — the hard blocker (spec: "⚠ No file received: PP-2244")."""
    file_keys = [_file_key(f) for f in filenames]
    missing: list[str] = []
    for pn in part_numbers:
        key = _part_key(pn)
        if not key:
            continue
        matched = any(
            key == fk or re.search(rf"(?:^|_){re.escape(key)}(?:_|$)", fk) for fk in file_keys
        )
        if not matched and pn not in missing:
            missing.append(pn)
    return missing


#: DE + EN export-control / dual-use keywords (DACH delta: EU dual-use, not
#: ITAR). Matched case-insensitively on whole words; each distinct hit surfaces
#: one flag. Never suppressible.
_COMPLIANCE_TERMS = (
    "itar",
    "ear99",
    "dual-use",
    "dual use",
    "cui",
    "ausfuhr",
    "ausfuhrkontrolle",
    "exportkontrolle",
    "export control",
    "export-controlled",
    "wehrtechnik",
    "rüstung",
    "ruestung",
    "verteidigung",
    "military",
    "waffen",
    "defense",
    "defence",
)


def scan_compliance(text: str, export_controlled: bool) -> list[dict[str, Any]]:
    """Deterministic compliance flags — always surfaced, never suppressible.

    Two sources: (a) an ``export_controlled`` part/RFQ flag; (b) a keyword scan
    of the email subject + body. Returns one ``warn`` flag per source/term.
    """
    flags: list[dict[str, Any]] = []
    if export_controlled:
        flags.append(
            {
                "code": "export_control",
                "severity": "warn",
                "source": "part_flag",
                "detail": "Teil als exportkontrolliert (EU Dual-Use) markiert",
            }
        )
    haystack = (text or "").casefold()
    seen: set[str] = set()
    for term in _COMPLIANCE_TERMS:
        if term in seen:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack):
            seen.add(term)
            flags.append(
                {
                    "code": "export_control",
                    "severity": "warn",
                    "source": "keyword",
                    "term": term,
                    "detail": f"Exportkontroll-Hinweis im Text erkannt: „{term}“",
                }
            )
    return flags


#: Deterministic process families keyed off file class + material/keyword hints,
#: plus the per-part base minutes each contributes to est-time-to-quote. These
#: constants stand in for the spec's "per-org historical avg" until a history
#: table accrues over the pilot (DECISIONS 2026-06-23 fixtures) — ASSUMED,
#: cheap-to-reverse, tuned so the spec example (7 parts -> ~2-3 hrs) holds.
_PROCESS_BASE_MIN = {"machining": 22, "sheet": 16, "print": 18, "unknown": 20}

#: Each pattern anchors EVERY alternative at a word boundary (the group sits
#: inside the ``\b``), so "worksheet"/"laserjet" can't false-positive while the
#: German stems still prefix-match ("fräsen", "frästeil").
_MATERIAL_PROCESS_HINTS = (
    (re.compile(r"\b(?:blech|sheet|laser|abkant|biege|stanz)", re.I), "sheet", "Blechbearbeitung"),
    (re.compile(r"\b(?:dreh|turn|drehteil)", re.I), "machining", "Drehen"),
    (re.compile(r"\b(?:fräs|mill|cnc)", re.I), "machining", "CNC-Fräsen"),
    (re.compile(r"\b(?:eloxal|eloxier|anodis|anodize)", re.I), "machining", "Eloxieren"),
)


def detect_processes(filenames: list[str], text: str) -> list[dict[str, Any]]:
    """Deterministic process-family hints from file classes + material keywords
    (spec: "From material keywords + file types"). The AI enrichment may refine
    these labels, but est-time never depends on the AI output."""
    procs: dict[str, dict[str, Any]] = {}
    exts = [_ext(f) for f in filenames]
    if any(e in _SHEET_EXTS for e in exts):
        procs["sheet"] = {"family": "sheet", "name": "Blechbearbeitung", "likelihood": "likely"}
    if any(e in _CAD_EXTS for e in exts):
        procs.setdefault(
            "machining", {"family": "machining", "name": "CNC-Fräsen", "likelihood": "likely"}
        )
    for pattern, family, label in _MATERIAL_PROCESS_HINTS:
        if pattern.search(text or ""):
            procs.setdefault(family, {"family": family, "name": label, "likelihood": "likely"})
    for proc in procs.values():
        proc["source"] = "deterministic"
    return list(procs.values())


def estimate_time_to_quote(part_count: int, processes: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic est-time-to-quote (spec: ``part count * process type *
    per-org historical avg``, **not AI**). Identical across runs; monotonic in
    part count. Returns minutes + a German ``ca. X-Y Std.`` display."""
    count = max(int(part_count), 0)
    families = [p.get("family", "unknown") for p in processes]
    base = max(
        (_PROCESS_BASE_MIN.get(f, _PROCESS_BASE_MIN["unknown"]) for f in families), default=0
    )
    if base == 0:
        base = _PROCESS_BASE_MIN["unknown"]
    total = count * base
    low_min = round(total * 0.8)
    high_min = round(total * 1.2)
    low_h = max(round(low_min / 60), 0)
    high_h = max(round(high_min / 60), low_h)
    if total == 0:
        display = "—"
    elif low_h == high_h:
        display = f"ca. {high_h} Std." if high_h else "< 1 Std."
    else:
        display = f"ca. {low_h}-{high_h} Std."
    return {
        "low_min": low_min,
        "high_min": high_min,
        "display": display,
        "deterministic": True,
    }


def need_by(requested_date: Any, now: datetime) -> dict[str, Any]:
    """Need-by date + days-until + a German urgency band (spec: feeds the
    dashboard urgency score). ``requested_date`` may be a ``date``/``datetime``
    or ISO string; ``None`` → no deadline."""
    if requested_date is None:
        return {"date": None, "days_until": None, "urgency": "keine"}
    if isinstance(requested_date, str):
        try:
            parsed = datetime.fromisoformat(requested_date)
        except ValueError:
            return {"date": None, "days_until": None, "urgency": "keine"}
        target = parsed.date()
    elif isinstance(requested_date, datetime):
        target = requested_date.date()
    else:  # date
        target = requested_date
    days = (target - now.date()).days
    if days < 0:
        urgency = "überfällig"
    elif days <= 3:
        urgency = "hoch"
    elif days <= 10:
        urgency = "mittel"
    else:
        urgency = "niedrig"
    return {"date": target.isoformat(), "days_until": days, "urgency": urgency}


def customer_line(known: bool, name: str | None, prior_quotes: int) -> str:
    """Deterministic German one-liner (spec: new-vs-known; the full customer
    intelligence brief fires at send-time, M5). The AI enrichment may replace
    this phrasing, but it must never fabricate history."""
    who = name or "Unbekannter Absender"
    if known:
        return f"Bestandskunde · {who} · {prior_quotes} bisherige Anfragen"
    return f"Neukunde · {who}"


# --------------------------------------------------------------------------- #
# Brief assembly (deterministic core + optional AI enrichment)
# --------------------------------------------------------------------------- #


def assemble_brief(
    *,
    now: datetime,
    ai_reason: str,
    part_count: int,
    files: dict[str, Any],
    missing: list[str],
    processes: list[dict[str, Any]],
    est_time: dict[str, Any],
    customer: dict[str, Any],
    compliance: list[dict[str, Any]],
    need_by_signal: dict[str, Any],
) -> dict[str, Any]:
    """Build the versioned ``triage_brief`` JSONB payload."""
    return {
        "version": TRIAGE_BRIEF_VERSION,
        "prompt_version": TRIAGE_PROMPT_VERSION,
        "generated_at": now.isoformat(),
        "ai": {"enabled": ai_reason == "ok", "reason": ai_reason},
        "parts": {"count": part_count, "files": files},
        "missing_files": missing,
        "detected_processes": processes,
        "est_time_to_quote": est_time,
        "customer": customer,
        "compliance_flags": compliance,
        "need_by": need_by_signal,
    }


class TriageEnricher(Protocol):
    """The AI enrichment seam (spec: single Claude call over the email-parse
    output). Returns refined process labels + a customer one-liner; the caller
    treats every field as optional and never lets it fabricate history."""

    async def enrich(self, core: dict[str, Any]) -> dict[str, Any]: ...


_registered: TriageEnricher | None = None


def register(enricher: TriageEnricher | None) -> None:
    """Install (or clear) the process-wide enricher — tests/``create_app``."""
    global _registered
    _registered = enricher


def resolve() -> TriageEnricher:
    """The enricher for the current process (registered, else from settings)."""
    if _registered is not None:
        return _registered
    return make_enricher(get_settings())


def make_enricher(settings: Settings) -> TriageEnricher:
    """Build the settings-configured enricher (reuses the Lens provider seam:
    same Claude account/model/EU routing, DECISIONS 2026-07-15)."""
    if settings.lens_provider != "anthropic":
        raise RuntimeError(f"Unknown LENS_PROVIDER {settings.lens_provider!r}")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — live triage enrichment needs it.")
    return AnthropicTriageEnricher(
        api_key=settings.anthropic_api_key,
        model=settings.lens_model,
        inference_geo=settings.lens_inference_geo or None,
    )


_ENRICH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "detected_processes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "likelihood": {"type": "string", "enum": ["likely", "possible"]},
                },
                "required": ["name", "likelihood"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["detected_processes"],
    "additionalProperties": False,
}


def _core_json(core: dict[str, Any]) -> str:
    return json.dumps(core, ensure_ascii=False)


_ENRICH_PROMPT = (
    f"[{TRIAGE_PROMPT_VERSION}] Du bist ein Fertigungs-Kalkulator. Leite aus den "
    "strukturierten RFQ-Signalen zusätzliche wahrscheinliche Fertigungsprozesse auf "
    "DEUTSCH ab. Gib NUR JSON zurück: `detected_processes` (Prozess-Labels aus "
    "Material-Stichworten und Dateitypen). Erfinde KEINE Werte, die nicht in den "
    "Signalen stehen. Kundenhistorie und Zeiten sind vorgegeben — nicht ableiten. "
    "Signale:\n"
)


class AnthropicTriageEnricher:
    """Text-only Claude enrichment (structured JSON), mirroring
    :class:`app.lens_provider.AnthropicLensProvider` (same ``inference_geo``
    routing; no PDF/print bytes are ever sent — only the derived text core)."""

    def __init__(self, *, api_key: str, model: str, inference_geo: str | None) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._inference_geo = inference_geo

    async def enrich(self, core: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 1024,
            "output_config": {"format": {"type": "json_schema", "schema": _ENRICH_SCHEMA}},
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": _ENRICH_PROMPT + _core_json(core)}],
                }
            ],
        }
        if self._inference_geo:
            params["inference_geo"] = self._inference_geo
        response = await self._client.messages.create(**params)
        if response.stop_reason == "refusal":
            raise LensProviderError("provider_refusal")
        if response.stop_reason == "max_tokens":
            raise LensProviderError("provider_truncated")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LensProviderError("provider_empty_response")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LensProviderError("provider_invalid_json") from exc
        if not isinstance(payload, dict):
            raise LensProviderError("provider_invalid_json")
        return payload


# --------------------------------------------------------------------------- #
# Orchestration: build the brief for one ingested quote, then the Celery task
# --------------------------------------------------------------------------- #


def _line_item_part_numbers(suggested: dict[str, Any] | None) -> list[str]:
    """Part numbers from the stored email-parse payload (``RequestForQuote.
    suggested_line_items``), preserving order and dropping blanks."""
    if not suggested:
        return []
    out: list[str] = []
    for item in suggested.get("items", []):
        pn = (item or {}).get("part_number")
        if isinstance(pn, str) and pn.strip():
            out.append(pn.strip())
    return out


async def build_triage_snapshot(
    session: Any,
    *,
    org_id: uuid.UUID,
    quote_id: uuid.UUID,
    now: datetime,
) -> dict[str, Any] | None:
    """Gather the **deterministic** triage snapshot — reads only, **no AI call**.

    Reads the quote, its RFQ (``rfq.quote_id == quote_id``), the received files
    (``part_file.rfq_id``), and the account history — all within the caller's
    org-scoped session. Returns a snapshot dict (deterministic fields + the AI
    gating decision + the ``core`` passed to enrichment), or ``None`` when the
    quote is gone. The LLM enrichment runs **outside** this session (the M3.4
    pool-exhaustion lesson), so this function must not touch the provider."""
    from .ai_settings import get_ai_flags
    from .models import Account, Part, PartFile, Quote, RequestForQuote

    quote = await session.get(Quote, quote_id)
    if quote is None:
        return None

    rfq = (
        await session.scalars(select(RequestForQuote).where(RequestForQuote.quote_id == quote_id))
    ).first()
    body_text = ""
    requested_date: Any = quote.due_date
    export_controlled = False
    received_parts = 0
    if rfq is not None:
        body_text = f"{rfq.subject or ''}\n{rfq.description or ''}"
        requested_date = rfq.requested_delivery_date or requested_date
        export_controlled = bool(rfq.export_controlled)
        filenames = list(
            (
                await session.scalars(select(PartFile.filename).where(PartFile.rfq_id == rfq.id))
            ).all()
        )
        part_numbers = _line_item_part_numbers(rfq.suggested_line_items)
        # Count PARTS, not attachments: a bundled STEP+PDF is one part (spec
        # "7 parts · 5 STEP + 3 PDF" — parts and files are distinct signals).
        received_parts = (
            await session.scalar(
                select(func.count(func.distinct(PartFile.part_id))).where(PartFile.rfq_id == rfq.id)
            )
        ) or 0
        # Any export-controlled part also gates the AI call — parts link to the
        # RFQ through their files (``part_file.rfq_id``), so join across.
        if not export_controlled:
            export_controlled = bool(
                (
                    await session.scalars(
                        select(Part.id)
                        .join(PartFile, PartFile.part_id == Part.id)
                        .where(PartFile.rfq_id == rfq.id, Part.export_controlled.is_(True))
                    )
                ).first()
            )
    else:
        filenames = []
        part_numbers = []

    files = summarize_files(filenames)
    part_count = max(len(part_numbers), int(received_parts))
    missing = detect_missing_files(part_numbers, filenames)
    processes = detect_processes(filenames, body_text)
    est_time = estimate_time_to_quote(part_count, processes)
    compliance = scan_compliance(body_text, export_controlled)
    need_by_signal = need_by(requested_date, now)

    # Customer known/new (deterministic; full brief is send-time, M5).
    known = False
    name: str | None = None
    prior_quotes = 0
    if quote.account_id is not None:
        account = await session.get(Account, quote.account_id)
        name = account.name if account is not None else None
        prior_quotes = (
            await session.scalar(
                select(func.count())
                .select_from(Quote)
                .where(Quote.account_id == quote.account_id, Quote.id != quote_id)
            )
        ) or 0
        known = prior_quotes > 0
    customer = {
        "known": known,
        "name": name,
        "prior_quotes": int(prior_quotes),
        "one_liner": customer_line(known, name, int(prior_quotes)),
    }

    # Gate the AI enrichment (spec #ai-settings; DECISIONS 2026-07-15).
    flags = await get_ai_flags(session, org_id)
    if not flags.master_enabled:
        ai_reason = "master_disabled"
    elif not flags.triage_brief_enabled:
        ai_reason = "triage_disabled"
    elif export_controlled:
        ai_reason = "export_controlled"
        # M6.9: make the refusal evidential. The spec states the rule absolutely
        # ("CUI/ITAR-flagged files are always skipped regardless of the toggle"),
        # so the compliance log has to show the skips, not just claim them.
        # Subject is the RFQ when there is one — that is what carries the flag or
        # joins to the flagged parts — else the quote.
        await record_ai_skip(
            session,
            org_id=org_id,
            subject_type=(
                ExportControlSubject.request_for_quote
                if rfq is not None
                else ExportControlSubject.quote
            ),
            subject_id=rfq.id if rfq is not None else quote_id,
            route="triage.brief",
        )
    else:
        ai_reason = "ok"

    return {
        "ai_reason": ai_reason,
        "part_count": part_count,
        "files": files,
        "missing": missing,
        "processes": processes,
        "est_time": est_time,
        "customer": customer,
        "compliance": compliance,
        "need_by_signal": need_by_signal,
        # The read-only input handed to the LLM (no print bytes — text only).
        "core": {
            "parts_count": part_count,
            "files": files,
            "missing_files": missing,
            "detected_processes": processes,
            "compliance_flags": compliance,
            "need_by": need_by_signal,
        },
    }


def _family_for(label: str) -> str:
    """Best-effort family for an AI-provided process label (only affects the
    display grouping — est-time already used the deterministic families)."""
    for pattern, family, _ in _MATERIAL_PROCESS_HINTS:
        if pattern.search(label):
            return family
    return "unknown"


def _merge_ai_processes(
    deterministic: list[dict[str, Any]], enriched: dict[str, Any]
) -> list[dict[str, Any]]:
    """Merge AI-inferred process hints onto the deterministic list **without
    dropping any deterministic fact** (never-hallucinate): every deterministic
    process is kept; an AI process whose name isn't already present is appended
    as an advisory ``source: "ai"`` entry."""
    merged = list(deterministic)
    seen = {p.get("name", "").casefold() for p in merged}
    ep = enriched.get("detected_processes")
    if isinstance(ep, list):
        for p in ep:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name", "")).strip()
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            merged.append(
                {
                    "family": _family_for(name),
                    "name": name,
                    "likelihood": p.get("likelihood", "possible"),
                    "source": "ai",
                }
            )
    return merged


async def run_generate_triage_brief(
    db_url: str, *, org_id: uuid.UUID, quote_id: uuid.UUID
) -> dict[str, Any]:
    """Task core — idempotent: overwrites ``quote.triage_brief`` with a fresh
    build (deterministic core is stable; the AI enrichment is advisory).

    Three phases with the external LLM call **between** two short transactions,
    never inside one — a degraded provider must not hold a pooled connection
    (the M3.4 pool-exhaustion lesson): (1) read the deterministic snapshot,
    (2) enrich outside any session, (3) write the assembled brief."""
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        now = datetime.now(UTC)

        # Phase 1 — deterministic snapshot (read-only, short txn).
        async with org_scoped_session(sessionmaker, org_id) as session:
            snap = await build_triage_snapshot(session, org_id=org_id, quote_id=quote_id, now=now)
        if snap is None:
            return {"failed": True, "error_code": "quote_gone"}

        # Phase 2 — AI enrichment OUTSIDE any DB session. Deterministic facts
        # (customer one-liner, est-time, compliance, deterministic processes)
        # are never overwritten by the model; AI only *adds* process hints.
        ai_reason = snap["ai_reason"]
        processes = snap["processes"]
        if ai_reason == "ok":
            try:
                enriched = await resolve().enrich(snap["core"])
            except (LensProviderError, RuntimeError, AttributeError) as exc:
                code = exc.code if isinstance(exc, LensProviderError) else "provider_unavailable"
                logger.info("triage_enrich_skipped", extra={"code": code})
                ai_reason = f"error:{code}"
            else:
                processes = _merge_ai_processes(snap["processes"], enriched)

        brief = assemble_brief(
            now=now,
            ai_reason=ai_reason,
            part_count=snap["part_count"],
            files=snap["files"],
            missing=snap["missing"],
            processes=processes,
            est_time=snap["est_time"],
            customer=snap["customer"],
            compliance=snap["compliance"],
            need_by_signal=snap["need_by_signal"],
        )

        # Phase 3 — persist (short txn). The brief is a triage-time signal for a
        # *new* RFQ; re-validate under the row lock that the quote is still an
        # unstarted draft, so a quote opened/sent between the snapshot and now
        # (variable AI latency) is never overwritten with a stale brief.
        from .models import Quote, QuoteStatus

        async with org_scoped_session(sessionmaker, org_id) as session:
            quote = await session.get(Quote, quote_id, with_for_update=True)
            if quote is None:
                return {"failed": True, "error_code": "quote_gone"}
            if quote.status != QuoteStatus.draft:
                return {"skipped": "not_draft", "ai": brief["ai"]["reason"]}
            quote.triage_brief = brief
        return {
            "ok": True,
            "ai": brief["ai"]["reason"],
            "compliance": len(brief["compliance_flags"]),
            "missing": len(brief["missing_files"]),
        }
    finally:
        await engine.dispose()


async def find_rerun_target(session: Any, part_id: uuid.UUID) -> uuid.UUID | None:
    """The quote to re-brief when a file is added to ``part_id``, or ``None``.

    Spec: "re-runs if new files are added **before any estimator opens it**."
    A file is tied to a quote through its RFQ (``part_file.rfq_id`` ->
    ``rfq.quote_id``); the re-run is gated on the quote still being an *unopened*
    draft — ``started_at IS NULL`` is the "estimator begins work" heuristic
    (DECISIONS 2026-06-25), so once work starts the brief freezes."""
    from .models import PartFile, Quote, QuoteStatus, RequestForQuote

    quote_id = (
        await session.scalars(
            select(RequestForQuote.quote_id)
            .join(PartFile, PartFile.rfq_id == RequestForQuote.id)
            .where(PartFile.part_id == part_id, RequestForQuote.quote_id.is_not(None))
        )
    ).first()
    if quote_id is None:
        return None
    quote = await session.get(Quote, quote_id)
    if quote is None or quote.status != QuoteStatus.draft or quote.started_at is not None:
        return None
    return cast("uuid.UUID", quote_id)


def enqueue_triage_brief(org_id: uuid.UUID, quote_id: uuid.UUID) -> None:
    """Fire-and-forget enqueue seam (post-commit; never raises) — mirrors
    ``email_ingest._enqueue_body_parse``."""
    try:
        generate_triage_brief_task.delay(str(org_id), str(quote_id))
    except Exception:  # pragma: no cover - broker hiccup must not fail caller
        logger.warning("triage_enqueue_failed", extra={"quote_id": str(quote_id)})


@celery_app.task(
    base=BaseTask,
    name="app.generate_triage_brief",
    bind=True,
    soft_time_limit=120,
    time_limit=180,
)
def generate_triage_brief_task(self: Any, org_id: str, quote_id: str) -> dict[str, Any]:
    """Chains after the email-parse job; caches the brief on the quote (§5)."""
    binding = {"org_id": org_id, "quote_id": quote_id}
    task_id = self.request.id
    # Redelivery guard (M3.1 precedent): worker died after commit, before ack.
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    from .task_resources import resolve as resolve_task_resources

    db_url, _storage = resolve_task_resources()
    result = _run_on_own_loop(
        run_generate_triage_brief(db_url, org_id=uuid.UUID(org_id), quote_id=uuid.UUID(quote_id))
    )
    out = cast("dict[str, Any]", result)
    logger.info("triage_brief_generated", extra={"task_id": task_id, **out, **binding})
    return {**out, **binding}
