"""M4.12 — AI: Requote Diff Assistant (spec ``#ai-requote-diff``).

"What changed between this revision and the last time I quoted this part?"

When a part on a draft quote has a Part-Library **Exact File / Exact
Geometric** match (M4.11) with a prior quote, a Celery job computes a
``DiffResult`` — geometry delta (OCCT stats subtraction over the persisted
``PartGeometry.raw``) + ``ExtractionFinding`` set-diff — caches it as
``quote.requote_diff`` JSONB, and Claude writes ONE synthesis paragraph over
the **structured diff JSON** (never raw files; AI-LENS discipline).

Everything downstream of the diff is a **suggestion** behind the AI-Governor
explicit-accept gate: the three-choice banner (Import router from Rev A /
Review field-by-field / Start fresh) copies **nothing** without a click — the
import itself is the existing ``POST /components/{id}/import-router``.

Deterministic vs AI (the M4.13 contract): ``geometry_delta.significant`` and
``finding_diff.material_changes`` are computed HERE, deterministically —
M4.13's server-side Accept-All suppression reads them and must never depend
on LLM output. The synthesis paragraph is advisory display copy only.

Orchestration mirrors M3.9 (``app.triage``): snapshot txn → LLM call outside
any DB session → persist under row-lock; provider failure degrades to the
deterministic diff with ``ai.reason = error:<code>``.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, cast

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .celery_app import celery_app
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker, org_scoped_session
from .deps import get_session
from .errors import AppError
from .lens_provider import LensProviderError
from .models import (
    Component,
    ExtractionFinding,
    FindingStatus,
    Part,
    PartFile,
    PartGeometry,
    Quote,
    QuoteItem,
    QuoteStatus,
    RequestForQuote,
)
from .part_library import _live_other_parts, _parts_with_file_key, _subject_keys
from .tasks import BaseTask

logger = logging.getLogger(__name__)

REQUOTE_DIFF_VERSION = "rqd-1"
REQUOTE_PROMPT_VERSION = "rqd-prompt-1"

#: Deterministic significance thresholds for ``geometry_delta.significant``
#: (consumed by M4.13's server-side Accept-All gate). ASSUMED defaults — the
#: spec is silent; tune here, the values travel inside the cached JSONB.
VOLUME_SIGNIFICANT_PCT = 5.0
BBOX_SIGNIFICANT_MM = 1.0

#: Finding types whose change is always material (a different Werkstoff or
#: surface spec invalidates the prior router/pricing).
_MATERIAL_TYPES = {"material", "finish", "coating"}

#: Fields compared for the changed/unchanged verdict on a finding pair.
#: ``category`` is included so a category-only transition (e.g. a note
#: reclassified into ``requirements``) surfaces as a change, not a no-op.
_COMPARE_FIELDS = ("normalized_value", "value", "tolerance", "gdt", "units", "category")

requote_router = APIRouter(prefix="/api/quotes", tags=["requote-diff"])


# --------------------------------------------------------------------------- #
# Geometry delta — pure functions over the persisted AnalysisResult dicts
# --------------------------------------------------------------------------- #


def _feature_counts(raw: dict[str, Any]) -> dict[str, int]:
    """Per-name feature counts + integer ``*_count`` family scalars (bend/
    pierce…), kept under their own keys so the panel shows the same numbers
    the recognizers produced (no gv1-style merging)."""
    counts: dict[str, int] = {}
    for feature in raw.get("features") or []:
        name = str(feature.get("name") or "feature")
        counts[name] = counts.get(name, 0) + 1
    for key, value in (raw.get("family_scalars") or {}).items():
        if not key.endswith("_count"):
            continue
        try:
            counts[key] = counts.get(key, 0) + int(value or 0)
        except (TypeError, ValueError):
            continue
    return counts


def geometry_delta(raw_a: dict[str, Any] | None, raw_b: dict[str, Any] | None) -> dict[str, Any]:
    """OCCT stats subtraction (a = baseline revision, b = new revision).

    ``available: False`` when either side has no interrogation result (a
    PDF-only part) — ``significant`` stays False: an exact-file match means
    byte-identical inputs, and there is nothing to subtract."""
    dims_a = (raw_a or {}).get("dimensions") or {}
    dims_b = (raw_b or {}).get("dimensions") or {}
    vol_a, vol_b = dims_a.get("volume"), dims_b.get("volume")
    if raw_a is None or raw_b is None or not vol_a or not vol_b:
        return {"available": False, "significant": False}

    delta_pct = (float(vol_b) - float(vol_a)) / float(vol_a) * 100.0
    bbox: dict[str, Any] = {}
    bbox_significant = False
    for key in ("size_x", "size_y", "size_z"):
        a, b = float(dims_a.get(key) or 0.0), float(dims_b.get(key) or 0.0)
        delta = b - a
        bbox[key] = {"a": a, "b": b, "delta": round(delta, 3)}
        if abs(delta) > BBOX_SIGNIFICANT_MM:
            bbox_significant = True

    counts_a = _feature_counts(raw_a)
    counts_b = _feature_counts(raw_b)
    features: dict[str, Any] = {}
    features_changed = False
    for name in sorted(set(counts_a) | set(counts_b)):
        a_count, b_count = counts_a.get(name, 0), counts_b.get(name, 0)
        features[name] = {"a": a_count, "b": b_count, "delta": b_count - a_count}
        if a_count != b_count:
            features_changed = True

    return {
        "available": True,
        "significant": (
            abs(delta_pct) > VOLUME_SIGNIFICANT_PCT or bbox_significant or features_changed
        ),
        "volume": {"a": vol_a, "b": vol_b, "delta_pct": round(delta_pct, 2)},
        "bbox": bbox,
        "features": features,
    }


# --------------------------------------------------------------------------- #
# ExtractionFinding set-diff — pure functions over serialized findings
# --------------------------------------------------------------------------- #


def _finding_key(finding: dict[str, Any]) -> tuple[str, str]:
    return (str(finding.get("type") or ""), str(finding.get("role") or ""))


def _fingerprint(finding: dict[str, Any]) -> str:
    return json.dumps({k: finding.get(k) for k in _COMPARE_FIELDS}, sort_keys=True)


def _unmatched(findings: list[dict[str, Any]], common: Counter[str]) -> list[dict[str, Any]]:
    """Drop findings whose fingerprint pairs off against the other side."""
    used: Counter[str] = Counter()
    rest: list[dict[str, Any]] = []
    for finding in findings:
        fp = _fingerprint(finding)
        if used[fp] < common[fp]:
            used[fp] += 1
            continue
        rest.append(finding)
    return rest


def _anchored(finding_a: dict[str, Any], finding_b: dict[str, Any], key: tuple[str, str]) -> bool:
    """A lone leftover pair reads as *the same callout, changed* only when it
    shares an identity anchor — a non-empty role (``bore_3``) or an equal
    normalized value. Two unrelated free-text notes are an add + a remove."""
    if key[1]:
        return True
    normalized = finding_a.get("normalized_value")
    return normalized is not None and normalized == finding_b.get("normalized_value")


def finding_diff(
    findings_a: list[dict[str, Any]], findings_b: list[dict[str, Any]]
) -> dict[str, Any]:
    """Set-diff of two serialized finding lists (a = baseline, b = new).

    Findings are grouped by ``(type, role)``; identical fingerprints pair off,
    a lone leftover on each side of a key is a **changed** finding, anything
    else is added/removed. ``material_changes`` is the deterministic
    classification M4.13's Accept-All gate consumes."""
    by_key_a: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_key_b: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for finding in findings_a:
        by_key_a.setdefault(_finding_key(finding), []).append(finding)
    for finding in findings_b:
        by_key_b.setdefault(_finding_key(finding), []).append(finding)

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for key in sorted(set(by_key_a) | set(by_key_b)):
        list_a = by_key_a.get(key, [])
        list_b = by_key_b.get(key, [])
        common = Counter(map(_fingerprint, list_a)) & Counter(map(_fingerprint, list_b))
        rest_a = _unmatched(list_a, common)
        rest_b = _unmatched(list_b, common)
        if len(rest_a) == 1 and len(rest_b) == 1 and _anchored(rest_a[0], rest_b[0], key):
            changes = [k for k in _COMPARE_FIELDS if rest_a[0].get(k) != rest_b[0].get(k)]
            changed.append(
                {
                    "key": {"type": key[0], "role": key[1] or None},
                    "a": rest_a[0],
                    "b": rest_b[0],
                    "changes": changes,
                }
            )
        else:
            removed.extend(rest_a)
            added.extend(rest_b)

    material: list[dict[str, Any]] = []
    for kind, findings in (("added", added), ("removed", removed)):
        for finding in findings:
            if str(finding.get("type") or "") in _MATERIAL_TYPES:
                material.append({"kind": kind, "reason": "material_changed", "finding": finding})
            elif finding.get("category") == "requirements":
                material.append(
                    {"kind": kind, "reason": f"requirements_{kind}", "finding": finding}
                )
    for entry in changed:
        if str(entry["b"].get("type") or "") in _MATERIAL_TYPES:
            material.append(
                {"kind": "changed", "reason": "material_changed", "finding": entry["b"]}
            )
        elif "tolerance" in entry["changes"]:
            material.append(
                {"kind": "changed", "reason": "tolerance_changed", "finding": entry["b"]}
            )
        elif "requirements" in (entry["a"].get("category"), entry["b"].get("category")):
            # Either direction is material: a callout becoming a requirement
            # AND a requirement being dropped both invalidate the prior router
            # review (M4.13's Accept-All must stay suppressed for both).
            material.append(
                {"kind": "changed", "reason": "requirements_changed", "finding": entry["b"]}
            )

    return {"added": added, "removed": removed, "changed": changed, "material_changes": material}


