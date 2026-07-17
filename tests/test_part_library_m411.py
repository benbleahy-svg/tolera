"""M4.11 — Part-Library geometry indexes: Exact Geometric + Similar Geometries.

The two buckets M2.12 stubbed as ``pending_m4`` become real: equal ``gs1``
signature (topology-tolerant, M4.0 PASS) fills Exact Geometric, and pgvector
L2 nearest-neighbour over the ``gv1`` scalar feature vector fills Similar
Geometries (spec ``#partlib`` — the decided v1; learned embeddings are
post-pilot). Both are org-scoped like every other bucket; a CAD subject whose
async interrogation hasn't finished reports ``processing`` instead of a
false empty result.

Runs against real Postgres + the real OCCT engine (eager Celery inline).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.models import MembershipRole
from tests.conftest import Seeder, authed
from tests.support import eager_celery

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "cad"
CUBE = (FIXTURES / "cube-20mm.step").read_bytes()
CUBE_SPLITFACE = (FIXTURES / "cube-20mm-splitface.step").read_bytes()
TUBE = (FIXTURES / "tube-rect-40x20-t2-l200.step").read_bytes()
TUBE_CUTOUT = (FIXTURES / "tube-rect-cutout-40x20-t2-d10-l150.step").read_bytes()

ADMIN = [MembershipRole.admin]


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"{slug}-admin")
    seeder.membership(user, org, roles=ADMIN)
    return org, user


def _part_with_step(client: TestClient, name: str, body: bytes) -> str:
    """A part whose PRIMARY STEP upload has been fully interrogated inline."""
    part_id: str = client.post("/api/parts").json()["id"]
    with eager_celery():
        resp = client.post(
            f"/api/parts/{part_id}/files",
            files=[("files", (name, body, "application/step"))],
        )
        assert resp.status_code == 201, resp.text
    return part_id


def _matches(client: TestClient, part_id: str) -> dict[str, Any]:
    resp = client.get(f"/api/parts/{part_id}/matches")
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _bucket(body: dict[str, Any], key: str) -> dict[str, Any]:
    [bucket] = [b for b in body["buckets"] if b["key"] == key]
    return dict(bucket)


def _part_ids(bucket: dict[str, Any]) -> list[str]:
    return [m["part_id"] for m in bucket["matches"]]


class TestExactGeometric:
    def test_topology_variant_pair_matches_geometric_not_file(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """The M4.0 pair: same manufactured geometry, different bytes — the
        acceptance case for the topology-tolerant signature."""
        org, admin = _org_with_admin(seeder, "org-geo1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _part_with_step(app_client, "Wuerfel.step", CUBE)
            variant = _part_with_step(app_client, "Wuerfel-split.step", CUBE_SPLITFACE)
            other = _part_with_step(app_client, "Rohr.step", TUBE)
            body = _matches(app_client, subject)

        geometric = _bucket(body, "exact_geometric")
        assert geometric["status"] == "ready"
        assert _part_ids(geometric) == [variant]
        # Different bytes: the file bucket must NOT see the variant.
        assert variant not in _part_ids(_bucket(body, "exact_file"))
        assert other not in _part_ids(geometric)

    def test_org_scoped(self, app_client: TestClient, seeder: Seeder) -> None:
        """Another org's byte- and geometry-identical part never surfaces."""
        org_a, admin_a = _org_with_admin(seeder, "org-geo2a")
        org_b, admin_b = _org_with_admin(seeder, "org-geo2b")
        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            _part_with_step(app_client, "Wuerfel.step", CUBE)
        with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
            subject = _part_with_step(app_client, "Wuerfel.step", CUBE)
            body = _matches(app_client, subject)

        assert _bucket(body, "exact_geometric")["count"] == 0
        assert _bucket(body, "similar_geometries")["count"] == 0
        assert _bucket(body, "exact_file")["count"] == 0


