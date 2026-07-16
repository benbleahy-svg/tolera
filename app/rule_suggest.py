"""Rule Auto-Suggestion — AI Feature 2 (spec ``#ai-rule-suggest``; M3.10).

Governing question: *"Is there tribal knowledge I'm applying manually that
should be a rule?"*

Design — a **deterministic detector** + a **gated, purely-cosmetic AI touch**:

* **Pattern detection is a DB aggregate, never AI** (spec: "Pattern detection is
  a DB aggregate query"). :func:`detect_rule_suggestions` finds every operation
  that an estimator has *manually* added (``operation.added_manually``) to 3+
  distinct parts in the *same* process family + material class within the last
  90 days. This is what "the pattern query (not Claude) decides eligibility"
  means — the threshold is arithmetic and reproducible.
* **Claude only writes the human-readable sentence** (spec: "Claude only
  translates the detected pattern into a human-readable suggestion sentence and
  pre-seeds the rule dialog with a condition draft"). The pre-seed itself (rule
  name, operation, keyword condition) is deterministic; the sentence is enriched
  by Claude in the nightly scan and falls back to a deterministic German
  sentence when AI is off or errors. The on-add drawer path never calls Claude —
  it must be instant and can't hold a request on an LLM.

**The AI never creates a rule.** A suggestion only pre-seeds the Create Rule
dialog; the human clicks CREATE RULE (the human gate lives in M3.8's modal).

Everything is gated by ``org_ai_settings`` — ``master_enabled`` then
``rule_suggest_enabled`` (:pyattr:`app.ai_settings.AiFlags.rule_suggest_active`).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from celery.result import AsyncResult
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .ai_settings import get_ai_flags
from .celery_app import celery_app
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker, org_scoped_session
from .lens_extract import _run_on_own_loop
from .lens_provider import LensProviderError
from .models import (
    Component,
    Material,
    MaterialClass,
    MaterialFamily,
    Operation,
    OperationDef,
    Process,
    ProcessFamily,
    SuggestedAction,
    SuggestedActionKind,
    SuggestedActionStatus,
)
from .tasks import BaseTask

logger = logging.getLogger("app.rule_suggest")

#: Bump when the persisted ``payload`` shape changes (readers key off it).
RULE_SUGGEST_VERSION = 1
#: Versioned prompt id (repeatability; M3.11 eval-harness alignment).
RULE_SUGGEST_PROMPT_VERSION = "rule-suggest-v1"

#: Spec: "3+ parts ... in the last 90 days".
DEFAULT_THRESHOLD = 3
DEFAULT_WINDOW_DAYS = 90

#: German process-family labels for the suggestion copy (German-first UI). Falls
#: back to the enum value for any family not listed.
_FAMILY_LABELS_DE: dict[ProcessFamily, str] = {
    ProcessFamily.SHEET_METAL: "Blech",
    ProcessFamily.MILLING: "Fräs",
    ProcessFamily.LATHE: "Dreh",
    ProcessFamily.TUBE_LASER: "Rohrlaser",
    ProcessFamily.WIRE_EDM: "Drahterodier",
    ProcessFamily.CAST_URETHANE: "Urethanguss",
    ProcessFamily.ADDITIVE: "additiv gefertigte",
    ProcessFamily.ASSEMBLY: "Baugruppen",
    ProcessFamily.GENERIC: "",
}


@dataclasses.dataclass(frozen=True, slots=True)
class RuleSuggestionPattern:
    """One detected pattern: an operation an estimator keeps hand-adding to
    parts of one process family + material class."""

    operation_def_id: uuid.UUID
    operation_name: str
    process_family: ProcessFamily
    material_class_id: uuid.UUID
    material_class_name: str
    part_count: int

    @property
    def dedup_key(self) -> str:
        """Stable identity of the pattern — one open suggestion per pattern/org."""
        return (
            f"{SuggestedActionKind.rule_suggestion.value}:"
            f"{self.operation_def_id}:{self.process_family.value}:{self.material_class_id}"
        )


def _family_label(family: ProcessFamily) -> str:
    return _FAMILY_LABELS_DE.get(family, family.value)


async def detect_rule_suggestions(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    now: datetime | None = None,
    operation_def_id: uuid.UUID | None = None,
    threshold: int = DEFAULT_THRESHOLD,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[RuleSuggestionPattern]:
    """Every (operation, process family, material class) an estimator has
    *manually* added to ``threshold``+ distinct parts within ``window_days``.

    Deterministic and AI-free. Inner joins exclude components with no process or
    material — a pattern needs both to say "same family + material class". Counts
    **distinct components** (parts), so duplicating an op on one part never
    inflates the count. ``operation_def_id`` narrows to a single operation (the
    on-add drawer probe)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=window_days)
    part_count = func.count(func.distinct(Operation.component_id))
    stmt = (
        select(
            Operation.operation_def_id,
            OperationDef.name.label("operation_name"),
            Process.family.label("process_family"),
            MaterialClass.id.label("material_class_id"),
            MaterialClass.name.label("material_class_name"),
            part_count.label("part_count"),
        )
        .join(Component, Component.id == Operation.component_id)
        .join(Process, Process.id == Component.process_id)
        .join(Material, Material.id == Component.material_id)
        .join(MaterialFamily, MaterialFamily.id == Material.family_id)
        .join(MaterialClass, MaterialClass.id == MaterialFamily.class_id)
        .join(OperationDef, OperationDef.id == Operation.operation_def_id)
        .where(
            Operation.org_id == org_id,
            Operation.added_manually.is_(True),
            Operation.operation_def_id.is_not(None),
            Operation.created_at >= cutoff,
        )
        .group_by(
            Operation.operation_def_id,
            OperationDef.name,
            Process.family,
            MaterialClass.id,
            MaterialClass.name,
        )
        .having(part_count >= threshold)
    )
    if operation_def_id is not None:
        stmt = stmt.where(Operation.operation_def_id == operation_def_id)

    rows = (await session.execute(stmt)).all()
    return [
        RuleSuggestionPattern(
            operation_def_id=row.operation_def_id,
            operation_name=row.operation_name,
            process_family=ProcessFamily(row.process_family),
            material_class_id=row.material_class_id,
            material_class_name=row.material_class_name,
            part_count=row.part_count,
        )
        for row in rows
    ]


