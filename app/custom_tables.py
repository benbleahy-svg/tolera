"""Custom Tables API (M1.9) — the org tables behind Kalk ``table_var`` /
``table_lookup`` (spec ``#kalk-tables``; DECISIONS.md 2026-07-08).

Surface (Configure → Custom Tables; mutations need ``config_edit``, reads
``view_all`` — estimators browse tables from the quoting UI):

* ``GET  /api/custom-tables``               — list (id, name, columns, row_count)
* ``POST /api/custom-tables``               — create (name + typed columns)
* ``GET  /api/custom-tables/{id}``          — detail incl. rows
* ``PATCH /api/custom-tables/{id}``         — rename / edit columns (rows are
  coerced: removed columns drop, added columns fill null, a type change nulls
  values that no longer fit — documented, reversible)
* ``DELETE /api/custom-tables/{id}``        — delete (rows cascade)
* ``PUT  /api/custom-tables/{id}/rows``     — replace all rows (spreadsheet save)
* ``POST /api/custom-tables/{id}/import``   — CSV upload replacing all rows

Column names are alphanumeric with no leading digit (dot-accessed in Kalk);
types are **boolean | numeric | string**; row count is capped at the
``table_lookup`` bound (10,000). Values are stored in JSONB; ``null`` = empty
cell (never matches a filter, sorts last — the tables runtime contract).
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import CustomTable, CustomTableRow
from .services.kalk.tables import COLUMN_TYPES, TABLE_LOOKUP_MAX_ROWS

custom_tables_router = APIRouter(prefix="/api/custom-tables", tags=["custom-tables"])

#: Kalk dot-access requires identifier-shaped names; leading underscores are
#: forbidden in the sandbox grammar, so column names start with a letter.
_COLUMN_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_MAX_CSV_BYTES = 5 * 1024 * 1024

_TRUE_WORDS = frozenset({"true", "1", "yes", "ja", "wahr", "x"})
_FALSE_WORDS = frozenset({"false", "0", "no", "nein", "falsch", ""})


class ColumnSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)]
    type: str

    def validated(self) -> ColumnSpec:
        if not _COLUMN_NAME.match(self.name):
            raise AppError(
                "invalid_column_name",
                f"Column name {self.name!r} must be alphanumeric and start with a letter.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if self.type not in COLUMN_TYPES:
            raise AppError(
                "invalid_column_type",
                f"Column type must be one of: {', '.join(COLUMN_TYPES)}.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return self


class CustomTableCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    columns: Annotated[list[ColumnSpec], Field(min_length=1, max_length=100)]


class CustomTableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    columns: Annotated[list[ColumnSpec] | None, Field(min_length=1, max_length=100)] = None


class RowsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: Annotated[
        list[dict[str, bool | int | float | str | None]],
        Field(max_length=TABLE_LOOKUP_MAX_ROWS),
    ]


class CustomTableOut(BaseModel):
    id: uuid.UUID
    name: str
    columns: list[ColumnSpec]
    row_count: int


class CustomTableDetail(CustomTableOut):
    rows: list[dict[str, Any]]  # includes row_number


def _validate_columns(columns: list[ColumnSpec]) -> list[dict[str, str]]:
    seen: set[str] = set()
    for col in columns:
        col.validated()
        if col.name in seen:
            raise AppError(
                "duplicate_column",
                f"Column {col.name!r} is listed twice.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        seen.add(col.name)
    return [{"name": c.name, "type": c.type} for c in columns]


def _value_fits(value: Any, column_type: str) -> bool:
    if value is None:
        return True
    if column_type == "boolean":
        return isinstance(value, bool)
    if column_type == "numeric":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, str)


def _coerce_rows_to_columns(
    rows: list[CustomTableRow], columns: list[dict[str, str]]
) -> None:
    """After a column edit: drop removed keys, null new/no-longer-fitting cells."""
    for row in rows:
        data = {
            col["name"]: (
                row.data.get(col["name"])
                if _value_fits(row.data.get(col["name"]), col["type"])
                else None
            )
            for col in columns
        }
        row.data = data


def _validate_row(
    data: dict[str, Any], columns: list[dict[str, str]], index: int
) -> dict[str, Any]:
    by_name = {c["name"]: c["type"] for c in columns}
    unknown = set(data) - set(by_name)
    if unknown:
        raise AppError(
            "unknown_column",
            f"Row {index + 1} has values for unknown columns: {', '.join(sorted(unknown))}.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    clean: dict[str, Any] = {}
    for name, column_type in by_name.items():
        value = data.get(name)
        if not _value_fits(value, column_type):
            raise AppError(
                "invalid_cell",
                f"Row {index + 1}, column {name!r}: value does not fit type {column_type}.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        clean[name] = value
    return clean


async def _get_table_or_404(session: AsyncSession, table_id: uuid.UUID) -> CustomTable:
    table = await session.get(CustomTable, table_id)
    if table is None:
        raise AppError(
            "not_found", "Custom table not found.", status_code=status.HTTP_404_NOT_FOUND
        )
    return table


async def _row_count(session: AsyncSession, table_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(CustomTableRow)
            .where(CustomTableRow.table_id == table_id)
        )
    ) or 0


def _out(table: CustomTable, row_count: int) -> CustomTableOut:
    return CustomTableOut(
        id=table.id,
        name=table.name,
        columns=[ColumnSpec(name=c["name"], type=c["type"]) for c in table.columns],
        row_count=row_count,
    )


async def _replace_rows(
    session: AsyncSession,
    table: CustomTable,
    clean_rows: list[dict[str, Any]],
    org_id: uuid.UUID,
) -> None:
    existing = (
        await session.scalars(
            select(CustomTableRow).where(CustomTableRow.table_id == table.id)
        )
    ).all()
    for row in existing:
        await session.delete(row)
    await session.flush()
    for index, data in enumerate(clean_rows):
        session.add(
            CustomTableRow(
                org_id=org_id, table_id=table.id, row_number=index + 1, data=data
            )
        )
    await session.flush()


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@custom_tables_router.get("")
async def list_custom_tables(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> list[CustomTableOut]:
    tables = (await session.scalars(select(CustomTable).order_by(CustomTable.name))).all()
    counts = dict(
        (
            await session.execute(
                select(CustomTableRow.table_id, func.count()).group_by(CustomTableRow.table_id)
            )
        )
        .tuples()
        .all()
    )
    return [_out(table, counts.get(table.id, 0)) for table in tables]


@custom_tables_router.post("", status_code=status.HTTP_201_CREATED)
async def create_custom_table(
    payload: CustomTableCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> CustomTableOut:
    columns = _validate_columns(payload.columns)
    duplicate = await session.scalar(
        select(CustomTable.id).where(CustomTable.name == payload.name)
    )
    if duplicate is not None:
        raise AppError(
            "duplicate_table",
            "A custom table with this name already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )
    table = CustomTable(org_id=principal.active_org_id, name=payload.name, columns=columns)
    session.add(table)
    await session.flush()
    return _out(table, 0)


@custom_tables_router.get("/{table_id}")
async def get_custom_table(
    table_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.view_all))],
) -> CustomTableDetail:
    table = await _get_table_or_404(session, table_id)
    rows = (
        await session.scalars(
            select(CustomTableRow)
            .where(CustomTableRow.table_id == table.id)
            .order_by(CustomTableRow.row_number)
        )
    ).all()
    return CustomTableDetail(
        id=table.id,
        name=table.name,
        columns=[ColumnSpec(name=c["name"], type=c["type"]) for c in table.columns],
        row_count=len(rows),
        rows=[{"row_number": r.row_number, **r.data} for r in rows],
    )


@custom_tables_router.patch("/{table_id}")
async def update_custom_table(
    table_id: uuid.UUID,
    payload: CustomTableUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> CustomTableOut:
    table = await _get_table_or_404(session, table_id)
    if payload.name is not None and payload.name != table.name:
        duplicate = await session.scalar(
            select(CustomTable.id).where(CustomTable.name == payload.name)
        )
        if duplicate is not None:
            raise AppError(
                "duplicate_table",
                "A custom table with this name already exists.",
                status_code=status.HTTP_409_CONFLICT,
            )
        table.name = payload.name
    if payload.columns is not None:
        columns = _validate_columns(payload.columns)
        table.columns = columns
        rows = (
            await session.scalars(
                select(CustomTableRow).where(CustomTableRow.table_id == table.id)
            )
        ).all()
        _coerce_rows_to_columns(list(rows), columns)
    await session.flush()
    return _out(table, await _row_count(session, table.id))


@custom_tables_router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_table(
    table_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> None:
    table = await _get_table_or_404(session, table_id)
    await session.delete(table)  # rows cascade
    await session.flush()


@custom_tables_router.put("/{table_id}/rows")
async def replace_rows(
    table_id: uuid.UUID,
    payload: RowsUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> CustomTableDetail:
    table = await _get_table_or_404(session, table_id)
    columns = list(table.columns)
    clean = [_validate_row(row, columns, i) for i, row in enumerate(payload.rows)]
    await _replace_rows(session, table, clean, principal.active_org_id)
    return CustomTableDetail(
        id=table.id,
        name=table.name,
        columns=[ColumnSpec(name=c["name"], type=c["type"]) for c in table.columns],
        row_count=len(clean),
        rows=[{"row_number": i + 1, **data} for i, data in enumerate(clean)],
    )


@custom_tables_router.post("/{table_id}/import")
async def import_csv(
    table_id: uuid.UUID,
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.config_edit))],
) -> CustomTableOut:
    """Replace all rows from a CSV whose header names the table's columns
    (order-insensitive; extra/missing headers are a clean 422). Values parse by
    column type — numeric via float/int, boolean via ja/nein/true/false/1/0 —
    and an empty cell is null."""
    table = await _get_table_or_404(session, table_id)
    raw = await file.read()
    if len(raw) > _MAX_CSV_BYTES:
        raise AppError(
            "file_too_large",
            "CSV imports are limited to 5 MB.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError(
            "invalid_csv",
            "The file is not UTF-8 encoded text.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from None

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise AppError(
            "invalid_csv", "The CSV is empty.", status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        ) from None
    header = [h.strip() for h in header]
    expected = [c["name"] for c in table.columns]
    if sorted(header) != sorted(expected):
        raise AppError(
            "csv_header_mismatch",
            f"The CSV header must name exactly these columns: {', '.join(expected)}.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    types = {c["name"]: c["type"] for c in table.columns}

    rows: list[dict[str, Any]] = []
    for index, record in enumerate(reader):
        if len(rows) >= TABLE_LOOKUP_MAX_ROWS:
            raise AppError(
                "too_many_rows",
                f"Custom tables are limited to {TABLE_LOOKUP_MAX_ROWS} rows.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if not record or all(not cell.strip() for cell in record):
            continue  # skip blank lines
        if len(record) != len(header):
            raise AppError(
                "invalid_csv",
                f"Row {index + 1} has {len(record)} cells, expected {len(header)}.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data: dict[str, Any] = {}
        for name, cell in zip(header, record, strict=True):
            data[name] = _parse_cell(cell.strip(), types[name], name, index)
        rows.append(data)

    await _replace_rows(session, table, rows, principal.active_org_id)
    return _out(table, len(rows))


def _parse_cell(cell: str, column_type: str, name: str, index: int) -> Any:
    if cell == "":
        return None
    if column_type == "string":
        return cell
    if column_type == "numeric":
        try:
            value = float(cell.replace(",", "."))  # accept German decimal commas
        except ValueError:
            raise AppError(
                "invalid_cell",
                f"Row {index + 1}, column {name!r}: {cell!r} is not a number.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from None
        return int(value) if value.is_integer() else value
    lowered = cell.lower()
    if lowered in _TRUE_WORDS:
        return True
    if lowered in _FALSE_WORDS:
        return False
    raise AppError(
        "invalid_cell",
        f"Row {index + 1}, column {name!r}: {cell!r} is not a boolean.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
