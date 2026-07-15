"""Rules AST evaluator (M3.7) — the deterministic core behind review items.

Spec ``#rules-engine`` / ``#rules-signals``; RULES-ENGINE-SPEC §4 build note
("a small, serializable **query AST** over the part's analyzed data") and §8
(the integration map naming each signal's producer).

Given a component's analyzed data, walk the M3.6 rule AST (:mod:`app.rules_schema`)
and decide which rules match. This module is **pure** — no DB, no session, no
I/O: :class:`EvaluationContext` in, matched rules out. Review-item creation,
the lifecycle and the resolution mutations are M3.8; loading the context from
DB rows is M3.8's wiring. That split keeps the semantics below exhaustively
testable without a database.

Three things this module gets right, because they are the ones that are easy to
get wrong:

**Interrogation gating** (§2, §9). An interrogation-result signal must *not*
fire before the relevant interrogation has run — per *family*, so a sheet-metal
run does not un-gate a ``three_axis_mill`` signal. A gated group evaluates to
**False**, not "skip": treating it as neutral would let an AND rule fire while
claiming an unmeasured condition holds. The signal sources themselves arrive
with M4's GeometryService; until then ``interrogation_result`` is simply absent
and these groups stay silent.

**Combination semantics** (§4, "the part everyone gets wrong"). A group's
``logical_operator`` combines its queries *within a single item* — an AND group
needs **one** item satisfying every query, not one item per query. Groups
combine within a signal, signals within a rule, by their own operators.

**Normalization** (§7 DACH). Collections are built with their numeric fields
already in **mm** / **deg** using each finding's own ``units``; a query's
threshold is converted from ``units`` at comparison time. A missing unit means
mm/deg — never inches (CLAUDE.md §5, metric-native). ``in`` stays accepted so a
pasted PP rule set still evaluates correctly.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .rules_schema import CONTROL_FRAME_PATHS, Group, Query, RuleSchema, Signal

#: Exact by definition (ISO 2768 / international inch).
MM_PER_INCH = 25.4

#: Unit spellings a finding may carry for an inch value. Findings store units
#: as free text (``extraction_finding.units``), so match leniently — but only
#: an explicit inch marker converts; everything else is mm (the DACH default).
_INCH_UNITS = frozenset({"in", "in.", "inch", "inches", '"', "zoll"})

#: ``document_path`` → the ``extraction_finding.type`` carrying that tolerance
#: (the Lens dimensions taxonomy: length/diameter/radius/angle).
_TOLERANCE_PATH_TYPES = {
    "length_tolerances": "length",
    "diameter_tolerances": "diameter",
    "radius_tolerances": "radius",
    "angular_tolerances": "angle",
}

#: Only a *length-like* dimension is a distance: an angle written as mm would
#: be silently wrong (the ``_AXIS_SOURCE_TYPES`` precedent in M3.2's
#: ``lens_findings``). Drives greatest/least_distance_dimension.
_DISTANCE_DIMENSION_TYPES = frozenset({"length", "diameter", "radius"})

#: ISO GPS symbology → the control-frame characteristic (§7: "control-frame
#: signals interpret ISO GPS symbology"). ``gdt.symbol`` is an open field —
#: M3.1's prompt asks for "control_frame with ISO GPS symbols" but the model may
#: equally emit the English characteristic name, so :func:`_frame_characteristic`
#: accepts either. The 13 keys mirror ``CONTROL_FRAME_PATHS``.
_ISO_GPS_SYMBOLS = {
    "⏤": "straightness",
    "⏥": "flatness",
    "○": "circularity",
    "⌭": "cylindricity",
    "⌒": "profile_of_line",
    "⌓": "profile_of_surface",
    "∥": "parallelism",
    "⊥": "perpendicularity",
    "⌖": "position",
    "◎": "concentricity",
    "⌯": "symmetry",
    "↗": "runout",
    "⌰": "total_runout",
}

_CHARACTERISTICS = frozenset(path.removesuffix("_control_frames") for path in CONTROL_FRAME_PATHS)

#: Distinguishes "field absent" from "field present but null" — a null value
#: never satisfies a predicate, and neither raises.
_MISSING = object()


@dataclass(frozen=True)
class EvaluationContext:
    """A component's analyzed data — the evaluator's whole world (§4 build note).

    ``extractions`` are :class:`app.models.ExtractionFinding` rows as mappings
    (Lens); ``document_texts`` is one entry per document's text layer, the
    ``text`` document_path's source (§2: "raw text from any .pdf .tiff .doc
    .docx" — the *document*, of which findings are only a subset).
    ``part_attributes`` is the ``part``/``part_geometry`` attribute mapping,
    already metric (``PartGeometry`` stores effective mm/mm²/mm³/g).
    ``files`` is ``{has_model, has_print}``; absent means neither exists.
    ``interrogation_result`` is keyed by family (``three_axis_mill``,
    ``sheet_metal``, ``tube_laser``, ``lathe``) → property → value, and its
    absence is what gates those signals off until M4.

    ``line_item`` / ``quote`` complete the §4 context but are currently inert:
    M3.6's ``document_path`` catalog exposes no path addressing them (§2 lists
    min/max qty and account as signal categories — cataloging them is a schema
    change, M3.6's domain, not this evaluator's).
    """

    extractions: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    document_texts: Sequence[str] = field(default_factory=tuple)
    part_attributes: Mapping[str, Any] | None = None
    files: Mapping[str, Any] | None = None
    interrogation_result: Mapping[str, Mapping[str, Any]] | None = None
    line_item: Mapping[str, Any] | None = None
    quote: Mapping[str, Any] | None = None


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def evaluate_rules(rules: Sequence[RuleSchema], ctx: EvaluationContext) -> list[RuleSchema]:
    """The rules that match ``ctx``, input order preserved.

    Matches only — M3.8 turns these into review items. Filtering out inactive
    rules is the caller's job (``rule.is_active`` is an internal flag, not part
    of the canonical AST).
    """
    return [rule for rule in rules if evaluate_rule(rule, ctx)]


def evaluate_rule(rule: RuleSchema, ctx: EvaluationContext) -> bool:
    """Does this rule's signal set match the component's data?"""
    return _combine(rule.logical_operator, (_eval_signal(s, ctx) for s in rule.signals))


# --------------------------------------------------------------------------- #
# AST walk
# --------------------------------------------------------------------------- #
def _combine(operator: str, results: Iterable[bool]) -> bool:
    """AND → all, OR → any (§4: "Same recursion applies" at every level)."""
    return all(results) if operator == "AND" else any(results)


def _eval_signal(signal: Signal, ctx: EvaluationContext) -> bool:
    return _combine(signal.logical_operator, (_eval_group(g, ctx) for g in signal.groups))


def _eval_group(group: Group, ctx: EvaluationContext) -> bool:
    """A group tests one collection: does an item satisfy the predicates?

    Gating (§9): an unavailable interrogation collection yields ``None`` and the
    group is False — the interrogation has not run, so its condition is not
    known to hold.
    """
    collection = _resolve_collection(group.document_path, ctx)
    if collection is None:
        return False

    matching = [item for item in collection if _item_matches(group, item)]
    if group.count_query is not None:
        # count_query tests the count of *matching* items — with no queries that
        # degenerates to the collection's own count (the §5 rule-4 usage). It is
        # authoritative when present: "at most 2 X" must match a component with
        # none.
        return _compare_numeric(
            float(len(matching)), group.count_query.operator, float(group.count_query.value)
        )
    return bool(matching)


def _item_matches(group: Group, item: Mapping[str, Any]) -> bool:
    """An AND group needs ONE item satisfying every query — not one item per
    query (§4). A group with only a count_query matches every item."""
    if not group.queries:
        return True
    return _combine(group.logical_operator, (_eval_query(q, item) for q in group.queries))


def _eval_query(query: Query, item: Mapping[str, Any]) -> bool:
    value = _lookup(item, query.field_name)
    if value is _MISSING or value is None:
        return False

    if query.filter_type == "numeric":
        actual = _as_number(value)
        if actual is None:
            return False
        threshold = _normalize_threshold(query.value, query.value_type, query.units)
        if threshold is None:
            return False
        return _compare_numeric(actual, query.operator, threshold)

    if query.filter_type == "boolean":
        return isinstance(value, bool) and value == query.value

    return _compare_string(str(value), query.operator, query.value)


def _lookup(item: Mapping[str, Any], field_name: Sequence[str]) -> Any:
    """``field_name`` is a path — the fixture is uniformly arity-1, where a path
    and a plain field name coincide; nesting generalizes it."""
    current: Any = item
    for part in field_name:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #
def _compare_numeric(actual: float, operator: str, threshold: float) -> bool:
    if operator == "lessThanOrEqual":
        return actual <= threshold or math.isclose(actual, threshold, rel_tol=1e-9)
    if operator == "greaterThanOrEqual":
        return actual >= threshold or math.isclose(actual, threshold, rel_tol=1e-9)
    # `equals` on a float that survived a unit conversion cannot use `==`:
    # 12 in → 304.79999999999995 mm must still equal 304.8.
    return math.isclose(actual, threshold, rel_tol=1e-9, abs_tol=1e-12)


def _compare_string(actual: str, operator: str, expected: Any) -> bool:
    if operator == "includesCaseInsensitive":
        keywords = expected if isinstance(expected, list) else [expected]
        haystack = actual.casefold()
        return any(str(k).casefold() in haystack for k in keywords)
    if operator == "regex":
        # MULTILINE: a print's text layer is line-oriented, and the §5 rule-7
        # pattern the spec dictates is anchored (``^SPX-[A-Za-z0-9-]+$``). Bound
        # to the whole document those anchors would only ever match a file whose
        # entire text is one spec code — the rule would be dead on arrival. Per
        # line, it means what it reads as: a line that *is* a spec code.
        return re.search(str(expected), actual, re.MULTILINE) is not None
    # `equals` admits a keyword list too (the schema allows a list value on any
    # string filter). Comparing str to list would silently never match, so read
    # a list as any-of — the only sensible reading of "equals one of these".
    if isinstance(expected, list):
        return any(actual == str(k) for k in expected)
    return bool(actual == expected)


# --------------------------------------------------------------------------- #
# units & numbers
# --------------------------------------------------------------------------- #
def _normalize_threshold(value: Any, value_type: str, units: str | None) -> float | None:
    """A query's threshold in the collection's units (mm / deg).

    Only ``distance`` converts — ``deg`` is the sole angle unit in the catalog,
    and number/string/boolean carry no unit. A null unit is mm/deg: the DACH
    default is never inches (§7).
    """
    number = _as_number(value)
    if number is None:
        return None
    if value_type == "distance" and _is_inches(units):
        return number * MM_PER_INCH
    return number


def _is_inches(units: str | None) -> bool:
    return units is not None and units.strip().casefold() in _INCH_UNITS


def _to_mm(value: float, units: str | None) -> float:
    return value * MM_PER_INCH if _is_inches(units) else value


def _as_number(value: Any) -> float | None:
    """Parse a finding's value. ``None`` means "not a number" — the caller
    treats that as no-match rather than an error: a dimension reading
    "siehe Tabelle" must not fire a threshold rule, nor raise.

    Findings store values as text, and a German print writes ``0,05``
    (German-first, CLAUDE.md §5). Separator handling: the **last** of ``.``/``,``
    is the decimal separator, any earlier one is a thousands separator — so
    ``1.234,56`` → 1234.56 and ``0,05`` → 0.05.
    """
    if isinstance(value, bool):
        return None
    # Decimal, not just int/float: every part_geometry dimension is a Numeric
    # column, so the real part_attributes mapping hands us Decimal — rejecting
    # it would silently kill every `part` rule the moment M3.8 wires the row.
    if isinstance(value, int | float | Decimal):
        number = float(value)
        return number if math.isfinite(number) else None
    if not isinstance(value, str):
        return None

    # A trailing separator is punctuation, not a decimal point: without this
    # "0,05." reads its dot as the decimal separator and strips the comma as
    # thousands, giving 5.0 — a silent 100x error.
    text = value.strip().rstrip(".,")
    if not text:
        return None
    last_dot, last_comma = text.rfind("."), text.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal, thousands = (",", ".") if last_comma > last_dot else (".", ",")
        text = text.replace(thousands, "").replace(decimal, ".")
    elif last_comma >= 0:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _finding_number(finding: Mapping[str, Any]) -> float | None:
    """A finding's ``value``, normalized to mm/deg by its own ``units``.

    Deliberately **not** ``normalized_value``: that channel has no pinned unit
    semantics (M3.1's provider schema requires the field but neither prompt
    defines what "normalized" means), so pairing it with ``units`` could convert
    a value that was already converted. M3.2's accept path reached the same
    conclusion and reads ``value`` for exactly this reason (ship-review
    2026-07-15, ``lens_findings``). ``value`` is also the guarded channel — the
    never-hallucinate rule covers it, but not ``normalized_value``.
    """
    number = _as_number(finding.get("value"))
    if number is None:
        return None
    return _to_mm(number, finding.get("units"))


# --------------------------------------------------------------------------- #
# collection resolution (§4 document_path catalog)
# --------------------------------------------------------------------------- #
def _resolve_collection(path: str, ctx: EvaluationContext) -> list[Mapping[str, Any]] | None:
    """The items addressed by ``document_path``, or ``None`` if the collection
    is *gated* — an interrogation that has not run (§9). An empty list is a
    different thing: the collection exists and holds nothing."""
    if "." in path:
        return _resolve_interrogation(path, ctx)
    if path in _TOLERANCE_PATH_TYPES:
        return _tolerance_items(ctx, _TOLERANCE_PATH_TYPES[path])
    if path in CONTROL_FRAME_PATHS:
        return _frame_items(ctx, path.removesuffix("_control_frames"))
    if path == "control_frames":
        return _frame_items(ctx, None)
    if path == "datums":
        return [f for f in ctx.extractions if f.get("type") == "datum"]
    if path in ("greatest_distance_dimension", "least_distance_dimension"):
        return _extreme_dimension(ctx, greatest=path.startswith("greatest"))
    if path == "part":
        return [ctx.part_attributes] if ctx.part_attributes is not None else []
    if path == "files":
        # No file record at all means the part has neither a model nor a print —
        # exactly what the §5 "Missing model or print" rule must catch.
        return [ctx.files if ctx.files is not None else {"has_model": False, "has_print": False}]
    if path == "text":
        return [{"raw_text": text} for text in ctx.document_texts]
    return []


def _resolve_interrogation(path: str, ctx: EvaluationContext) -> list[Mapping[str, Any]] | None:
    """``<family>.<property>`` — gated on *that family* having been interrogated.

    Returns ``None`` (gated) when the family has not run; the property's value
    is a collection to count/test. M4's GeometryService supplies the real
    ``AnalysisResult``; the shape assumed here is family → property → value.
    """
    family, _, prop_path = path.partition(".")
    if ctx.interrogation_result is None or family not in ctx.interrogation_result:
        return None
    value: Any = ctx.interrogation_result[family]
    for part in prop_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return []
        value = value[part]
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [item if isinstance(item, Mapping) else {"value": item} for item in value]
    return [{"value": value}]


def _tolerance_items(ctx: EvaluationContext, finding_type: str) -> list[Mapping[str, Any]]:
    """Toleranced dimensions of one type, exposing ``smallest_delta`` (§4:
    "tightest of upper/lower") alongside the dimension's own ``value``."""
    items: list[Mapping[str, Any]] = []
    for finding in ctx.extractions:
        if finding.get("type") != finding_type or not isinstance(finding.get("tolerance"), Mapping):
            continue
        delta = _smallest_delta(finding["tolerance"], finding.get("units"))
        if delta is None:
            continue
        items.append({"smallest_delta": delta, "value": _finding_number(finding)})
    return items