def deterministic_sentence(pattern: RuleSuggestionPattern) -> str:
    """The AI-free suggestion copy (German-first). Used on the instant drawer
    path and as the fallback whenever the Claude sentence is unavailable."""
    label = _family_label(pattern.process_family)
    teile = f"{label}-Teilen" if label else "Teilen"
    return (
        f"„{pattern.operation_name}“ wurde in den letzten {DEFAULT_WINDOW_DAYS} Tagen "
        f"manuell zu {pattern.part_count} {teile} aus {pattern.material_class_name} "
        "hinzugefügt. Als Regel automatisieren?"
    )


def build_payload(pattern: RuleSuggestionPattern, *, sentence: str) -> dict[str, Any]:
    """The persisted ``suggested_action.payload``: the human sentence plus the
    deterministic pre-seed the Create Rule dialog opens with (spec: "pre-seeds
    the rule dialog with a condition draft" — signal name, operation, likely
    condition). The keyword condition is the material-class name, a text-signal
    draft the human refines."""
    label = _family_label(pattern.process_family)
    teile = f"{label}-Teile" if label else "Teile"
    rule_name = f"{pattern.operation_name} für {teile} aus {pattern.material_class_name}"
    return {
        "version": RULE_SUGGEST_VERSION,
        "sentence": sentence,
        "pattern": {
            "operation_def_id": str(pattern.operation_def_id),
            "operation_name": pattern.operation_name,
            "process_family": pattern.process_family.value,
            "material_class_id": str(pattern.material_class_id),
            "material_class": pattern.material_class_name,
            "part_count": pattern.part_count,
        },
        # The pre-seed for M3.8's Create Rule modal. Deterministic; the human
        # edits it before CREATE RULE. No rule is created here.
        "rule_draft": {
            "name": rule_name,
            "description": sentence,
            "operation_def_id": str(pattern.operation_def_id),
            "operation_name": pattern.operation_name,
            "process_family": pattern.process_family.value,
            "material_class": pattern.material_class_name,
            "keyword": pattern.material_class_name,
        },
    }


