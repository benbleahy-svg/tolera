"""Unit tests for the quotes filter/sort grammar (M1.3) — no DB required.

Exercises the allow-list: a valid ``{field, op, value}`` parses and coerces; an
unknown field, an op a field doesn't support, or a malformed value is a clean
``ValidationError`` (→ 422 at the edge), never a 500 or a raw SQL error.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models import Quote
from app.quote_filters import (
    FilterClause,
    SortClause,
    apply_filters,
    apply_sort,
    apply_system_view,
    is_system_view,
)


def _clause(**kw: object) -> FilterClause:
    return FilterClause.model_validate(kw)


# --------------------------------------------------------------------------- #
# Valid clauses
# --------------------------------------------------------------------------- #
def test_status_eq_and_in_are_valid() -> None:
    _clause(field="status", op="eq", value="draft")
    _clause(field="status", op="in", value=["draft", "sent"])


def test_uuid_field_eq_in_is_null_are_valid() -> None:
    some = str(uuid.uuid4())
    _clause(field="salesperson_id", op="eq", value=some)
    _clause(field="account_id", op="in", value=[some])
    _clause(field="estimator_id", op="is_null", value=True)


def test_datetime_range_and_due_date_is_null_are_valid() -> None:
    _clause(field="created_at", op="gte", value="2026-06-01T00:00:00Z")
    _clause(field="created_at", op="lte", value="2026-06-30")
    _clause(field="due_date", op="is_null", value=False)


# --------------------------------------------------------------------------- #
# Rejected clauses (allow-list enforcement)
# --------------------------------------------------------------------------- #
def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        _clause(field="priority", op="eq", value="high")  # priority is not a v1 field


def test_op_not_allowed_for_field_rejected() -> None:
    with pytest.raises(ValidationError):
        _clause(field="status", op="gte", value="draft")  # status has no range op
    with pytest.raises(ValidationError):
        _clause(field="created_at", op="eq", value="2026-06-01")  # datetime has no eq


def test_in_requires_nonempty_list() -> None:
    with pytest.raises(ValidationError):
        _clause(field="status", op="in", value="draft")  # not a list
    with pytest.raises(ValidationError):
        _clause(field="status", op="in", value=[])  # empty


def test_is_null_requires_bool() -> None:
    with pytest.raises(ValidationError):
        _clause(field="account_id", op="is_null", value="yes")


def test_scalar_op_rejects_list_and_null() -> None:
    with pytest.raises(ValidationError):
        _clause(field="status", op="eq", value=["draft"])
    with pytest.raises(ValidationError):
        _clause(field="status", op="eq", value=None)


def test_malformed_values_rejected() -> None:
    with pytest.raises(ValidationError):
        _clause(field="status", op="eq", value="not-a-status")
    with pytest.raises(ValidationError):
        _clause(field="account_id", op="eq", value="not-a-uuid")
    with pytest.raises(ValidationError):
        _clause(field="created_at", op="gte", value="not-a-date")
    with pytest.raises(ValidationError):
        _clause(field="account_id", op="in", value=["not-a-uuid"])


def test_extra_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        _clause(field="status", op="eq", value="draft", extra="x")


# --------------------------------------------------------------------------- #
# Sort clauses
# --------------------------------------------------------------------------- #
def test_sort_defaults_to_asc_and_validates_field() -> None:
    assert SortClause.model_validate({"field": "created_at"}).dir.value == "asc"
    SortClause.model_validate({"field": "number", "dir": "desc"})
    with pytest.raises(ValidationError):
        SortClause.model_validate({"field": "account_id"})  # not a sortable field


# --------------------------------------------------------------------------- #
# Application produces SQL (compiled-string smoke checks; no DB)
# --------------------------------------------------------------------------- #
def _sql(stmt: object) -> str:
    return str(stmt).lower()


def test_apply_filters_emits_where_per_clause() -> None:
    stmt = apply_filters(
        Quote.__table__.select(),
        [
            _clause(field="status", op="in", value=["draft", "sent"]),
            _clause(field="salesperson_id", op="is_null", value=True),
        ],
    )
    sql = _sql(stmt)
    assert "status in" in sql
    assert "salesperson_id is null" in sql


def test_apply_sort_defaults_to_created_at_desc_with_id_tiebreak() -> None:
    sql = _sql(apply_sort(Quote.__table__.select(), []))
    assert "order by" in sql
    assert "created_at desc" in sql
    assert "id desc" in sql  # deterministic tiebreaker


def test_system_views_registered_and_appliable() -> None:
    assert is_system_view("overdue")
    assert not is_system_view("nope")
    sql = _sql(apply_system_view(Quote.__table__.select(), "my-quotes", user_id=uuid.uuid4()))
    assert "salesperson_id =" in sql and "estimator_id =" in sql
