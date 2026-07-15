"""M3.6 — Rules schema + JSON import/export (the query AST).

Slice 1 — the canonical schema seam (``app/rules_schema.py``): a rule set
parses from / serializes to a single canonical JSON string byte-equivalently
(spec ``#rules-schema``); the ``document_path``/operator/value_type literal
sets are enforced (spec ``#rules-paths``); ``units``/``value_type`` are
retained verbatim for M3.7 normalization.

The nine RULES-ENGINE-SPEC §5 worked rules (re-unit'd to mm, German keywords
per §7) live at ``fixtures/rules/worked-rules.json`` in canonical form and are
the round-trip golden.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models import MembershipRole
from app.rules_schema import RuleSchema, parse_rules_json, serialize_rules
from tests.conftest import Seeder, authed

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "rules" / "worked-rules.json"


def _minimal_rule(**overrides: object) -> dict[str, object]:
    """One schema-valid rule; tests mutate a single aspect via ``overrides``."""
    rule: dict[str, object] = {
        "uuid": "00000000-0000-4000-8000-0000000000aa",
        "name": "Testregel",
        "description": "",
        "logical_operator": "OR",
        "signals": [
            {
                "logical_operator": "AND",
                "groups": [
                    {
                        "document_path": "length_tolerances",
                        "logical_operator": "AND",
                        "queries": [
                            {
                                "field_name": ["smallest_delta"],
                                "operator": "lessThanOrEqual",
                                "value": 0.13,
                                "value_type": "distance",
                                "filter_type": "numeric",
                                "units": "mm",
                            }
                        ],
                        "count_query": None,
                    }
                ],
            }
        ],
        "resolutions": [{"type": "RESOLVE", "parameters": [], "custom_label": "Erledigt"}],
        "default_assignee_id": None,
    }
    rule.update(overrides)
    return rule


def _parse_one(rule: dict[str, object]) -> list[RuleSchema]:
    return parse_rules_json(json.dumps([rule]))


# --------------------------------------------------------------------------- #
# Round-trip golden — the block's acceptance criterion
# --------------------------------------------------------------------------- #
class TestWorkedRulesRoundTrip:
    def test_nine_worked_rules_import_and_serialize_byte_equivalently(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        rules = parse_rules_json(text)
        assert len(rules) == 9
        assert serialize_rules(rules) == text

    def test_fixture_is_re_unitized_to_metric(self) -> None:
        """DACH §7: thresholds in mm — the tight-tolerance rule compares
        smallest_delta ≤ 0.13 mm (5 thou re-unit'd) in every one of its
        signals, and no query in the golden set carries imperial units."""
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        units = {
            q["units"]
            for rule in payload
            for signal in rule["signals"]
            for group in signal["groups"]
            for q in group["queries"]
        }
        assert "in" not in units
        tight = next(r for r in payload if r["name"] == "All tight dimension tolerances")
        assert len(tight["signals"]) == 17  # 4 tolerance + 13 control-frame paths
        for signal in tight["signals"]:
            (query,) = signal["groups"][0]["queries"]
            assert query["value"] == 0.13
            assert query["units"] == "mm"
            assert query["value_type"] == "distance"
        envelope = next(r for r in payload if r["name"] == "Machine envelope exceeded")
        (env_query,) = envelope["signals"][0]["groups"][0]["queries"]
        assert env_query["value"] == 305  # 12 in → mm bed limit
        assert env_query["units"] == "mm"

    def test_german_finish_keywords_present(self) -> None:
        """DACH §7: the finish-keyword rule's own keyword list carries the
        German terms alongside English, at the exact AST location the
        evaluator will read."""
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        finish = next(r for r in payload if r["name"] == "Finish keyword adds finishing operation")
        (query,) = finish["signals"][0]["groups"][0]["queries"]
        assert query["operator"] == "includesCaseInsensitive"
        for keyword in ("eloxier", "entgrat", "passivier", "schleif"):
            assert any(keyword in item for item in query["value"])

    def test_export_of_empty_set_is_empty_array(self) -> None:
        assert serialize_rules([]) == "[]"
        assert parse_rules_json("[]") == []


# --------------------------------------------------------------------------- #
# Literal sets — "the schema accepts each document_path/operator/value_type"
# --------------------------------------------------------------------------- #
class TestDocumentPathCatalog:
    ALL_CATALOG_PATHS: ClassVar[list[str]] = [
        "length_tolerances",
        "diameter_tolerances",
        "radius_tolerances",
        "angular_tolerances",
        "flatness_control_frames",
        "parallelism_control_frames",
        "perpendicularity_control_frames",
        "position_control_frames",
        "cylindricity_control_frames",
        "straightness_control_frames",
        "concentricity_control_frames",
        "profile_of_line_control_frames",
        "profile_of_surface_control_frames",
        "runout_control_frames",
        "total_runout_control_frames",
        "symmetry_control_frames",
        "circularity_control_frames",
        "control_frames",
        "datums",
        "greatest_distance_dimension",
        "least_distance_dimension",
        "part",
        "files",
        "text",
    ]

    @pytest.mark.parametrize("path", ALL_CATALOG_PATHS)
    def test_accepts_every_catalog_path(self, path: str) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = path
        assert len(_parse_one(rule)) == 1

    @pytest.mark.parametrize(
        "path",
        [
            "three_axis_mill.machine_direction",
            "sheet_metal.bend_count",
            "tube_laser.profile_type",
            "lathe.max_turn_diameter",
        ],
    )
    def test_accepts_interrogation_family_paths(self, path: str) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = path
        assert len(_parse_one(rule)) == 1

    @pytest.mark.parametrize(
        "path",
        ["", "bogus_path", "five_axis_mill.machine_direction", "text.raw", "LENGTH_TOLERANCES"],
    )
    def test_rejects_paths_outside_the_catalog(self, path: str) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = path
        with pytest.raises(ValidationError):
            _parse_one(rule)


class TestLiteralSets:
    def test_rejects_unknown_operator(self) -> None:
        rule = _minimal_rule()
        query = rule["signals"][0]["groups"][0]["queries"][0]  # type: ignore[index]
        query["operator"] = "lessThan"
        with pytest.raises(ValidationError):
            _parse_one(rule)

    def test_rejects_unknown_value_type(self) -> None:
        rule = _minimal_rule()
        query = rule["signals"][0]["groups"][0]["queries"][0]  # type: ignore[index]
        query["value_type"] = "length"
        with pytest.raises(ValidationError):
            _parse_one(rule)

    def test_rejects_unknown_resolution_type(self) -> None:
        rule = _minimal_rule(
            resolutions=[{"type": "DELETE_QUOTE", "parameters": [], "custom_label": None}]
        )
        with pytest.raises(ValidationError):
            _parse_one(rule)

    def test_rejects_unknown_top_level_key(self) -> None:
        rule = _minimal_rule(is_active=True)  # is_active is internal, not canonical
        with pytest.raises(ValidationError):
            _parse_one(rule)

    def test_count_query_takes_numeric_operators_only(self) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = "control_frames"
        group["queries"] = []
        group["count_query"] = {"operator": "regex", "value": 7}
        with pytest.raises(ValidationError):
            _parse_one(rule)
        group["count_query"] = {"operator": "greaterThanOrEqual", "value": 7}
        assert len(_parse_one(rule)) == 1

    def test_group_needs_queries_or_count_query(self) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["queries"] = []
        group["count_query"] = None
        with pytest.raises(ValidationError):
            _parse_one(rule)


# --------------------------------------------------------------------------- #
# Retention — units/value_type kept verbatim for M3.7 normalization
# --------------------------------------------------------------------------- #
class TestRetention:
    def test_inch_units_are_accepted_and_retained_not_normalized(self) -> None:
        """Portability: a pasted PP rule set keeps ``"in"`` — the DACH delta
        forbids the imperial *default*, not the unit; M3.7 normalizes."""
        rule = _minimal_rule()
        query = rule["signals"][0]["groups"][0]["queries"][0]  # type: ignore[index]
        query["value"] = 0.005
        query["units"] = "in"
        (parsed,) = parse_rules_json(json.dumps([rule]))
        out = json.loads(serialize_rules([parsed]))
        kept = out[0]["signals"][0]["groups"][0]["queries"][0]
        assert kept["units"] == "in"
        assert kept["value"] == 0.005
        assert kept["value_type"] == "distance"

    def test_boolean_value_survives_as_boolean(self) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = "files"
        group["queries"] = [
            {
                "field_name": ["has_model"],
                "operator": "equals",
                "value": False,
                "value_type": "boolean",
                "filter_type": "boolean",
                "units": None,
            }
        ]
        (parsed,) = _parse_one(rule)
        out = json.loads(serialize_rules([parsed]))
        assert out[0]["signals"][0]["groups"][0]["queries"][0]["value"] is False

    def test_integer_value_does_not_become_float(self) -> None:
        rule = _minimal_rule()
        query = rule["signals"][0]["groups"][0]["queries"][0]  # type: ignore[index]
        query["value"] = 305
        (parsed,) = _parse_one(rule)
        assert '"value":305' in serialize_rules([parsed])

    def test_keyword_list_value_retained(self) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = "text"
        group["queries"] = [
            {
                "field_name": ["raw_text"],
                "operator": "includesCaseInsensitive",
                "value": ["eloxier", "anodiz"],
                "value_type": "string",
                "filter_type": "string",
                "units": None,
            }
        ]
        (parsed,) = _parse_one(rule)
        out = json.loads(serialize_rules([parsed]))
        assert out[0]["signals"][0]["groups"][0]["queries"][0]["value"] == ["eloxier", "anodiz"]


# --------------------------------------------------------------------------- #
# Edge validation
# --------------------------------------------------------------------------- #
class TestEdgeValidation:
    def test_invalid_regex_is_rejected_at_parse(self) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = "text"
        group["queries"] = [
            {
                "field_name": ["raw_text"],
                "operator": "regex",
                "value": "([unclosed",
                "value_type": "string",
                "filter_type": "string",
                "units": None,
            }
        ]
        with pytest.raises(ValidationError):
            _parse_one(rule)

    def test_not_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="JSON"):
            parse_rules_json("not json {")

    def test_top_level_object_instead_of_array_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_rules_json(json.dumps(_minimal_rule()))


# --------------------------------------------------------------------------- #
# Slice 2 — API seam: /api/rules list / import / export (org-scoped, RLS)
# --------------------------------------------------------------------------- #
ADMIN = [MembershipRole.admin]
ESTIMATOR = [MembershipRole.estimator]
VIEWER = [MembershipRole.viewer]


def _org_with_admin(seeder: Seeder, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    admin = seeder.user(f"admin@{slug}.example")
    seeder.membership(admin, org, ADMIN)
    return org, admin


def test_import_then_export_is_byte_equivalent_end_to_end(
    app_client: TestClient, seeder: Seeder
) -> None:
    """The block's acceptance criterion, through the HTTP seam."""
    org, admin = _org_with_admin(seeder, "org-a")
    text = FIXTURE.read_text(encoding="utf-8")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        imported = app_client.post("/api/rules/import", json={"rules_json": text})
        assert imported.status_code == 200, imported.text
        assert imported.json() == {"created": 9, "updated": 0}
        exported = app_client.get("/api/rules/export")
        assert exported.status_code == 200
        assert exported.json()["count"] == 9
        assert exported.json()["rules_json"] == text


def test_reimport_is_an_idempotent_upsert(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    text = FIXTURE.read_text(encoding="utf-8")
    renamed = text.replace("All tight dimension tolerances", "Enge Toleranzen")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        app_client.post("/api/rules/import", json={"rules_json": text})
        second = app_client.post("/api/rules/import", json={"rules_json": renamed})
        assert second.json() == {"created": 0, "updated": 9}
        names = [r["name"] for r in app_client.get("/api/rules").json()]
        assert names.count("Enge Toleranzen") == 1
        assert len(names) == 9  # upsert on (org, uuid) — never a duplicate


def test_rules_are_org_scoped(app_client: TestClient, seeder: Seeder) -> None:
    org_a, admin_a = _org_with_admin(seeder, "org-a")
    org_b, admin_b = _org_with_admin(seeder, "org-b")
    text = FIXTURE.read_text(encoding="utf-8")
    with authed(app_client, user_id=admin_a, org_id=org_a, roles=ADMIN):
        app_client.post("/api/rules/import", json={"rules_json": text})
    with authed(app_client, user_id=admin_b, org_id=org_b, roles=ADMIN):
        assert app_client.get("/api/rules").json() == []
        assert app_client.get("/api/rules/export").json()["rules_json"] == "[]"
        # The same set imports into org B — portable uuids never collide cross-org.
        again = app_client.post("/api/rules/import", json={"rules_json": text})
        assert again.json() == {"created": 9, "updated": 0}


def test_import_needs_config_edit_export_needs_view(app_client: TestClient, seeder: Seeder) -> None:
    """Rule building/editing is gated on the process-edit permission
    (RULES-ENGINE-SPEC §6 → ``config_edit``); reads on ``view_all``."""
    org, _admin = _org_with_admin(seeder, "org-a")
    estimator = seeder.user("estimator@org-a.example")
    seeder.membership(estimator, org, ESTIMATOR)
    viewer = seeder.user("viewer@org-a.example")
    seeder.membership(viewer, org, VIEWER)
    text = FIXTURE.read_text(encoding="utf-8")
    with authed(app_client, user_id=estimator, org_id=org, roles=ESTIMATOR):
        denied = app_client.post("/api/rules/import", json={"rules_json": text})
        assert denied.status_code == 403
        assert denied.json()["code"] == "forbidden"
    with authed(app_client, user_id=viewer, org_id=org, roles=VIEWER):
        assert app_client.get("/api/rules").status_code == 200
        assert app_client.get("/api/rules/export").status_code == 200


def test_import_rejects_bad_payloads_with_error_envelope(
    app_client: TestClient, seeder: Seeder
) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    bad_schema = json.dumps([_minimal_rule(logical_operator="XOR")])
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        not_json = app_client.post("/api/rules/import", json={"rules_json": "nope {"})
        assert not_json.status_code == 422
        assert not_json.json()["code"] == "invalid_rules_json"
        invalid = app_client.post("/api/rules/import", json={"rules_json": bad_schema})
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_rules_json"
        # All-or-nothing paste-in: a valid rule ahead of an invalid one must
        # not be persisted either.
        bad_second = _minimal_rule(
            uuid="00000000-0000-4000-8000-0000000000bb", logical_operator="XOR"
        )
        mixed = app_client.post(
            "/api/rules/import",
            json={"rules_json": json.dumps([_minimal_rule(), bad_second])},
        )
        assert mixed.status_code == 422
        assert app_client.get("/api/rules").json() == []


def test_list_returns_summaries_with_retained_ast(app_client: TestClient, seeder: Seeder) -> None:
    org, admin = _org_with_admin(seeder, "org-a")
    text = FIXTURE.read_text(encoding="utf-8")
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        app_client.post("/api/rules/import", json={"rules_json": text})
        rules = app_client.get("/api/rules").json()
    tight = next(r for r in rules if r["name"] == "All tight dimension tolerances")
    assert tight["is_active"] is True
    assert tight["uuid"] == "00000000-0000-4000-8000-000000000001"
    query = tight["signals"][0]["groups"][0]["queries"][0]
    assert query["units"] == "mm"  # units retained verbatim for M3.7
    assert query["value_type"] == "distance"
    assert len(tight["resolutions"]) == 3


# --------------------------------------------------------------------------- #
# Review-hardening regressions (fresh-eyes findings, pre-merge)
# --------------------------------------------------------------------------- #
class TestReviewHardening:
    def test_non_finite_numbers_are_rejected(self) -> None:
        """NaN/Infinity parse as Python floats but are invalid in Postgres
        jsonb AND in a re-exported JSON string — reject at the edge."""
        rule = _minimal_rule()
        text = json.dumps([rule]).replace("0.13", "NaN")
        with pytest.raises(ValueError, match=r"[Nn]on-finite"):
            parse_rules_json(text)
        text = json.dumps([rule]).replace("0.13", "Infinity")
        with pytest.raises(ValueError, match=r"[Nn]on-finite"):
            parse_rules_json(text)

    def test_count_query_value_is_strict(self) -> None:
        rule = _minimal_rule()
        group = rule["signals"][0]["groups"][0]  # type: ignore[index]
        group["document_path"] = "control_frames"
        group["queries"] = []
        for bad in ("7", 7.0):
            group["count_query"] = {"operator": "greaterThanOrEqual", "value": bad}
            with pytest.raises(ValidationError):
                _parse_one(rule)

    def test_string_filter_rejects_numeric_operator(self) -> None:
        rule = _minimal_rule()
        query = rule["signals"][0]["groups"][0]["queries"][0]  # type: ignore[index]
        query.update(
            {
                "operator": "lessThanOrEqual",
                "value": "abc",
                "value_type": "string",
                "filter_type": "string",
                "units": None,
            }
        )
        with pytest.raises(ValidationError):
            _parse_one(rule)


def test_custom_validator_rejection_returns_envelope_not_500(
    app_client: TestClient, seeder: Seeder
) -> None:
    """Regression: pydantic stuffs the raw ValueError of a custom validator
    into ``ctx`` — unredacted it 500s during JSON serialization. An unknown
    document_path (a custom-validator failure) must come back as the 422
    envelope."""
    org, admin = _org_with_admin(seeder, "org-a")
    rule = _minimal_rule()
    rule["signals"][0]["groups"][0]["document_path"] = "bogus_path"  # type: ignore[index]
    with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
        resp = app_client.post("/api/rules/import", json={"rules_json": json.dumps([rule])})
        assert resp.status_code == 422
        assert resp.json()["code"] == "invalid_rules_json"
        nan_resp = app_client.post(
            "/api/rules/import",
            json={"rules_json": json.dumps([_minimal_rule()]).replace("0.13", "NaN")},
        )
        assert nan_resp.status_code == 422
        assert nan_resp.json()["code"] == "invalid_rules_json"
