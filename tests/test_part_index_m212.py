"""M2.12 — Part-Library index fields (spec `#partlib` "How matching works").

Pure-helper contract for `app/part_index.py`: filename normalization (File Name
Match key), SHA-256 file hashing (Exact File Match key), deterministic STEP
`PRODUCT` part-number extraction (Part Number Match key — the Lens/M3 title-block
path stays out per CLAUDE.md §5 never-hallucinate), and PDF text extraction
(the `pdf_text` full-text column behind the global Parts-Library search).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.part_index import (
    PDF_TEXT_MAX_CHARS,
    extract_pdf_text,
    extract_step_part_number,
    file_sha256,
    normalize_filename,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
STEP_BYTES = (FIXTURES / "cad" / "cube-20mm.step").read_bytes()
PDF_BYTES = (FIXTURES / "drawings" / "halter-4711-rev-b.pdf").read_bytes()


class TestNormalizeFilename:
    """spec#partlib: "strip extension, lowercase, tokenize"."""

    def test_strips_extension_and_lowercases(self) -> None:
        assert normalize_filename("Bracket.stp") == "bracket"

    def test_tokenizes_separators_to_single_underscore(self) -> None:
        # The KB merge example: print `5-X-9__B.pdf` vs model `5-X-9.STEP`.
        assert normalize_filename("5-X-9__B.pdf") == "5_x_9_b"
        assert normalize_filename("5-X-9.STEP") == "5_x_9"

    def test_spaces_and_mixed_separators(self) -> None:
        assert normalize_filename("3601215 _ OFFSET CONNECTOR.STEP") == "3601215_offset_connector"

    def test_same_stem_different_extension_normalizes_equal(self) -> None:
        # The auto-bundling key: Bracket.stp + Bracket.pdf → one part.
        assert normalize_filename("Bracket.stp") == normalize_filename("Bracket.pdf")

    def test_only_last_extension_is_stripped(self) -> None:
        assert normalize_filename("halter.4711.step") == "halter_4711"

    def test_no_extension(self) -> None:
        assert normalize_filename("README") == "readme"

    def test_degenerate_name_yields_none(self) -> None:
        # An empty key must never join (empty-string equality would cross-match).
        assert normalize_filename("---.pdf") is None


class TestFileSha256:
    def test_matches_hashlib_hexdigest(self) -> None:
        assert file_sha256(STEP_BYTES) == hashlib.sha256(STEP_BYTES).hexdigest()

    def test_byte_identical_files_hash_equal(self) -> None:
        assert file_sha256(PDF_BYTES) == file_sha256(bytes(PDF_BYTES))


class TestExtractStepPartNumber:
    def test_reads_product_entity_from_fixture(self) -> None:
        assert extract_step_part_number(STEP_BYTES) == "cube-20mm"

    def test_does_not_match_product_context(self) -> None:
        # PRODUCT_CONTEXT / PRODUCT_DEFINITION entities must not be mistaken
        # for the PRODUCT record that carries the part id.
        body = (
            b"#1=PRODUCT_CONTEXT('ctx',#2,'mechanical');\n#3=PRODUCT_DEFINITION('x','y',#4,#5);\n"
        )
        assert extract_step_part_number(body) is None

    def test_empty_product_id_yields_none(self) -> None:
        assert extract_step_part_number(b"#1=PRODUCT('','desc','',(#2));") is None

    def test_non_step_bytes_yield_none(self) -> None:
        assert extract_step_part_number(PDF_BYTES) is None


class TestExtractPdfText:
    def test_reads_title_block_text(self) -> None:
        text = extract_pdf_text(PDF_BYTES)
        assert text is not None
        assert "Halter 4711" in text
        assert "1.4301" in text  # Werkstoffnummer survives extraction

    def test_garbage_bytes_yield_none(self) -> None:
        assert extract_pdf_text(b"ISO-10303-21; not a pdf") is None

    def test_output_is_capped(self) -> None:
        text = extract_pdf_text(PDF_BYTES)
        assert text is not None
        assert len(text) <= PDF_TEXT_MAX_CHARS
