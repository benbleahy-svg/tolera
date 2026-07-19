"""Data-subject rights: Auskunft/Export + Löschung/Erasure (M6.9).

DACH-DELTA-LAYER §5 requires "data-subject rights (Auskunft/Löschung/
Portabilität)" with "retention reconciled with GoBD". This module is the engine;
:mod:`app.retention` holds the policy it executes, so *what* happens to which
column is reviewable as a table rather than buried in control flow.

**The subject is an email address.** Every data subject this surface can act on —
customer contact, account channel, RFQ enquirer, vendor contact, portal recipient
— is reached through an address. Internal users (``app_user``) are deliberately
out of scope: they are a platform identity shared across orgs (E4-a), so erasing
one from a single org's admin surface would reach into another tenant's data.
:data:`app.retention.RETENTION_POLICY` says so explicitly, and the erasure report
repeats it rather than staying silent.

**Org-scoped by construction.** Both endpoints run on the ordinary RLS-bound
session pinned to the caller's active org, so a subject who is a contact at two
tenants gets two separate answers — never one merged one (E4-a: "export/erasure
must respect per-org membership — no cross-org data leakage"). There is no
``org_id`` predicate written by hand anywhere below; RLS is the boundary, exactly
as it is for every other read in the app.

**Admin-only** (:attr:`~app.authz.Permission.compliance_manage`): export returns
a person's complete personal data and erasure destroys it. ``settings_edit``
would have leaked both to managers.

Erasure is **irreversible**, so it carries a confirmation ceremony: the caller
must echo the subject's address in ``confirm_email``. A mistyped address should
not be able to anonymise a live customer.

**SQL construction note.** The statements below interpolate table and column
names, which are *not* user input — they come from the frozen tuples in
:mod:`app.retention` and :data:`SUBJECT_LOCATORS` in this module. Every value a
caller supplies is a bound parameter. :func:`_assert_identifier` enforces the
former structurally so a future policy edit cannot turn into an injection.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .authz import Permission, require
from .deps import get_session
from .errors import AppError
from .models import GdprRequestKind, GdprRequestLog
from .retention import (
    ERASURE_POLICY,
    RETENTION_POLICY,
    Disposition,
    policy_report,
    tombstone_email,
)

gdpr_router = APIRouter(prefix="/api/settings/privacy", tags=["settings"])

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _assert_identifier(name: str) -> str:
    """Structural guard on every interpolated table/column name.

    These names come from module constants, not from callers — but this makes
    that a property the code enforces rather than one a reader has to verify.
    """
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"unsafe SQL identifier in retention policy: {name!r}")
    return name


@dataclass(frozen=True)
class SubjectLocator:
    """One place a data subject is reachable by email address.

    ``context_columns`` are non-personal columns included in the export so the
    subject can tell *which* record each entry is (Art. 15 asks for the data, and
    a bare list of their own address back is not a useful answer).
    """

    table: str
    email_column: str
    context_columns: tuple[str, ...]
    #: True when the column's type is ``citext``, which compares
    #: case-insensitively in the database. The four customer/vendor tables use it;
    #: ``quote_token.recipient_email`` and ``vendor_rfq_recipient.contact_email``
    #: are plain ``text``. Without this distinction an erasure would silently
    #: skip exactly those two rows for an address typed in different case —
    #: returning 200 with a partial result that reads as a complete erasure.
    citext: bool = True

    @property
    def match_predicate(self) -> str:
        """SQL comparing the email column to ``:email``.

        ``citext`` columns are compared directly so their indexes stay usable;
        plain ``text`` columns are folded on both sides."""
        column = _assert_identifier(self.email_column)
        if self.citext:
            return f"{column} = :email"
        return f"lower({column}) = lower(:email)"


#: Every table where a customer/vendor data subject is reachable. Deliberately
#: does not include ``app_user`` (see the module docstring).
SUBJECT_LOCATORS: tuple[SubjectLocator, ...] = (
    SubjectLocator("contact", "email", ("id", "account_id", "created_at", "deleted_at")),
    SubjectLocator("account", "email", ("id", "name", "created_at", "deleted_at")),
    SubjectLocator("request_for_quote", "email", ("id", "quote_id", "created_at")),
    SubjectLocator("vendor_contact", "email", ("id", "vendor_id", "created_at", "deleted_at")),
    SubjectLocator(
        "quote_token",
        "recipient_email",
        ("id", "scope", "quote_id", "created_at"),
        citext=False,
    ),
    SubjectLocator(
        "vendor_rfq_recipient", "contact_email", ("id", "rfq_id", "sent_at"), citext=False
    ),
)


def _erasable_columns(table: str) -> tuple[str, ...]:
    """The columns :mod:`app.retention` says to overwrite for this table."""
    return tuple(
        rule.column
        for rule in ERASURE_POLICY
        if rule.table == table and rule.disposition is Disposition.anonymize
    )


def _tombstone_for(table: str, column: str, row_id: uuid.UUID) -> str | None:
    """The replacement value for one column of one row.

    ``"unique-email"`` resolves **per row**, not per request: ``contact.email`` is
    NOT NULL under a live-unique partial index, so two live rows for the same
    subject would collide on a shared constant.
    """
    rule = next(r for r in ERASURE_POLICY if r.table == table and r.column == column)
    if rule.tombstone == "unique-email":
        return tombstone_email(row_id)
    return rule.tombstone


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class SubjectRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ErasureRequest(SubjectRequest):
    #: Must equal ``email``. Erasure is irreversible; a single mistyped field
    #: should not be able to anonymise a live customer.
    confirm_email: str = Field(min_length=3, max_length=320)


class SubjectExport(BaseModel):
    """The Art. 15 (Auskunft) / Art. 20 (Portabilität) answer."""

    email: str
    org_id: str
    generated_at: datetime
    #: table -> the subject's rows in it, personal columns spelled out.
    records: dict[str, list[dict[str, Any]]]
    record_count: int
    #: What this org holds but does not return as personal data, and why —
    #: so the answer is transparent about the boundary it drew.
    retained_categories: list[dict[str, str]]


class ErasureReport(BaseModel):
    """The Art. 17 (Löschung) answer, reconciled with GoBD."""

    email: str
    org_id: str
    performed_at: datetime
    #: table -> number of rows anonymised.
    anonymized: dict[str, int]
    anonymized_row_count: int
    #: Records knowingly left intact, with the obligation that required it.
    #: Reported in full: an erasure report that silently omits what survived is
    #: worse than no report at all.
    retained: list[dict[str, str]]


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def _retained_report() -> list[dict[str, str]]:
    return [
        {"table": rule.table, "column": rule.column, "reason": rule.reason}
        for rule in RETENTION_POLICY
    ]


def _record_request(
    session: AsyncSession,
    *,
    principal: Principal,
    kind: GdprRequestKind,
    email: str,
    affected: dict[str, int],
) -> None:
    """File the request in the append-only :class:`GdprRequestLog`.

    Shares the caller's transaction on purpose: if the erasure rolls back, so
    does its record, and the log never claims a destruction that did not happen.
    """
    session.add(
        GdprRequestLog(
            org_id=principal.active_org_id,
            actor_user_id=principal.user_id,
            kind=kind,
            subject_email=email,
            affected=dict(affected),
            affected_row_count=sum(affected.values()),
        )
    )


@gdpr_router.post("/subject-export", response_model=SubjectExport)
async def export_subject(
    payload: SubjectRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.compliance_manage))],
) -> SubjectExport:
    """Auskunft/Portabilität: everything this org holds about one address.

    Returns an empty ``records`` map (not a 404) when the address is unknown —
    "we hold nothing about you" is a valid and complete Art. 15 answer, and a 404
    would leak whether an address is a customer of this shop.
    """
    email = payload.email.strip()
    records: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for locator in SUBJECT_LOCATORS:
        table = _assert_identifier(locator.table)
        columns = [
            _assert_identifier(c)
            for c in (
                *locator.context_columns,
                locator.email_column,
                *_erasable_columns(locator.table),
            )
        ]
        # dict.fromkeys preserves order while de-duplicating (the email column
        # is usually in the erasable set too).
        select_list = ", ".join(dict.fromkeys(columns))
        rows = (
            await session.execute(
                text(f"SELECT {select_list} FROM {table} WHERE {locator.match_predicate}"),
                {"email": email},
            )
        ).mappings()
        found = [{k: _jsonable(v) for k, v in row.items()} for row in rows]
        if found:
            records[locator.table] = found
            total += len(found)

    # An access request is itself a processing activity worth evidencing — and
    # it exposes a person's whole record, so who ran it matters.
    _record_request(
        session,
        principal=principal,
        kind=GdprRequestKind.export,
        email=email,
        affected={table: len(rows) for table, rows in records.items()},
    )
    return SubjectExport(
        email=email,
        org_id=str(principal.active_org_id),
        generated_at=datetime.now(UTC),
        records=records,
        record_count=total,
        retained_categories=_retained_report(),
    )


@gdpr_router.post("/subject-erasure", response_model=ErasureReport)
async def erase_subject(
    payload: ErasureRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require(Permission.compliance_manage))],
) -> ErasureReport:
    """Löschung: anonymise the subject's direct identifiers, org-scoped.

    GoBD-mandated records (orders, quotes, the append-only event and
    correspondence tables) are **not** touched — the reconciliation
    DACH-DELTA §63 requires — and every one of them is named in ``retained`` so
    the requester learns what survived and under which obligation.
    """
    email = payload.email.strip()
    if payload.confirm_email.strip() != email:
        raise AppError(
            "confirmation_mismatch",
            "Bestätigung stimmt nicht überein — die E-Mail-Adresse muss identisch "
            "wiederholt werden. Die Löschung ist unwiderruflich.",
            status_code=422,
        )

    anonymized: dict[str, int] = {}
    total = 0
    for locator in SUBJECT_LOCATORS:
        table = _assert_identifier(locator.table)
        erasable = _erasable_columns(locator.table)
        if not erasable:
            continue
        # Row ids first: the tombstone address is derived per row, and the
        # e-mail predicate stops matching the moment the first row is rewritten.
        ids = list(
            (
                await session.execute(
                    text(f"SELECT id FROM {table} WHERE {locator.match_predicate}"),
                    {"email": email},
                )
            ).scalars()
        )
        for row_id in ids:
            assignments = []
            params: dict[str, Any] = {"row_id": row_id}
            for column in erasable:
                col = _assert_identifier(column)
                assignments.append(f"{col} = :val_{col}")
                params[f"val_{col}"] = _tombstone_for(locator.table, column, row_id)
            await session.execute(
                text(f"UPDATE {table} SET {', '.join(assignments)} WHERE id = :row_id"),
                params,
            )
        if ids:
            anonymized[locator.table] = len(ids)
            total += len(ids)

    _record_request(
        session,
        principal=principal,
        kind=GdprRequestKind.erasure,
        email=email,
        affected=anonymized,
    )
    await session.flush()
    return ErasureReport(
        email=email,
        org_id=str(principal.active_org_id),
        performed_at=datetime.now(UTC),
        anonymized=anonymized,
        anonymized_row_count=total,
        retained=_retained_report(),
    )


@gdpr_router.get("/retention-policy")
async def get_retention_policy(
    principal: Annotated[Principal, Depends(require(Permission.compliance_manage))],
) -> list[dict[str, str]]:
    """The full GDPR-vs-GoBD policy — the machine-readable half of the ROPA."""
    return policy_report()


def _jsonable(value: Any) -> Any:
    """UUIDs and timestamps become strings; everything else passes through."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
