"""M3.8 — Review-item generator + lifecycle + resolutions + SET ALL.

Spec ``#rules`` / ``#rules-lifecycle`` / ``#rules-resolutions``;
RULES-ENGINE-SPEC §3 (resolutions) + §6 (lifecycle & collaboration).

The block's acceptance criteria, in order: a matching rule creates a review
item; NO_QUOTE sets the line-item status; SET_PROCESS / ADD_OPERATION mutate
the router; RESOLVE(label) closes with no mutation; the assignee is notified;
SET ALL resolves across all flagged parts; up to 5 prior decisions show; rule
editing is blocked without process-edit, resolving without quote-edit.

The rules here are built from the M3.6 canonical AST rather than the §5 golden
fixture, so each test states the exact signal it turns on — the fixture's own
nine rules are already regression-tested in ``test_rules_m37.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import MembershipRole, MembershipStatus
from tests.conftest import Seeder, authed

ADMIN = [MembershipRole.admin]
ESTIMATOR = [MembershipRole.estimator]
#: view + annotate only — no quote_edit, no config_edit (authz `_SUPPORT`).
ENGINEER = [MembershipRole.engineer]


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def _org_with(
    seeder: Seeder, slug: str, roles: list[MembershipRole]
) -> tuple[uuid.UUID, uuid.UUID]:
    org = seeder.org(slug)
    user = seeder.user(f"{slug}-user@example.test")
    seeder.membership(user, org, roles)
    return org, user


def _rule(
    *,
    name: str = "Fehlende Zeichnung",
    document_path: str = "files",
    field_name: str = "has_print",
    operator: str = "equals",
    value: Any = False,
    value_type: str = "boolean",
    filter_type: str = "boolean",
    units: str | None = None,
    resolutions: list[dict[str, Any]] | None = None,
    default_assignee_id: str | None = None,
) -> dict[str, Any]:
    """One canonical rule. Defaults to the §5 "missing print" signal — it needs
    no findings and no text layer, so a test that is about the *lifecycle* does
    not have to stage an extraction to get a match."""
    return {
        "uuid": str(uuid.uuid4()),
        "name": name,
        "description": "",
        "logical_operator": "OR",
        "signals": [
            {
                "logical_operator": "AND",
                "groups": [
                    {
                        "document_path": document_path,
                        "logical_operator": "AND",
                        "queries": [
                            {
                                "field_name": [field_name],
                                "operator": operator,
                                "value": value,
                                "value_type": value_type,
                                "filter_type": filter_type,
                                "units": units,
                            }
                        ],
                        "count_query": None,
                    }
                ],
            }
        ],
        "resolutions": resolutions
        or [{"type": "RESOLVE", "parameters": [], "custom_label": "Kunde kontaktiert"}],
        "default_assignee_id": default_assignee_id,
    }


def _import_rules(client: TestClient, rules: list[dict[str, Any]]) -> None:
    import json

    res = client.post("/api/rules/import", json={"rules_json": json.dumps(rules)})
    assert res.status_code == 200, res.text


def _rule_id(client: TestClient, name: str) -> str:
    rows = client.get("/api/rules").json()
    return str(next(r for r in rows if r["name"] == name)["id"])


def _new_quote_item(client: TestClient) -> tuple[str, str, str, str]:
    """quote id, quote item id, root component id, part id."""
    qid = client.post("/api/quotes", json={}).json()["id"]
    item = client.post(f"/api/quotes/{qid}/items").json()["items"][0]
    return qid, str(item["id"]), str(item["root_component_id"]), str(item["part_id"])


def _an_op_def_id(client: TestClient) -> str:
    """Any live operation def from the seeded 54-op library."""
    return str(client.get("/api/operation-defs").json()[0]["id"])


def _a_process_id(client: TestClient) -> str:
    return str(client.get("/api/processes").json()[0]["id"])


def _generate(client: TestClient, component_id: str) -> list[dict[str, Any]]:
    res = client.post(f"/api/components/{component_id}/review-items/generate")
    assert res.status_code == 200, res.text
    return list(res.json())


def _items_for(client: TestClient, component_id: str) -> list[dict[str, Any]]:
    res = client.get(f"/api/components/{component_id}/review-items")
    assert res.status_code == 200, res.text
    return list(res.json())


# --------------------------------------------------------------------------- #
# 1. Generation — "a matching rule creates a review item"
# --------------------------------------------------------------------------- #
class TestGeneration:
    def test_a_matching_rule_creates_a_review_item(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "gen-a", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)

            created = _generate(app_client, component_id)

            assert len(created) == 1
            assert created[0]["rule_name"] == "Fehlende Zeichnung"
            assert created[0]["status"] == "open"

    def test_a_non_matching_rule_creates_nothing(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """The same rule inverted: has_print == true, which a part with no
        files does not satisfy."""
        org, user = _org_with(seeder, "gen-b", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule(value=True)])
            _, _, component_id, _ = _new_quote_item(app_client)

            assert _generate(app_client, component_id) == []

    def test_generation_is_idempotent(self, app_client: TestClient, seeder: Seeder) -> None:
        """Lens re-runs on every upload, so generation runs again and again —
        it must converge on the one row, not pile up duplicates (the
        ``uq_review_item_component_rule`` contract)."""
        org, user = _org_with(seeder, "gen-c", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)

            first = _generate(app_client, component_id)
            _generate(app_client, component_id)
            _generate(app_client, component_id)

            items = _items_for(app_client, component_id)
            assert len(items) == 1
            assert items[0]["id"] == first[0]["id"], "the same row, not a replacement"

    def test_an_inactive_rule_does_not_fire(self, app_client: TestClient, seeder: Seeder) -> None:
        org, user = _org_with(seeder, "gen-d", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            rule_id = _rule_id(app_client, "Fehlende Zeichnung")
            seeder.sql(
                "UPDATE rule SET is_active = false WHERE id = :id AND org_id = :org",
                {"id": rule_id, "org": str(org)},
            )
            _, _, component_id, _ = _new_quote_item(app_client)

            assert _generate(app_client, component_id) == []

    def test_a_stale_open_item_is_withdrawn_when_the_rule_stops_matching(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """ASSUMED (no spec line): re-evaluation withdraws an *unresolved* item
        whose rule no longer matches — e.g. the missing print was uploaded. The
        alternative (leave it) leaves the estimator burning down work the
        drawing no longer asks for. A *resolved* item is never withdrawn: it is
        the audit trail (§6.6)."""
        org, user = _org_with(seeder, "gen-e", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, part_id = _new_quote_item(app_client)
            assert len(_generate(app_client, component_id)) == 1

            # the print arrives → has_print becomes true → the rule stops matching
            seeder.part_file(org, uuid.UUID(part_id), "zeichnung.pdf", file_type="document")

            _generate(app_client, component_id)
            assert _items_for(app_client, component_id) == []


# --------------------------------------------------------------------------- #
# 2. Assignment + notification (§6.2)
# --------------------------------------------------------------------------- #
class TestAssignment:
    def test_default_assignee_is_applied_and_notified(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "asg-a", ADMIN)
        mate = seeder.user("senior@asg-a.example.test")
        seeder.membership(mate, org, ESTIMATOR)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule(default_assignee_id=str(mate))])
            _, _, component_id, _ = _new_quote_item(app_client)

            created = _generate(app_client, component_id)
            assert created[0]["assignee_id"] == str(mate)

        with authed(app_client, user_id=mate, org_id=org, roles=ESTIMATOR):
            kinds = [n["kind"] for n in app_client.get("/api/notifications").json()]
            assert "review_item_assigned" in kinds, "§6.2: auto-assign + notify"

    def test_a_default_assignee_outside_the_org_is_ignored_not_fatal(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """``Rule.default_assignee_id`` is deliberately un-FK'd because an
        imported rule set may name a user absent from this org (M3.6 docstring
        defers the check to "assignment time" — here). An unknown assignee must
        leave the item unassigned rather than lose the whole review item."""
        org, user = _org_with(seeder, "asg-b", ADMIN)
        stranger = seeder.user("stranger@elsewhere.example.test")  # no membership
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule(default_assignee_id=str(stranger))])
            _, _, component_id, _ = _new_quote_item(app_client)

            created = _generate(app_client, component_id)
            assert len(created) == 1, "the item still exists"
            assert created[0]["assignee_id"] is None

    def test_reassignment_notifies_the_new_assignee(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "asg-c", ADMIN)
        mate = seeder.user("kollege@asg-c.example.test")
        seeder.membership(mate, org, ESTIMATOR)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            item = _generate(app_client, component_id)[0]

            res = app_client.patch(
                f"/api/review-items/{item['id']}", json={"assignee_id": str(mate)}
            )
            assert res.status_code == 200, res.text
            assert res.json()["assignee_id"] == str(mate)

        with authed(app_client, user_id=mate, org_id=org, roles=ESTIMATOR):
            assert any(
                n["kind"] == "review_item_assigned"
                for n in app_client.get("/api/notifications").json()
            )


# --------------------------------------------------------------------------- #
# 3. Resolution effects (§3) — the acceptance criteria, one per effect
# --------------------------------------------------------------------------- #
class TestResolutionEffects:
    def test_no_quote_sets_the_line_item_status(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "res-a", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(
                app_client,
                [_rule(resolutions=[{"type": "NO_QUOTE", "parameters": [], "custom_label": None}])],
            )
            qid, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "NO_QUOTE"}
            )
            assert res.status_code == 200, res.text
            assert res.json()["status"] == "resolved"

            items = app_client.get(f"/api/quotes/{qid}").json()["items"]
            assert items[0]["workflow_status"] == "no_quote"

    def test_add_operation_appends_to_the_router(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "res-b", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def_id = _an_op_def_id(app_client)
            _import_rules(
                app_client,
                [
                    _rule(
                        resolutions=[
                            {
                                "type": "ADD_OPERATION",
                                "parameters": [{"name": "op_def_ids", "value": [op_def_id]}],
                                "custom_label": None,
                            }
                        ]
                    )
                ],
            )
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve",
                json={"resolution_type": "ADD_OPERATION"},
            )
            assert res.status_code == 200, res.text

            ops = app_client.get(f"/api/components/{component_id}/costing").json()["operations"]
            assert len(ops) == 1, "the rule's operation is on the router"

    def test_add_operation_does_not_duplicate_an_operation_already_on_the_router(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """Spec ``#rules``: "Applying an 'Add operation' resolution must not
        insert an operation the router already has; the system blocks
        duplicates"."""
        org, user = _org_with(seeder, "res-c", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            op_def_id = _an_op_def_id(app_client)
            _import_rules(
                app_client,
                [
                    _rule(
                        resolutions=[
                            {
                                "type": "ADD_OPERATION",
                                "parameters": [{"name": "op_def_ids", "value": [op_def_id]}],
                                "custom_label": None,
                            }
                        ]
                    )
                ],
            )
            _, _, component_id, _ = _new_quote_item(app_client)
            added = app_client.post(
                f"/api/components/{component_id}/operations", json={"operation_def_id": op_def_id}
            )
            assert added.status_code == 201, added.text

            review = _generate(app_client, component_id)[0]
            app_client.post(
                f"/api/review-items/{review['id']}/resolve",
                json={"resolution_type": "ADD_OPERATION"},
            )

            ops = app_client.get(f"/api/components/{component_id}/costing").json()["operations"]
            assert len(ops) == 1, "the duplicate was blocked"

    def test_set_process_sets_the_component_process(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "res-d", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            process_id = _a_process_id(app_client)
            _import_rules(
                app_client,
                [
                    _rule(
                        resolutions=[
                            {
                                "type": "SET_PROCESS",
                                "parameters": [{"name": "process_id", "value": process_id}],
                                "custom_label": None,
                            }
                        ]
                    )
                ],
            )
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "SET_PROCESS"}
            )
            assert res.status_code == 200, res.text

            costing = app_client.get(f"/api/components/{component_id}/costing").json()
            assert str(costing["process_id"]) == process_id

    def test_resolve_with_a_label_closes_without_mutating_anything(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "res-e", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])  # RESOLVE / "Kunde kontaktiert"
            qid, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve",
                json={"resolution_type": "RESOLVE", "custom_label": "Kunde kontaktiert"},
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["status"] == "resolved"
            assert body["resolution_label"] == "Kunde kontaktiert"

            ops = app_client.get(f"/api/components/{component_id}/costing").json()
            assert ops["operations"] == [], "RESOLVE mutates nothing"
            items = app_client.get(f"/api/quotes/{qid}").json()["items"]
            assert items[0]["workflow_status"] == "not_started"

    def test_assign_estimator_routes_the_line_item_and_notifies(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "res-f", ADMIN)
        mate = seeder.user("schaetzer@res-f.example.test")
        seeder.membership(mate, org, ESTIMATOR)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(
                app_client,
                [
                    _rule(
                        resolutions=[
                            {
                                "type": "ASSIGN_ESTIMATOR",
                                "parameters": [{"name": "estimator_id", "value": str(mate)}],
                                "custom_label": None,
                            }
                        ]
                    )
                ],
            )
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve",
                json={"resolution_type": "ASSIGN_ESTIMATOR"},
            )
            assert res.status_code == 200, res.text
            assert res.json()["status"] == "resolved"

    def test_a_resolution_the_rule_does_not_offer_is_rejected(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """§3: "A rule offers one or more resolutions; the user picks the one
        that applies." Picking one it never offered would let any caller
        no-quote a line item through a rule about deburring."""
        org, user = _org_with(seeder, "res-g", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])  # offers RESOLVE only
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "NO_QUOTE"}
            )
            assert res.status_code == 422, res.text

    def test_resolving_an_already_resolved_item_is_rejected(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "res-h", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]
            first = app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "RESOLVE"}
            )
            assert first.status_code == 200, first.text

            again = app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "RESOLVE"}
            )
            assert again.status_code == 409, again.text


