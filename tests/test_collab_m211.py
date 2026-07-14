"""Tests for M2.11 — TEAM/EXTERNAL collaboration: channels · messages ·
annotations · tasks · notifications.

The vertical slice (block acceptance): select a face (3D) or a drawing region
(PDF), post a face/region annotation to a channel, ``@mention`` a teammate,
Assign Task — and see that task on the Dashboard (``GET /api/tasks``). Channels
are org-scoped (RLS); assignee/mention must be active members; message
edit/delete is author-only; ``overdue`` is derived from a passed ``due_date``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
VIEWER = [MembershipRole.viewer]

STEP_BYTES = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
PDF_BYTES = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

# A 3D face locator (M2.7 EntityRef) and a PDF region locator (M2.2 pdf-units).
FACE_REF = {"kind": "face", "entity": {"bodyId": "b0", "kind": "face", "index": 7}}
REGION_REF = {"page": 1, "rect": {"x": 72, "y": 700, "width": 120, "height": 40}}


@contextmanager
def _as(
    client: TestClient, org: uuid.UUID, user: uuid.UUID, roles: list[MembershipRole]
) -> Iterator[TestClient]:
    with authed(client, user_id=user, org_id=org, roles=roles):
        yield client


def _member(seeder: Seeder, org: uuid.UUID, email: str, roles: list[MembershipRole]) -> uuid.UUID:
    user = seeder.user(email)
    seeder.membership(user, org, roles)
    return user


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    return org, _member(seeder, org, f"admin@{slug}.example", ADMIN)


def _part_with_file(client: TestClient, filename: str, data: bytes, ctype: str) -> tuple[str, str]:
    part_id = str(client.post("/api/parts").json()["id"])
    uploaded = client.post(
        f"/api/parts/{part_id}/files", files=[("files", (filename, data, ctype))]
    )
    assert uploaded.status_code == 201, uploaded.text
    return part_id, str(uploaded.json()[0]["id"])


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #


def test_team_channel_is_auto_provisioned_once(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-team")
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        first = client.get(f"/api/parts/{part_id}/channels")
        assert first.status_code == 200, first.text
        teams = [c for c in first.json() if c["scope"] == "team"]
        assert len(teams) == 1  # exactly one TEAM channel, auto-provisioned
        # Idempotent: listing again does not spawn a second TEAM channel.
        again = client.get(f"/api/parts/{part_id}/channels").json()
        assert [c["id"] for c in again if c["scope"] == "team"] == [teams[0]["id"]]


def test_external_channels_are_created_explicitly(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-ext")
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        created = client.post(
            f"/api/parts/{part_id}/channels",
            json={"scope": "external", "label": "Plating RFQ"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["scope"] == "external"
        assert created.json()["label"] == "Plating RFQ"


def test_viewer_cannot_create_channel(seeder: Seeder, app_client: TestClient) -> None:
    org, admin = _org_with_admin(seeder, "m211-vgate")
    viewer = _member(seeder, org, "v@m211-vgate.example", VIEWER)
    with _as(app_client, org, admin, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
    with _as(app_client, org, viewer, VIEWER) as client:
        res = client.post(f"/api/parts/{part_id}/channels", json={"scope": "external"})
        assert res.status_code == 403


# --------------------------------------------------------------------------- #
# Messages bound to annotations (the face/region → chat slice)
# --------------------------------------------------------------------------- #


def _team_channel(client: TestClient, part_id: str) -> str:
    channels = client.get(f"/api/parts/{part_id}/channels").json()
    return str(next(c["id"] for c in channels if c["scope"] == "team"))


def test_message_binds_a_3d_face_annotation(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-face")
    with _as(app_client, org, user, ADMIN) as client:
        part_id, file_id = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        channel_id = _team_channel(client, part_id)
        posted = client.post(
            f"/api/channels/{channel_id}/messages",
            json={
                "body": "@engineer wie erreichen wir diese Passung?",
                "annotation": {"kind": "face", "geometry_ref": {"file_id": file_id, **FACE_REF}},
            },
        )
        assert posted.status_code == 201, posted.text
        msg = posted.json()
        assert msg["annotation"]["kind"] == "face"
        # geometry_ref round-trips so clicking re-focuses the exact feature (M2.7 id).
        assert msg["annotation"]["geometry_ref"]["file_id"] == file_id
        assert msg["annotation"]["geometry_ref"]["entity"]["index"] == 7


def test_external_message_binds_a_pdf_region(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-region")
    with _as(app_client, org, user, ADMIN) as client:
        part_id, file_id = _part_with_file(client, "d.pdf", PDF_BYTES, "application/pdf")
        channel = client.post(
            f"/api/parts/{part_id}/channels", json={"scope": "external", "label": "Kunde"}
        ).json()
        posted = client.post(
            f"/api/channels/{channel['id']}/messages",
            json={
                "body": "Bitte diese Bemaßung bestätigen",
                "annotation": {
                    "kind": "region",
                    "geometry_ref": {"file_id": file_id, **REGION_REF},
                },
            },
        )
        assert posted.status_code == 201, posted.text
        assert posted.json()["annotation"]["geometry_ref"]["page"] == 1


def test_mention_creates_a_notification(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-mention")
    mate = _member(seeder, org, "mate@m211-mention.example", [MembershipRole.estimator])
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        channel_id = _team_channel(client, part_id)
        client.post(
            f"/api/channels/{channel_id}/messages",
            json={"body": "@mate schau mal", "mentions": [str(mate)]},
        )
    # The mentioned teammate has a 'mention' notification waiting.
    with _as(app_client, org, mate, [MembershipRole.estimator]) as client:
        notes = client.get("/api/notifications").json()
        assert any(n["kind"] == "mention" for n in notes)


def test_mention_of_non_member_is_rejected(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-badmention")
    other_org = seeder.org("m211-badmention-other")
    outsider = _member(seeder, other_org, "out@other.example", ADMIN)
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        channel_id = _team_channel(client, part_id)
        res = client.post(
            f"/api/channels/{channel_id}/messages",
            json={"body": "@ghost", "mentions": [str(outsider)]},
        )
        assert res.status_code == 422


def test_message_edit_and_delete_are_author_only(seeder: Seeder, app_client: TestClient) -> None:
    org, author = _org_with_admin(seeder, "m211-edit")
    other = _member(seeder, org, "other@m211-edit.example", ADMIN)
    with _as(app_client, org, author, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        channel_id = _team_channel(client, part_id)
        msg_id = client.post(f"/api/channels/{channel_id}/messages", json={"body": "erste"}).json()[
            "id"
        ]
    # A different user cannot edit or delete someone else's message.
    with _as(app_client, org, other, ADMIN) as client:
        assert client.patch(f"/api/messages/{msg_id}", json={"body": "gekapert"}).status_code == 403
        assert client.delete(f"/api/messages/{msg_id}").status_code == 403
    # The author edits (stamps edited_at) then deletes (tombstone survives in the list).
    with _as(app_client, org, author, ADMIN) as client:
        edited = client.patch(f"/api/messages/{msg_id}", json={"body": "korrigiert"})
        assert edited.status_code == 200
        assert edited.json()["body"] == "korrigiert"
        assert edited.json()["edited_at"] is not None
        assert client.delete(f"/api/messages/{msg_id}").status_code == 204
        listing = client.get(f"/api/channels/{channel_id}/messages").json()
        tomb = next(m for m in listing if m["id"] == msg_id)
        assert tomb["deleted"] is True and tomb["body"] == ""


# --------------------------------------------------------------------------- #
# Assign Task → Dashboard  (the exit check)
# --------------------------------------------------------------------------- #


def test_face_annotation_assign_task_surfaces_on_dashboard(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_with_admin(seeder, "m211-exit")
    mate = _member(seeder, org, "mate@m211-exit.example", [MembershipRole.estimator])
    with _as(app_client, org, user, ADMIN) as client:
        part_id, file_id = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        channel_id = _team_channel(client, part_id)
        # Post a face annotation…
        msg = client.post(
            f"/api/channels/{channel_id}/messages",
            json={
                "body": "diese Löcher maskieren",
                "annotation": {"kind": "face", "geometry_ref": {"file_id": file_id, **FACE_REF}},
            },
        ).json()
        annotation_id = msg["annotation"]["id"]
        # …and Assign a Task on it.
        task = client.post(
            f"/api/parts/{part_id}/tasks",
            json={
                "assignee_id": str(mate),
                "message": "Maskierung prüfen",
                "annotation_id": annotation_id,
            },
        )
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]

        # The task is queryable on the Dashboard, bound to the annotation.
        dash = client.get("/api/tasks").json()
        row = next(t for t in dash if t["id"] == task_id)
        assert row["status"] == "open"
        assert row["annotation_id"] == annotation_id
        assert row["part_id"] == part_id
    # And the assignee got a task_assigned notification.
    with _as(app_client, org, mate, [MembershipRole.estimator]) as client:
        assert any(n["kind"] == "task_assigned" for n in client.get("/api/notifications").json())


def test_task_assignee_must_be_active_member(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-taskguard")
    other_org = seeder.org("m211-taskguard-other")
    outsider = _member(seeder, other_org, "out@tg.example", ADMIN)
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        res = client.post(f"/api/parts/{part_id}/tasks", json={"assignee_id": str(outsider)})
        assert res.status_code == 422


def test_task_overdue_is_derived_from_due_date(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-overdue")
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        client.post(
            f"/api/parts/{part_id}/tasks",
            json={"assignee_id": str(user), "message": "spät", "due_date": "2000-01-01"},
        )
        dash = client.get("/api/tasks").json()
        assert dash[0]["status"] == "overdue"  # stored open, derived overdue


def test_task_can_be_resolved(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-resolve")
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        task_id = client.post(
            f"/api/parts/{part_id}/tasks", json={"assignee_id": str(user)}
        ).json()["id"]
        done = client.patch(f"/api/tasks/{task_id}", json={"status": "resolved"})
        assert done.status_code == 200 and done.json()["status"] == "resolved"


# --------------------------------------------------------------------------- #
# Tenancy — channels/tasks are org-scoped (RLS)
# --------------------------------------------------------------------------- #


def test_reply_to_foreign_channel_message_is_rejected(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_with_admin(seeder, "m211-reply")
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        team_id = _team_channel(client, part_id)
        other = client.post(
            f"/api/parts/{part_id}/channels", json={"scope": "external", "label": "X"}
        ).json()["id"]
        # A message posted in the EXTERNAL channel…
        foreign_msg = client.post(
            f"/api/channels/{other}/messages", json={"body": "extern"}
        ).json()["id"]
        # …cannot be a reply parent in the TEAM channel.
        res = client.post(
            f"/api/channels/{team_id}/messages",
            json={"body": "antwort", "parent_id": foreign_msg},
        )
        assert res.status_code == 422


def test_mentions_are_deduped_and_self_mention_dropped(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, user = _org_with_admin(seeder, "m211-dedup")
    mate = _member(seeder, org, "mate@m211-dedup.example", [MembershipRole.estimator])
    with _as(app_client, org, user, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        channel_id = _team_channel(client, part_id)
        msg = client.post(
            f"/api/channels/{channel_id}/messages",
            json={"body": "@mate @mate", "mentions": [str(mate), str(mate), str(user)]},
        ).json()
        # duplicates collapsed, the author's self-mention dropped
        assert msg["mentions"] == [str(mate)]
    # exactly one notification for the teammate (no self-notification)
    with _as(app_client, org, mate, [MembershipRole.estimator]) as client:
        notes = [n for n in client.get("/api/notifications").json() if n["kind"] == "mention"]
        assert len(notes) == 1


def test_task_annotation_must_belong_to_the_part(seeder: Seeder, app_client: TestClient) -> None:
    org, user = _org_with_admin(seeder, "m211-taskann")
    with _as(app_client, org, user, ADMIN) as client:
        part_a, file_a = _part_with_file(client, "a.step", STEP_BYTES, "model/step")
        chan_a = _team_channel(client, part_a)
        ann_id = client.post(
            f"/api/channels/{chan_a}/messages",
            json={
                "body": "face",
                "annotation": {"kind": "face", "geometry_ref": {"file_id": file_a, **FACE_REF}},
            },
        ).json()["annotation"]["id"]
        # A different part cannot bind part A's annotation to its task.
        part_b, _ = _part_with_file(client, "b.step", STEP_BYTES, "model/step")
        res = client.post(
            f"/api/parts/{part_b}/tasks",
            json={"assignee_id": str(user), "annotation_id": ann_id},
        )
        assert res.status_code == 422


def test_org_members_lists_only_active_members_of_the_active_org(
    seeder: Seeder, app_client: TestClient
) -> None:
    org, admin = _org_with_admin(seeder, "m211-members")
    _member(seeder, org, "teammate@m211-members.example", [MembershipRole.estimator])
    other_org = seeder.org("m211-members-other")
    _member(seeder, other_org, "outsider@other.example", ADMIN)
    with _as(app_client, org, admin, ADMIN) as client:
        emails = {m["email"] for m in client.get("/api/org/members").json()}
    assert "teammate@m211-members.example" in emails
    assert "admin@m211-members.example" in emails
    assert "outsider@other.example" not in emails  # scoped to the active org


def test_channels_and_tasks_are_org_scoped(seeder: Seeder, app_client: TestClient) -> None:
    org_a, user_a = _org_with_admin(seeder, "m211-a")
    org_b, user_b = _org_with_admin(seeder, "m211-b")
    with _as(app_client, org_a, user_a, ADMIN) as client:
        part_id, _ = _part_with_file(client, "m.step", STEP_BYTES, "model/step")
        channel_id = _team_channel(client, part_id)
        client.post(
            f"/api/parts/{part_id}/tasks", json={"assignee_id": str(user_a), "message": "geheim"}
        )
    # Org B sees neither org A's channel messages nor its tasks.
    with _as(app_client, org_b, user_b, ADMIN) as client:
        assert client.get(f"/api/channels/{channel_id}/messages").status_code == 404
        assert client.get("/api/tasks").json() == []