def _serialize_finding(finding: ExtractionFinding) -> dict[str, Any]:
    return {
        "type": finding.type,
        "category": finding.category.value,
        "role": finding.role,
        "value": finding.value,
        "normalized_value": finding.normalized_value,
        "units": finding.units,
        "tolerance": finding.tolerance,
        "gdt": finding.gdt,
    }


# --------------------------------------------------------------------------- #
# The AI synthesis seam (register/resolve — the M3.9 pattern)
# --------------------------------------------------------------------------- #


class RequoteSynthesizer(Protocol):
    """One Claude call over the structured diff JSON → one German paragraph
    labelling material vs cosmetic changes. Advisory only — never consulted
    for ``significant``/``material_changes``."""

    async def synthesize(self, diff: dict[str, Any]) -> dict[str, Any]: ...


_registered: RequoteSynthesizer | None = None


def register(synthesizer: RequoteSynthesizer | None) -> None:
    """Install (or clear) the process-wide synthesizer — tests/``create_app``."""
    global _registered
    _registered = synthesizer


def resolve() -> RequoteSynthesizer:
    if _registered is not None:
        return _registered
    return make_synthesizer(get_settings())


def make_synthesizer(settings: Settings) -> RequoteSynthesizer:
    """Settings-configured synthesizer (same Claude account/model/EU routing
    as Lens + Triage — DECISIONS 2026-07-15)."""
    if settings.lens_provider != "anthropic":
        raise RuntimeError(f"Unknown LENS_PROVIDER {settings.lens_provider!r}")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — live requote synthesis needs it.")
    return AnthropicRequoteSynthesizer(
        api_key=settings.anthropic_api_key,
        model=settings.lens_model,
        inference_geo=settings.lens_inference_geo or None,
    )


_SYNTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"synthesis": {"type": "string"}},
    "required": ["synthesis"],
    "additionalProperties": False,
}

_SYNTH_PROMPT = (
    f"[{REQUOTE_PROMPT_VERSION}] Du bist ein Fertigungs-Kalkulator. Ein Teil wird "
    "erneut angefragt; unten steht der strukturierte Diff zwischen der alten und der "
    "neuen Revision (Geometrie-Delta + Zeichnungsänderungen). Schreibe EINEN kurzen "
    "Absatz auf DEUTSCH: welche Änderungen sind fertigungsrelevant (Router/Preis "
    "prüfen), welche nur kosmetisch, und ob der bisherige Router voraussichtlich "
    "weiter gültig ist. Beziehe dich NUR auf Werte aus dem Diff — erfinde nichts. "
    "Gib NUR JSON zurück: `synthesis` (der Absatz). Diff:\n"
)


class AnthropicRequoteSynthesizer:
    """Text-only Claude call over the diff JSON (structured output), mirroring
    :class:`app.triage.AnthropicTriageEnricher` — no file bytes are ever sent."""

    def __init__(self, *, api_key: str, model: str, inference_geo: str | None) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._inference_geo = inference_geo

    async def synthesize(self, diff: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 1024,
            "output_config": {"format": {"type": "json_schema", "schema": _SYNTH_SCHEMA}},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _SYNTH_PROMPT + json.dumps(diff, ensure_ascii=False),
                        }
                    ],
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
# Snapshot: trigger conditions + baseline + deterministic diff (one read txn)
# --------------------------------------------------------------------------- #


