"""Authorization policy — the single source of truth for roles → permissions.

One declarative module owns the whole RBAC contract (spec ``#authz``/``#personas``):
the :class:`Permission` capabilities, the :data:`ROLE_PERMISSIONS` matrix, and the
:func:`require` API guard every endpoint calls. Changing a cell here changes
enforcement everywhere — there are no scattered role-string checks (M0.3 goal).

Model (decided, spec ``#authz``): fixed role presets, predefined permissions
(not admin-customizable in v1). A user may hold several roles; **effective
permissions are the union** (DECISIONS.md 2026-06-19 "Multi-organization users").
Roles are evaluated within the caller's **active-org** membership — ``Principal``
already carries the active-org roles (M0.2), so a check is inherently org-scoped.

Three deliberate divergences from the raw spec matrix, all recorded in
DECISIONS.md 2026-06-24:
  * ``manager`` is granted ``quote_finalize`` directly (spec keeps it off Exec);
    ``manager`` therefore equals ``admin`` across the M0.3 capability set.
  * ``salesperson``/``estimator`` get **no** ``quote_delete`` — the spec's
    owner-only delete needs ownership, which doesn't exist until M1/M5; we
    under-grant rather than over-grant.
  * ``review_step_update`` is granted only coarsely (admin/manager); the
    per-stage/assigned mapping is deferred to M1 (no quote item/stage yet).

The 5 review *stages* are :class:`ReviewStage` — workflow states on a quote item,
**not** roles (M0.3 acceptance criterion). They carry no permissions here.
"""

from __future__ import annotations

import enum
from collections.abc import Awaitable, Callable, Iterable
from typing import Annotated

from fastapi import Depends, status

from .auth import Principal, get_principal
from .errors import AppError
from .models import MembershipRole


class Permission(enum.StrEnum):
    """A capability gate — one per row of the spec ``#authz`` matrix.

    ``quote_annotate`` (read + comment) is distinct from ``quote_edit`` so the
    spec's "view + annotate" support roles are modelled faithfully without being
    able to edit costing. ``quote_finalize`` covers finalize / send / convert /
    edit-order-pre-ship (one matrix row)."""

    view_all = "view_all"
    quote_annotate = "quote_annotate"
    quote_edit = "quote_edit"
    quote_finalize = "quote_finalize"
    review_step_update = "review_step_update"
    config_edit = "config_edit"
    settings_edit = "settings_edit"
    users_manage = "users_manage"
    quote_delete = "quote_delete"


class ReviewStage(enum.StrEnum):
    """The 5 default review/workflow stages (spec ``#personas``). These are quote-
    item **states**, not roles — kept disjoint from :class:`MembershipRole` and
    granted no permissions. Stages are org-configurable from M1 (per-org
    ``WorkflowStepDef``); this enum is the seed default + a documentation anchor."""

    sales_review = "sales_review"
    engineering_review = "engineering_review"
    material_pricing = "material_pricing"
    outside_service_pricing = "outside_service_pricing"
    executive_review = "executive_review"


# Matrix-row groupings, named to mirror the spec table.
_EDIT = frozenset(
    {
        Permission.view_all,
        Permission.quote_annotate,
        Permission.quote_edit,
        Permission.quote_finalize,
    }
)
_SUPPORT = frozenset({Permission.view_all, Permission.quote_annotate})
_ALL = frozenset(Permission)

#: The authoritative role → permission map. Every :class:`MembershipRole` has an
#: explicit entry (enforced at import below) so a forgotten role fails closed.
ROLE_PERMISSIONS: dict[MembershipRole, frozenset[Permission]] = {
    MembershipRole.admin: _ALL,
    MembershipRole.manager: _ALL,  # == admin (DECISIONS 2026-06-24 manager-finalize)
    MembershipRole.salesperson: _EDIT,  # no delete (under-grant)
    MembershipRole.estimator: _EDIT,  # no delete (under-grant)
    MembershipRole.engineer: _SUPPORT,
    MembershipRole.material_purchasing: _SUPPORT,
    MembershipRole.outside_service: _SUPPORT,
    MembershipRole.viewer: frozenset({Permission.view_all}),  # read-only (non-spec)
}

# Fail-closed: a role without an explicit entry would silently grant nothing
# (a lockout risk and a maintenance trap). Surface it loudly at import instead.
_unmapped = set(MembershipRole) - set(ROLE_PERMISSIONS)
if _unmapped:  # pragma: no cover - guards against a future enum value
    raise RuntimeError(
        "ROLE_PERMISSIONS is missing entries for: " + ", ".join(sorted(r.value for r in _unmapped))
    )


def permissions_for(roles: Iterable[MembershipRole]) -> frozenset[Permission]:
    """Effective permissions = the union over a membership's roles."""
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS[role]
    return frozenset(granted)


def has_permission(roles: Iterable[MembershipRole], permission: Permission) -> bool:
    """Whether the union over ``roles`` grants ``permission``."""
    return permission in permissions_for(roles)


def require(permission: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    """API dependency factory: allow the request only if the caller's active-org
    roles grant ``permission``. Composes with ``get_principal`` — an unauthenticated
    request is rejected there (401); this raises 403 ``forbidden`` via the standard
    error envelope. Every endpoint gates on this one guard."""

    async def _guard(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not has_permission(principal.roles, permission):
            raise AppError(
                "forbidden",
                "You do not have permission to perform this action",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return principal

    return _guard
