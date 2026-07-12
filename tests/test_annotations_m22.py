"""Tests for M2.2 — the persisted PDF annotation layer.

The viewer saves its whole markup document (`{"objects": [...]}`) per file;
the layer round-trips exactly, upserts on re-save, is org-scoped (RLS), and
the bare download stays byte-identical (the layer never touches the file)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]

PDF_BYTES = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

RECT = {
    "id": "a1",
    "page": 1,
    "type": "rectangle",
    "rect": {"x": 72, "y": 700, "width": 120, "height": 40},
    "style": {"stroke": "#d6409f", "strokeWidth": 2, "fill": "none", "opacity": 1},
}
NOTE = {
    "id": "a2",
    "page": 1,
    "type": "note",
    "at": {"x": 200, "y": 650},
    "text": "Kante entgraten",
    "style": {"stroke": "#1d4ed8", "strokeWidth": 1, "fill": "#fef3c7", "opacity": 1},
}


@contextmanager
def _as_admin(client: TestClient, org: uuid.UUID, user: uuid.UUID) -> Iterator[TestClient]:
    with authed(client, user_id=user, org_id=org, roles=ADMIN):
        yield client


def _org_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"admin@{slug}.example")
    seeder.membership(user, org, ADMIN)
    return org, user


def _part_with_pdf(client: TestClient) -> tuple[str, str]:
    part_id = str(client.post("/api/parts").json()["id"])
    uploaded = client.post(
        f"/api/parts/{part_id}/files",
        files=[("files", ("drawing.pdf", PDF_BYTES, "application/pdf"))],
    )
    assert uploaded.status_code == 201, uploaded.text
    return part_id, str(uploaded.json()[0]["id"])


def test_layer_round_trips_and_upserts(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "m22-layer")
    with _as_admin(app_client, org, user) as client:
        part_id, file_id = _part_with_pdf(client)
        url = f"/api/parts/{part_id}/files/{file_id}/annotations"

        assert client.get(url).json() == {"objects": []}  # empty until saved

        res = client.put(url, json={"objects": [RECT, NOTE]})
        assert res.status_code == 200, res.text
        assert client.get(url).json() == {"objects": [RECT, NOTE]}  # exact round-trip

        # re-save replaces atomically (undo/redo lives client-side)
        res = client.put(url, json={"objects": [NOTE]})
        assert res.status_code == 200, res.text
        assert client.get(url).json() == {"objects": [NOTE]}

        # the bare download is unaffected (M2.1 AC preserved)
        download = client.get(f"/api/parts/{part_id}/files/{file_id}/download")
        assert download.content == PDF_BYTES


def test_layer_is_org_scoped(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_admin(seeder, "m22-org-a")
    org_b, user_b = _org_admin(seeder, "m22-org-b")
    with _as_admin(app_client, org_a, user_a) as client:
        part_id, file_id = _part_with_pdf(client)
        client.put(f"/api/parts/{part_id}/files/{file_id}/annotations", json={"objects": [RECT]})
    with _as_admin(app_client, org_b, user_b) as client:
        # the other org can't even see the part, let alone the layer
        res = client.get(f"/api/parts/{part_id}/files/{file_id}/annotations")
        assert res.status_code == 404


def test_layer_size_guard(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_admin(seeder, "m22-guard")
    with _as_admin(app_client, org, user) as client:
        part_id, file_id = _part_with_pdf(client)
        res = client.put(
            f"/api/parts/{part_id}/files/{file_id}/annotations",
            json={"objects": [RECT] * 2001},
        )
        assert res.status_code == 422
