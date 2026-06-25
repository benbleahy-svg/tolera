"""M1.2 — supported-file allow-list, classification, PRIMARY rank, magic sniff.

Pure logic (no DB / storage) — always runs, even without Postgres.
"""

from __future__ import annotations

import pytest

from app.file_types import (
    FileCategory,
    classify,
    is_allowed,
    primary_rank,
    sniff_matches_extension,
    split_extension,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("bracket.step", FileCategory.brep_cad),
        ("bracket.STP", FileCategory.brep_cad),  # case-insensitive
        ("housing.SLDPRT", FileCategory.brep_cad),
        ("model.iges", FileCategory.brep_cad),
        ("scan.stl", FileCategory.mesh),
        ("web.glb", FileCategory.mesh),
        ("flat.dxf", FileCategory.vector_2d),
        ("flat.dwg", FileCategory.vector_2d),
        ("drawing.pdf", FileCategory.document),
        ("photo.JPG", FileCategory.document),
        ("bom.xlsx", FileCategory.document),
        ("rfq.eml", FileCategory.email),
        ("packed.zip", FileCategory.archive),
    ],
)
def test_classify_known_extensions(filename: str, expected: FileCategory) -> None:
    assert classify(filename) == expected
    assert is_allowed(filename) is True


@pytest.mark.parametrize("filename", ["malware.exe", "script.sh", "noext", "archive.rar", "a.dll"])
def test_disallowed_extensions(filename: str) -> None:
    assert classify(filename) is None
    assert is_allowed(filename) is False


def test_split_extension() -> None:
    assert split_extension("Part.STEP") == "step"
    assert split_extension("a.b.pdf") == "pdf"
    assert split_extension("noext") == ""


def test_primary_rank_orders_cad_above_print() -> None:
    """The auto-PRIMARY heuristic: a CAD solid outranks a print (the headline
    acceptance behaviour — upload STEP + PDF, STEP becomes PRIMARY)."""
    assert primary_rank(FileCategory.brep_cad) > primary_rank(FileCategory.mesh)
    assert primary_rank(FileCategory.mesh) > primary_rank(FileCategory.vector_2d)
    assert primary_rank(FileCategory.vector_2d) > primary_rank(FileCategory.document)
    assert primary_rank(FileCategory.document) >= primary_rank(FileCategory.archive)


def test_sniff_accepts_matching_magic() -> None:
    assert sniff_matches_extension("a.pdf", b"%PDF-1.7\n...") is True
    assert sniff_matches_extension("a.zip", b"PK\x03\x04rest") is True
    assert sniff_matches_extension("a.step", b"ISO-10303-21;\nHEADER;") is True


def test_sniff_rejects_spoofed_container() -> None:
    """A non-PDF renamed to .pdf (or non-zip to .zip) is caught by the sniff."""
    assert sniff_matches_extension("evil.pdf", b"MZ\x90\x00") is False  # a PE/exe
    assert sniff_matches_extension("evil.zip", b"not a zip") is False


def test_sniff_passes_unsniffed_types() -> None:
    """Types without a reliable magic signature are not sniffed (return True)."""
    assert sniff_matches_extension("scan.stl", b"anything") is True
    assert sniff_matches_extension("flat.dxf", b"0\nSECTION") is True


@pytest.mark.parametrize("name", ["bom.xlsx", "deck.pptx", "sheet.ods", "model.3mf", "part.stpz"])
def test_sniff_validates_zip_backed_containers(name: str) -> None:
    """OOXML/ODF/3MF/zipped-STEP are ZIP containers → must carry PK magic, so a
    renamed binary can't slip past the allow-list (CodeRabbit PR #8)."""
    assert sniff_matches_extension(name, b"PK\x03\x04rest-of-zip") is True
    assert sniff_matches_extension(name, b"MZ\x90\x00 not a zip") is False
