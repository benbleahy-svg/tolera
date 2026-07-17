"""BOM Builder — split PDF → detect → extract → child BOMs → publish (M4.9).

Spec ``#bombuilder``: the builder is a **staging area**. Lens's ``bom_tables``
findings (DECISIONS.md 2026-07-17 contract) seed an *editable* document, split
pages match rows by their title-block part number (``part_file.part_number_
extracted``, filled at split time), child-BOM suggestions enter the draft only
via the client's explicit accept (AI-Governor), and nothing touches
``part``/``node``/``component`` until CHECK AND PUBLISH commits the whole tree
in one transaction. CHECK BOM runs the same validation without committing.

Semantics encoded here (KB ``The-BOM-Builder``; DOMAIN-MODEL §1):
  * **Linking:** rows with the same part number + revision are ONE part (one
    ``Part``, many ``Node``s — a repeated part is quoted once). Conflicting
    row data on linked rows is a validation error; the same part twice at one
    level is a validation error.
  * **Capacity:** at most ``UNIQUE_PARTS_CAP`` unique parts per BOM.
  * **Flat qty is derived** — quantities multiply down the tree; nothing is
    persisted beyond ``node.qty_relative_to_parent`` (+ sibling ``position``).
  * **Republish reuses parts** by part#+rev (pricing and files survive a
    re-edit); parts that vanish from the tree lose their child component and
    are soft-deleted when nothing else references them (ASSUMED — cheap to
    reverse; the alternative is orphan rows polluting the Part Library).
  * **Purchased rows publish unassigned** — the purchased-component library
    lands in M4.10 (DECISIONS.md 2026-07-17); CHECK reports them as a notice,
    never an error.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import (
    BomDraft,
    Component,
    ExtractionFinding,
    FindingStatus,
    Node,
    ObtainMethod,
    Part,
    PartFile,
    Quote,
    QuoteItem,
)
from .quotes import _is_editable

logger = logging.getLogger(__name__)

bom_router = APIRouter(prefix="/api/quote-items", tags=["bom-builder"])

#: KB ``The-BOM-Builder`` FAQ: "up to 1000 unique parts" (per-account capacity).
UNIQUE_PARTS_CAP = 1000

#: The Lens finding type carrying a detected BOM table (DECISIONS.md 2026-07-17).
BOM_TABLE_FINDING_TYPE = "bom_tables"

RowType = Literal["assembly_root", "subassembly", "manufactured", "purchased"]

#: node.qty_relative_to_parent is a PostgreSQL integer — a qty above this
#: would pass a naive check and then blow up the INSERT at publish.
MAX_QTY = 2_147_483_647


# --------------------------------------------------------------------------- #
# The draft document (staging state — what bom_draft.payload holds)
# --------------------------------------------------------------------------- #
class BomRow(BaseModel):
    """One editable row of the staged BOM tree."""

    model_config = ConfigDict(extra="forbid")

    row_id: str = Field(min_length=1, max_length=64)
    row_type: RowType = "manufactured"
    part_number: str | None = None
    revision: str | None = None
    description: str | None = None
    qty: int = 1
    primary_file_id: uuid.UUID | None = None
    supporting_file_ids: list[uuid.UUID] = Field(default_factory=list)
    children: list[BomRow] = Field(default_factory=list)


class BomDoc(BaseModel):
    """The whole staged tree; ``root`` mirrors the line item's part."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    root: BomRow


BomRow.model_rebuild()


# --------------------------------------------------------------------------- #
# The Lens bom_tables value contract (DECISIONS.md 2026-07-17)
# --------------------------------------------------------------------------- #
class BomTableRow(BaseModel):
    """One extracted BOM-table row (suggestion data, never auto-committed)."""

    model_config = ConfigDict(extra="ignore")

    item_no: str | None = None
    part_number: str | None = None
    revision: str | None = None
    #: None = not printed on the table (never-hallucinate: the provider omits
    #: unprinted values; the UI shows the editable default, the human confirms).
    qty: int | None = None
    description: str | None = None
    type_hint: Literal["subassembly", "manufactured", "purchased"] | None = None