async def _part_findings(session: AsyncSession, part_id: uuid.UUID) -> list[dict[str, Any]]:
    """All non-rejected findings across the part's files — the print as
    extracted; a rejected finding is one the estimator declared wrong."""
    rows = (
        await session.scalars(
            select(ExtractionFinding)
            .join(PartFile, PartFile.id == ExtractionFinding.source_file_id)
            .where(
                PartFile.part_id == part_id,
                ExtractionFinding.status != FindingStatus.rejected,
            )
            .order_by(ExtractionFinding.created_at)
        )
    ).all()
    return [_serialize_finding(f) for f in rows]


async def _find_baseline(
    session: AsyncSession, part: Part, *, target_quote: Quote
) -> dict[str, Any] | None:
    """The most recent chronologically-PRIOR quote of an Exact-File /
    Exact-Geometric matched part (exact_file preferred — byte-identical beats
    topology-identical). A quote created after the target is a *later*
    revision, never a requote baseline."""
    keys = await _subject_keys(session, part)
    exact_file = await _parts_with_file_key(session, part.id, PartFile.file_hash, keys["hashes"])
    exact_geometric: list[uuid.UUID] = []
    if part.geom_hash is not None:
        exact_geometric = list(
            await session.scalars(
                select(Part.id).where(Part.geom_hash == part.geom_hash, _live_other_parts(part.id))
            )
        )
    for match_type, candidate_ids in (
        ("exact_file", exact_file),
        ("exact_geometric", exact_geometric),
    ):
        if not candidate_ids:
            continue
        row = (
            await session.execute(
                select(Component.part_id, Component.id, Quote.id, Quote.number)
                .join(QuoteItem, QuoteItem.root_component_id == Component.id)
                .join(Quote, Quote.id == QuoteItem.quote_id)
                .where(
                    Component.part_id.in_(candidate_ids),
                    Quote.deleted_at.is_(None),
                    Quote.id != target_quote.id,
                    Quote.created_at <= target_quote.created_at,
                )
                # Total order: id/position break created_at ties so a re-run
                # always picks the same baseline (deterministic re-resolution).
                .order_by(
                    Quote.created_at.desc(),
                    Quote.id.desc(),
                    QuoteItem.position,
                    QuoteItem.id,
                )
            )
        ).first()
        if row is None:
            continue
        matched_part_id, component_id, quote_id, number = row
        matched = await session.get(Part, matched_part_id)
        if matched is None:
            continue
        return {
            "match_type": match_type,
            "part": matched,
            "component_id": component_id,
            "quote_id": quote_id,
            "quote_number": number,
        }
    return None


