"""M3.1 — Lens extraction pipeline + ``ExtractionFinding`` persistence.

Deterministic-core tests per the M3 two-track plan: the model is ALWAYS mocked
here (a ``FakeProvider``); extraction *quality* is the eval harness's job
(M3.11). What gates this PR:

* the **never-hallucinate guard** — a value absent from the print's text layer
  is never emitted/persisted (exact negative test, spec ``#lens-models``),
* the **EU-routing guarantee** — an export-controlled part's file never
  reaches any provider (zero calls; spec ``#lens-models`` DACH routing,
  ``part.export_controlled`` per DECISIONS.md 2026-06-26),
* the two-pass pipeline shape (quote-setup whole-doc; requirements per
  "print"-classified page; first 10 pages; spec ``#lens-extraction``),
* ``ExtractionFinding`` persistence — category/type/value/tolerance/role,
  org-scoped, status defaults ``suggested`` (spec ``#lens-finding``),
* re-run semantics — a new run replaces prior *suggested* findings, never
  human-touched rows (CLAUDE.md §5 never-destroy-human-input).
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter

from app import lens_provider
from app.celery_app import celery_app
from app.lens import (
    MAX_EXTRACTION_PAGES,
    RawFinding,
    extract_page_texts,
    hallucination_guard,
    run_document_extraction,
)
from app.lens_provider import AnthropicLensProvider, LensProviderError
from app.models import FindingCategory, MembershipRole
from tests.conftest import Seeder, authed

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "drawings"
HALTER_PDF = (FIXTURES / "halter-4711-rev-b.pdf").read_bytes()
THREE_PAGE_PDF = (FIXTURES / "halter-4711-blaetter.pdf").read_bytes()

ADMIN = [MembershipRole.admin]


def _finding(**overrides: object) -> RawFinding:
    base: dict[str, object] = {
        "category": FindingCategory.quote_setup,
        "type": "part_number",
        "raw_text": "Halter 4711",
        "value": "4711",
        "confidence": 0.92,
        "page": 1,
    }
    base.update(overrides)
    return RawFinding.model_validate(base)


class FakeProvider:
    """A scripted provider: returns canned findings, records every call."""

    def __init__(
        self,
        *,
        quote_setup: list[RawFinding] | None = None,
        requirements: dict[int, list[RawFinding]] | None = None,
        print_pages: set[int] | None = None,
    ) -> None:
        self.quote_setup = quote_setup or []
        self.requirements = requirements or {}
        self.print_pages = print_pages if print_pages is not None else {1}
        self.calls: list[tuple[str, object]] = []

    async def classify_print_pages(self, pdf: bytes, page_texts: list[str]) -> list[bool]:
        self.calls.append(("classify", len(page_texts)))
        return [(i + 1) in self.print_pages for i in range(len(page_texts))]

    async def extract_quote_setup(self, pdf: bytes, page_texts: list[str]) -> list[RawFinding]:
        self.calls.append(("quote_setup", len(page_texts)))
        return list(self.quote_setup)

    async def extract_requirements(
        self, pdf: bytes, page_no: int, page_text: str
    ) -> list[RawFinding]:
        self.calls.append(("requirements", page_no))
        return list(self.requirements.get(page_no, []))


# --------------------------------------------------------------------------- #
# Never-hallucinate guard (pure)
# --------------------------------------------------------------------------- #
class TestHallucinationGuard:
    PAGES: ClassVar[list[str]] = [
        "Zeichnung: Halter 4711\nWerkstoff:  1.4301 (X5CrNi18-10)",
        "Blatt 2\nØ10 H7",
    ]

    def test_raw_text_on_the_print_is_kept_despite_whitespace(self) -> None:
        # The page has two spaces after "Werkstoff:"; the finding has one.
        kept, dropped = hallucination_guard(
            [_finding(raw_text="Werkstoff: 1.4301", value="1.4301")], self.PAGES
        )
        assert len(kept) == 1 and not dropped

    def test_invented_raw_text_is_dropped(self) -> None:
        kept, dropped = hallucination_guard(
            [_finding(raw_text="Werkstoff: 1.7225", value="1.7225")], self.PAGES
        )
        assert not kept and len(dropped) == 1

    def test_value_is_checked_when_raw_text_is_absent(self) -> None:
        kept, dropped = hallucination_guard(
            [
                _finding(raw_text=None, value="X5CrNi18-10"),
                _finding(raw_text=None, value="42CrMo4"),
            ],
            self.PAGES,
        )
        assert [f.value for f in kept] == ["X5CrNi18-10"]
        assert [f.value for f in dropped] == ["42CrMo4"]

    def test_region_finding_without_text_claim_is_kept(self) -> None:
        region = _finding(
            category=FindingCategory.regions,
            type="title_block",
            raw_text=None,
            value=None,
            bbox={"x": 10.0, "y": 700.0, "width": 200.0, "height": 80.0},
        )
        kept, dropped = hallucination_guard([region], self.PAGES)
        assert len(kept) == 1 and not dropped

    def test_text_on_another_page_is_not_hallucinated(self) -> None:
        # "Wrong existing string" is allowed by spec — only *invented* values die.
        kept, _ = hallucination_guard(
            [_finding(raw_text="Ø10 H7", value="Ø10 H7", page=1)], self.PAGES
        )
        assert len(kept) == 1

    def test_invented_value_riding_a_real_raw_text_is_dropped(self) -> None:
        # Ship-review 🔴: BOTH claims must be on the print — a genuine snippet
        # must not smuggle in a fabricated value (normalized_value is the
        # legitimate transform channel and stays unguarded).
        kept, dropped = hallucination_guard(
            [_finding(raw_text="Werkstoff: 1.4301", value="1.7225")], self.PAGES
        )
        assert not kept and len(dropped) == 1

    def test_normalized_value_is_not_guarded(self) -> None:
        kept, _ = hallucination_guard(
            [_finding(raw_text="Ø10 H7", value=None, normalized_value="10.0")], self.PAGES
        )
        assert len(kept) == 1


# --------------------------------------------------------------------------- #
# Two-pass pipeline (pure, fake provider)
# --------------------------------------------------------------------------- #
def _n_page_pdf(n: int) -> bytes:
    writer = PdfWriter()
    src = PdfReader(io.BytesIO(HALTER_PDF))
    for _ in range(n):
        writer.add_page(src.pages[0])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestRunDocumentExtraction:
    @pytest.mark.asyncio
    async def test_two_pass_flow_requirements_only_on_print_pages(self) -> None:
        provider = FakeProvider(
            quote_setup=[_finding()],
            requirements={
                1: [
                    _finding(
                        category=FindingCategory.requirements,
                        type="material",
                        raw_text="1.4301",
                        value="1.4301",
                        normalized_value="1.4301",
                    )
                ]
            },
            print_pages={1},
        )
        three_pages = _n_page_pdf(3)
        result = await run_document_extraction(provider, three_pages)
        assert ("quote_setup", 3) in provider.calls
        assert ("classify", 3) in provider.calls
        # Requirements pass ran for page 1 only — pages 2/3 aren't prints.
        req_calls = [c for c in provider.calls if c[0] == "requirements"]
        assert req_calls == [("requirements", 1)]
        assert {f.type for f in result.findings} == {"part_number", "material"}

    @pytest.mark.asyncio
    async def test_only_first_10_pages_are_analyzed(self) -> None:
        provider = FakeProvider(print_pages=set(range(1, 13)))
        result = await run_document_extraction(provider, _n_page_pdf(12))
        assert MAX_EXTRACTION_PAGES == 10
        assert ("classify", 10) in provider.calls
        req_pages = [c[1] for c in provider.calls if c[0] == "requirements"]
        assert req_pages == list(range(1, 11))
        assert result.pages_total == 12
        assert result.pages_analyzed == 10

    @pytest.mark.asyncio
    async def test_units_fall_back_to_document_default_mm(self) -> None:
        dim = _finding(
            category=FindingCategory.dimensions,
            type="length",
            raw_text="Halter 4711",
            value="4711",
            units=None,
            role="basic",
        )
        provider = FakeProvider(requirements={1: [dim]}, print_pages={1})
        result = await run_document_extraction(provider, HALTER_PDF)
        (length,) = [f for f in result.findings if f.type == "length"]
        assert length.units == "mm"

    @pytest.mark.asyncio
    async def test_document_units_finding_sets_the_default(self) -> None:
        doc_units = _finding(type="document_units", raw_text="Halter", value="in", units=None)
        dim = _finding(
            category=FindingCategory.dimensions,
            type="length",
            raw_text="Halter 4711",
            value="4711",
            units=None,
        )
        provider = FakeProvider(quote_setup=[doc_units], requirements={1: [dim]}, print_pages={1})
        result = await run_document_extraction(provider, HALTER_PDF)
        (length,) = [f for f in result.findings if f.type == "length"]
        assert length.units == "in"

    @pytest.mark.asyncio
    async def test_guard_runs_inside_the_pipeline(self) -> None:
        invented = _finding(raw_text="Werkstoff: 1.7225", value="1.7225")
        real = _finding(raw_text="Werkstoff: 1.4301", value="1.4301", type="material")
        provider = FakeProvider(quote_setup=[real, invented])
        result = await run_document_extraction(provider, HALTER_PDF)
        assert [f.value for f in result.findings] == ["1.4301"]
        assert result.dropped_count == 1

    def test_confidence_is_validated_to_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            _finding(confidence=1.5)
        with pytest.raises(ValidationError):
            _finding(confidence=-0.1)

    def test_page_texts_come_from_the_pdf_text_layer(self) -> None:
        texts = extract_page_texts(HALTER_PDF)
        assert len(texts) == 1
        assert "Halter 4711" in texts[0]
        assert "1.4301" in texts[0]


# --------------------------------------------------------------------------- #
# Anthropic provider: deterministic non-answers must not retry (ship-review)
# --------------------------------------------------------------------------- #
class _StubResponse:
    def __init__(self, stop_reason: str, text: str | None) -> None:
        self.stop_reason = stop_reason
        self.content = [] if text is None else [type("B", (), {"type": "text", "text": text})()]


class TestAnthropicProviderGuards:
    def _provider(self, response: _StubResponse) -> AnthropicLensProvider:
        provider = AnthropicLensProvider(
            api_key="test-key", model="claude-opus-4-8", inference_geo="eu"
        )

        async def fake_create(**kwargs: object) -> _StubResponse:
            return response

        provider._client.messages.create = fake_create  # type: ignore[assignment,method-assign]
        return provider

    @pytest.mark.asyncio
    async def test_refusal_maps_to_a_deterministic_error(self) -> None:
        provider = self._provider(_StubResponse("refusal", None))
        with pytest.raises(LensProviderError) as exc:
            await provider.classify_print_pages(HALTER_PDF, ["x"])
        assert exc.value.code == "provider_refusal"

    @pytest.mark.asyncio
    async def test_truncated_output_maps_to_a_deterministic_error(self) -> None:
        provider = self._provider(_StubResponse("max_tokens", '{"is_print": [tru'))
        with pytest.raises(LensProviderError) as exc:
            await provider.classify_print_pages(HALTER_PDF, ["x"])
        assert exc.value.code == "provider_truncated"

    @pytest.mark.asyncio
    async def test_malformed_json_maps_to_a_deterministic_error(self) -> None:
        provider = self._provider(_StubResponse("end_turn", "not json"))
        with pytest.raises(LensProviderError) as exc:
            await provider.classify_print_pages(HALTER_PDF, ["x"])
        assert exc.value.code == "provider_invalid_json"


# --------------------------------------------------------------------------- #
# HTTP contract + persistence (real Postgres, eager Celery, fake provider)
# --------------------------------------------------------------------------- #
@pytest.fixture
def eager_celery() -> Iterator[None]:
    saved = {
        key: celery_app.conf[key]
        for key in (
            "task_always_eager",
            "task_store_eager_result",
            "task_eager_propagates",
            "result_backend",
        )
    }
    celery_app.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
        task_eager_propagates=False,
        result_backend="cache+memory://",
    )
    celery_app.__dict__.pop("backend", None)
    yield
    celery_app.conf.update(saved)
    celery_app.__dict__.pop("backend", None)


@pytest.fixture
def fake_provider() -> Iterator[FakeProvider]:
    """Register a scripted provider for the golden Halter print (model mocked)."""
    provider = FakeProvider(
        quote_setup=[
            _finding(type="part_number", raw_text="Halter 4711", value="4711"),
            _finding(type="revision", raw_text="Rev B", value="B", confidence=0.99),
            _finding(type="document_units", raw_text="Masse in mm", value="mm"),
        ],
        requirements={
            1: [
                _finding(
                    category=FindingCategory.requirements,
                    type="material",
                    raw_text="Werkstoff: 1.4301 (X5CrNi18-10)",
                    value="1.4301",
                    normalized_value="1.4301",
                ),
                _finding(
                    category=FindingCategory.requirements,
                    type="global_tolerances",
                    raw_text="Allgemeintoleranzen ISO 2768-m",
                    value="ISO 2768-m",
                    role=None,
                ),
                _finding(
                    category=FindingCategory.dimensions,
                    type="length",
                    raw_text="Halter 4711",
                    value="4711",
                    units=None,
                    role="basic",
                    tolerance={"kind": "bilateral", "upper": "0.1", "lower": "-0.1"},
                    bbox={"x": 40.0, "y": 500.0, "width": 60.0, "height": 12.0},
                ),
            ]
        },
        print_pages={1},
    )
    lens_provider.register(provider)
    yield provider
    lens_provider.register(None)


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def _create_part(client: TestClient) -> str:
    created = client.post("/api/parts")
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _upload_pdf(client: TestClient, part_id: str, name: str, data: bytes) -> str:
    resp = client.post(
        f"/api/parts/{part_id}/files", files=[("files", (name, data, "application/pdf"))]
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()[0]["id"])


def _run_extraction(client: TestClient, part_id: str, file_id: str) -> dict[str, object]:
    resp = client.post(f"/api/parts/{part_id}/files/{file_id}/extract")
    assert resp.status_code == 202, resp.text
    task_id = resp.json()["task_id"]
    status = client.get(f"/api/parts/{part_id}/files/{file_id}/extract/{task_id}")
    assert status.status_code == 200, status.text
    return dict(status.json())


class TestExtractionEndpoint:
    def test_fixture_print_persists_golden_findings(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        fake_provider: FakeProvider,
    ) -> None:
        """Acceptance: the Halter print → findings with the right category /
        type / value / tolerance / role, status ``suggested``, bound to the file."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-rev-b.pdf", HALTER_PDF)

            status = _run_extraction(app_client, part_id, file_id)
            assert status["state"] == "succeeded"
            assert status["finding_count"] == 6

            listed = app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings")
            assert listed.status_code == 200, listed.text
            findings = {f["type"]: f for f in listed.json()}
            assert len(findings) == 6
            assert findings["part_number"]["category"] == "quote_setup"
            assert findings["part_number"]["value"] == "4711"
            assert findings["revision"]["value"] == "B"
            assert findings["material"]["value"] == "1.4301"
            assert findings["material"]["normalized_value"] == "1.4301"
            assert findings["global_tolerances"]["value"] == "ISO 2768-m"
            dim = findings["length"]
            assert dim["category"] == "dimensions"
            assert dim["role"] == "basic"
            assert dim["units"] == "mm"  # fallback to the document default (DACH)
            assert dim["tolerance"] == {"kind": "bilateral", "upper": "0.1", "lower": "-0.1"}
            assert dim["bbox"] == {"x": 40.0, "y": 500.0, "width": 60.0, "height": 12.0}
            assert all(f["status"] == "suggested" for f in findings.values())
            assert all(f["source_file_id"] == file_id for f in findings.values())
            assert all(f["component_id"] is None for f in findings.values())

    def test_never_hallucinate_a_value_absent_from_the_print(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        fake_provider: FakeProvider,
    ) -> None:
        """THE negative test: the provider asserts a Werkstoff that is not on
        the print — it must never be persisted (spec #lens-models)."""
        fake_provider.quote_setup.append(
            _finding(type="material", raw_text="Werkstoff: 1.7225", value="1.7225")
        )
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-rev-b.pdf", HALTER_PDF)

            status = _run_extraction(app_client, part_id, file_id)
            assert status["state"] == "succeeded"
            assert status["dropped_count"] == 1

            listed = app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings").json()
            assert "1.7225" not in {f["value"] for f in listed}

    def test_export_controlled_file_never_reaches_the_provider(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        fake_provider: FakeProvider,
    ) -> None:
        """THE EU-routing test: a dual-use-flagged part's file is skipped with
        zero provider calls — it never leaves the DPA region (spec #lens-models,
        #ai-settings 'automatically skipped regardless')."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-rev-b.pdf", HALTER_PDF)
            flagged = app_client.patch(f"/api/parts/{part_id}", json={"export_controlled": True})
            assert flagged.status_code == 200, flagged.text

            resp = app_client.post(f"/api/parts/{part_id}/files/{file_id}/extract")
            assert resp.status_code == 422
            assert resp.json()["code"] == "export_controlled"
            assert fake_provider.calls == []

            listed = app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings").json()
            assert listed == []

    def test_rerun_replaces_suggested_but_preserves_human_touched_rows(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        fake_provider: FakeProvider,
    ) -> None:
        """CLAUDE.md §5: recalculation never destroys human input — a re-run
        replaces prior *suggested* rows; an accepted row survives."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-rev-b.pdf", HALTER_PDF)
            assert _run_extraction(app_client, part_id, file_id)["state"] == "succeeded"
            first = app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings").json()
            assert len(first) == 6

        accepted_id = next(f["id"] for f in first if f["type"] == "material")
        seeder.sql(
            "UPDATE extraction_finding SET status = 'accepted' WHERE id = :id",
            {"id": accepted_id},
        )

        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            assert _run_extraction(app_client, part_id, file_id)["state"] == "succeeded"
            second = app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings").json()
            # 6 fresh suggested + the surviving accepted row = 7.
            assert len(second) == 7
            by_id = {f["id"]: f for f in second}
            assert by_id[accepted_id]["status"] == "accepted"
            # None of the other first-run (suggested) rows survived.
            first_ids = {f["id"] for f in first} - {accepted_id}
            assert first_ids.isdisjoint(by_id)

    def test_cross_org_file_is_a_404(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        fake_provider: FakeProvider,
    ) -> None:
        org_a, admin_a = _org_with_admin(seeder, "org-a")
        org_b, admin_b = _org_with_admin(seeder, "org-b")
        with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-rev-b.pdf", HALTER_PDF)
            assert _run_extraction(app_client, part_id, file_id)["state"] == "succeeded"

        with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
            assert (
                app_client.post(f"/api/parts/{part_id}/files/{file_id}/extract").status_code == 404
            )
            assert (
                app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings").status_code == 404
            )

    def test_non_extractable_upload_is_rejected_at_the_edge(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        fake_provider: FakeProvider,
    ) -> None:
        """A STEP file is not a print — 422, nothing enqueued, zero provider calls."""
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            resp = app_client.post(
                f"/api/parts/{part_id}/files",
                files=[("files", ("bracket.step", b"ISO-10303-21;\nEND-ISO-10303-21;", None))],
            )
            assert resp.status_code == 201, resp.text
            step_id = resp.json()[0]["id"]
            rejected = app_client.post(f"/api/parts/{part_id}/files/{step_id}/extract")
            assert rejected.status_code == 422
            assert rejected.json()["code"] == "not_extractable"
            assert fake_provider.calls == []

    def test_findings_list_is_empty_before_any_extraction(
        self,
        app_client: TestClient,
        seeder: Seeder,
        eager_celery: None,
        fake_provider: FakeProvider,
    ) -> None:
        org, admin = _org_with_admin(seeder, "org-a")
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            part_id = _create_part(app_client)
            file_id = _upload_pdf(app_client, part_id, "halter-4711-rev-b.pdf", HALTER_PDF)
            listed = app_client.get(f"/api/parts/{part_id}/files/{file_id}/findings")
            assert listed.status_code == 200
            assert listed.json() == []
