"""Supported-file-type allow-list + classification (M1.2, spec ``#supported-file-types``).

The single source of truth for *which* uploads Tolera accepts (ingest only — no
rendering or interrogation yet; those land in M2/M4) and how a file's geometric
richness ranks, which drives the auto-PRIMARY heuristic.

Decisions encoded here (DECISIONS.md 2026-06-25, M1.2 grill):
  * The allow-list is an **app-level constant**, grouped by the
    ``VIEWER-AND-FILE-TYPES.md`` capability tiers (B-Rep CAD / mesh / 2D-vector /
    document / email / archive). A disallowed extension is rejected at the edge.
  * **PRIMARY auto-assignment** uses a file-type-tier rank — the file with the
    most geometric information wins (CAD > mesh > 2D-vector > everything else),
    mirroring the upstream "most geometric information" rule
    (``swap-primary-and-supporting-files``); ties resolve to first-uploaded.
  * A cheap **magic-byte sniff** for the common containers (PDF, ZIP, STEP)
    resists a spoofed extension; see :func:`sniff_matches_extension`.

ZIP is accepted as an opaque stored object in M1.2 — pack-and-go *unpacking* is
deferred to M4, so a ZIP ranks as low-geometry here.
"""

from __future__ import annotations

import enum
import os


class FileCategory(enum.StrEnum):
    """A supported-file capability tier (``VIEWER-AND-FILE-TYPES.md`` matrix).

    Stored on ``part_file.file_type`` and used to rank PRIMARY candidates. The
    order of declaration is *not* the rank — see :data:`_CATEGORY_RANK`."""

    brep_cad = "brep_cad"  # full B-Rep solid (STEP, native CAD) — richest geometry
    mesh = "mesh"  # tessellated surface (STL, OBJ, GLB) — additive-only interrogation
    vector_2d = "vector_2d"  # 2D vector (DXF/DWG/SVG) — flat-pattern geometry
    document = "document"  # print / image / office doc (PDF, PNG, XLSX) — no geometry
    email = "email"  # message container (MSG, EML)
    archive = "archive"  # ZIP (pack-and-go unpacked only from M4 — opaque here)


# Extension (lower-case, no dot) → category. The B-Rep + mesh + 2D lists are the
# ``#supported-file-types`` allow-list; document/email/archive cover supporting
# files (prints, vendor quotes, RFQ attachments). ``prt`` is shared by Creo and
# NX — disambiguation by header is an interrogation concern (M4), not ingest.
_EXTENSION_CATEGORY: dict[str, FileCategory] = {
    # --- B-Rep solids (full interrogation once M4 lands) ---
    **dict.fromkeys(
        (
            "step",
            "stp",
            "stpz",
            "jt",
            "iges",
            "igs",
            "ipt",
            "sat",
            "sab",
            "3dm",
            "exp",
            "model",
            "catpart",
            "catshape",
            "par",
            "psm",
            "x_b",
            "x_t",
            "sldprt",
            "neu",
            "prt",
            "ifc",
        ),
        FileCategory.brep_cad,
    ),
    # --- meshes (viewable, additive-only interrogation) ---
    **dict.fromkeys(
        (
            "stl",
            "3mf",
            "3ds",
            "dwf",
            "dwfx",
            "cgr",
            "3dxml",
            "dae",
            "glb",
            "fbx",
            "obj",
            "prc",
            "vrml",
            "wrl",
        ),
        FileCategory.mesh,
    ),
    # --- 2D vector (flat-pattern geometry for sheet/laser) ---
    **dict.fromkeys(("dxf", "dwg", "svg"), FileCategory.vector_2d),
    # --- documents (prints / images / office) ---
    **dict.fromkeys(
        ("pdf", "tif", "tiff", "jpg", "jpeg", "png", "pptx", "xlsx", "ods", "odp", "csv", "txt"),
        FileCategory.document,
    ),
    # --- email containers ---
    **dict.fromkeys(("msg", "eml"), FileCategory.email),
    # --- pack-and-go archive (opaque in M1.2; unpacked in M4) ---
    "zip": FileCategory.archive,
}

# PRIMARY-candidate rank — higher = more geometric information (DECISIONS.md
# 2026-06-25). The first file on a part with no PRIMARY, or the highest-ranked
# among a multi-file upload, becomes PRIMARY.
_CATEGORY_RANK: dict[FileCategory, int] = {
    FileCategory.brep_cad: 4,
    FileCategory.mesh: 3,
    FileCategory.vector_2d: 2,
    FileCategory.document: 1,
    FileCategory.email: 0,
    FileCategory.archive: 0,
}

# ZIP local-file-header / empty / spanned signatures. Every OOXML/ODF/3MF/OPC
# format below is really a ZIP container, so the same magic applies.
_ZIP_SIGS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
# Magic-byte signatures for the containers worth sniffing (DECISIONS.md
# 2026-06-25). A spoofed extension (e.g. a ``.exe`` renamed ``.pdf``) fails here.
# STEP is plain text with a known leading token. Keyed by extension so a ``.png``
# carrying PDF magic isn't checked against the PDF signature. The ZIP-backed allowed
# formats are sniffed too, so a renamed binary can't slip through (CodeRabbit PR #8).
_SNIFFED_EXTENSIONS: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "step": (b"ISO-10303-21",),
    "stp": (b"ISO-10303-21",),
    "zip": _ZIP_SIGS,
    "xlsx": _ZIP_SIGS,
    "pptx": _ZIP_SIGS,
    "ods": _ZIP_SIGS,
    "odp": _ZIP_SIGS,
    "3mf": _ZIP_SIGS,
    "dwfx": _ZIP_SIGS,
    "stpz": _ZIP_SIGS,
}
#: How many leading bytes a caller must read for :func:`sniff_matches_extension`.
MAGIC_SNIFF_BYTES = 16


def split_extension(filename: str) -> str:
    """Return the lower-case extension without the dot (``"Part.STEP"`` → ``"step"``).

    Empty string when there is no extension."""
    return os.path.splitext(filename)[1].lstrip(".").lower()


def classify(filename: str) -> FileCategory | None:
    """Map a filename to its :class:`FileCategory`, or ``None`` if not allowed."""
    return _EXTENSION_CATEGORY.get(split_extension(filename))


def is_allowed(filename: str) -> bool:
    """Whether the filename's extension is on the supported-file allow-list."""
    return classify(filename) is not None


def primary_rank(category: FileCategory) -> int:
    """Geometric-richness rank used to pick the auto-PRIMARY (higher wins)."""
    return _CATEGORY_RANK[category]


def sniff_matches_extension(filename: str, header: bytes) -> bool:
    """Whether ``header`` (the file's leading bytes) is consistent with the
    extension's expected magic signature.

    Returns ``True`` for any extension we don't sniff (most types have no reliable
    magic, or are plain text) — the sniff only *rejects* a clear container spoof
    (a ``.pdf``/``.zip``/``.step`` whose bytes don't match). ``header`` should be at
    least :data:`MAGIC_SNIFF_BYTES` bytes (fewer is fine for short files)."""
    expected = _SNIFFED_EXTENSIONS.get(split_extension(filename))
    if expected is None:
        return True
    return any(header.startswith(sig) for sig in expected)
