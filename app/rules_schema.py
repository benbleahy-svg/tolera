"""Canonical review-rule schema — the portable query AST (M3.6).

Spec ``#rules-schema`` ("build to this") / RULES-ENGINE-SPEC §4: a rule set
imports/exports as a **single JSON string** (paste-in on the rules config
page) so rule sets are portable and diffable. This module owns that contract:

* the Pydantic models for ``Rule → Signal → Group → Query → Resolution`` with
  the exact spec literal sets (operators, value/filter types, resolutions);
* the ``document_path`` catalog (spec ``#rules-paths``) — a closed set plus a
  pattern for the per-family interrogation paths, whose property sets stay
  open until GeometryService lands (M4);
* :func:`parse_rules_json` / :func:`serialize_rules` — the canonical
  serialization. Canonical form follows the Kalk precedent (DECISIONS.md
  2026-07-08): sorted keys, compact separators, ``ensure_ascii=False``, rules
  ordered by ``uuid`` — so ``serialize(parse(s)) == s`` for canonical input
  (the round-trip acceptance criterion).

``units``/``value_type`` are **retained verbatim** — normalization to mm/deg
is the M3.7 evaluator's job, never done at import. ``"in"`` stays accepted
for pasted PP rule sets; the DACH delta forbids the imperial *default*, not
the unit (RULES-ENGINE-SPEC §2/§7).
"""

from __future__ import annotations

import json
import re  # internal, developer-authored patterns only (INTERROGATION_PATH)
import uuid as uuid_mod
from typing import Annotated, Literal

import regex  # the engine that executes org-authored rule patterns
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

# --------------------------------------------------------------------------- #
# document_path catalog (spec #rules-paths)
# --------------------------------------------------------------------------- #
TOLERANCE_PATHS = frozenset(
    {"length_tolerances", "diameter_tolerances", "radius_tolerances", "angular_tolerances"}
)

#: The 13 per-characteristic control-frame collections (ISO GPS symbology).
CONTROL_FRAME_PATHS = frozenset(
    f"{characteristic}_control_frames"
    for characteristic in (
        "flatness",
        "parallelism",
        "perpendicularity",
        "position",
        "cylindricity",
        "straightness",
        "concentricity",
        "profile_of_line",
        "profile_of_surface",
        "runout",
        "total_runout",
        "symmetry",
        "circularity",
    )
)

#: Aggregate frame/datum count collections (typically used with count_query).
COUNT_PATHS = frozenset({"control_frames", "datums"})

DIMENSION_PATHS = frozenset({"greatest_distance_dimension", "least_distance_dimension"})

#: Single-item collections: part attributes, file presence, document text.
SINGLETON_PATHS = frozenset({"part", "files", "text"})

DOCUMENT_PATH_CATALOG = frozenset(
    TOLERANCE_PATHS | CONTROL_FRAME_PATHS | COUNT_PATHS | DIMENSION_PATHS | SINGLETON_PATHS
)

#: Interrogation-result paths are per-family properties (e.g.
#: ``three_axis_mill.machine_direction``). The property sets arrive with M4's
#: GeometryService, so v1 validates the family + a dotted-identifier shape
#: rather than a closed list (they stay gated off in the M3.7 evaluator).
INTERROGATION_PATH = re.compile(
    r"^(three_axis_mill|sheet_metal|tube_laser|lathe)\.[a-z0-9_]+(\.[a-z0-9_]+)*$"
)

# --------------------------------------------------------------------------- #
# Import-time ReDoS reject (DECISIONS.md 2026-07-16, option (b))
# --------------------------------------------------------------------------- #
#: Budget for a single probe of an authored pattern. Small: this runs per regex
#: query on the import path, and a *safe* pattern returns in microseconds — only
#: a pathological one ever spends the budget.
_PROBE_TIMEOUT_SECONDS = 0.1

#: Adversarial probes: long runs that fail to match only at the very end, which
#: is the shape that forces a backtracking engine to explore every partition.
#: Deliberately generic — this is a best-effort early warning, not the
#: guarantee. The guarantee is option (a), the enforced timeout in
#: ``app.rules_eval._search_bounded``; a pattern whose blow-up these probes miss
#: is still contained there, just later and more quietly.
_REDOS_PROBES = (
    "a" * 64 + "!",
    "1" * 64 + "!",
    "ab" * 32 + "!",
    "1-" * 32 + "!",
    " " * 64 + "!",
)