# --------------------------------------------------------------------------- #
# 4. Quote-level aggregation + SET ALL (§6.5)
# --------------------------------------------------------------------------- #
class TestQuoteLevelAndSetAll:
    def test_set_all_resolves_every_flagged_part_in_one_click(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "all-a", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(
                app_client,
                [_rule(resolutions=[{"type": "NO_QUOTE", "parameters": [], "custom_label": None}])],
            )
            qid = app_client.post("/api/quotes", json={}).json()["id"]
            components = []
            for _ in range(3):
                item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][-1]
                components.append(str(item["root_component_id"]))
            for component_id in components:
                assert len(_generate(app_client, component_id)) == 1

            rule_id = _rule_id(app_client, "Fehlende Zeichnung")
            res = app_client.post(
                f"/api/quotes/{qid}/review-items/set-all",
                json={"rule_id": rule_id, "resolution_type": "NO_QUOTE"},
            )
            assert res.status_code == 200, res.text
            assert res.json()["resolved_count"] == 3

            quote = app_client.get(f"/api/quotes/{qid}").json()
            statuses = [i["workflow_status"] for i in quote["items"]]
            assert statuses == ["no_quote"] * 3
            for component_id in components:
                assert all(i["status"] == "resolved" for i in _items_for(app_client, component_id))

    def test_set_all_skips_already_resolved_items(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "all-b", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            qid = app_client.post("/api/quotes", json={}).json()["id"]
            first = app_client.post(f"/api/quotes/{qid}/items").json()["items"][0]
            second = app_client.post(f"/api/quotes/{qid}/items").json()["items"][-1]
            for item in (first, second):
                _generate(app_client, str(item["root_component_id"]))

            review = _items_for(app_client, str(first["root_component_id"]))[0]
            app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "RESOLVE"}
            )

            rule_id = _rule_id(app_client, "Fehlende Zeichnung")
            res = app_client.post(
                f"/api/quotes/{qid}/review-items/set-all",
                json={"rule_id": rule_id, "resolution_type": "RESOLVE"},
            )
            assert res.json()["resolved_count"] == 1, "only the still-open one"

    def test_the_quote_lists_its_items_grouped_by_rule(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "all-c", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            qid = app_client.post("/api/quotes", json={}).json()["id"]
            for _ in range(2):
                item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][-1]
                _generate(app_client, str(item["root_component_id"]))

            groups = app_client.get(f"/api/quotes/{qid}/review-items").json()
            assert len(groups) == 1, "one group per rule"
            assert groups[0]["rule_name"] == "Fehlende Zeichnung"
            assert groups[0]["unresolved_count"] == 2
            assert len(groups[0]["items"]) == 2

    def test_unresolved_items_drive_the_quote_outstanding_work_count(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """Spec ``#rules``: "The unresolved count drives the quote's Outstanding
        Work / Incomplete Quote Items"."""
        org, user = _org_with(seeder, "all-d", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            qid, _, component_id, _ = _new_quote_item(app_client)
            _generate(app_client, component_id)

            tracker = app_client.get(f"/api/quotes/{qid}").json()["workflow"]
            assert tracker["unresolved_review_item_count"] == 1

            review = _items_for(app_client, component_id)[0]
            app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "RESOLVE"}
            )
            tracker = app_client.get(f"/api/quotes/{qid}").json()["workflow"]
            assert tracker["unresolved_review_item_count"] == 0