async def build_requote_snapshot(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    part_id: uuid.UUID,
    now: datetime,
    quote_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Everything the task needs in one read txn, or a skip verdict.

    Returns ``None`` when the part is gone; ``{"skipped": ...}`` when there is
    no quote / the quote left draft / no baseline; else ``{"quote_id",
    "ai_reason", "entry"}`` with the deterministic diff already computed."""
    part = await session.get(Part, part_id)
    if part is None or part.deleted_at is not None:
        return None

    # The manual refresh trigger names its quote; the interrogation-chained
    # trigger targets the part's most recent live quote.
    stmt = (
        select(Quote, Component.id)
        .join(QuoteItem, QuoteItem.quote_id == Quote.id)
        .join(Component, Component.id == QuoteItem.root_component_id)
        .where(Component.part_id == part_id, Quote.deleted_at.is_(None))
        .order_by(Quote.created_at.desc())
    )
    if quote_id is not None:
        stmt = stmt.where(Quote.id == quote_id)
    quote_row = (await session.execute(stmt)).first()
    if quote_row is None:
        return {"skipped": "no_quote"}
    quote, target_component_id = quote_row
    if quote.status != QuoteStatus.draft:
        return {"skipped": "not_draft"}

    baseline = await _find_baseline(session, part, target_quote=quote)
    if baseline is None:
        return {"skipped": "no_baseline"}
    matched = baseline["part"]

    raw_a = await session.scalar(
        select(PartGeometry.raw).where(PartGeometry.part_id == baseline["part"].id)
    )
    raw_b = await session.scalar(select(PartGeometry.raw).where(PartGeometry.part_id == part_id))
    diff = {
        "geometry_delta": geometry_delta(raw_a, raw_b),
        "finding_diff": finding_diff(
            await _part_findings(session, baseline["part"].id),
            await _part_findings(session, part_id),
        ),
    }

    # Gate the AI synthesis (spec #ai-settings; export path DECISIONS 2026-07-15:
    # a dual-use-flagged RFQ's print content never reaches any provider — the
    # finding diff carries extracted print values).
    from .ai_settings import get_ai_flags

    flags = await get_ai_flags(session, org_id)
    # The part-level dual-use flag on EITHER revision (the flag travels with
    # the part across quotes, DECISIONS 2026-06-26) OR an export-controlled RFQ
    # on EITHER quote — the diff payload carries extracted print values from
    # both revisions, so both sides' RFQs gate the external provider.
    export_controlled = (
        bool(part.export_controlled)
        or bool(matched.export_controlled)
        or bool(
            (
                await session.scalars(
                    select(RequestForQuote.id).where(
                        RequestForQuote.quote_id.in_([quote.id, baseline["quote_id"]]),
                        RequestForQuote.export_controlled.is_(True),
                    )
                )
            ).first()
        )
    )
    if not flags.master_enabled:
        ai_reason = "master_disabled"
    elif not flags.requote_diff_enabled:
        ai_reason = "requote_diff_disabled"
    elif export_controlled:
        ai_reason = "export_controlled"
    else:
        ai_reason = "ok"

    return {
        "quote_id": quote.id,
        "ai_reason": ai_reason,
        "entry": {
            "version": REQUOTE_DIFF_VERSION,
            "prompt_version": REQUOTE_PROMPT_VERSION,
            "generated_at": now.isoformat(),
            "part_id": str(part_id),
            "match_type": baseline["match_type"],
            "matched": {
                "part_id": str(matched.id),
                "part_number": matched.part_number,
                "revision": matched.revision,
                "quote_id": str(baseline["quote_id"]),
                "quote_number": baseline["quote_number"],
                "component_id": str(baseline["component_id"]),
            },
            "target_component_id": str(target_component_id),
            "diff": diff,
            "ai": None,
            "synthesis": None,
            "choice": None,
        },
    }


# --------------------------------------------------------------------------- #
# Task core + Celery wiring (the M3.9 three-phase shape)
# --------------------------------------------------------------------------- #


async def run_generate_requote_diff(
    db_url: str, *, org_id: uuid.UUID, part_id: uuid.UUID, quote_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Task core — idempotent: recomputing overwrites the part's entry (an
    already-recorded choice is preserved for the audit trail). Three phases,
    the LLM call strictly between two short transactions (M3.4 lesson)."""
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        now = datetime.now(UTC)

        async with org_scoped_session(sessionmaker, org_id) as session:
            snap = await build_requote_snapshot(
                session, org_id=org_id, part_id=part_id, now=now, quote_id=quote_id
            )
        if snap is None:
            return {"failed": True, "error_code": "part_gone"}
        if "skipped" in snap:
            return snap

        entry = snap["entry"]
        ai_reason = snap["ai_reason"]
        synthesis: str | None = None
        if ai_reason == "ok":
            try:
                out = await resolve().synthesize(entry["diff"])
            except (LensProviderError, RuntimeError, AttributeError) as exc:
                code = exc.code if isinstance(exc, LensProviderError) else "provider_unavailable"
                logger.info(
                    "requote_synthesis_skipped", extra={"code": code, "org_id": str(org_id)}
                )
                ai_reason = f"error:{code}"
            else:
                text = out.get("synthesis")
                synthesis = str(text).strip() or None if isinstance(text, str) else None
                if synthesis is None:
                    ai_reason = "error:provider_empty_response"
        entry["ai"] = {"enabled": ai_reason == "ok", "reason": ai_reason}
        entry["synthesis"] = synthesis

        # Persist under the row lock; the banner is estimating-time chrome, so
        # only a still-draft quote is written (a sent quote is frozen history).
        async with org_scoped_session(sessionmaker, org_id) as session:
            quote = await session.get(Quote, snap["quote_id"], with_for_update=True)
            if quote is None:
                return {"failed": True, "error_code": "quote_gone"}
            if quote.status != QuoteStatus.draft:
                return {"skipped": "not_draft"}
            cache = dict(quote.requote_diff or {})
            entries = dict(cache.get("entries") or {})
            prior = entries.get(entry["part_id"])
            if isinstance(prior, dict) and prior.get("choice"):
                entry["choice"] = prior["choice"]
            entries[entry["part_id"]] = entry
            quote.requote_diff = {"version": REQUOTE_DIFF_VERSION, "entries": entries}
        return {
            "ok": True,
            "quote_id": str(snap["quote_id"]),
            "match_type": entry["match_type"],
            "ai": ai_reason,
        }
    finally:
        await engine.dispose()


def enqueue_requote_diff(
    org_id: uuid.UUID, part_id: uuid.UUID, quote_id: uuid.UUID | None = None
) -> None:
    """Fire-and-forget enqueue seam (post-commit; never raises) — chained off
    interrogation success and the manual refresh endpoint (which pins its
    quote so the diff can't land on a different, newer quote)."""
    try:
        generate_requote_diff_task.delay(
            str(org_id), str(part_id), str(quote_id) if quote_id else None
        )
    except Exception:  # pragma: no cover - broker hiccup must not fail caller
        logger.warning("requote_diff_enqueue_failed", extra={"part_id": str(part_id)})


@celery_app.task(
    base=BaseTask,
    name="app.generate_requote_diff",
    bind=True,
    soft_time_limit=120,
    time_limit=180,
)
def generate_requote_diff_task(
    self: Any, org_id: str, part_id: str, quote_id: str | None = None
) -> dict[str, Any]:
    """Chains after interrogation success; caches the diff on the quote."""
    from .interrogation import _run_on_own_loop
    from .task_resources import resolve as resolve_task_resources

    binding = {"org_id": org_id, "part_id": part_id}
    task_id = self.request.id
    # Redelivery guard (M3.1 precedent): worker died after commit, before ack.
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    db_url, _storage = resolve_task_resources()
    result = _run_on_own_loop(
        run_generate_requote_diff(
            db_url,
            org_id=uuid.UUID(org_id),
            part_id=uuid.UUID(part_id),
            quote_id=uuid.UUID(quote_id) if quote_id else None,
        )
    )
    out = cast("dict[str, Any]", result)
    logger.info("requote_diff_generated", extra={"task_id": task_id, **out, **binding})
    return {**out, **binding}


# --------------------------------------------------------------------------- #
# API — read the cached diff; record the explicit choice; manual refresh
# --------------------------------------------------------------------------- #


async def _get_quote_or_404(session: AsyncSession, quote_id: uuid.UUID, **kw: Any) -> Quote:
    quote = await session.get(Quote, quote_id, **kw)
    if quote is None or quote.deleted_at is not None:
        raise AppError("not_found", "Quote not found.", status_code=status.HTTP_404_NOT_FOUND)
    return quote


def _entries_out(quote: Quote) -> dict[str, Any]:
    cache = quote.requote_diff or {}
    entries = cache.get("entries") or {}
    return {"entries": sorted(entries.values(), key=lambda e: str(e.get("part_id")))}


class RequoteChoiceIn(BaseModel):
    part_id: uuid.UUID
    choice: Literal["import_router", "review", "start_fresh"]


@requote_router.get("/{quote_id}/requote-diff")
async def get_requote_diff(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> dict[str, Any]:
    """The cached requote diff for the estimating banner/panel — empty list
    until the task has run (never a silent 404 for a real quote)."""
    quote = await _get_quote_or_404(session, quote_id)
    return _entries_out(quote)


@requote_router.post("/{quote_id}/requote-diff/choice")
async def record_requote_choice(
    quote_id: uuid.UUID,
    payload: RequoteChoiceIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, Any]:
    """Record the estimator's explicit choice (audit trail + dismissal). The
    router copy itself stays on ``POST /components/{id}/import-router`` — this
    endpoint never moves a value."""
    quote = await _get_quote_or_404(session, quote_id, with_for_update=True)
    if quote.status != QuoteStatus.draft:
        raise AppError(
            "quote_locked",
            "This quote is no longer a draft; the requote gate is frozen.",
            status_code=status.HTTP_409_CONFLICT,
        )
    cache = dict(quote.requote_diff or {})
    entries = dict(cache.get("entries") or {})
    entry = entries.get(str(payload.part_id))
    if entry is None:
        raise AppError(
            "no_requote_entry",
            "No requote diff exists for this part.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    entry = dict(entry)
    entry["choice"] = {
        "choice": payload.choice,
        "at": datetime.now(UTC).isoformat(),
        "user_id": str(principal.user_id),
    }
    entries[str(payload.part_id)] = entry
    quote.requote_diff = {**cache, "entries": entries}
    return _entries_out(quote)


@requote_router.post("/{quote_id}/requote-diff/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_requote_diff(
    quote_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> dict[str, Any]:
    """Manual trigger (spec trigger (c) — the Part Library match panel):
    re-enqueue the diff for every part on the quote. Frozen quotes are
    rejected up front — the task would skip them anyway, and a 202 "queued"
    answer for work that can never land would be a lie."""
    quote = await _get_quote_or_404(session, quote_id)
    if quote.status != QuoteStatus.draft:
        raise AppError(
            "quote_locked",
            "This quote is no longer a draft; the requote gate is frozen.",
            status_code=status.HTTP_409_CONFLICT,
        )
    part_ids = (
        await session.scalars(
            select(Component.part_id)
            .join(QuoteItem, QuoteItem.root_component_id == Component.id)
            .where(QuoteItem.quote_id == quote.id, Component.part_id.is_not(None))
            .distinct()
        )
    ).all()
    for part_id in part_ids:
        enqueue_requote_diff(principal.active_org_id, part_id, quote.id)
    return {"queued": len(part_ids)}