def _rejects_as_catastrophic(pattern: str) -> bool:
    """Does ``pattern`` blow up on an adversarial probe within the budget?

    **Empirical, not structural** — and that distinction is the whole design.
    The obvious reading of option (b) is "reject nested quantifiers", but the
    ``regex`` engine *optimizes those away*: ``^(a+)+$`` and ``(\\d+[ -]?)+``
    (the very pattern the DECISIONS entry was written about) both return in
    under a millisecond against a 4096-char probe. A structural check would
    reject provably-safe patterns and train authors to route around it. Running
    the pattern instead rejects only what actually misbehaves *on the engine
    that will execute it*.
    """
    for probe in _REDOS_PROBES:
        try:
            regex.search(pattern, probe, flags=regex.MULTILINE, timeout=_PROBE_TIMEOUT_SECONDS)
        except TimeoutError:
            return True
        except regex.error:
            # Not our failure to report: the compile check above owns it.
            return False
    return False


#: Which operators each filter_type admits — one map so a future operator
#: can't be added to one branch and forgotten in another.
FILTER_TYPE_OPERATORS: dict[str, tuple[str, ...]] = {
    "numeric": ("lessThanOrEqual", "greaterThanOrEqual", "equals"),
    "boolean": ("equals",),
    "string": ("equals", "includesCaseInsensitive", "regex"),
}

QueryOperator = Literal[
    "lessThanOrEqual", "greaterThanOrEqual", "equals", "includesCaseInsensitive", "regex"
]
LogicalOperator = Literal["AND", "OR"]

#: A query's comparison value: scalar, keyword list, or regex string. Strict
#: members keep JSON types verbatim (True must never collapse into 1, nor
#: 305 into 305.0 — byte-equivalence depends on it).
QueryValue = StrictBool | StrictInt | StrictFloat | StrictStr | list[StrictStr]


class CountQuery(BaseModel):
    """Test the COUNT of items in the group's collection (spec #rules-schema)."""

    model_config = ConfigDict(extra="forbid")

    operator: Literal["lessThanOrEqual", "greaterThanOrEqual", "equals"]
    value: Annotated[StrictInt, Field(ge=0)]


class Query(BaseModel):
    """A field-level predicate within a document_path collection."""

    model_config = ConfigDict(extra="forbid")

    field_name: Annotated[list[StrictStr], Field(min_length=1)]
    operator: QueryOperator
    value: QueryValue
    value_type: Literal["distance", "angle", "number", "string", "boolean"]
    filter_type: Literal["numeric", "string", "boolean"]
    units: Literal["mm", "deg", "in"] | None

    @model_validator(mode="after")
    def _value_matches_filter_type(self) -> Query:
        if self.operator == "regex":
            if not isinstance(self.value, str):
                raise ValueError("a regex query's value must be a pattern string")
            try:
                # Validate with the engine that will EXECUTE this pattern
                # (``app.rules_eval._search_bounded``), not stdlib ``re``:
                # validating with a different engine than the one that runs it
                # is how a set imports clean and then never fires.
                regex.compile(self.value)
            except regex.error as exc:
                raise ValueError(f"invalid regex pattern: {exc}") from exc
            # Option (b): reject at config time, while the author is looking at
            # the pattern. The evaluator's timeout (option (a)) already makes a
            # runaway pattern *safe*, but it fails closed silently — the rule
            # merely never fires, which surfaces as a support mystery weeks
            # later. Refusing the paste is the honest moment to say so.
            if _rejects_as_catastrophic(self.value):
                raise ValueError(
                    f"das Regex-Muster {self.value!r} braucht zu lange und wurde abgelehnt: "
                    "Es kann bei bestimmten Zeichenketten katastrophal zurücksetzen "
                    "(ReDoS) und die Regelauswertung blockieren. Bitte verschachtelte "
                    "Quantoren und überlappende Alternativen vermeiden (z. B. '(a|a)+')."
                )
        if self.operator not in FILTER_TYPE_OPERATORS[self.filter_type]:
            raise ValueError(f"a {self.filter_type} filter does not support {self.operator}")
        if self.filter_type == "numeric":
            if isinstance(self.value, bool) or not isinstance(self.value, int | float):
                raise ValueError("a numeric filter needs a numeric value")
        elif self.filter_type == "boolean":
            if not isinstance(self.value, bool):
                raise ValueError("a boolean filter needs a true/false value")
        elif not isinstance(self.value, str | list):
            raise ValueError("a string filter needs a string or keyword-list value")
        return self


