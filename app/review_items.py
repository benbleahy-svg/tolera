"""Review items — matched rules become assignable, resolvable work (M3.8).

Spec ``#rules`` / ``#rules-lifecycle`` / ``#rules-resolutions``;
RULES-ENGINE-SPEC §3 (resolution catalogue) + §6 (lifecycle & collaboration).

This is where the rules engine stops being deterministic machinery and becomes
work an estimator does. M3.6 owns the AST, M3.7 evaluates it (pure, no DB);
this module is the wiring in between and the lifecycle on top:

* **Context** — :func:`build_context` assembles the component's analyzed data
  from DB rows into M3.7's :class:`EvaluationContext`.
* **Generation** — :func:`generate_for_component` evaluates the org's active
  rules and reconciles the resulting review items (§6.1).
* **Lifecycle** — assign + notify (§6.2), thread (§6.3), prior decisions
  (§6.4), resolve with effects (§3/§6.5), audit (§6.6).

**Resolutions are suggestions until applied** (spec ``#rules``: "Resolutions
are suggested one-click actions until applied"). Nothing here mutates a router
or a line item without an explicit human resolve call — the same posture the
Lens layer takes toward Kalk (CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import logging
import uuid as uuid_mod
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .auth import Principal
from .authz import Permission, require
from .celery_app import celery_app
from .costing import recalculate_component
from .db import org_scoped_session
from .deps import get_session
from .errors import AppError
from .file_types import FileCategory
from .models import (
    Channel,
    Component,
    ExtractionFinding,
    FindingStatus,
    MembershipStatus,
    Message,
    Notification,
    Operation,
    OperationDef,
    Part,
    PartFile,
    PartGeometry,
    Process,
    QiWorkflowStatus,
    QuoteItem,
    ResolutionType,
    ReviewItem,
    ReviewItemStatus,
    Rule,
    UserOrgMembership,
)
from .operations import attach_operation_from_def
from .rules_eval import EvaluationContext, evaluate_rules
from .rules_schema import Resolution, RuleSchema
from .task_resources import resolve as resolve_task_resources
from .tasks import BaseTask

logger = logging.getLogger(__name__)

review_items_router = APIRouter(prefix="/api", tags=["review-items"])

#: §6.4 — "show up to 5 past parts the rule flagged + the decision taken there".
PRIOR_DECISION_LIMIT = 5

#: Notification kind for §6.2's auto-assign + notify. ``notification.kind`` is a
#: bare text column (no enum/CHECK), so a new kind needs no migration.
NOTIFICATION_ASSIGNED = "review_item_assigned"

#: A part "has a model" if it carries solid/mesh geometry; a "print" is the
#: 2D document (``FileCategory`` collapses pdf/tif/png into ``document``).
#: RULES-ENGINE-SPEC §4: the ``files`` collection exposes has_model/has_print.
_MODEL_CATEGORIES = frozenset({FileCategory.brep_cad.value, FileCategory.mesh.value})
_PRINT_CATEGORIES = frozenset({FileCategory.document.value, FileCategory.vector_2d.value})

#: PartGeometry's numeric columns, exposed to the ``part`` document_path. The
#: stored values are already effective (COALESCE(override, raw) is materialized
#: at write time) and already metric, so the evaluator can read them directly.
_PART_GEOMETRY_ATTRS = (
    "size_x",
    "size_y",
    "size_z",
    "max_dim",
    "med_dim",
    "min_dim",
    "area",
    "volume",
    "weight",
)


# --------------------------------------------------------------------------- #
# wire models
# --------------------------------------------------------------------------- #
class ReviewItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid_mod.UUID
    rule_id: uuid_mod.UUID
    rule_name: str
    component_id: uuid_mod.UUID
    quote_id: uuid_mod.UUID
    quote_item_id: uuid_mod.UUID
    status: str
    assignee_id: uuid_mod.UUID | None
    resolution_type: str | None
    resolution_label: str | None
    resolved_at: datetime | None
    resolved_by: uuid_mod.UUID | None
    detail: dict[str, Any]
    #: The §3 options this rule offers — the card's stacked one-click buttons.
    resolution_options: list[dict[str, Any]]


class ReviewItemGroupOut(BaseModel):
    """Quote-level aggregation: findings grouped by rule across all parts, the
    unit SET ALL acts on (spec ``#rules`` "Review Items workflow")."""

    model_config = ConfigDict(extra="forbid")

    rule_id: uuid_mod.UUID
    rule_name: str
    unresolved_count: int
    items: list[ReviewItemOut]


class PriorDecisionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid_mod.UUID
    component_id: uuid_mod.UUID
    resolution_type: str
    resolution_label: str | None
    resolved_at: datetime | None
    resolved_by: uuid_mod.UUID | None


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee_id: uuid_mod.UUID | None


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_type: ResolutionType
    custom_label: str | None = None


class SetAllIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: uuid_mod.UUID
    resolution_type: ResolutionType
    custom_label: str | None = None


class SetAllOut(BaseModel):
    resolved_count: int


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str


class MessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid_mod.UUID
    author_id: uuid_mod.UUID | None
    body: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# context building (M3.7's EvaluationContext, from DB rows)
# --------------------------------------------------------------------------- #
async def build_context(session: AsyncSession, component: Component) -> EvaluationContext:
    """A component's analyzed data — RULES-ENGINE-SPEC §8's integration map,
    read from the rows each producer actually writes.

    ``interrogation_result`` is deliberately ``None``: GeometryService lands in
    M4, and M3.7 gates those signals off precisely while it is absent, so a
    rule about an un-run interrogation stays silent rather than fires on
    nothing.
    """
    findings = (
        (
            await session.execute(
                select(ExtractionFinding)
                .join(PartFile, PartFile.id == ExtractionFinding.source_file_id)
                .where(PartFile.part_id == component.part_id)
                # A finding the human rejected is not evidence (M3.2's
                # correction path); `suggested`/`accepted`/`edited` all are.
                .where(ExtractionFinding.status != FindingStatus.rejected)
            )
        )
        .scalars()
        .all()
    )
    extractions = [
        {
            "category": f.category.value if f.category is not None else None,
            "type": f.type,
            "value": f.value,
            "normalized_value": f.normalized_value,
            "units": f.units,
            "tolerance": f.tolerance,
            "raw_text": f.raw_text,
            "gdt": f.gdt,
        }
        for f in findings
    ]

    files = (
        (await session.execute(select(PartFile).where(PartFile.part_id == component.part_id)))
        .scalars()
        .all()
    )
    document_texts = [f.pdf_text for f in files if f.pdf_text]

    part = await session.get(Part, component.part_id)
    geometry = await session.scalar(
        select(PartGeometry).where(PartGeometry.part_id == component.part_id)
    )
    part_attributes: dict[str, Any] = {
        "is_assembly": bool(part.is_assembly) if part is not None else False,
        # §2 lists is_root as a part property; the quoting layer owns it.
        "is_root": bool(component.is_root_component),
    }
    if geometry is not None:
        for attr in _PART_GEOMETRY_ATTRS:
            part_attributes[attr] = getattr(geometry, attr)

    return EvaluationContext(
        extractions=extractions,
        document_texts=document_texts,
        part_attributes=part_attributes,
        files={
            "has_model": any(f.file_type in _MODEL_CATEGORIES for f in files),
            "has_print": any(f.file_type in _PRINT_CATEGORIES for f in files),
        },
        interrogation_result=None,
    )


# --------------------------------------------------------------------------- #
# generation (§6.1)
# --------------------------------------------------------------------------- #
def _rule_schema(row: Rule) -> RuleSchema:
    return RuleSchema.model_validate(
        {
            "uuid": row.uuid,
            "name": row.name,
            "description": row.description,
            "logical_operator": row.logical_operator,
            "signals": row.signals,
            "resolutions": row.resolutions,
            "default_assignee_id": row.default_assignee_id,
        }
    )


async def _is_active_member(
    session: AsyncSession, org_id: uuid_mod.UUID, user_id: uuid_mod.UUID
) -> bool:
    """``Rule.default_assignee_id`` is un-FK'd on purpose — an imported rule set
    may name a user who does not exist here (M3.6 defers the check to
    "assignment time", which is this). The ``collab.py`` membership guard.

    **Active**, not merely present: a suspended member is not someone work can be
    routed to, and every caller here is routing work (default assignment,
    reassignment, ASSIGN_ESTIMATOR). ``collab._require_active_member`` draws the
    same line."""
    found = await session.scalar(
        select(UserOrgMembership.id).where(
            UserOrgMembership.user_id == user_id,
            UserOrgMembership.org_id == org_id,
            UserOrgMembership.status == MembershipStatus.active,
        )
    )
    return found is not None


async def _notify_assignee(
    session: AsyncSession, org_id: uuid_mod.UUID, item: ReviewItem, user_id: uuid_mod.UUID
) -> None:
    session.add(
        Notification(
            org_id=org_id,
            user_id=user_id,
            kind=NOTIFICATION_ASSIGNED,
            payload={
                "review_item_id": str(item.id),
                "quote_id": str(item.quote_id),
                "component_id": str(item.component_id),
            },
        )
    )


async def generate_for_component(
    session: AsyncSession, org_id: uuid_mod.UUID, component: Component
) -> list[ReviewItem]:
    """Evaluate the org's active rules against ``component`` and reconcile its
    review items (spec ``#rules``: "create/update ReviewItems").

    Idempotent by construction — the ``(org_id, component_id, rule_id)`` identity
    means a re-run after every Lens extraction converges on the same rows rather
    than accumulating duplicates.

    A rule that *stops* matching withdraws its **unresolved** item (the print
    arrived; the flag is moot). A **resolved** item is never withdrawn — it is
    the audit trail (§6.6). ASSUMED: the spec says "create/update" without
    naming the withdrawal case; leaving stale items would make an estimator burn
    down work the drawing no longer asks for. Cheap to reverse (one branch).
    """
    # Serialize concurrent reconciliations of the same component (two uploads →
    # two extractions → two generate tasks). Without this both can observe "no
    # item", both insert, and one dies on `uq_review_item_component_rule`. The
    # M3.1 precedent (`lens_extract`'s replace-suggested lock); held to commit.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"review_items:{component.id}"},
    )
    quote_item = await session.scalar(
        select(QuoteItem).where(QuoteItem.root_component_id == component.id)
    )
    if quote_item is None:
        # Only root components map to a line item today (BOM children arrive
        # with M4's builder). No line item → nothing a resolution could mutate.
        return []

    rules = (
        (await session.execute(select(Rule).where(Rule.is_active.is_(True)).order_by(Rule.name)))
        .scalars()
        .all()
    )
    by_id = {row.id: row for row in rules}
    context = await build_context(session, component)
    matched = {
        row.id
        for row, schema in ((row, _rule_schema(row)) for row in rules)
        if evaluate_rules([schema], context)
    }

    existing = {
        item.rule_id: item
        for item in (
            await session.execute(select(ReviewItem).where(ReviewItem.component_id == component.id))
        )
        .scalars()
        .all()
    }

    live: list[ReviewItem] = []
    for rule_id in matched:
        item = existing.get(rule_id)
        if item is None:
            rule = by_id[rule_id]
            item = ReviewItem(
                org_id=org_id,
                quote_id=quote_item.quote_id,
                quote_item_id=quote_item.id,
                component_id=component.id,
                rule_id=rule_id,
                status=ReviewItemStatus.open.value,
                detail={"rule_name": rule.name},
            )
            if rule.default_assignee_id is not None and await _is_active_member(
                session, org_id, rule.default_assignee_id
            ):
                item.assignee_id = rule.default_assignee_id
            session.add(item)
            await session.flush()
            if item.assignee_id is not None:
                await _notify_assignee(session, org_id, item, item.assignee_id)
        live.append(item)

    for rule_id, item in existing.items():
        if rule_id not in matched and item.status == ReviewItemStatus.open.value:
            await session.delete(item)

    await session.flush()
    return sorted(live, key=lambda i: by_id[i.rule_id].name)