def _smallest_delta(tolerance: Mapping[str, Any], units: str | None) -> float | None:
    """The tightest side of a tolerance, in mm/deg.

    ``unilateral``/``bilateral`` carry deltas → ``min(|upper|, |lower|)`` over
    the **non-zero** sides. ``limit`` carries absolute limits, not deltas — its
    equivalent ± band is ``(upper - lower) / 2``.

    ASSUMED (DECISIONS.md ``OPEN:`` 2026-07-16): the zero-side exclusion. Read
    literally, "tightest of upper/lower" makes a ``+0.5/-0`` callout yield 0 —
    tighter than anything — so *every* unilateral ``+X/-0``, including ``+5/-0``,
    would fire the §5 tight-tolerance rule as a false positive; the identical
    requirement written as the limits ``25.0/25.5`` yields 0.25 and does not,
    so the two branches would contradict each other. Excluding zero sides keeps
    the reading for real tolerances (``±0.05`` → 0.05, ``+0.1/-0.05`` → 0.05)
    without the degeneracy. A genuinely zero-tolerance callout (both sides 0)
    still yields 0 and still fires. The KB defines PP's rule *set* but never
    this computation, so the ladder is silent — cheap to reverse (one function,
    fixtures only, no shop has authored a rule yet), hence a default not a halt.
    """
    upper = _as_number(tolerance.get("upper"))
    lower = _as_number(tolerance.get("lower"))
    if tolerance.get("kind") == "limit":
        if upper is None or lower is None:
            return None
        return _to_mm(abs(upper - lower) / 2, units)
    sides = [abs(side) for side in (upper, lower) if side is not None]
    toleranced = [side for side in sides if side > 0]
    if toleranced:
        return _to_mm(min(toleranced), units)
    return _to_mm(0.0, units) if sides else None


