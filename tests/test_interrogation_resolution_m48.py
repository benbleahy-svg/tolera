"""M4.8 — most-specific CustomInterrogation resolution (pure ranking core).

INTERROGATION-ENGINE-SPEC §4 / KB ``custom-interrogations``: a profile links
to a material class, family, material and/or operation defs; the engine picks
the MOST APPLICABLE one — material beats family beats class beats the org
default (all links NULL). Op-def links are an eligibility filter (a profile
linked to ops is only a candidate when the part's process routing contains
one), and an op-matched profile outranks the bare default at equal material
specificity. Ties resolve oldest-first so re-resolution is deterministic.

No DB here — ``select_most_specific`` ranks plain candidate objects; the
wiring (material chain + process ops + RLS) is covered in
tests/test_interrogation_config_m48.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.interrogation import select_most_specific

T0 = datetime(2026, 7, 1, tzinfo=UTC)

MAT = uuid.uuid4()  # e.g. EN AW-6061
FAM = uuid.uuid4()  # e.g. Aluminium
CLS = uuid.uuid4()  # e.g. Metall
OTHER_MAT = uuid.uuid4()
OTHER_FAM = uuid.uuid4()
OP_A = uuid.uuid4()
OP_B = uuid.uuid4()


@dataclass
class Candidate:
    """The attribute shape ``select_most_specific`` reads (mirrors the model)."""

    material_id: uuid.UUID | None = None
    material_family_id: uuid.UUID | None = None
    material_class_id: uuid.UUID | None = None
    created_at: datetime = T0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


def pick(
    candidates: list[Candidate],
    *,
    material_id: uuid.UUID | None = MAT,
    material_family_id: uuid.UUID | None = FAM,
    material_class_id: uuid.UUID | None = CLS,
    op_links: dict[uuid.UUID, set[uuid.UUID]] | None = None,
    process_operation_def_ids: set[uuid.UUID] | None = None,
) -> Candidate | None:
    return select_most_specific(
        candidates,
        material_id=material_id,
        material_family_id=material_family_id,
        material_class_id=material_class_id,
        op_links=op_links or {},
        process_operation_def_ids=process_operation_def_ids or set(),
    )


# --------------------------------------------------------------------------- #
# The specificity ladder: material > family > class > default
# --------------------------------------------------------------------------- #
def test_material_link_beats_family_link() -> None:
    family_level = Candidate(material_family_id=FAM)
    material_level = Candidate(material_id=MAT)
    assert pick([family_level, material_level]) is material_level


def test_family_link_beats_class_link() -> None:
    class_level = Candidate(material_class_id=CLS)
    family_level = Candidate(material_family_id=FAM)
    assert pick([class_level, family_level]) is family_level


def test_class_link_beats_default() -> None:
    default = Candidate()
    class_level = Candidate(material_class_id=CLS)
    assert pick([default, class_level]) is class_level


def test_default_wins_when_nothing_more_specific_matches() -> None:
    default = Candidate()
    unrelated = Candidate(material_family_id=OTHER_FAM)
    assert pick([unrelated, default]) is default


def test_non_matching_linked_profile_is_never_selected() -> None:
    unrelated = Candidate(material_id=OTHER_MAT)
    assert pick([unrelated]) is None


def test_no_candidates_returns_none() -> None:
    assert pick([]) is None


def test_part_without_material_resolves_only_the_default() -> None:
    material_level = Candidate(material_id=MAT)
    default = Candidate()
    assert (
        pick(
            [material_level, default],
            material_id=None,
            material_family_id=None,
            material_class_id=None,
        )
        is default
    )


def test_row_with_multiple_links_ranks_by_its_most_specific_match() -> None:
    # Material link points elsewhere, family link matches -> ranks as family (2),
    # so a true material-level row still beats it.
    combo = Candidate(material_id=OTHER_MAT, material_family_id=FAM)
    material_level = Candidate(material_id=MAT)
    assert pick([combo, material_level]) is material_level
    assert pick([combo, Candidate(material_class_id=CLS)]) is combo


# --------------------------------------------------------------------------- #
# Op-def links: eligibility filter + half-step above the bare default
# --------------------------------------------------------------------------- #
def test_op_linked_profile_requires_a_matching_process_op() -> None:
    linked = Candidate()
    default = Candidate()
    op_links = {linked.id: {OP_A}}
    # Process routing does not contain OP_A -> the linked profile is ineligible.
    assert pick([linked, default], op_links=op_links, process_operation_def_ids={OP_B}) is default
    # No process context at all -> same.
    assert pick([linked, default], op_links=op_links) is default


def test_op_matched_profile_beats_the_bare_default() -> None:
    linked = Candidate()
    default = Candidate()
    op_links = {linked.id: {OP_A}}
    assert pick([linked, default], op_links=op_links, process_operation_def_ids={OP_A}) is linked


def test_material_specificity_dominates_op_match() -> None:
    # KB: selection is "based on its material" — an op-matched default-material
    # profile never outranks a family-level material match.
    op_matched = Candidate()
    family_level = Candidate(material_family_id=FAM)
    op_links = {op_matched.id: {OP_A}}
    assert (
        pick([op_matched, family_level], op_links=op_links, process_operation_def_ids={OP_A})
        is family_level
    )


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_equal_specificity_tie_breaks_oldest_first() -> None:
    older = Candidate(material_family_id=FAM, created_at=T0)
    newer = Candidate(material_family_id=FAM, created_at=T0 + timedelta(minutes=1))
    assert pick([newer, older]) is older
    assert pick([older, newer]) is older


def test_identical_timestamps_tie_break_on_id() -> None:
    a, b = sorted([Candidate(material_id=MAT), Candidate(material_id=MAT)], key=lambda c: c.id)
    assert pick([b, a]) is a
    assert pick([a, b]) is a