async def upsert_suggestion(
    session: AsyncSession,
    org_id: uuid.UUID,
    pattern: RuleSuggestionPattern,
    *,
    sentence: str,
) -> None:
    """Idempotently record one open suggestion per pattern (spec: "surfaces via
    the existing ``SuggestedAction`` mechanism").

    ``ON CONFLICT (org_id, dedup_key)`` refreshes an existing **open** row's
    payload; a *dismissed* row is left untouched (the ``WHERE status='open'``
    guard) so a waved-away suggestion is never re-nagged."""
    payload = build_payload(pattern, sentence=sentence)
    stmt = (
        pg_insert(SuggestedAction)
        .values(
            org_id=org_id,
            kind=SuggestedActionKind.rule_suggestion.value,
            status=SuggestedActionStatus.open.value,
            dedup_key=pattern.dedup_key,
            operation_def_id=pattern.operation_def_id,
            payload=payload,
        )
        .on_conflict_do_update(
            constraint="uq_suggested_action_dedup",
            set_={"payload": payload, "updated_at": func.now()},
            where=SuggestedAction.status == SuggestedActionStatus.open.value,
        )
    )
    await session.execute(stmt)


# --------------------------------------------------------------------------- #
# On-add drawer probe (instant, AI-free)
# --------------------------------------------------------------------------- #
async def suggestion_for_component(
    session: AsyncSession,
    org_id: uuid.UUID,
    component: Component,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """The chip shown in the operation drawer right after a manual add.

    Gated by ``rule_suggest_active``. Runs the pure-DB detector for the
    component's own process family + material class, upserts any patterns (so
    they also reach the dashboard strip), and returns the pattern that involves
    *this* component — or ``None``. Never calls Claude (the request path must be
    instant); the sentence is deterministic here."""
    flags = await get_ai_flags(session, org_id)
    if not flags.rule_suggest_active:
        return None
    if component.process_id is None or component.material_id is None:
        return None

    patterns = await detect_rule_suggestions(session, org_id, now=now)
    if not patterns:
        return None

    # The op_defs manually present on THIS component — the ones the estimator
    # just touched — restrict which pattern the drawer surfaces.
    op_def_ids = set(
        (
            await session.execute(
                select(Operation.operation_def_id).where(
                    Operation.component_id == component.id,
                    Operation.added_manually.is_(True),
                    Operation.operation_def_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    class_id = await _material_class_id(session, component.material_id)
    family = await _process_family(session, component.process_id)

    match: RuleSuggestionPattern | None = None
    for pattern in patterns:
        await upsert_suggestion(session, org_id, pattern, sentence=deterministic_sentence(pattern))
        if (
            match is None
            and pattern.operation_def_id in op_def_ids
            and pattern.process_family == family
            and pattern.material_class_id == class_id
        ):
            match = pattern
    if match is None:
        return None
    # Surface from the *persisted* row so a dismissed suggestion never
    # reappears on the drawer (the upsert left a dismissed row untouched).
    row = await session.scalar(
        select(SuggestedAction).where(
            SuggestedAction.dedup_key == match.dedup_key,
            SuggestedAction.status == SuggestedActionStatus.open.value,
        )
    )
    if row is None:
        return None
    # Carry the row id so the drawer chip can dismiss/consume the *persisted*
    # suggestion (not just hide locally) — otherwise it re-nags on the dashboard
    # strip and a second CREATE RULE would import a duplicate rule.
    return {**row.payload, "suggested_action_id": str(row.id)}


async def _material_class_id(session: AsyncSession, material_id: uuid.UUID) -> uuid.UUID | None:
    class_id = await session.scalar(
        select(MaterialClass.id)
        .join(MaterialFamily, MaterialFamily.class_id == MaterialClass.id)
        .join(Material, Material.family_id == MaterialFamily.id)
        .where(Material.id == material_id)
    )
    return class_id


async def _process_family(session: AsyncSession, process_id: uuid.UUID) -> ProcessFamily | None:
    fam = await session.scalar(select(Process.family).where(Process.id == process_id))
    return ProcessFamily(fam) if fam is not None else None


# --------------------------------------------------------------------------- #
# AI enrichment seam (nightly scan only) — mirrors app.triage's enricher
# --------------------------------------------------------------------------- #
class RuleSuggestEnricher(Protocol):
    """The Claude seam: rewrite the deterministic facts into one natural German
    sentence. Cosmetic only — it never changes eligibility or the pre-seed."""

    async def suggest(self, facts: dict[str, Any]) -> dict[str, Any]: ...


_registered: RuleSuggestEnricher | None = None


def register(enricher: RuleSuggestEnricher | None) -> None:
    """Install (or clear) the process-wide enricher — tests/``create_app``."""
    global _registered
    _registered = enricher


def resolve() -> RuleSuggestEnricher:
    if _registered is not None:
        return _registered
    return make_enricher(get_settings())


def make_enricher(settings: Settings) -> RuleSuggestEnricher:
    """Build the settings-configured enricher (reuses the Lens provider seam:
    same Claude account/model/EU routing as triage — DECISIONS 2026-07-15)."""
    if settings.lens_provider != "anthropic":
        raise RuntimeError(f"Unknown LENS_PROVIDER {settings.lens_provider!r}")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — live rule-suggest enrichment needs it.")
    return AnthropicRuleSuggestEnricher(
        api_key=settings.anthropic_api_key,
        model=settings.lens_model,
        inference_geo=settings.lens_inference_geo or None,
    )


_SUGGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"sentence": {"type": "string"}},
    "required": ["sentence"],
    "additionalProperties": False,
}

_SUGGEST_PROMPT = (
    f"[{RULE_SUGGEST_PROMPT_VERSION}] Du bist ein Fertigungs-Kalkulator. Formuliere aus "
    "den strukturierten Fakten EINEN kurzen, natürlichen deutschen Satz, der dem "
    "Kalkulator vorschlägt, aus einem wiederholt manuell hinzugefügten Arbeitsgang eine "
    "Regel zu machen. Gib NUR JSON zurück: `sentence`. Erfinde KEINE Zahlen oder Fakten, "
    "die nicht in den Fakten stehen. Fakten:\n"
)


class AnthropicRuleSuggestEnricher:
    """Text-only Claude call (structured JSON), mirroring
    :class:`app.triage.AnthropicTriageEnricher` — only the derived facts are
    sent, never any file bytes."""

    def __init__(self, *, api_key: str, model: str, inference_geo: str | None) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._inference_geo = inference_geo

    async def suggest(self, facts: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 512,
            "output_config": {"format": {"type": "json_schema", "schema": _SUGGEST_SCHEMA}},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _SUGGEST_PROMPT + json.dumps(facts, ensure_ascii=False),
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
        text_block = next((b.text for b in response.content if b.type == "text"), None)
        if text_block is None:
            raise LensProviderError("provider_empty_response")
        try:
            payload = json.loads(text_block)
        except json.JSONDecodeError as exc:
            raise LensProviderError("provider_invalid_json") from exc
        if not isinstance(payload, dict):
            raise LensProviderError("provider_invalid_json")
        return payload


async def _enriched_sentence(pattern: RuleSuggestionPattern) -> str:
    """The Claude sentence, or the deterministic one on any failure (the AI
    touch is advisory — a degraded provider never blocks a suggestion)."""
    fallback = deterministic_sentence(pattern)
    try:
        out = await resolve().suggest(
            {
                "operation": pattern.operation_name,
                "process_family": pattern.process_family.value,
                "material_class": pattern.material_class_name,
                "part_count": pattern.part_count,
                "window_days": DEFAULT_WINDOW_DAYS,
            }
        )
    except (LensProviderError, RuntimeError, AttributeError) as exc:
        code = exc.code if isinstance(exc, LensProviderError) else "provider_unavailable"
        logger.info("rule_suggest_enrich_skipped", extra={"code": code})
        return fallback
    sentence = out.get("sentence")
    return sentence.strip() if isinstance(sentence, str) and sentence.strip() else fallback


# --------------------------------------------------------------------------- #
# Nightly scan (Celery beat) — dashboard suggested-actions strip
# --------------------------------------------------------------------------- #
async def run_scan_org(
    db_url: str, *, org_id: uuid.UUID, now: datetime | None = None
) -> dict[str, Any]:
    """Scan one org: detect patterns, enrich each sentence via Claude (outside
    any DB session — the M3.4 pool-exhaustion posture), upsert. Idempotent."""
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        stamp = now or datetime.now(UTC)

        # Phase 1 — gate + detect (short read txn).
        async with org_scoped_session(sessionmaker, org_id) as session:
            flags = await get_ai_flags(session, org_id)
            if not flags.rule_suggest_active:
                return {"skipped": "ai_disabled", "org_id": str(org_id)}
            patterns = await detect_rule_suggestions(session, org_id, now=stamp)
        if not patterns:
            return {"suggestions": 0, "org_id": str(org_id)}

        # Phase 2 — AI enrichment OUTSIDE any DB session.
        sentences = [await _enriched_sentence(p) for p in patterns]

        # Phase 3 — upsert (short write txn).
        async with org_scoped_session(sessionmaker, org_id) as session:
            for pattern, sentence in zip(patterns, sentences, strict=True):
                await upsert_suggestion(session, org_id, pattern, sentence=sentence)
        return {"suggestions": len(patterns), "org_id": str(org_id)}
    finally:
        await engine.dispose()


async def _list_scan_org_ids(db_url: str) -> list[uuid.UUID]:
    """Cross-org id enumeration via the SECURITY DEFINER ``list_scan_org_ids``
    (the ``list_email_sync_targets`` precedent, 0024) — the beat fan-out has no
    org context, and every domain read then happens org-scoped."""
    engine = make_engine(db_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        async with sessionmaker() as session:
            rows = await session.execute(text("SELECT org_id FROM list_scan_org_ids()"))
            return [row[0] for row in rows]
    finally:
        await engine.dispose()


@celery_app.task(
    base=BaseTask,
    name="app.scan_rule_suggestions",
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def scan_rule_suggestions_task(self: Any) -> dict[str, Any]:
    """Nightly beat entry point: fan out one scan per org (spec: "Nightly Celery
    job scans for patterns per org")."""
    task_id = self.request.id
    if task_id is not None:
        prior = AsyncResult(task_id, app=celery_app)
        if prior.state == "SUCCESS" and isinstance(prior.result, dict):
            return cast("dict[str, Any]", prior.result)
    from .task_resources import resolve as resolve_task_resources

    db_url, _storage = resolve_task_resources()
    org_ids = _run_on_own_loop(_list_scan_org_ids(db_url))
    total = 0
    for org_id in org_ids:
        result = cast("dict[str, Any]", _run_on_own_loop(run_scan_org(db_url, org_id=org_id)))
        total += int(result.get("suggestions", 0))
    logger.info("rule_suggest_scan", extra={"orgs": len(org_ids), "suggestions": total})
    return {"orgs": len(org_ids), "suggestions": total}
