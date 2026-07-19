"""Integration-Action lifecycle + the prohibited-operation guard (M6.8).

INTEGRATION-API-CONTRACT §2 defines the lifecycle an integration must follow:

    receive trigger (event) → create/find the Action log → ``in_progress``
    → do work async → terminal status + human-readable ``status_message``

This module is that lifecycle, and it is the *only* way an action log row is
written, so three invariants hold by construction rather than by convention:

1. **No resurrection.** A terminal status is final; a late worker cannot walk a
   ``failed`` row back to ``in_progress`` and hide the failure from the log.
2. **Export-only failure notifications** (§6). A notification is generated when
   *all* of: the definition has ``notify_on_failure``, the definition's direction
   is ``export``, and the row reached ``failed``/``cancelled``/``timed_out``.
   The default is deliberately asymmetric — a DATEV/ERP export failing silently
   is the dangerous case; an import failure shows up as "the data never
   arrived".
3. **No credentials in the log.** ``request_payload`` is scrubbed of anything
   that looks like a secret before it is persisted, because the payload is
   surfaced in the manager UI and replayed on manual resend.

**Prohibited via API** (§5, "server-enforced regardless of token scope"): no
integration path may alter sharing/permissions/ACLs, hard-delete data, change
security settings, or move funds. :func:`assert_permitted` enforces that on the
*request* path — the adapters themselves simply have no such method, so this is
the second of two independent barriers, not the only one.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    INTEGRATION_FAILURE_STATUSES,
    INTEGRATION_TERMINAL_STATUSES,
    Integration,
    IntegrationAction,
    IntegrationActionDefinition,
    IntegrationActionDirection,
    IntegrationActionStatus,
    Notification,
)

logger = logging.getLogger(__name__)


class ProhibitedIntegrationAction(Exception):
    """An integration asked for something no token scope may authorise (§5)."""

    def __init__(self, action_type: str, rule: str) -> None:
        super().__init__(f"Integration action {action_type!r} is prohibited: {rule}")
        self.action_type = action_type
        self.rule = rule


class IntegrationActionConflict(Exception):
    """A transition off an already-terminal action log row."""


#: The four server-enforced prohibitions of §5, as **token** sets matched against
#: an action ``type``. Token matching rather than an allow-list because the
#: action vocabulary is open — an integration author names their own
#: capabilities — so the guard has to catch a *new* name that means one of these
#: things, not merely reject names absent from a fixed list.
#:
#: Tokens, not substrings: a substring rule would fire on innocent names
#: ("export_charges_report" contains "charge"), and a regex ``\b`` boundary is
#: useless here because ``_`` is itself a word character, so ``\bpermission\b``
#: never matches inside ``update_permissions``. Splitting on non-alphanumerics
#: and comparing whole tokens is both stricter and more predictable.
_PROHIBITED_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "may not alter sharing, permissions or ACLs",
        frozenset(
            {
                "acl",
                "acls",
                "permission",
                "permissions",
                "sharing",
                "share",
                "grant",
                "revoke",
            }
        ),
    ),
    (
        "may not hard-delete data",
        frozenset({"purge", "destroy", "erase", "drop", "hard"}),
    ),
    (
        "may not change security settings",
        frozenset({"security", "auth", "mfa", "sso", "credentials", "apikey"}),
    ),
    (
        "may not move funds (billing flows from Paddle into Tolera, never the reverse)",
        frozenset({"refund", "refunds", "charge", "payout", "funds", "payment", "billing"}),
    ),
)

#: Multi-token phrases that are prohibited only together, so a legitimate name
#: containing one half stays allowed (e.g. an "export_api_key_usage" report is
#: not a security-settings change, but "rotate_api_key" is).
_PROHIBITED_PHRASES: tuple[tuple[str, frozenset[str]], ...] = (
    ("may not change security settings", frozenset({"api", "key"})),
)


def assert_permitted(action_type: str) -> None:
    """Raise :class:`ProhibitedIntegrationAction` if ``action_type`` is barred.

    Called before *any* action log row is created, so a prohibited capability
    cannot even be recorded as queued, let alone executed. Normalisation runs
    first, so casing and separator tricks ("Hard-Delete-Quote", "ISSUE REFUND",
    "update.permissions") cannot slip one past the guard."""
    tokens = {token for token in re.split(r"[^a-z0-9]+", action_type.strip().lower()) if token}
    for rule, prohibited in _PROHIBITED_RULES:
        if tokens & prohibited:
            raise ProhibitedIntegrationAction(action_type, rule)
    for rule, phrase in _PROHIBITED_PHRASES:
        if phrase <= tokens:
            raise ProhibitedIntegrationAction(action_type, rule)


#: Payload keys whose values never reach the action log.
_SECRET_KEYS = re.compile(
    r"(password|secret|token|api_key|apikey|authorization|credential|private_key)",
    re.IGNORECASE,
)
_REDACTED = "[redacted]"


def scrub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact secret-looking values before persisting a payload."""

    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (_REDACTED if _SECRET_KEYS.search(str(key)) else _walk(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [_walk(item) for item in value]
        return value

    scrubbed = _walk(payload)
    assert isinstance(scrubbed, dict)
    return scrubbed


async def get_definition(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    integration_key: str,
    action_type: str,
) -> IntegrationActionDefinition | None:
    """Resolve one capability by its integration key + action type."""
    stmt = (
        select(IntegrationActionDefinition)
        .join(
            Integration,
            (Integration.id == IntegrationActionDefinition.integration_id)
            & (Integration.org_id == IntegrationActionDefinition.org_id),
        )
        .where(
            IntegrationActionDefinition.org_id == org_id,
            Integration.key == integration_key,
            IntegrationActionDefinition.type == action_type,
        )
    )
    return (await session.execute(stmt)).scalars().first()


async def request_action(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    definition: IntegrationActionDefinition,
    related_object_type: str | None = None,
    related_object_id: uuid.UUID | None = None,
    requested_by: uuid.UUID | None = None,
    request_payload: dict[str, Any] | None = None,
) -> IntegrationAction:
    """Open one attempt in ``queued`` (§2 "Integration Action Request").

    Tolera creates the ``queued`` log immediately so the user gets feedback and
    does not double-request. The matching ``integration_action.requested`` event
    is emitted by the caller inside the same transaction (transactional
    outbox) — this function does not emit, so a caller can open a log for an
    *event-driven* attempt that needs no request event."""
    assert_permitted(definition.type)
    action = IntegrationAction(
        org_id=org_id,
        definition_id=definition.id,
        status=IntegrationActionStatus.queued,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        requested_by=requested_by,
        request_payload=scrub_payload(request_payload or {}),
    )
    session.add(action)
    await session.flush()
    return action


async def transition_action(
    session: AsyncSession,
    action: IntegrationAction,
    status: IntegrationActionStatus,
    *,
    status_message: str | None = None,
) -> IntegrationAction:
    """Advance one attempt, generating the export-failure notification (§6).

    Refuses to move off a terminal status — see invariant 1 in the module
    docstring."""
    if action.status in INTEGRATION_TERMINAL_STATUSES:
        raise IntegrationActionConflict(
            f"integration action {action.id} is already {action.status.value}"
        )
    action.status = status
    if status_message is not None:
        action.status_message = status_message
    await session.flush()

    if status in INTEGRATION_FAILURE_STATUSES:
        await _notify_failure(session, action)
    return action


async def _notify_failure(session: AsyncSession, action: IntegrationAction) -> None:
    """In-app notification per §6 — **export** actions only, by default.

    Recipients are the org's active members; the §6 refinement "users with *View
    logs* or higher on Integrations" needs the Integrations permission the
    Integration-Manager UI introduces post-pilot, so v1 notifies the members who
    can already see the org's settings surface (admins). Widening the audience
    later is additive."""
    definition = await session.get(IntegrationActionDefinition, action.definition_id)
    if definition is None or not definition.notify_on_failure:
        return
    if definition.direction is not IntegrationActionDirection.export:
        # Import failures do not notify (§6): the dangerous silent case is an
        # export that never left.
        return

    for user_id in await _notification_recipients(session, action.org_id):
        session.add(
            Notification(
                org_id=action.org_id,
                user_id=user_id,
                kind="integration_action_failed",
                payload={
                    "integration_action_id": str(action.id),
                    "action_type": definition.type,
                    "display_title": definition.display_title,
                    "status": action.status.value,
                    "status_message": action.status_message,
                    "related_object_type": action.related_object_type,
                    "related_object_id": (
                        str(action.related_object_id) if action.related_object_id else None
                    ),
                },
            )
        )
    await session.flush()
    logger.warning(
        "integration_action_failed",
        extra={
            "org_id": str(action.org_id),
            "action_type": definition.type,
            "status": action.status.value,
        },
    )


async def _notification_recipients(session: AsyncSession, org_id: uuid.UUID) -> list[uuid.UUID]:
    from .models import MembershipRole, MembershipStatus, UserOrgMembership

    stmt = select(UserOrgMembership.user_id).where(
        UserOrgMembership.org_id == org_id,
        UserOrgMembership.status == MembershipStatus.active,
        UserOrgMembership.roles.contains([MembershipRole.admin]),
    )
    return list((await session.execute(stmt)).scalars().all())