# --------------------------------------------------------------------------- #
# resolution effects (§3)
# --------------------------------------------------------------------------- #
def _parameter(resolution: Resolution, name: str) -> Any:
    for param in resolution.parameters:
        if param.name == name:
            return param.value
    return None


def _offered(rule: Rule, resolution_type: ResolutionType) -> Resolution:
    """§3: "A rule offers one or more resolutions; the user picks the one that
    applies." Anything else is not a choice the rule authorised — accepting it
    would let a deburring rule no-quote a line item."""
    for raw in rule.resolutions:
        resolution = Resolution.model_validate(raw)
        if resolution.type == resolution_type.value:
            return resolution
    raise AppError(
        code="resolution_not_offered",
        message="Diese Auflösung wird von der Regel nicht angeboten.",
        status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


async def _apply_effect(
    session: AsyncSession,
    org_id: uuid_mod.UUID,
    item: ReviewItem,
    resolution: Resolution,
) -> None:
    """The §3 catalogue's mutations. RESOLVE mutates nothing by definition —
    its label captures a real-world task the system cannot model."""
    if resolution.type == ResolutionType.RESOLVE.value:
        return

    if resolution.type == ResolutionType.NO_QUOTE.value:
        quote_item = await session.get(QuoteItem, item.quote_item_id)
        if quote_item is not None:
            quote_item.workflow_status = QiWorkflowStatus.no_quote
        return

    if resolution.type == ResolutionType.ASSIGN_ESTIMATOR.value:
        estimator_id = _parameter(resolution, "estimator_id")
        if estimator_id is None:
            return
        user_id = uuid_mod.UUID(str(estimator_id))
        if not await _is_active_member(session, org_id, user_id):
            raise AppError(
                code="unknown_estimator",
                message="Die Regel benennt eine Person, die nicht zu dieser Organisation gehört.",
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        item.assignee_id = user_id
        await session.flush()
        await _notify_assignee(session, org_id, item, user_id)
        return

    component = await session.get(Component, item.component_id)
    if component is None:  # pragma: no cover - FK guarantees it
        return

    if resolution.type == ResolutionType.SET_PROCESS.value:
        process_id = _parameter(resolution, "process_id")
        if process_id is None:
            return
        process = await session.scalar(
            select(Process).where(
                Process.id == uuid_mod.UUID(str(process_id)), Process.deleted_at.is_(None)
            )
        )
        if process is None:
            raise AppError(
                code="unknown_process",
                message="Die Regel benennt einen Prozess, den es nicht mehr gibt.",
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        component.process_id = process.id
        await session.flush()
        await recalculate_component(session, org_id, component.id)
        return

    if resolution.type == ResolutionType.ADD_OPERATION.value:
        op_def_ids = _parameter(resolution, "op_def_ids") or []
        if not isinstance(op_def_ids, list):
            op_def_ids = [op_def_ids]
        # Spec #rules: "must not insert an operation the router already has;
        # the system blocks duplicates".
        present = set(
            (
                await session.execute(
                    select(Operation.operation_def_id).where(Operation.component_id == component.id)
                )
            )
            .scalars()
            .all()
        )
        added = False
        for raw_id in op_def_ids:
            op_def_id = uuid_mod.UUID(str(raw_id))
            if op_def_id in present:
                continue
            op_def = await session.scalar(
                select(OperationDef).where(
                    OperationDef.id == op_def_id, OperationDef.deleted_at.is_(None)
                )
            )
            if op_def is None:
                raise AppError(
                    code="unknown_operation_def",
                    message="Die Regel benennt eine Operation, die es nicht mehr gibt.",
                    status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            # Rule-added, not estimator-added: excluded from the M3.10
            # rule-suggestion pattern detector (spec ``#ai-rule-suggest``).
            await attach_operation_from_def(
                session, org_id, component, op_def, added_manually=False
            )
            present.add(op_def_id)
            added = True
        if added:
            await recalculate_component(session, org_id, component.id)


async def _resolve(
    session: AsyncSession,
    org_id: uuid_mod.UUID,
    item: ReviewItem,
    rule: Rule,
    resolution_type: ResolutionType,
    custom_label: str | None,
    actor_id: uuid_mod.UUID | None,
) -> None:
    if item.status == ReviewItemStatus.resolved.value:
        raise AppError(
            code="already_resolved",
            message="Dieser Prüfpunkt ist bereits erledigt.",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    resolution = _offered(rule, resolution_type)
    await _apply_effect(session, org_id, item, resolution)
    item.status = ReviewItemStatus.resolved.value
    item.resolution_type = resolution_type.value
    # The rule's own label is the default; an explicit one wins (§3: the label
    # captures the real-world decision).
    item.resolution_label = custom_label or resolution.custom_label
    item.resolved_at = datetime.now(UTC)
    item.resolved_by = actor_id


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
async def _component_or_404(session: AsyncSession, component_id: uuid_mod.UUID) -> Component:
    component = await session.get(Component, component_id)
    if component is None:
        raise AppError(
            code="not_found",
            message="Bauteil nicht gefunden.",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    return component


async def _item_or_404(
    session: AsyncSession, item_id: uuid_mod.UUID, *, for_update: bool = False
) -> ReviewItem:
    """``for_update`` claims the row for a resolve: without it two concurrent
    resolves (or one racing SET ALL) both read ``status == 'open'``, both pass
    the guard, and both apply the effects — two operations on the router, two
    notifications. The lock makes the open→resolved transition the serialization
    point (the ``_lock_editable_quote`` precedent)."""
    if for_update:
        item = await session.scalar(
            select(ReviewItem)
            .where(ReviewItem.id == item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        item = await session.get(ReviewItem, item_id)
    if item is None:
        raise AppError(
            code="not_found",
            message="Prüfpunkt nicht gefunden.",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    return item


async def _rule_or_404(session: AsyncSession, rule_id: uuid_mod.UUID) -> Rule:
    rule = await session.get(Rule, rule_id)
    if rule is None:
        raise AppError(
            code="not_found",
            message="Regel nicht gefunden.",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    return rule


def _out(item: ReviewItem, rule: Rule) -> ReviewItemOut:
    return ReviewItemOut(
        id=item.id,
        rule_id=item.rule_id,
        rule_name=rule.name,
        component_id=item.component_id,
        quote_id=item.quote_id,
        quote_item_id=item.quote_item_id,
        status=item.status,
        assignee_id=item.assignee_id,
        resolution_type=item.resolution_type,
        resolution_label=item.resolution_label,
        resolved_at=item.resolved_at,
        resolved_by=item.resolved_by,
        detail=item.detail,
        resolution_options=list(rule.resolutions),
    )


async def _rules_by_id(session: AsyncSession, items: list[ReviewItem]) -> dict[uuid_mod.UUID, Rule]:
    if not items:
        return {}
    rule_ids = {item.rule_id for item in items}
    rows = (await session.execute(select(Rule).where(Rule.id.in_(rule_ids)))).scalars().all()
    return {row.id: row for row in rows}


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@review_items_router.post(
    "/components/{component_id}/review-items/generate", response_model=list[ReviewItemOut]
)
async def generate_review_items(
    component_id: uuid_mod.UUID,
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ReviewItemOut]:
    """Re-evaluate this component (spec ``#rules``: "a refresh re-evaluates the
    part"). The same entry point M3.9's post-extraction trigger calls."""
    component = await _component_or_404(session, component_id)
    items = await generate_for_component(session, principal.active_org_id, component)
    rules = await _rules_by_id(session, items)
    return [_out(item, rules[item.rule_id]) for item in items]


@review_items_router.get(
    "/components/{component_id}/review-items", response_model=list[ReviewItemOut]
)
async def list_component_review_items(
    component_id: uuid_mod.UUID,
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ReviewItemOut]:
    await _component_or_404(session, component_id)
    items = list(
        (
            await session.execute(
                select(ReviewItem)
                .where(ReviewItem.component_id == component_id)
                .order_by(ReviewItem.created_at)
            )
        )
        .scalars()
        .all()
    )
    rules = await _rules_by_id(session, items)
    return [_out(item, rules[item.rule_id]) for item in items]


@review_items_router.get("/quotes/{quote_id}/review-items", response_model=list[ReviewItemGroupOut])
async def list_quote_review_items(
    quote_id: uuid_mod.UUID,
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ReviewItemGroupOut]:
    """Quote level: findings grouped by rule across all parts — the unit SET ALL
    acts on (spec ``#rules`` "Review Items workflow")."""
    items = list(
        (
            await session.execute(
                select(ReviewItem)
                .where(ReviewItem.quote_id == quote_id)
                .order_by(ReviewItem.created_at)
            )
        )
        .scalars()
        .all()
    )
    rules = await _rules_by_id(session, items)
    groups: dict[uuid_mod.UUID, list[ReviewItem]] = {}
    for item in items:
        groups.setdefault(item.rule_id, []).append(item)
    return [
        ReviewItemGroupOut(
            rule_id=rule_id,
            rule_name=rules[rule_id].name,
            unresolved_count=sum(1 for i in grouped if i.status == ReviewItemStatus.open.value),
            items=[_out(i, rules[rule_id]) for i in grouped],
        )
        for rule_id, grouped in sorted(groups.items(), key=lambda kv: rules[kv[0]].name)
    ]


@review_items_router.patch("/review-items/{item_id}", response_model=ReviewItemOut)
async def assign_review_item(
    item_id: uuid_mod.UUID,
    payload: AssignIn,
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewItemOut:
    """§6.2: items can be reassigned; the new assignee is notified."""
    item = await _item_or_404(session, item_id)
    rule = await _rule_or_404(session, item.rule_id)
    if payload.assignee_id is not None:
        if not await _is_active_member(session, principal.active_org_id, payload.assignee_id):
            raise AppError(
                code="unknown_assignee",
                message="Diese Person gehört nicht zu dieser Organisation.",
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        changed = item.assignee_id != payload.assignee_id
        item.assignee_id = payload.assignee_id
        if changed:
            await _notify_assignee(session, principal.active_org_id, item, payload.assignee_id)
    else:
        item.assignee_id = None
    await session.flush()
    return _out(item, rule)


@review_items_router.post("/review-items/{item_id}/resolve", response_model=ReviewItemOut)
async def resolve_review_item(
    item_id: uuid_mod.UUID,
    payload: ResolveIn,
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewItemOut:
    """§6.5: the user selects one configured resolution → it mutates the
    quote/router as applicable → the item closes."""
    item = await _item_or_404(session, item_id, for_update=True)
    rule = await _rule_or_404(session, item.rule_id)
    await _resolve(
        session,
        principal.active_org_id,
        item,
        rule,
        payload.resolution_type,
        payload.custom_label,
        principal.user_id,
    )
    await session.flush()
    return _out(item, rule)


@review_items_router.post("/quotes/{quote_id}/review-items/set-all", response_model=SetAllOut)
async def set_all(
    quote_id: uuid_mod.UUID,
    payload: SetAllIn,
    principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SetAllOut:
    """§6.5's bulk action: apply one resolution to every part carrying the flag
    ("no-quote them all" in one click). Already-resolved items are left alone —
    SET ALL is for burning down what is still open, and re-resolving would
    rewrite a decision someone already made."""
    rule = await _rule_or_404(session, payload.rule_id)
    items = list(
        (
            await session.execute(
                select(ReviewItem)
                .where(
                    ReviewItem.quote_id == quote_id,
                    ReviewItem.rule_id == payload.rule_id,
                    ReviewItem.status == ReviewItemStatus.open.value,
                )
                .order_by(ReviewItem.created_at)
                # Same claim as the single resolve, in a stable order so two
                # concurrent SET ALLs queue rather than deadlock.
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for item in items:
        await _resolve(
            session,
            principal.active_org_id,
            item,
            rule,
            payload.resolution_type,
            payload.custom_label,
            principal.user_id,
        )
    await session.flush()
    return SetAllOut(resolved_count=len(items))


@review_items_router.get(
    "/review-items/{item_id}/prior-decisions", response_model=list[PriorDecisionOut]
)
async def prior_decisions(
    item_id: uuid_mod.UUID,
    _: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PriorDecisionOut]:
    """§6.4: "show up to 5 past parts the rule flagged + the decision taken
    there, so juniors act consistently"."""
    item = await _item_or_404(session, item_id)
    rows = (
        (
            await session.execute(
                select(ReviewItem)
                .where(
                    ReviewItem.rule_id == item.rule_id,
                    ReviewItem.id != item.id,
                    ReviewItem.status == ReviewItemStatus.resolved.value,
                )
                .order_by(ReviewItem.resolved_at.desc())
                .limit(PRIOR_DECISION_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    return [
        PriorDecisionOut(
            id=row.id,
            component_id=row.component_id,
            resolution_type=row.resolution_type or "",
            resolution_label=row.resolution_label,
            resolved_at=row.resolved_at,
            resolved_by=row.resolved_by,
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# collaboration thread (§6.3)
# --------------------------------------------------------------------------- #
async def _thread_channel(
    session: AsyncSession, org_id: uuid_mod.UUID, item: ReviewItem
) -> Channel:
    """§6.3: "each item carries a chat thread; discussion/decisions are
    permanently stored". Reuses the M2.11 channel/message spine rather than a
    second messaging table — one part's conversation, labelled per item."""
    component = await session.get(Component, item.component_id)
    if component is None:  # pragma: no cover - FK guarantees it
        raise AppError(
            code="not_found",
            message="Bauteil nicht gefunden.",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    label = f"review-item:{item.id}"
    channel = await session.scalar(
        select(Channel).where(Channel.part_id == component.part_id, Channel.label == label)
    )
    if channel is None:
        channel = Channel(
            org_id=org_id,
            part_id=component.part_id,
            quote_id=item.quote_id,
            scope="team",
            label=label,
        )
        session.add(channel)
        await session.flush()
    return channel


@review_items_router.get("/review-items/{item_id}/messages", response_model=list[MessageOut])
async def list_thread(
    item_id: uuid_mod.UUID,
    principal: Annotated[Principal, Depends(require(Permission.view_all))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MessageOut]:
    item = await _item_or_404(session, item_id)
    channel = await _thread_channel(session, principal.active_org_id, item)
    rows = (
        (
            await session.execute(
                select(Message)
                .where(Message.channel_id == channel.id, Message.deleted_at.is_(None))
                .order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        MessageOut(id=r.id, author_id=r.author_id, body=r.body or "", created_at=r.created_at)
        for r in rows
    ]


@review_items_router.post(
    "/review-items/{item_id}/messages",
    response_model=MessageOut,
    status_code=http_status.HTTP_201_CREATED,
)
async def post_to_thread(
    item_id: uuid_mod.UUID,
    payload: MessageIn,
    principal: Annotated[Principal, Depends(require(Permission.quote_annotate))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MessageOut:
    """Discussing an item needs only annotate rights — an engineer who cannot
    resolve can still weigh in (the ``collab.py`` boundary)."""
    item = await _item_or_404(session, item_id)
    channel = await _thread_channel(session, principal.active_org_id, item)
    message = Message(
        org_id=principal.active_org_id,
        channel_id=channel.id,
        author_id=principal.user_id,
        body=payload.body,
    )
    session.add(message)
    await session.flush()
    return MessageOut(
        id=message.id,
        author_id=message.author_id,
        body=message.body or "",
        created_at=message.created_at,
    )


# --------------------------------------------------------------------------- #
# post-extraction trigger (§6.1)
# --------------------------------------------------------------------------- #
def _run_on_own_loop(coro: Any) -> Any:
    """Run ``coro`` whether or not a loop is running (worker vs eager tests) —
    the M2.5 pattern (see ``file_split._run_on_own_loop``)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _generate_for_part(db_url: str, org_id: uuid_mod.UUID, part_id: uuid_mod.UUID) -> int:
    """Regenerate review items for every component built on ``part_id``."""
    engine = create_async_engine(db_url)
    try:
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with org_scoped_session(sessionmaker, org_id) as session:
            components = (
                (await session.execute(select(Component).where(Component.part_id == part_id)))
                .scalars()
                .all()
            )
            total = 0
            for component in components:
                total += len(await generate_for_component(session, org_id, component))
            return total
    finally:
        await engine.dispose()


@celery_app.task(base=BaseTask, name="app.review_items_generate", bind=True)
def review_items_generate_task(self: Any, org_id: str, part_id: str) -> dict[str, Any]:
    """§6.1: "after AI/interrogation finishes, matching rules create review
    items". Chained from ``lens_extract_task`` — extraction is what changes the
    data the rules read, so it is what must re-run them.

    Safe to re-run: :func:`generate_for_component` reconciles rather than
    inserts, so a Celery redelivery converges on the same rows. That is why this
    needs no ``AsyncResult`` guard of its own (unlike the extraction task, whose
    findings are append-only).
    """
    db_url, _ = resolve_task_resources()
    count = _run_on_own_loop(
        _generate_for_part(db_url, uuid_mod.UUID(org_id), uuid_mod.UUID(part_id))
    )
    # Counts only — a rule name can quote print content (§5 logging).
    logger.info(
        "review_items_generated",
        extra={"org_id": org_id, "part_id": part_id, "review_item_count": count},
    )
    return {"org_id": org_id, "part_id": part_id, "review_item_count": count}
