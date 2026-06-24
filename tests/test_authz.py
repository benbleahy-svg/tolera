"""M0.3 authorization policy — the role x permission matrix is the contract.

These tests pin the *single source of truth* (``app.authz``): a declarative
oracle (``EXPECTED``) is asserted cell-by-cell against the module, so any drift
between the spec ``#authz`` matrix (+ the three DECISIONS.md 2026-06-24
overrides) and the code fails here. The endpoint tests prove the ``require()``
guard enforces that matrix at the API layer (401 unauth is covered by
``test_tenancy``); they need no database.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import Principal, get_principal
from app.authz import (
    ROLE_PERMISSIONS,
    Permission,
    ReviewStage,
    has_permission,
    permissions_for,
    require,
)
from app.errors import register_exception_handlers
from app.models import MembershipRole

R = MembershipRole
P = Permission

_ALL: frozenset[Permission] = frozenset(Permission)
_EDIT_SET = {P.view_all, P.quote_annotate, P.quote_edit, P.quote_finalize}
_SUPPORT_SET = {P.view_all, P.quote_annotate}

# The declarative oracle: spec #authz matrix + DECISIONS.md 2026-06-24 overrides
# (manager == admin; sales/estimator have no delete; viewer is read-only).
EXPECTED: dict[MembershipRole, set[Permission]] = {
    R.admin: set(_ALL),
    R.manager: set(_ALL),
    R.salesperson: set(_EDIT_SET),
    R.estimator: set(_EDIT_SET),
    R.engineer: set(_SUPPORT_SET),
    R.material_purchasing: set(_SUPPORT_SET),
    R.outside_service: set(_SUPPORT_SET),
    R.viewer: {P.view_all},
}


# --------------------------------------------------------------------------- #
# The matrix is complete and correct, cell by cell.
# --------------------------------------------------------------------------- #
def test_oracle_covers_every_role_and_permission() -> None:
    """Guards against a new enum value silently slipping past the matrix."""
    assert set(EXPECTED) == set(MembershipRole)
    assert set(ROLE_PERMISSIONS) == set(MembershipRole)
    for role, perms in ROLE_PERMISSIONS.items():
        assert perms <= _ALL, f"{role} maps to an unknown permission"


@pytest.mark.parametrize("permission", list(Permission))
@pytest.mark.parametrize("role", list(MembershipRole))
def test_matrix_cell(role: MembershipRole, permission: Permission) -> None:
    """Every (role, permission) cell matches the oracle — in the map and via the API."""
    expected = permission in EXPECTED[role]
    assert (permission in ROLE_PERMISSIONS[role]) is expected
    assert has_permission((role,), permission) is expected


# --------------------------------------------------------------------------- #
# Effective permissions are the union over a membership's roles.
# --------------------------------------------------------------------------- #
def test_effective_permissions_are_the_union() -> None:
    roles = (R.engineer, R.salesperson)
    assert permissions_for(roles) == frozenset(EXPECTED[R.engineer] | EXPECTED[R.salesperson])


def test_a_read_only_role_never_subtracts_from_the_union() -> None:
    assert permissions_for((R.viewer, R.estimator)) == permissions_for((R.estimator,))


def test_no_roles_grants_nothing() -> None:
    assert permissions_for(()) == frozenset()


# --------------------------------------------------------------------------- #
# The three DECISIONS.md 2026-06-24 overrides, pinned as regressions.
# --------------------------------------------------------------------------- #
def test_manager_can_finalize() -> None:
    """Deliberate divergence from spec #authz (which keeps finalize off Exec)."""
    assert has_permission((R.manager,), P.quote_finalize)
    assert permissions_for((R.manager,)) == permissions_for((R.admin,))


def test_sales_and_estimator_cannot_delete() -> None:
    """Under-grant: owner-only delete is deferred until ownership exists (M1/M5)."""
    assert not has_permission((R.salesperson,), P.quote_delete)
    assert not has_permission((R.estimator,), P.quote_delete)
    assert has_permission((R.admin,), P.quote_delete)
    assert has_permission((R.manager,), P.quote_delete)


def test_viewer_is_read_only() -> None:
    assert permissions_for((R.viewer,)) == frozenset({P.view_all})


@pytest.mark.parametrize("role", [R.engineer, R.material_purchasing, R.outside_service])
def test_support_roles_annotate_but_do_not_edit(role: MembershipRole) -> None:
    assert has_permission((role,), P.quote_annotate)
    assert not has_permission((role,), P.quote_edit)


# --------------------------------------------------------------------------- #
# Review stages are quote-item states, NOT roles (acceptance criterion).
# --------------------------------------------------------------------------- #
def test_review_stages_are_not_roles() -> None:
    """No review stage masquerades as a role (and vice versa)."""
    role_values = {r.value for r in MembershipRole}
    stage_values = {s.value for s in ReviewStage}
    assert role_values.isdisjoint(stage_values)


def test_the_five_default_review_stages() -> None:
    assert [s.value for s in ReviewStage] == [
        "sales_review",
        "engineering_review",
        "material_pricing",
        "outside_service_pricing",
        "executive_review",
    ]


# --------------------------------------------------------------------------- #
# require() enforces the matrix at the API layer (no DB needed).
# --------------------------------------------------------------------------- #
def _guarded_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/guarded")
    async def guarded(
        principal: Annotated[Principal, Depends(require(Permission.quote_edit))],
    ) -> dict[str, str]:
        return {"user": str(principal.user_id)}

    return app


def _act_as(app: FastAPI, *roles: MembershipRole) -> None:
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=uuid.uuid4(), active_org_id=uuid.uuid4(), roles=tuple(roles)
    )


def test_require_allows_an_authorized_role() -> None:
    app = _guarded_app()
    _act_as(app, R.estimator)
    with TestClient(app) as client:
        assert client.get("/guarded").status_code == 200


def test_require_denies_an_unauthorized_role_via_the_envelope() -> None:
    app = _guarded_app()
    _act_as(app, R.viewer)
    with TestClient(app) as client:
        resp = client.get("/guarded")
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_require_honors_the_union_across_roles() -> None:
    app = _guarded_app()
    _act_as(app, R.viewer, R.estimator)  # estimator supplies quote_edit
    with TestClient(app) as client:
        assert client.get("/guarded").status_code == 200
