"""Lens document-extraction core (M3.1 — spec ``#lens-engine`` / ``#lens-extraction``).

The deterministic heart of Lens pipeline 3 ("Found in Files"): the finding
contract, the **never-hallucinate guard**, and the **two-pass** orchestration —
quote-setup pass over the whole document, requirements pass per page classified
as a print, both bounded to the first :data:`MAX_EXTRACTION_PAGES` pages
(spec ``#lens-extraction``). Pure bytes/models in → models out; no ORM, no
Celery — so the guard logic is unit-testable with the model mocked (the M3
two-track test plan). The provider seam lives in :mod:`app.lens_provider`;
persistence + the HTTP surface in :mod:`app.lens_extract`.

Findings are AI **suggestions** (AI-Governor): they inform the human, the
Found-in-Files panel (M3.2) and Rules signals (M3.7) — never Kalk costing
(CLAUDE.md §5).
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from .models import FindingCategory

logger = logging.getLogger("app.lens")

#: Both passes analyze at most the first 10 pages (spec #lens-extraction).
MAX_EXTRACTION_PAGES = 10

#: Version stamp for the extraction prompt set — the M3 test plan pins
#: model + prompts so eval scores (M3.11) are comparable across runs.
PROMPT_VERSION = "lens-extract-v1"

#: Metric-native document default (DACH); a `document_units` finding overrides.
DEFAULT_DOCUMENT_UNITS = "mm"


class ToleranceSpec(BaseModel):
    """``{kind, upper, lower}`` per the spec contract (unilateral/bilateral/limit)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["unilateral", "bilateral", "limit"]
    upper: str | None = None
    lower: str | None = None


class GdtSpec(BaseModel):
    """ISO GPS control-frame payload (spec ``#lens-finding``)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    datum_refs: list[str] = Field(default_factory=list)
    material_condition: str | None = None


class BboxSpec(BaseModel):
    """Unrotated pdf-unit page coordinates — the M2.2 annotation-layer
    convention (DECISIONS.md 2026-07-12), consumed by the viewer overlay."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float
    height: float


class RawFinding(BaseModel):
    """One provider-emitted extraction, validated at the seam (Pydantic v2 at
    the edge, CLAUDE.md §5) before the guard and persistence ever see it."""

    model_config = ConfigDict(extra="forbid")

    category: FindingCategory
    type: str
    raw_text: str | None = None
    value: str | None = None
    normalized_value: str | None = None
    units: str | None = None
    tolerance: ToleranceSpec | None = None
    role: Literal["basic", "critical_to_quality", "reference"] | None = None
    gdt: GdtSpec | None = None
    bbox: BboxSpec | None = None
    confidence: float = Field(ge=0, le=1)
    page: int | None = None


class RawLineItem(BaseModel):
    """One provider-suggested email parts-list line (M3.4 — AI-LENS §3),
    validated at the seam before the guard in :mod:`app.email_parts` sees it.

    ``requested_date_raw`` is the verbatim body snippet the date came from —
    the guarded claim; ``requested_date`` is its ISO-8601 normalization (the
    transformed channel, unguarded — the ``normalized_value`` precedent)."""

    model_config = ConfigDict(extra="forbid")

    part_number: str
    revision: str | None = None
    description: str | None = None
    quantities: list[int] = Field(default_factory=list)
    requested_date: str | None = None
    requested_date_raw: str | None = None
    confidence: float = Field(ge=0, le=1)


class LensProvider(Protocol):
    """The configurable model seam (spec ``#lens-models``): Anthropic Claude in
    production (:mod:`app.lens_provider`), a scripted fake in the gating tests."""

    async def classify_print_pages(self, pdf: bytes, page_texts: list[str]) -> list[bool]:
        """Per-page "is this a print?" — gates the requirements pass."""
        ...

    async def extract_quote_setup(self, pdf: bytes, page_texts: list[str]) -> list[RawFinding]:
        """Whole-document pass: part#/rev/desc/drawing#/document_units/…"""
        ...

    async def extract_requirements(
        self, pdf: bytes, page_no: int, page_text: str
    ) -> list[RawFinding]:
        """Per-print-page pass: the full 5-category taxonomy."""
        ...


class NotExtractableError(Exception):
    """The stored file can't run document extraction (not a parseable PDF, or
    no text layer — OCR pre-stages are the M2 file pipeline, out of M3.1)."""

    code = "not_extractable"