class Group(BaseModel):
    """WHAT collection to test + the predicates over it."""

    model_config = ConfigDict(extra="forbid")

    document_path: StrictStr
    logical_operator: LogicalOperator
    queries: list[Query]
    count_query: CountQuery | None

    @field_validator("document_path")
    @classmethod
    def _known_document_path(cls, path: str) -> str:
        if path in DOCUMENT_PATH_CATALOG or INTERROGATION_PATH.fullmatch(path):
            return path
        raise ValueError(f"unknown document_path {path!r} — not in the spec #rules-paths catalog")

    @model_validator(mode="after")
    def _has_a_predicate(self) -> Group:
        if not self.queries and self.count_query is None:
            raise ValueError("a group needs at least one query or a count_query")
        return self


class Signal(BaseModel):
    """One "case" — a conjunction/disjunction of groups."""

    model_config = ConfigDict(extra="forbid")

    logical_operator: LogicalOperator
    groups: Annotated[list[Group], Field(min_length=1)]


class ResolutionParameter(BaseModel):
    """A named resolution argument (e.g. op_def_ids) — retained verbatim;
    wiring/validation against the org catalog is M3.8's scope."""

    model_config = ConfigDict(extra="forbid")

    name: StrictStr
    value: (
        StrictBool
        | StrictInt
        | StrictFloat
        | StrictStr
        | list[StrictBool | StrictInt | StrictFloat | StrictStr]
        | None
    )


class Resolution(BaseModel):
    """One selectable outcome on the review item (RULES-ENGINE-SPEC §3)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["NO_QUOTE", "RESOLVE", "ADD_OPERATION", "SET_PROCESS", "ASSIGN_ESTIMATOR"]
    parameters: list[ResolutionParameter]
    custom_label: StrictStr | None


class RuleSchema(BaseModel):
    """The canonical serialized rule (spec #rules-schema, "build to this").

    ``uuid`` is the portable identity (import upserts on it per org);
    ``default_assignee_id`` stays an unvalidated UUID — an imported set may
    name a user absent from this org, and M3.8 validates at assignment time.
    ``is_active`` is deliberately NOT part of the canonical shape (internal
    flag, DB-SCHEMA.sql ``rule.is_active``)."""

    model_config = ConfigDict(extra="forbid")

    uuid: uuid_mod.UUID
    name: Annotated[StrictStr, Field(min_length=1)]
    description: StrictStr
    logical_operator: LogicalOperator
    signals: Annotated[list[Signal], Field(min_length=1)]
    resolutions: Annotated[list[Resolution], Field(min_length=1)]
    default_assignee_id: uuid_mod.UUID | None


# --------------------------------------------------------------------------- #
# Canonical serialization (the single JSON string)
# --------------------------------------------------------------------------- #
#: Paste-in size ceiling — a rule set is configuration, not bulk data.
MAX_RULES_JSON_BYTES = 1024 * 1024


def _reject_non_finite(literal: str) -> float:
    raise ValueError(f"non-finite number {literal!r} is not allowed in a rule set")


def parse_rules_json(text: str) -> list[RuleSchema]:
    """Parse the pasted JSON string into validated rules.

    Raises ``ValueError`` for malformed JSON / a non-array top level, and
    ``pydantic.ValidationError`` for schema violations (both map to the 422
    error envelope at the API edge).
    """
    if len(text.encode("utf-8")) > MAX_RULES_JSON_BYTES:
        raise ValueError("rules JSON exceeds the 1 MB paste-in limit")
    try:
        # NaN/Infinity would poison the contract twice over: Postgres rejects
        # them in jsonb, and an export containing them is not valid JSON.
        payload = json.loads(text, parse_constant=_reject_non_finite)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("the rules JSON string must be a top-level array of rules")
    return [RuleSchema.model_validate(item) for item in payload]


def serialize_rules(rules: list[RuleSchema]) -> str:
    """Serialize rules to the canonical single JSON string.

    Canonical form (Kalk precedent, DECISIONS.md 2026-07-08): rules ordered by
    ``uuid``, sorted keys, compact separators, no ASCII escaping — a
    deterministic, diffable export where import→export is byte-stable.
    """
    ordered = sorted(rules, key=lambda rule: str(rule.uuid))
    payload = [rule.model_dump(mode="json") for rule in ordered]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
