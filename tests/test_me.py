"""M0.4 session bootstrap — ``GET /api/me``.

The shell calls this once on load to learn who the caller is, which org is
active (name/locale/currency/country), every org they belong to (for the
org-switcher), and what they may do (capabilities). The hard part it proves: the
caller's *own* cross-org identity is read **without** weakening tenancy — the
restricted app role has no grant on ``app_user`` and RLS is active-org-only, so
the read goes through the audited ``app_current_identity`` SECURITY DEFINER
function (DECISIONS.md 2026-06-24). A caller still only ever sees their own data.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.authz import Permission, permissions_for
from app.models import MembershipRole
from tests.conftest import Seeder, authed

R = MembershipRole


def test_me_returns_identity_active_org_and_capabilities(
    app_client: TestClient, seeder: Seeder
) -> None:
    """A multi-membership user gets their identity, the active org's config, every
    membership (switcher source), and capabilities = the union over active roles."""
    fechner = seeder.org("fechner", name="Fechner GmbH")  # DE / EUR / de-DE defaults
    helvetia = seeder.org(
        "helvetia", name="Helvetia AG", country="CH", currency="CHF", locale="de-CH"
    )
    user = seeder.user("estimator@fechner.example")
    seeder.membership(user, fechner, [R.estimator])
    seeder.membership(user, helvetia, [R.viewer])

    with authed(app_client, user_id=user, org_id=fechner, roles=[R.estimator]):
        resp = app_client.get("/api/me")

    assert resp.status_code == 200
    body = resp.json()

    # Identity comes from app_user (which the app role cannot read directly).
    assert body["user"]["email"] == "estimator@fechner.example"

    # Active org reflects the claim's org, with its own DACH config.
    assert body["active_org"]["slug"] == "fechner"
    assert body["active_org"]["country"] == "DE"
    assert body["active_org"]["currency"] == "EUR"
    assert body["active_org"]["locale"] == "de-DE"

    # All memberships are listed cross-org (the org-switcher source) — incl. the CHF org.
    by_slug = {m["org_slug"]: m for m in body["memberships"]}
    assert set(by_slug) == {"fechner", "helvetia"}
    assert by_slug["helvetia"]["currency"] == "CHF"
    assert by_slug["helvetia"]["locale"] == "de-CH"
    assert by_slug["fechner"]["roles"] == ["estimator"]
    assert by_slug["helvetia"]["roles"] == ["viewer"]

    # Capabilities are the union over the ACTIVE org's roles (M0.3 source of truth).
    expected = sorted(p.value for p in permissions_for((R.estimator,)))
    assert body["effective_permissions"] == expected
    assert body["roles"] == ["estimator"]
    # An estimator cannot administer config — nav must hide Configure for them.
    assert Permission.config_edit.value not in body["effective_permissions"]


def test_me_capabilities_are_the_union_of_multiple_active_roles(
    app_client: TestClient, seeder: Seeder
) -> None:
    """A membership with several roles yields the union of their capabilities."""
    org = seeder.org("multi")
    user = seeder.user("lead@multi.example")
    seeder.membership(user, org, [R.estimator, R.manager])

    with authed(app_client, user_id=user, org_id=org, roles=[R.estimator, R.manager]):
        body = app_client.get("/api/me").json()

    expected = sorted(p.value for p in permissions_for((R.estimator, R.manager)))
    assert body["effective_permissions"] == expected
    # The union includes manager-only capabilities (e.g. config/users admin).
    assert Permission.config_edit.value in body["effective_permissions"]


def test_me_reports_db_membership_roles_not_a_stale_claim(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Capabilities follow the authoritative DB membership, not the JWT claim. If
    the claim is stale/inflated (admin) but the membership row says viewer, /api/me
    must report viewer — never overstate access from a desynced claim."""
    org = seeder.org("drift")
    user = seeder.user("drift@drift.example")
    seeder.membership(user, org, [R.viewer])  # the DB (authoritative) says viewer

    # ...but the session claim is inflated to admin (a stale / not-yet-synced claim).
    with authed(app_client, user_id=user, org_id=org, roles=[R.admin]):
        body = app_client.get("/api/me").json()

    assert body["roles"] == ["viewer"]
    assert body["effective_permissions"] == sorted(p.value for p in permissions_for((R.viewer,)))
    assert Permission.config_edit.value not in body["effective_permissions"]


def test_me_requires_authentication(app_client: TestClient) -> None:
    """No session → 401 via the standard error envelope (not a 500 / leak)."""
    resp = app_client.get("/api/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


def test_me_rejects_an_active_org_the_user_does_not_belong_to(
    app_client: TestClient, seeder: Seeder
) -> None:
    """If the claim's active org isn't one of the user's memberships, fail closed
    (403) rather than returning a null/again-someone-else's active org."""
    home = seeder.org("home")
    stranger = seeder.org("stranger")
    user = seeder.user("user@home.example")
    seeder.membership(user, home, [R.admin])  # no membership in `stranger`

    with authed(app_client, user_id=user, org_id=stranger, roles=[R.admin]):
        resp = app_client.get("/api/me")

    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_me_rejects_a_token_for_a_nonexistent_user(app_client: TestClient) -> None:
    """A valid-looking token whose user has no identity row (e.g. deleted) → 401
    via the envelope, never a 500 / unhandled None."""
    with authed(app_client, user_id=uuid.uuid4(), org_id=uuid.uuid4(), roles=[R.admin]):
        resp = app_client.get("/api/me")

    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"