def extract_page_texts(pdf: bytes) -> list[str]:
    """Text layer per page (all pages). Raises :class:`NotExtractableError` for
    non-PDF/corrupt/encrypted input or a document with no extractable text."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            raise NotExtractableError("encrypted PDF")
        texts = [page.extract_text() or "" for page in reader.pages]
    except NotExtractableError:
        raise
    except Exception as exc:
        raise NotExtractableError("not a parseable PDF") from exc
    if not any(t.strip() for t in texts[:MAX_EXTRACTION_PAGES]):
        # A scanned print without OCR: every finding would fail the guard
        # anyway — reject honestly until the M2 OCR pre-stage lands.
        raise NotExtractableError("no text layer in the first pages")
    return texts


def _normalize(text: str) -> str:
    return " ".join(text.split())


def hallucination_guard(
    findings: list[RawFinding], page_texts: list[str]
) -> tuple[list[RawFinding], list[RawFinding]]:
    """The never-hallucinate constraint (spec ``#lens-models``): a value absent
    from the print is never emitted. Returns ``(kept, dropped)``.

    A finding claims print content through ``raw_text`` (verbatim snippet) AND
    ``value`` — **every** claim that is set must occur in the document's text
    layer, whitespace-normalized. Checking only one would let an invented
    ``value`` ride in on a genuine ``raw_text`` (ship-review finding); the
    legitimate channel for transformed values is ``normalized_value``, which is
    deliberately NOT guarded. The check is document-wide, not page-scoped — the
    model "may pick a wrong existing string but must never invent one", so text
    from another page is a wrong-but-real pick, not a hallucination. Findings
    with no textual claim at all (pure region boxes) pass — they assert
    geometry, not print content.
    """
    document = _normalize("\n".join(page_texts))
    kept: list[RawFinding] = []
    dropped: list[RawFinding] = []
    for finding in findings:
        claims = [c for c in (finding.raw_text, finding.value) if c is not None]
        if all(_normalize(claim) in document for claim in claims):
            kept.append(finding)
        else:
            dropped.append(finding)
    if dropped:
        # ids/counts only — raw_text/values are customer print content (§5).
        logger.warning(
            "lens_hallucination_dropped",
            extra={"dropped": len(dropped), "kept": len(kept)},
        )
    return kept, dropped


@dataclass
class ExtractionRunResult:
    """What one document-extraction run produced (pre-persistence)."""

    findings: list[RawFinding]
    dropped_count: int
    pages_total: int
    pages_analyzed: int
    print_pages: list[int]


def _apply_document_units(findings: list[RawFinding]) -> None:
    """Per-finding units fall back to the document default (spec: the
    ``document_units`` finding sets it; mm otherwise — DACH metric-native)."""
    doc_units = DEFAULT_DOCUMENT_UNITS
    for finding in findings:
        if finding.type == "document_units" and finding.value in ("mm", "in"):
            doc_units = finding.value
    for finding in findings:
        needs_units = finding.category in (FindingCategory.dimensions, FindingCategory.features)
        if needs_units and finding.units is None:
            finding.units = doc_units


async def run_document_extraction(provider: LensProvider, pdf: bytes) -> ExtractionRunResult:
    """The two-pass extractor over one text-extractable PDF (first 10 pages).

    Independent provider calls run concurrently (up to 12 round-trips on a
    10-print-page pack would otherwise serialize into minutes of latency)."""
    all_texts = extract_page_texts(pdf)
    page_texts = all_texts[:MAX_EXTRACTION_PAGES]

    quote_setup, is_print = await asyncio.gather(
        provider.extract_quote_setup(pdf, page_texts),
        provider.classify_print_pages(pdf, page_texts),
    )
    findings = list(quote_setup)
    print_pages = [no for no, flag in enumerate(is_print[: len(page_texts)], start=1) if flag]
    per_page = await asyncio.gather(
        *(provider.extract_requirements(pdf, no, page_texts[no - 1]) for no in print_pages)
    )
    for page_no, page_findings in zip(print_pages, per_page, strict=True):
        for finding in page_findings:
            if finding.page is None:
                finding.page = page_no
        findings.extend(page_findings)

    kept, dropped = hallucination_guard(findings, page_texts)
    _apply_document_units(kept)
    return ExtractionRunResult(
        findings=kept,
        dropped_count=len(dropped),
        pages_total=len(all_texts),
        pages_analyzed=len(page_texts),
        print_pages=print_pages,
    )
