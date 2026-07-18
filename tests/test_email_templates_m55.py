"""Email Template CRUD (M5.5) — spec ``#settings`` Email Templates, DemoH 08.

Per-type templates (quote_send / order_shipment / order_refund), each with a name
and an optional DEFAULT flag (at most one per type); the default is protected from
deletion (the greyed trash in DemoH 08). Org-scoped via RLS.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import MembershipRole
from tests.conftest import Seeder, app_role_url, authed
from tests.support import build_settings

pytestmark = pytest.mark.usefixtures("tenancy_db")


@pytest.fixture
def client(tenancy_db: str) -> Iterator[TestClient]:
    settings = build_settings(database_url=tenancy_db, app_database_url=app_role_url(tenancy_db))
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug, f"{slug.title()} GmbH")
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, [MembershipRole.admin])
    return org, user


def _create(client: TestClient, **overrides: object) -> httpx.Response:
    payload = {
        "template_type": "quote_send",
        "name": "Neues Angebot",
        "subject": "Ihr Angebot %%QUOTE_NUMBER%%",
        "body": "Guten Tag, Ihr Angebot steht bereit: %%QUOTE_LINK%%",
        **overrides,
    }
    return cast(httpx.Response, client.post("/api/email-templates", json=payload))


def test_create_and_list(client: TestClient, seeder: Seeder) -> None:
    org, user = _admin(seeder, "et-create")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        resp = _create(client, is_default=True)
        assert resp.status_code == 201, resp.text
        row = resp.json()
        assert row["template_type"] == "quote_send"
        assert row["is_default"] is True
        # "Last edited by" is the editor's email (DemoH 08), resolved from the id.
        assert row["last_edited_by"] == "admin@et-create.example"

        listed = client.get("/api/email-templates").json()
    assert any(t["id"] == row["id"] for t in listed)


def test_type_filter(client: TestClient, seeder: Seeder) -> None:
    org, user = _admin(seeder, "et-filter")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        _create(client, template_type="quote_send", name="Q")
        _create(client, template_type="order_shipment", name="Versand")
        only_shipment = client.get("/api/email-templates?template_type=order_shipment").json()
    assert {t["template_type"] for t in only_shipment} == {"order_shipment"}


def test_second_default_unseats_the_first(client: TestClient, seeder: Seeder) -> None:
    org, user = _admin(seeder, "et-default")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        first = _create(client, name="Erst", is_default=True).json()
        second = _create(client, name="Zweit", is_default=True).json()
        rows = {t["id"]: t for t in client.get("/api/email-templates").json()}
    assert rows[second["id"]]["is_default"] is True
    assert rows[first["id"]]["is_default"] is False  # unseated — only one default per type


def test_update_body_and_promote_default(client: TestClient, seeder: Seeder) -> None:
    org, user = _admin(seeder, "et-update")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        a = _create(client, name="A", is_default=True).json()
        b = _create(client, name="B").json()
        resp = client.patch(
            f"/api/email-templates/{b['id']}",
            json={"body": "Neuer Text %%QUOTE_NUMBER%%", "is_default": True},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["body"] == "Neuer Text %%QUOTE_NUMBER%%"
        rows = {t["id"]: t for t in client.get("/api/email-templates").json()}
    assert rows[b["id"]]["is_default"] is True
    assert rows[a["id"]]["is_default"] is False


def test_delete_non_default(client: TestClient, seeder: Seeder) -> None:
    org, user = _admin(seeder, "et-del")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        _create(client, name="Keep", is_default=True)
        drop = _create(client, name="Drop").json()
        resp = client.delete(f"/api/email-templates/{drop['id']}")
        assert resp.status_code == 204, resp.text
        rows = [t["id"] for t in client.get("/api/email-templates").json()]
    assert drop["id"] not in rows


def test_cannot_delete_default(client: TestClient, seeder: Seeder) -> None:
    org, user = _admin(seeder, "et-del-def")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        default = _create(client, name="Standard", is_default=True).json()
        resp = client.delete(f"/api/email-templates/{default['id']}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "default_template_protected"


def test_update_rejects_explicit_null(client: TestClient, seeder: Seeder) -> None:
    org, user = _admin(seeder, "et-null")
    with authed(client, user_id=user, org_id=org, roles=[MembershipRole.admin]):
        made = _create(client, name="X").json()
        # An explicit null must 422 (never a NULL write to a NOT NULL column),
        # while omission (partial update) still works.
        bad = client.patch(f"/api/email-templates/{made['id']}", json={"name": None})
        assert bad.status_code == 422
        ok = client.patch(f"/api/email-templates/{made['id']}", json={"subject": "Neu"})
    assert ok.status_code == 200


def test_create_requires_settings_edit(client: TestClient, seeder: Seeder) -> None:
    org = seeder.org("et-perm", "Perm GmbH")
    viewer = seeder.user("viewer@et-perm.example")
    seeder.membership(viewer, org, [MembershipRole.viewer])
    with authed(client, user_id=viewer, org_id=org, roles=[MembershipRole.viewer]):
        resp = _create(client)
    assert resp.status_code == 403


def test_org_isolation(client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _admin(seeder, "et-iso-a")
    org_b, admin_b = _admin(seeder, "et-iso-b")
    with authed(client, user_id=admin_a, org_id=org_a, roles=[MembershipRole.admin]):
        made = _create(client, name="A-only").json()
    with authed(client, user_id=admin_b, org_id=org_b, roles=[MembershipRole.admin]):
        # B cannot see or fetch A's template.
        assert made["id"] not in [t["id"] for t in client.get("/api/email-templates").json()]
        assert client.get(f"/api/email-templates/{made['id']}").status_code == 404