def _frame_items(ctx: EvaluationContext, characteristic: str | None) -> list[Mapping[str, Any]]:
    """Control frames — all of them, or one characteristic's.

    Each exposes ``value`` (the tolerance zone, mm) and ``datum_count`` (how
    many datums the frame references), the two fields the §4 catalog names.
    """
    items: list[Mapping[str, Any]] = []
    for finding in ctx.extractions:
        if finding.get("type") != "control_frame":
            continue
        if characteristic is not None and _frame_characteristic(finding) != characteristic:
            continue
        gdt = finding.get("gdt")
        datum_refs = gdt.get("datum_refs") if isinstance(gdt, Mapping) else None
        items.append({"value": _finding_number(finding), "datum_count": _count(datum_refs)})
    return items


def _count(value: Any) -> int:
    """How many entries a JSONB collection holds — 0 for anything else.

    ``gdt`` is unvalidated on read and a ``str`` IS a ``Sequence``, so without
    the exclusion ``datum_refs: "A|B|C"`` would count 5 datums (the same
    exclusion :func:`_resolve_interrogation` applies).
    """
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        return 0
    return len(value)


def _frame_characteristic(finding: Mapping[str, Any]) -> str | None:
    """Which characteristic a control frame carries — by ISO GPS symbol or by
    name, since ``gdt.symbol`` is an open field (M3.1's taxonomy is open)."""
    gdt = finding.get("gdt")
    if not isinstance(gdt, Mapping):
        return None
    symbol = gdt.get("symbol")
    if not isinstance(symbol, str):
        return None
    symbol = symbol.strip()
    if symbol in _ISO_GPS_SYMBOLS:
        return _ISO_GPS_SYMBOLS[symbol]
    name = symbol.casefold().replace(" ", "_").replace("-", "_")
    return name if name in _CHARACTERISTICS else None


def _extreme_dimension(ctx: EvaluationContext, *, greatest: bool) -> list[Mapping[str, Any]]:
    """The largest / smallest linear dimension on the print, in mm — a
    singleton collection, empty when the print carries no distance dimension."""
    values = [
        number
        for finding in ctx.extractions
        if finding.get("type") in _DISTANCE_DIMENSION_TYPES
        and (number := _finding_number(finding)) is not None
    ]
    if not values:
        return []
    return [{"value": max(values) if greatest else min(values)}]