class TestSimilarGeometries:
    def test_near_neighbour_found_far_part_excluded(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """The plain tube finds its cutout variant (distinct signature, close
        gv1 vector) but not the cube (far) — pgvector NN under the calibrated
        L2 threshold."""
        org, admin = _org_with_admin(seeder, "org-sim1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _part_with_step(app_client, "Rohr.step", TUBE)
            near = _part_with_step(app_client, "Rohr-Ausschnitt.step", TUBE_CUTOUT)
            far = _part_with_step(app_client, "Wuerfel.step", CUBE)
            body = _matches(app_client, subject)

        similar = _bucket(body, "similar_geometries")
        assert similar["status"] == "ready"
        assert near in _part_ids(similar)
        assert far not in _part_ids(similar)
        # The variant is geometrically DIFFERENT — not an exact match.
        assert _bucket(body, "exact_geometric")["count"] == 0

    def test_identical_geometry_stays_out_of_similar(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """ "Similar" means non-identical: the topology twin lives in Exact
        Geometric only (spec ``#partlib``)."""
        org, admin = _org_with_admin(seeder, "org-sim2")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _part_with_step(app_client, "Wuerfel.step", CUBE)
            _part_with_step(app_client, "Wuerfel-split.step", CUBE_SPLITFACE)
            body = _matches(app_client, subject)

        assert _bucket(body, "exact_geometric")["count"] == 1
        assert _bucket(body, "similar_geometries")["count"] == 0


class TestStaleness:
    def test_primary_swap_to_pdf_leaves_both_geometry_indexes(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """Swapping the PRIMARY to a non-CAD file clears signature AND vector —
        the part must stop serving geometry matches it no longer has."""
        org, admin = _org_with_admin(seeder, "org-stale1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            subject = _part_with_step(app_client, "Wuerfel.step", CUBE)
            twin = _part_with_step(app_client, "Wuerfel-2.step", CUBE)
            assert _bucket(_matches(app_client, subject), "exact_geometric")["count"] == 1

            # Swap the twin's PRIMARY to a PDF (no geometry).
            with eager_celery():
                up = app_client.post(
                    f"/api/parts/{twin}/files",
                    files=[("files", ("Zeichnung.pdf", b"%PDF-1.4 fake", "application/pdf"))],
                )
                assert up.status_code == 201, up.text
                pdf_id = up.json()[0]["id"]
                promote = app_client.post(f"/api/parts/{twin}/files/{pdf_id}/primary")
                assert promote.status_code == 200, promote.text

            body = _matches(app_client, subject)
            assert _bucket(body, "exact_geometric")["count"] == 0
            assert _bucket(body, "similar_geometries")["count"] == 0


class TestBucketStatus:
    def test_uninterrogated_cad_subject_reports_processing(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """Upload without the worker running: the async job hasn't produced a
        signature yet, so the geometry buckets say so instead of claiming
        "no matches"."""
        org, admin = _org_with_admin(seeder, "org-st1")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id: str = app_client.post("/api/parts").json()["id"]
            resp = app_client.post(
                f"/api/parts/{part_id}/files",
                files=[("files", ("Wuerfel.step", CUBE, "application/step"))],
            )
            assert resp.status_code == 201, resp.text
            body = _matches(app_client, part_id)

        for key in ("exact_geometric", "similar_geometries"):
            bucket = _bucket(body, key)
            assert bucket["status"] == "processing"
            assert bucket["count"] == 0

    def test_partless_subject_is_ready_and_empty(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """No CAD primary → no geometry indexes by design (spec pipeline
        step 2) — ready with zero matches, not stuck "processing"."""
        org, admin = _org_with_admin(seeder, "org-st2")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id: str = app_client.post("/api/parts").json()["id"]
            body = _matches(app_client, part_id)

        for key in ("exact_geometric", "similar_geometries"):
            bucket = _bucket(body, key)
            assert bucket["status"] == "ready"
            assert bucket["count"] == 0