# --------------------------------------------------------------------------- #
# 5. Prior decisions (§6.4) — "up to 5 past parts the rule flagged"
# --------------------------------------------------------------------------- #
class TestPriorDecisions:
    def test_prior_decisions_are_capped_at_five_newest_first(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "pri-a", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            qid = app_client.post("/api/quotes", json={}).json()["id"]
            resolved_labels = []
            for n in range(7):
                item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][-1]
                component_id = str(item["root_component_id"])
                review = _generate(app_client, component_id)[0]
                label = f"Entscheidung {n}"
                app_client.post(
                    f"/api/review-items/{review['id']}/resolve",
                    json={"resolution_type": "RESOLVE", "custom_label": label},
                )
                resolved_labels.append(label)

            # an eighth part, still open — its card shows the prior decisions
            item = app_client.post(f"/api/quotes/{qid}/items").json()["items"][-1]
            open_review = _generate(app_client, str(item["root_component_id"]))[0]

            priors = app_client.get(f"/api/review-items/{open_review['id']}/prior-decisions").json()
            assert len(priors) == 5, "§6.4 caps the context at five"
            assert [p["resolution_label"] for p in priors] == resolved_labels[::-1][:5]

    def test_prior_decisions_exclude_the_item_itself_and_open_items(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "pri-b", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            assert app_client.get(f"/api/review-items/{review['id']}/prior-decisions").json() == []


# --------------------------------------------------------------------------- #
# 6. Permissions (§6) + tenancy
# --------------------------------------------------------------------------- #
class TestPermissions:
    def test_resolving_requires_quote_edit(self, app_client: TestClient, seeder: Seeder) -> None:
        org, admin = _org_with(seeder, "perm-a", ADMIN)
        engineer = seeder.user("ing@perm-a.example.test")
        seeder.membership(engineer, org, ENGINEER)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

        with authed(app_client, user_id=engineer, org_id=org, roles=ENGINEER):
            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "RESOLVE"}
            )
            assert res.status_code == 403, "§6: resolving items needs quote-edit"

    def test_an_engineer_can_still_read_the_burn_down_list(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, admin = _org_with(seeder, "perm-b", ADMIN)
        engineer = seeder.user("ing@perm-b.example.test")
        seeder.membership(engineer, org, ENGINEER)
        with authed(app_client, user_id=admin, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            _generate(app_client, component_id)

        with authed(app_client, user_id=engineer, org_id=org, roles=ENGINEER):
            assert len(_items_for(app_client, component_id)) == 1

    def test_review_items_are_org_scoped(self, app_client: TestClient, seeder: Seeder) -> None:
        org_a, user_a = _org_with(seeder, "ten-a", ADMIN)
        org_b, user_b = _org_with(seeder, "ten-b", ADMIN)
        with authed(app_client, user_id=user_a, org_id=org_a, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

        with authed(app_client, user_id=user_b, org_id=org_b, roles=ADMIN):
            assert app_client.get(f"/api/components/{component_id}/review-items").status_code == 404
            res = app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "RESOLVE"}
            )
            assert res.status_code == 404, "RLS hides the other org's item"


# --------------------------------------------------------------------------- #
# 7. Collaboration thread (§6.3) — "each item carries a chat thread"
# --------------------------------------------------------------------------- #
class TestCollaboration:
    def test_an_item_exposes_a_thread_that_persists_the_discussion(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "chat-a", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]

            posted = app_client.post(
                f"/api/review-items/{review['id']}/messages",
                json={"body": "Zeichnung beim Kunden angefragt."},
            )
            assert posted.status_code == 201, posted.text

            messages = app_client.get(f"/api/review-items/{review['id']}/messages").json()
            assert [m["body"] for m in messages] == ["Zeichnung beim Kunden angefragt."]

    def test_the_thread_survives_resolution_as_the_audit_trail(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """§6.6: "resolutions, assignee, thread, and timestamps are retained"."""
        org, user = _org_with(seeder, "chat-b", ADMIN)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            review = _generate(app_client, component_id)[0]
            app_client.post(
                f"/api/review-items/{review['id']}/messages", json={"body": "Entgraten reicht."}
            )
            app_client.post(
                f"/api/review-items/{review['id']}/resolve", json={"resolution_type": "RESOLVE"}
            )

            messages = app_client.get(f"/api/review-items/{review['id']}/messages").json()
            assert len(messages) == 1, "the discussion outlives the resolution"


# --------------------------------------------------------------------------- #
# 8. The post-extraction trigger (§6.1) — "after AI/interrogation finishes"
# --------------------------------------------------------------------------- #
class TestPostExtractionTrigger:
    """The task chain, not the HTTP endpoint: extraction is what changes the
    data the rules read, so it is what must re-run them."""

    def test_extraction_success_dispatches_generation_for_the_part(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import lens_extract

        dispatched: list[tuple[str, str]] = []
        monkeypatch.setattr(
            lens_extract,
            "_run_on_own_loop",
            lambda coro: (coro.close(), {"skipped": False, "finding_count": 3})[1],
        )
        monkeypatch.setattr(
            "app.review_items.review_items_generate_task.delay",
            lambda org_id, part_id: dispatched.append((org_id, part_id)),
        )
        org, part = str(uuid.uuid4()), str(uuid.uuid4())

        lens_extract.lens_extract_task(org, part, str(uuid.uuid4()))

        assert dispatched == [(org, part)], "a completed extraction re-runs the rules"

    def test_a_skipped_extraction_does_not_dispatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An export-controlled part is skipped before any provider call — no
        findings changed, so there is nothing to re-evaluate."""
        from app import lens_extract

        dispatched: list[tuple[str, str]] = []
        monkeypatch.setattr(
            lens_extract,
            "_run_on_own_loop",
            lambda coro: (coro.close(), {"skipped": True, "reason": "export_controlled"})[1],
        )
        monkeypatch.setattr(
            "app.review_items.review_items_generate_task.delay",
            lambda org_id, part_id: dispatched.append((org_id, part_id)),
        )

        lens_extract.lens_extract_task(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))

        assert dispatched == []

    def test_a_broker_failure_never_fails_a_committed_extraction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review items are derived data: the extraction's findings are already
        committed, so a dispatch hiccup must not turn a success into a retry."""
        from app import lens_extract

        monkeypatch.setattr(
            lens_extract,
            "_run_on_own_loop",
            lambda coro: (coro.close(), {"skipped": False, "finding_count": 1})[1],
        )

        def boom(org_id: str, part_id: str) -> None:
            raise RuntimeError("broker down")

        monkeypatch.setattr("app.review_items.review_items_generate_task.delay", boom)

        out = lens_extract.lens_extract_task(
            str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        )

        assert out["skipped"] is False, "the extraction still reports its success"


# --------------------------------------------------------------------------- #
# 9. The seeded starter rule library (SEED-AND-FIXTURES §7 / spec #rules)
# --------------------------------------------------------------------------- #
class TestStarterRuleLibrary:
    def test_the_library_is_seeded_in_german(self, app_client: TestClient, seeder: Seeder) -> None:
        """DECISIONS 2026-07-16: German strings, Fechner reviews later."""
        org, user = _org_with(seeder, "seed-a", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            names = [r["name"] for r in app_client.get("/api/rules").json()]

        assert "Ausfuhrkontrolle prüfen (Dual-Use)" in names
        assert "Enge Toleranz — Senior-Schätzer" in names
        assert "Fehlendes Modell oder fehlende Zeichnung" in names
        assert "Entgraten gefordert" in names

    def test_re_seeding_creates_nothing_and_keeps_admin_edits(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """A re-seed must never silently revert a shop's tuning."""
        org, user = _org_with(seeder, "seed-b", ADMIN)
        first = seeder.configure_catalog(org)
        assert first.rules_created >= 4

        seeder.sql(
            "UPDATE rule SET name = :name WHERE org_id = :org AND name = :old",
            {
                "name": "Entgraten (angepasst)",
                "org": str(org),
                "old": "Entgraten gefordert",
            },
        )
        again = seeder.configure_catalog(org)
        assert again.rules_created == 0, "idempotent"

        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            names = [r["name"] for r in app_client.get("/api/rules").json()]
        assert "Entgraten (angepasst)" in names, "the admin's edit survived the re-seed"

    def test_the_seeded_missing_file_rule_fires_end_to_end(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """Demo C, in miniature: a seeded rule flags a real part, and its
        configured resolution closes it."""
        org, user = _org_with(seeder, "seed-c", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _, _, component_id, _ = _new_quote_item(app_client)

            created = _generate(app_client, component_id)
            names = [i["rule_name"] for i in created]
            assert "Fehlendes Modell oder fehlende Zeichnung" in names

            item = next(
                i for i in created if i["rule_name"] == "Fehlendes Modell oder fehlende Zeichnung"
            )
            res = app_client.post(
                f"/api/review-items/{item['id']}/resolve",
                json={"resolution_type": "RESOLVE", "custom_label": "Kunde kontaktiert"},
            )
            assert res.status_code == 200, res.text
            assert res.json()["resolution_label"] == "Kunde kontaktiert"

    def test_the_seeded_deburr_rule_adds_the_seeded_operation(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """§7's German finish keywords map to the seeded Operation Library ids —
        the whole point of seeding the rule and the op together."""
        org, user = _org_with(seeder, "seed-d", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _, _, component_id, part_id = _new_quote_item(app_client)
            file_id = seeder.part_file(
                org, uuid.UUID(part_id), "zeichnung.pdf", file_type="document"
            )
            seeder.sql(
                "UPDATE part_file SET pdf_text = :t WHERE id = :id",
                {"t": "Alle Kanten brechen und entgraten.", "id": str(file_id)},
            )

            created = _generate(app_client, component_id)
            item = next(i for i in created if i["rule_name"] == "Entgraten gefordert")

            res = app_client.post(
                f"/api/review-items/{item['id']}/resolve",
                json={"resolution_type": "ADD_OPERATION"},
            )
            assert res.status_code == 200, res.text

            ops = app_client.get(f"/api/components/{component_id}/costing").json()["operations"]
            assert [o["name"] for o in ops] == ["Entgraten"]

    def test_the_seeded_dual_use_rule_fires_on_a_flagged_print(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        """§7 DACH: the ITAR framing is replaced by an EU dual-use rule."""
        org, user = _org_with(seeder, "seed-e", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _, _, component_id, part_id = _new_quote_item(app_client)
            file_id = seeder.part_file(
                org, uuid.UUID(part_id), "zeichnung.pdf", file_type="document"
            )
            seeder.sql(
                "UPDATE part_file SET pdf_text = :t WHERE id = :id",
                {
                    "t": "Achtung: Ausfuhrgenehmigung erforderlich (EG 428/2009).",
                    "id": str(file_id),
                },
            )

            names = [i["rule_name"] for i in _generate(app_client, component_id)]
            assert "Ausfuhrkontrolle prüfen (Dual-Use)" in names


# --------------------------------------------------------------------------- #
# 10. Review findings (2026-07-16) — regressions for the fixes they prompted
# --------------------------------------------------------------------------- #
class TestAssignmentRequiresAnActiveMembership:
    """A disabled member (sessions revoked) or a pending invitee is not somewhere
    work can be routed. The helper is named ``_is_active_member`` and backs
    default assignment, reassignment and ASSIGN_ESTIMATOR; it checked only that a
    membership row existed, so it accepted both."""

    def test_a_disabled_default_assignee_is_not_assigned(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "susp-a", ADMIN)
        gone = seeder.user("beurlaubt@susp-a.example.test")
        seeder.membership(gone, org, ESTIMATOR, status=MembershipStatus.disabled)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule(default_assignee_id=str(gone))])
            _, _, component_id, _ = _new_quote_item(app_client)

            created = _generate(app_client, component_id)
            assert len(created) == 1, "the item still exists"
            assert created[0]["assignee_id"] is None

    def test_a_pending_member_cannot_be_assigned_manually(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "susp-b", ADMIN)
        gone = seeder.user("eingeladen@susp-b.example.test")
        # pending = invited, not yet accepted — not yet a colleague to route to.
        seeder.membership(gone, org, ESTIMATOR, status=MembershipStatus.pending)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(app_client, [_rule()])
            _, _, component_id, _ = _new_quote_item(app_client)
            item = _generate(app_client, component_id)[0]

            res = app_client.patch(
                f"/api/review-items/{item['id']}", json={"assignee_id": str(gone)}
            )
            assert res.status_code == 422, res.text

    def test_a_disabled_estimator_fails_the_assign_estimator_resolution(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "susp-c", ADMIN)
        gone = seeder.user("deaktiviert@susp-c.example.test")
        seeder.membership(gone, org, ESTIMATOR, status=MembershipStatus.disabled)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            _import_rules(
                app_client,
                [
                    _rule(
                        resolutions=[
                            {
                                "type": "ASSIGN_ESTIMATOR",
                                "parameters": [{"name": "estimator_id", "value": str(gone)}],
                                "custom_label": None,
                            }
                        ]
                    )
                ],
            )
            _, _, component_id, _ = _new_quote_item(app_client)
            item = _generate(app_client, component_id)[0]

            res = app_client.post(
                f"/api/review-items/{item['id']}/resolve",
                json={"resolution_type": "ASSIGN_ESTIMATOR"},
            )
            assert res.status_code == 422, res.text
            assert _items_for(app_client, component_id)[0]["status"] == "open", (
                "a failed effect must not close the item"
            )


class TestSeededTightToleranceUnits:
    """The angular threshold is its own number: sharing the linear 0.13 would
    print "0,13 mm" in the description while comparing degrees."""

    def test_angular_and_linear_thresholds_are_distinct_and_metric(
        self, app_client: TestClient, seeder: Seeder
    ) -> None:
        org, user = _org_with(seeder, "unit-a", ADMIN)
        seeder.configure_catalog(org)
        with authed(app_client, user_id=user, org_id=org, roles=ADMIN):
            rule = next(
                r
                for r in app_client.get("/api/rules").json()
                if r["name"] == "Enge Toleranz — Senior-Schätzer"
            )

        by_units: dict[str, set[float]] = {}
        for signal in rule["signals"]:
            query = signal["groups"][0]["queries"][0]
            by_units.setdefault(query["units"], set()).add(query["value"])

        assert by_units["mm"] == {0.13}, "PP's 5 thou re-unit'd (§7 DACH)"
        assert by_units["deg"] == {0.5}, "the angular threshold is not the linear scalar"
        assert "in" not in by_units, "metric-native: never inches"