class BomTable(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root_part_number: str | None = None
    rows: list[BomTableRow] = Field(default_factory=list)


def parse_bom_table_value(value: str | None) -> BomTable | None:
    """Tolerantly parse a ``bom_tables`` finding's ``value`` JSON.

    Malformed payloads are ignored, never an error — a bad extraction must not
    break the builder (the finding simply carries no usable suggestion)."""
    if not value:
        return None
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        table = BomTable.model_validate(data)
    except ValidationError:
        return None
    return table if table.rows else None


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
class BomIssue(BaseModel):
    """One CHECK BOM finding: an error blocks publish, a notice never does."""

    code: str
    message: str
    row_ids: list[str] = Field(default_factory=list)


def _walk(row: BomRow) -> list[BomRow]:
    out = [row]
    for child in row.children:
        out.extend(_walk(child))
    return out


def _part_key(row: BomRow) -> tuple[str, str] | None:
    """Identity for linking rows as one part: trimmed part# + revision.

    KB §Multiple instances: "the same exact part number and revision and no
    conflicting information" link as the same part."""
    pn = (row.part_number or "").strip()
    if not pn:
        return None
    return (pn, (row.revision or "").strip())


def unique_part_count(doc: BomDoc) -> int:
    """Unique parts in the staged tree (the "N/1000" counter, root included)."""
    keys: set[tuple[str, str]] = set()
    keyless = 0
    for row in _walk(doc.root):
        key = _part_key(row)
        if key is None:
            keyless += 1
        else:
            keys.add(key)
    return len(keys) + keyless


def validate_doc(
    doc: BomDoc, in_scope_file_ids: set[uuid.UUID]
) -> tuple[list[BomIssue], list[BomIssue]]:
    """CHECK BOM: (errors, notices). Publish runs exactly this and blocks on errors."""
    errors: list[BomIssue] = []
    notices: list[BomIssue] = []
    root = doc.root

    if root.row_type not in ("assembly_root", "manufactured"):
        errors.append(
            BomIssue(
                code="root_invalid",
                message="The root row must be an assembly root or a manufactured part.",
                row_ids=[root.row_id],
            )
        )
    if root.qty != 1:
        errors.append(
            BomIssue(
                code="root_invalid",
                message="The root row always has quantity 1.",
                row_ids=[root.row_id],
            )
        )

    rows = _walk(root)
    seen_ids: set[str] = set()
    by_key: dict[tuple[str, str], list[BomRow]] = {}
    for row in rows:
        if row.row_id in seen_ids:
            errors.append(
                BomIssue(
                    code="row_id_duplicate",
                    message="Row ids must be unique within the document.",
                    row_ids=[row.row_id],
                )
            )
        seen_ids.add(row.row_id)
        key = _part_key(row)
        if key is not None:
            by_key.setdefault(key, []).append(row)

        if row.qty < 1 or row.qty > MAX_QTY:
            errors.append(
                BomIssue(
                    code="qty_invalid",
                    message=f"Quantities must be between 1 and {MAX_QTY}.",
                    row_ids=[row.row_id],
                )
            )
        if key is None and row.primary_file_id is None and row is not root:
            errors.append(
                BomIssue(
                    code="row_incomplete",
                    message="A row needs a part number or a primary file.",
                    row_ids=[row.row_id],
                )
            )
        if row.row_type == "purchased" and row.children:
            errors.append(
                BomIssue(
                    code="purchased_with_children",
                    message="A purchased part cannot have child parts.",
                    row_ids=[row.row_id],
                )
            )
        if row is not root and row.row_type == "assembly_root":
            errors.append(
                BomIssue(
                    code="root_invalid",
                    message="Only the root row can be the assembly root.",
                    row_ids=[row.row_id],
                )
            )

        # Same part twice at ONE level is unrepresentable (KB: delete one and
        # bump the other's quantity instead).
        child_keys: dict[tuple[str, str], list[str]] = {}
        for child in row.children:
            child_key = _part_key(child)
            if child_key is not None:
                child_keys.setdefault(child_key, []).append(child.row_id)
        for ids in child_keys.values():
            if len(ids) > 1:
                errors.append(
                    BomIssue(
                        code="duplicate_at_level",
                        message="The same part cannot appear twice at one level.",
                        row_ids=ids,
                    )
                )

        for file_id in [row.primary_file_id, *row.supporting_file_ids]:
            if file_id is not None and file_id not in in_scope_file_ids:
                errors.append(
                    BomIssue(
                        code="file_not_in_scope",
                        message="Assigned files must belong to this line item.",
                        row_ids=[row.row_id],
                    )
                )

    # A non-root row that reuses the ROOT's identity would silently mint a
    # duplicate Part on publish (the root is never in the child reuse map) —
    # a self-referencing assembly is a structural error instead.
    root_key = _part_key(root)
    if root_key is not None:
        self_refs = [r for r in rows if r is not root and _part_key(r) == root_key]
        if self_refs:
            errors.append(
                BomIssue(
                    code="root_reference",
                    message="A child row cannot reuse the root part's part number.",
                    row_ids=[r.row_id for r in self_refs],
                )
            )

    # One file belongs to one part: rows of DIFFERENT parts claiming the same
    # file would move it back and forth on publish (linked rows already share).
    file_claims: dict[uuid.UUID, set[tuple[str, str] | str]] = {}
    for row in rows:
        claimant: tuple[str, str] | str = _part_key(row) or row.row_id
        for file_id in [row.primary_file_id, *row.supporting_file_ids]:
            if file_id is not None:
                file_claims.setdefault(file_id, set()).add(claimant)
    conflicted = [fid for fid, claimants in file_claims.items() if len(claimants) > 1]
    if conflicted:
        conflict_rows = [
            row.row_id
            for row in rows
            if any(
                fid in conflicted
                for fid in [row.primary_file_id, *row.supporting_file_ids]
                if fid is not None
            )
        ]
        errors.append(
            BomIssue(
                code="file_conflict",
                message="A file can only be assigned to one part.",
                row_ids=conflict_rows,
            )
        )

    # Linked rows (same part#+rev) must carry no conflicting information.
    for key, linked in by_key.items():
        if len(linked) < 2:
            continue
        descriptions = {(r.description or "").strip() for r in linked if r.description}
        primaries = {r.primary_file_id for r in linked if r.primary_file_id is not None}
        types = {r.row_type for r in linked if r is not doc.root}
        if len(descriptions) > 1 or len(primaries) > 1 or len(types) > 1:
            errors.append(
                BomIssue(
                    code="part_conflict",
                    message=(
                        f"Rows for part {key[0]} carry conflicting information "
                        "and cannot be linked."
                    ),
                    row_ids=[r.row_id for r in linked],
                )
            )

    count = unique_part_count(doc)
    if count > UNIQUE_PARTS_CAP:
        errors.append(
            BomIssue(
                code="capacity_exceeded",
                message=f"A BOM may contain at most {UNIQUE_PARTS_CAP} unique parts.",
            )
        )

    for row in rows:
        if row is root:
            continue
        if row.row_type in ("subassembly", "manufactured") and row.primary_file_id is None:
            notices.append(
                BomIssue(
                    code="missing_primary_file",
                    message="No drawing or model is assigned to this part yet.",
                    row_ids=[row.row_id],
                )
            )
        if row.row_type == "purchased":
            notices.append(
                BomIssue(
                    code="purchased_unassigned",
                    message=(
                        "Purchased parts are not linked to a component library "
                        "record yet (arrives with M4.10)."
                    ),
                    row_ids=[row.row_id],
                )
            )

    return errors, notices


# --------------------------------------------------------------------------- #
# Context loading (org-scoped; RLS makes cross-org a 404)
# --------------------------------------------------------------------------- #
class _Context:
    def __init__(
        self,
        quote_item: QuoteItem,
        quote: Quote,
        root_component: Component,
        root_part: Part,
        root_node: Node,
    ) -> None:
        self.quote_item = quote_item
        self.quote = quote
        self.root_component = root_component
        self.root_part = root_part
        self.root_node = root_node


async def _load_context(session: AsyncSession, quote_item_id: uuid.UUID) -> _Context:
    row = (
        await session.execute(
            select(QuoteItem, Quote, Component, Part)
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .join(Component, Component.id == QuoteItem.root_component_id)
            .join(Part, Part.id == Component.part_id)
            .where(QuoteItem.id == quote_item_id)
        )
    ).first()
    if row is None:
        raise AppError("not_found", "Quote item not found.", status_code=status.HTTP_404_NOT_FOUND)
    quote_item, quote, component, part = row
    root_node = await session.scalar(
        select(Node).where(Node.part_id == part.id, Node.parent_node_id.is_(None))
    )
    if root_node is None:  # unreachable for API-created parts (create_root_part)
        raise AppError(
            "not_found", "Quote item has no BOM root.", status_code=status.HTTP_404_NOT_FOUND
        )
    return _Context(quote_item, quote, component, part, root_node)


async def _load_child_nodes(session: AsyncSession, root_part_id: uuid.UUID) -> list[Node]:
    return list(
        (
            await session.scalars(
                select(Node)
                .where(Node.root_part_id == root_part_id, Node.parent_node_id.is_not(None))
                .order_by(Node.position, Node.created_at)
            )
        ).all()
    )


async def _load_tree_parts(
    session: AsyncSession, ctx: _Context, child_nodes: list[Node]
) -> dict[uuid.UUID, Part]:
    part_ids = {ctx.root_part.id, *(n.part_id for n in child_nodes)}
    parts = (await session.scalars(select(Part).where(Part.id.in_(part_ids)))).all()
    return {p.id: p for p in parts}


async def _load_scope_files(
    session: AsyncSession, part_ids: set[uuid.UUID]
) -> dict[uuid.UUID, PartFile]:
    files = (
        await session.scalars(
            select(PartFile).where(PartFile.part_id.in_(part_ids)).order_by(PartFile.created_at)
        )
    ).all()
    return {f.id: f for f in files}


async def _load_bom_findings(
    session: AsyncSession, file_ids: set[uuid.UUID]
) -> list[ExtractionFinding]:
    if not file_ids:
        return []
    return list(
        (
            await session.scalars(
                select(ExtractionFinding)
                .where(
                    ExtractionFinding.source_file_id.in_(file_ids),
                    ExtractionFinding.type == BOM_TABLE_FINDING_TYPE,
                    ExtractionFinding.status != FindingStatus.rejected,
                )
                .order_by(ExtractionFinding.created_at)
            )
        ).all()
    )


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #
class SuggestionOut(BaseModel):
    """The root BOM-table detection (the line-item banner + modal seed)."""

    finding_id: uuid.UUID
    file_id: uuid.UUID
    filename: str
    page: int | None


class QuoteFileOut(BaseModel):
    """One Quote-Files-pane entry (the Add-Files matching data rides along)."""

    id: uuid.UUID
    part_id: uuid.UUID
    filename: str
    role: str
    part_number_extracted: str | None
    has_bom_table: bool


class ChildSuggestionOut(BaseModel):
    """A detected BOM table on a (child) drawing — the purple-sparkle rows."""

    finding_id: uuid.UUID
    file_id: uuid.UUID
    page: int | None
    root_part_number: str | None
    rows: list[BomTableRow]


class DraftOut(BaseModel):
    payload: BomDoc
    updated_at: datetime


class BuilderStateOut(BaseModel):
    quote_item_id: uuid.UUID
    root_part_id: uuid.UUID
    root_component_id: uuid.UUID
    draft: DraftOut | None
    initial: BomDoc
    suggestion: SuggestionOut | None
    quote_files: list[QuoteFileOut]
    child_suggestions: list[ChildSuggestionOut]
    unique_parts: int
    cap: int


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: BomDoc


class DraftSavedOut(BaseModel):
    updated_at: datetime
    unique_parts: int


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: BomDoc | None = None


class CheckOut(BaseModel):
    errors: list[BomIssue]
    notices: list[BomIssue]
    unique_parts: int


class PublishedNodeOut(BaseModel):
    """One published tree node (flat qty derived, never stored)."""

    node_id: uuid.UUID
    part_id: uuid.UUID
    part_number: str | None
    revision: str | None
    description: str | None
    row_type: RowType
    qty_relative_to_parent: int
    flat_qty: int
    position: int
    children: list[PublishedNodeOut]


PublishedNodeOut.model_rebuild()


class PublishOut(BaseModel):
    tree: PublishedNodeOut


class BomStatusOut(BaseModel):
    """The line-item banner state ("BOM table found in <file>, page N")."""

    suggestion: SuggestionOut | None
    has_children: bool
    has_draft: bool


# --------------------------------------------------------------------------- #
# Initial-document seeding (extraction → editable rows; suggestion-only)
# --------------------------------------------------------------------------- #
def _row_type_for_part(part: Part, *, is_root: bool) -> RowType:
    if is_root:
        return "assembly_root" if part.is_assembly else "manufactured"
    if part.obtain_method is ObtainMethod.purchased:
        return "purchased"
    return "subassembly" if part.is_assembly else "manufactured"


def _doc_from_tree(ctx: _Context, child_nodes: list[Node], parts: dict[uuid.UUID, Part]) -> BomDoc:
    """Rebuild the editable doc from the published tree (the re-edit path)."""
    children_by_parent: dict[uuid.UUID, list[Node]] = {}
    for node in child_nodes:
        assert node.parent_node_id is not None  # filtered upstream
        children_by_parent.setdefault(node.parent_node_id, []).append(node)

    def build(node: Node, *, is_root: bool) -> BomRow:
        part = parts[node.part_id]
        return BomRow(
            row_id=str(node.id),
            row_type=_row_type_for_part(part, is_root=is_root),
            part_number=part.part_number,
            revision=part.revision,
            description=part.description,
            qty=node.qty_relative_to_parent,
            primary_file_id=part.primary_file_id,
            children=[build(child, is_root=False) for child in children_by_parent.get(node.id, [])],
        )

    return BomDoc(root=build(ctx.root_node, is_root=True))


def _doc_from_table(ctx: _Context, table: BomTable) -> BomDoc:
    """Seed the editable doc from the root ``bom_tables`` finding."""
    children = [
        BomRow(
            row_id=f"x-{index}",
            row_type=row.type_hint or "manufactured",
            part_number=row.part_number,
            revision=row.revision,
            description=row.description,
            qty=row.qty if row.qty is not None and row.qty >= 1 else 1,
        )
        for index, row in enumerate(table.rows, start=1)
    ]
    return BomDoc(
        root=BomRow(
            row_id="root",
            row_type="assembly_root",
            part_number=ctx.root_part.part_number or table.root_part_number,
            revision=ctx.root_part.revision,
            description=ctx.root_part.description,
            qty=1,
            primary_file_id=ctx.root_part.primary_file_id,
            children=children,
        )
    )


def _bare_doc(ctx: _Context) -> BomDoc:
    return BomDoc(
        root=BomRow(
            row_id="root",
            row_type="assembly_root" if ctx.root_part.is_assembly else "manufactured",
            part_number=ctx.root_part.part_number,
            revision=ctx.root_part.revision,
            description=ctx.root_part.description,
            qty=1,
            primary_file_id=ctx.root_part.primary_file_id,
            children=[],
        )
    )


def _pick_suggestion(
    ctx: _Context,
    findings: list[ExtractionFinding],
    files: dict[uuid.UUID, PartFile],
) -> tuple[ExtractionFinding, BomTable] | None:
    """The finding that seeds the ROOT BOM: prefer the root part's primary file
    (the uploaded assembly package), earliest page/created first."""

    def sort_key(f: ExtractionFinding) -> tuple[int, int]:
        is_primary = (
            f.source_file_id is not None
            and files.get(f.source_file_id) is not None
            and files[f.source_file_id].role == "primary"
            and files[f.source_file_id].part_id == ctx.root_part.id
        )
        return (0 if is_primary else 1, f.page or 0)

    for finding in sorted(findings, key=sort_key):
        source = files.get(finding.source_file_id) if finding.source_file_id else None
        if source is None or source.part_id != ctx.root_part.id:
            continue
        table = parse_bom_table_value(finding.value)
        if table is not None:
            return finding, table
    return None


async def _builder_inputs(
    session: AsyncSession, ctx: _Context
) -> tuple[
    list[Node],
    dict[uuid.UUID, Part],
    dict[uuid.UUID, PartFile],
    list[ExtractionFinding],
    tuple[ExtractionFinding, BomTable] | None,
]:
    child_nodes = await _load_child_nodes(session, ctx.root_part.id)
    parts = await _load_tree_parts(session, ctx, child_nodes)
    files = await _load_scope_files(session, set(parts.keys()))
    findings = await _load_bom_findings(session, set(files.keys()))
    suggestion = _pick_suggestion(ctx, findings, files)
    return child_nodes, parts, files, findings, suggestion


def _suggestion_out(
    picked: tuple[ExtractionFinding, BomTable], files: dict[uuid.UUID, PartFile]
) -> SuggestionOut:
    finding, _ = picked
    assert finding.source_file_id is not None  # picked findings are file-bound
    return SuggestionOut(
        finding_id=finding.id,
        file_id=finding.source_file_id,
        filename=files[finding.source_file_id].filename,
        page=finding.page,
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@bom_router.get("/{quote_item_id}/bom-builder")
async def get_builder_state(
    quote_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> BuilderStateOut:
    """Everything the modal needs: draft, seeded initial doc, files, suggestions."""
    ctx = await _load_context(session, quote_item_id)
    child_nodes, parts, files, findings, picked = await _builder_inputs(session, ctx)

    draft_row = await session.scalar(
        select(BomDraft).where(BomDraft.quote_item_id == ctx.quote_item.id)
    )
    draft: DraftOut | None = None
    if draft_row is not None:
        try:
            draft = DraftOut(
                payload=BomDoc.model_validate(draft_row.payload),
                updated_at=draft_row.updated_at,
            )
        except ValidationError:  # a schema bump left an unreadable draft behind
            logger.warning("bom_draft %s unreadable; ignoring", draft_row.id)

    if child_nodes:
        initial = _doc_from_tree(ctx, child_nodes, parts)
    elif picked is not None:
        initial = _doc_from_table(ctx, picked[1])
    else:
        initial = _bare_doc(ctx)

    root_finding_id = picked[0].id if picked is not None else None
    files_with_tables = {f.source_file_id for f in findings if f.source_file_id}
    child_suggestions: list[ChildSuggestionOut] = []
    for finding in findings:
        if finding.id == root_finding_id or finding.source_file_id is None:
            continue
        table = parse_bom_table_value(finding.value)
        if table is None:
            continue
        child_suggestions.append(
            ChildSuggestionOut(
                finding_id=finding.id,
                file_id=finding.source_file_id,
                page=finding.page,
                root_part_number=table.root_part_number,
                rows=table.rows,
            )
        )

    return BuilderStateOut(
        quote_item_id=ctx.quote_item.id,
        root_part_id=ctx.root_part.id,
        root_component_id=ctx.root_component.id,
        draft=draft,
        initial=initial,
        suggestion=_suggestion_out(picked, files) if picked is not None else None,
        quote_files=[
            QuoteFileOut(
                id=f.id,
                part_id=f.part_id,
                filename=f.filename,
                role=f.role,
                part_number_extracted=f.part_number_extracted,
                has_bom_table=f.id in files_with_tables,
            )
            for f in files.values()
        ],
        child_suggestions=child_suggestions,
        unique_parts=unique_part_count(draft.payload if draft else initial),
        cap=UNIQUE_PARTS_CAP,
    )


@bom_router.put("/{quote_item_id}/bom-builder/draft")
async def save_draft(
    quote_item_id: uuid.UUID,
    body: DraftIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> DraftSavedOut:
    """Autosave the staging state (one row per quote item; last write wins)."""
    ctx = await _load_context(session, quote_item_id)
    # Serialize with publish/discard on the quote-item row: an autosave that
    # raced publish would otherwise recreate the just-consumed draft.
    await session.execute(
        select(QuoteItem.id).where(QuoteItem.id == ctx.quote_item.id).with_for_update()
    )
    if not _is_editable(ctx.quote):
        raise AppError(
            "quote_locked",
            "The BOM can only be edited while the quote is a draft.",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = datetime.now(UTC)
    payload = body.payload.model_dump(mode="json")
    await session.execute(
        pg_insert(BomDraft)
        .values(
            org_id=ctx.quote_item.org_id,
            quote_item_id=ctx.quote_item.id,
            payload=payload,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_bom_draft_quote_item",
            set_={"payload": payload, "updated_at": now},
        )
    )
    await session.flush()
    return DraftSavedOut(updated_at=now, unique_parts=unique_part_count(body.payload))


@bom_router.delete("/{quote_item_id}/bom-builder/draft", status_code=status.HTTP_204_NO_CONTENT)
async def discard_draft(
    quote_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
) -> None:
    """Discard the draft — the BOM returns to its published state (KB §BOM drafts)."""
    ctx = await _load_context(session, quote_item_id)
    await session.execute(
        select(QuoteItem.id).where(QuoteItem.id == ctx.quote_item.id).with_for_update()
    )
    await session.execute(sa_delete(BomDraft).where(BomDraft.quote_item_id == ctx.quote_item.id))


async def _resolve_doc(session: AsyncSession, ctx: _Context, payload: BomDoc | None) -> BomDoc:
    """The document to check/publish: the request body, else the stored draft."""
    if payload is not None:
        return payload
    draft_row = await session.scalar(
        select(BomDraft).where(BomDraft.quote_item_id == ctx.quote_item.id)
    )
    if draft_row is None:
        raise AppError(
            "no_draft",
            "There is no BOM draft to publish — save or send the document first.",
            status_code=status.HTTP_409_CONFLICT,
        )
    try:
        return BomDoc.model_validate(draft_row.payload)
    except ValidationError as exc:
        raise AppError(
            "no_draft",
            "The stored BOM draft is unreadable — save the document again.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc


@bom_router.post("/{quote_item_id}/bom-builder/check")
async def check_bom(
    quote_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
    body: CheckIn | None = None,
) -> CheckOut:
    """CHECK BOM — validate the staged structure without committing anything."""
    ctx = await _load_context(session, quote_item_id)
    doc = await _resolve_doc(session, ctx, body.payload if body else None)
    child_nodes, parts, files, _findings, _picked = await _builder_inputs(session, ctx)
    del child_nodes, parts
    errors, notices = validate_doc(doc, set(files.keys()))
    return CheckOut(errors=errors, notices=notices, unique_parts=unique_part_count(doc))


@bom_router.post("/{quote_item_id}/bom-builder/publish")
async def publish_bom(
    quote_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.quote_edit))],
    body: CheckIn | None = None,
) -> PublishOut:
    """CHECK AND PUBLISH — commit the staged tree as part/node/component rows.

    One transaction (the request session): validation errors 409 before any
    mutation; success deletes the draft. Republish reuses parts by part#+rev."""
    ctx = await _load_context(session, quote_item_id)
    # Serialise concurrent publishes on the quote-item row (the add-item
    # precedent, models.py quote_item docstring): two interleaved publishes
    # would otherwise both rebuild the child nodes and double the tree.
    await session.execute(
        select(QuoteItem.id).where(QuoteItem.id == ctx.quote_item.id).with_for_update()
    )
    if not _is_editable(ctx.quote):
        raise AppError(
            "quote_locked",
            "The BOM can only be published while the quote is a draft.",
            status_code=status.HTTP_409_CONFLICT,
        )
    doc = await _resolve_doc(session, ctx, body.payload if body else None)
    child_nodes, parts, files, _findings, _picked = await _builder_inputs(session, ctx)
    errors, notices = validate_doc(doc, set(files.keys()))
    if errors:
        raise AppError(
            "bom_invalid",
            "The BOM has validation errors — resolve them and publish again.",
            status_code=status.HTTP_409_CONFLICT,
            details={
                "errors": [e.model_dump() for e in errors],
                "notices": [n.model_dump() for n in notices],
            },
        )

    tree = await _commit_tree(session, ctx, doc, child_nodes, parts, files)
    await session.execute(sa_delete(BomDraft).where(BomDraft.quote_item_id == ctx.quote_item.id))
    await session.flush()
    return PublishOut(tree=tree)


@bom_router.get("/{quote_item_id}/bom-status")
async def get_bom_status(
    quote_item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> BomStatusOut:
    """The line-item banner: detected BOM table + published/draft state."""
    ctx = await _load_context(session, quote_item_id)
    child_nodes, _parts, files, _findings, picked = await _builder_inputs(session, ctx)
    has_draft = (
        await session.scalar(select(BomDraft.id).where(BomDraft.quote_item_id == ctx.quote_item.id))
        is not None
    )
    return BomStatusOut(
        suggestion=_suggestion_out(picked, files) if picked is not None else None,
        has_children=bool(child_nodes),
        has_draft=has_draft,
    )


# --------------------------------------------------------------------------- #
# Publish — committing the staged tree
# --------------------------------------------------------------------------- #
def _obtain_method_for(row_type: RowType) -> ObtainMethod:
    return ObtainMethod.purchased if row_type == "purchased" else ObtainMethod.manufactured


async def _commit_tree(
    session: AsyncSession,
    ctx: _Context,
    doc: BomDoc,
    child_nodes: list[Node],
    parts: dict[uuid.UUID, Part],
    files: dict[uuid.UUID, PartFile],
) -> PublishedNodeOut:
    org_id = ctx.quote_item.org_id
    root_part = ctx.root_part
    now = datetime.now(UTC)

    # ---- resolve unique parts (link rows by part#+rev; reuse existing) ------ #
    existing_by_key: dict[tuple[str, str], Part] = {}
    for node in child_nodes:
        part = parts[node.part_id]
        existing_key = ((part.part_number or "").strip(), (part.revision or "").strip())
        if existing_key[0]:
            existing_by_key.setdefault(existing_key, part)

    rows = _walk(doc.root)
    non_root_rows = [r for r in rows if r is not doc.root]

    # First occurrence of a key carries the part data (conflicts already blocked).
    # Canonicalize linked rows first: conflicting non-null data was already
    # rejected by validate_doc, so merging here only FILLS gaps — a later
    # linked row's description/files must not be silently discarded just
    # because the first occurrence left them blank (CodeRabbit 2026-07-17).
    canonical: dict[str, BomRow] = {}
    canonical_for_key: dict[tuple[str, str], BomRow] = {}
    for row in non_root_rows:
        key = _part_key(row)
        if key is None:
            canonical[row.row_id] = row
            continue
        merged = canonical_for_key.get(key)
        if merged is None:
            canonical_for_key[key] = row
            canonical[row.row_id] = row
            continue
        supporting = list(dict.fromkeys([*merged.supporting_file_ids, *row.supporting_file_ids]))
        filled = merged.model_copy(
            update={
                "description": merged.description or row.description,
                "primary_file_id": merged.primary_file_id or row.primary_file_id,
                "supporting_file_ids": supporting,
            }
        )
        canonical_for_key[key] = filled
        canonical[merged.row_id] = filled

    part_for_key: dict[tuple[str, str], Part] = {}
    part_for_row: dict[str, Part] = {}
    reused_part_ids: set[uuid.UUID] = set()
    for raw_row in non_root_rows:
        key = _part_key(raw_row)
        if key is not None and key in part_for_key:
            part_for_row[raw_row.row_id] = part_for_key[key]
            continue
        row = canonical.get(raw_row.row_id, raw_row)
        is_assembly = row.row_type == "subassembly" or bool(row.children)
        if row.row_type == "purchased":
            is_assembly = False
        existing = existing_by_key.get(key) if key is not None else None
        if existing is not None:
            part = existing
            reused_part_ids.add(part.id)
        else:
            part = Part(org_id=org_id)
            session.add(part)
        part.part_number = (row.part_number or "").strip() or None
        part.revision = (row.revision or "").strip() or None
        part.description = row.description
        part.is_assembly = is_assembly
        part.obtain_method = _obtain_method_for(row.row_type)
        part_for_row[raw_row.row_id] = part
        if key is not None:
            part_for_key[key] = part
    await session.flush()

    # ---- components: one per unique child part (created if missing) --------- #
    unique_parts = {p.id: p for p in part_for_row.values()}
    existing_components = {
        c.part_id: c
        for c in (
            await session.scalars(
                select(Component).where(
                    Component.part_id.in_(unique_parts.keys()),
                    Component.is_root_component.is_(False),
                )
            )
        ).all()
    }
    for part in unique_parts.values():
        component = existing_components.get(part.id)
        if component is None:
            component = Component(
                org_id=org_id,
                part_id=part.id,
                is_root_component=False,
            )
            session.add(component)
        component.obtain_method = part.obtain_method
        component.is_assembly = part.is_assembly

    # ---- root part/component take the root row's data ----------------------- #
    # The grid is the authority for the root's identity: publishing writes what
    # the estimator sees, including deliberate clears (CodeRabbit 2026-07-17).
    root_row = doc.root
    root_part.part_number = (root_row.part_number or "").strip() or None
    root_part.revision = (root_row.revision or "").strip() or None
    root_part.description = root_row.description
    root_part.is_assembly = root_row.row_type == "assembly_root"
    root_part.obtain_method = ObtainMethod.manufactured
    ctx.root_component.is_assembly = root_part.is_assembly
    ctx.root_component.obtain_method = ObtainMethod.manufactured

    # ---- rebuild nodes (order = sibling position; flat qty stays derived) --- #
    await session.execute(
        sa_delete(Node).where(Node.root_part_id == root_part.id, Node.parent_node_id.is_not(None))
    )
    await session.flush()

    created_nodes: list[tuple[Node, BomRow, Part]] = []

    async def create_children(parent_node: Node, parent_row: BomRow) -> None:
        for index, row in enumerate(parent_row.children):
            part = part_for_row[row.row_id]
            node = Node(
                org_id=org_id,
                part_id=part.id,
                parent_node_id=parent_node.id,
                qty_relative_to_parent=row.qty,
                root_part_id=root_part.id,
                position=index,
            )
            session.add(node)
            await session.flush()
            created_nodes.append((node, row, part))
            await create_children(node, row)

    await create_children(ctx.root_node, root_row)

    # ---- retire parts that vanished from the tree --------------------------- #
    kept_part_ids = set(unique_parts.keys())
    removed_parts = [
        parts[node.part_id]
        for node in child_nodes
        if node.part_id not in kept_part_ids and node.part_id != root_part.id
    ]
    removed_seen: set[uuid.UUID] = set()
    for part in removed_parts:
        if part.id in removed_seen:
            continue
        removed_seen.add(part.id)
        # Only a part NO tree references anymore loses its child component —
        # a part still nodded elsewhere keeps it (deleting would CASCADE its
        # ComponentQuantity pricing cells away). Latent today (builder parts
        # are per-tree) but load-bearing once library parts join BOMs (M4.10).
        still_referenced = await session.scalar(
            select(Node.id).where(Node.part_id == part.id).limit(1)
        )
        if still_referenced is not None:
            continue
        await session.execute(
            sa_delete(Component).where(
                Component.part_id == part.id, Component.is_root_component.is_(False)
            )
        )
        other_component = await session.scalar(
            select(Component.id).where(Component.part_id == part.id).limit(1)
        )
        if other_component is None:
            # ASSUMED (M4.9): a builder-created part nothing references anymore
            # is soft-deleted rather than left to pollute the Part Library. Its
            # files return to the root's Quote Files staging first (KB
            # §Removing files: "sent back to Quote Files") — they would
            # otherwise vanish from the next builder session's scope.
            orphan_files = (
                await session.scalars(select(PartFile).where(PartFile.part_id == part.id))
            ).all()
            part.primary_file_id = None
            await session.flush()
            for orphan in orphan_files:
                orphan.part_id = root_part.id
                orphan.role = "supporting"
            part.deleted_at = now

    # ---- file assignments: move staged files onto their parts --------------- #
    async def assign_files(row: BomRow, part: Part) -> None:
        if row.primary_file_id is not None:
            file = files[row.primary_file_id]
            if file.part_id != part.id or file.role != "primary":
                current_primary = await session.scalar(
                    select(PartFile).where(PartFile.part_id == part.id, PartFile.role == "primary")
                )
                if current_primary is not None and current_primary.id != file.id:
                    current_primary.role = "supporting"
                source_part = parts.get(file.part_id)
                if source_part is not None and source_part.primary_file_id == file.id:
                    source_part.primary_file_id = None
                file.part_id = part.id
                file.role = "primary"
                # The composite FK (primary_file_id, id) → part_file(id, part_id)
                # needs the file's move flushed before the pointer can reference it.
                await session.flush()
            part.primary_file_id = file.id
        for file_id in row.supporting_file_ids:
            file = files[file_id]
            if file.part_id == part.id and file.role == "primary":
                # Staged as supporting on its own part: demote (the document
                # is the authority for roles at publish).
                if row.primary_file_id != file.id:
                    part.primary_file_id = None
                    await session.flush()
                    file.role = "supporting"
                continue
            if file.part_id != part.id:
                # Moving a part's PRIMARY away as another part's supporting
                # file must clear the source pointer, or the composite FK
                # (primary_file_id, id) → part_file(id, part_id) breaks.
                source_part = parts.get(file.part_id)
                if source_part is not None and source_part.primary_file_id == file.id:
                    source_part.primary_file_id = None
                    await session.flush()
                file.part_id = part.id
                file.role = "supporting"

    assigned: set[uuid.UUID] = set()
    for _node, row, part in created_nodes:
        if part.id in assigned:
            continue
        assigned.add(part.id)
        # The canonical (merged) row — a later linked row's file assignment
        # must land even when the first occurrence carried none.
        await assign_files(canonical.get(row.row_id, row), part)
    await assign_files(root_row, root_part)
    await session.flush()

    # ---- response tree (flat qty multiplies down from the root) ------------- #
    children_of: dict[uuid.UUID, list[tuple[Node, BomRow, Part]]] = {}
    for node, row, part in created_nodes:
        assert node.parent_node_id is not None  # created as children above
        children_of.setdefault(node.parent_node_id, []).append((node, row, part))

    def build_out(
        node: Node, row: BomRow, part: Part, *, multiplier: int, is_root: bool
    ) -> PublishedNodeOut:
        flat = multiplier * node.qty_relative_to_parent
        return PublishedNodeOut(
            node_id=node.id,
            part_id=part.id,
            part_number=part.part_number,
            revision=part.revision,
            description=part.description,
            row_type=row.row_type,
            qty_relative_to_parent=node.qty_relative_to_parent,
            flat_qty=flat,
            position=node.position,
            children=[
                build_out(n, r, p, multiplier=flat, is_root=False)
                for n, r, p in children_of.get(node.id, [])
            ],
        )

    return build_out(ctx.root_node, root_row, root_part, multiplier=1, is_root=True)
