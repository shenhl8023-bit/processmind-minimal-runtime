"""Execute public JSON against the actual CAD engine across mixed predicates."""

from itertools import product
import json

import pytest

from app.services.rule_packages.demo_tables import DemoTableError, compile_demo_tables, validate_demo_tables
from app.services.rule_packages.planner import plan_route
from test_demo_tables import bool_field, demo_tables, downstream_engine, leaf, package, route_for, rule


_LEAVES = [
    leaf("category", "a"),
    leaf("category", "ss", "neq"),
    leaf("category", ["a", "ss"], "in"),
    leaf("category", "s", "contains"),
    leaf("tags", "a", "contains"),
    leaf("tags", ["a", "ss"], "contains_all"),
    leaf("tags", ["a", "ss"], "contains_any"),
    leaf("approved", False),
    leaf("quantity", 0, "gte"),
    leaf("quantity", [-1, 1], "between"),
]
_CONDITIONS = [
    *_LEAVES,
    *[{"not": node} for node in _LEAVES],
    *[{"all": [left, {"not": right}]} for left, right in zip(_LEAVES, _LEAVES[1:])],
    *[{"any": [{"not": left}, right]} for left, right in zip(_LEAVES, _LEAVES[1:])],
]


@pytest.mark.parametrize("condition", _CONDITIONS)
def test_public_json_mixed_predicate_matrix_matches_native_selection(downstream_engine, condition):
    options = [{"value": value, "label": value} for value in ("A", "a", "ß", "SS", " B ")]
    value = package(fields=[
        {"key": "category", "label": "类别", "type": "single_select", "required": True, "options": options},
        {"key": "tags", "label": "标签", "type": "multi_select", "required": True, "options": options},
        bool_field("approved", required=True),
        {"key": "quantity", "label": "数量", "type": "number", "required": True},
    ], processes=[
        {"process_id": "base", "display_name": "准备", "main": True, "default_sequence": 1},
        {"process_id": "optional", "display_name": "可选", "default_sequence": 2},
    ], rules=[rule("predicate", condition, include=["optional"])])
    # Round-trip each of the three files separately, exactly as publication does.
    tables = {name: json.loads(json.dumps(table, ensure_ascii=False, allow_nan=False))
              for name, table in compile_demo_tables(value, route_for(value)).items()}
    validate_demo_tables(tables)
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    for category, tags, approved, quantity in product(
        ("A", "a", "ß", "SS", " B "),
        (["A"], ["ß"], ["A", "ß"], [" B "]),
        (False, True),
        (-1.001, -1, 0, 1, 1.001),
    ):
        inputs = dict(category=category, tags=tags, approved=approved, quantity=quantity)
        native_ids = plan_route(value, inputs).selected_process_ids
        actual = engine.run({"input_json": [], "factor_overrides": inputs})
        assert [process["process_name"] for process in actual["route"]] == (
            ["准备", "可选"] if "optional" in native_ids else ["准备"]
        ), (condition, inputs)


@pytest.mark.parametrize("first,second,expected", [
    (False, False, ["准备"]),
    (False, True, ["准备", "加工"]),
    (True, False, ["准备", "加工", "联动"]),
    (True, True, ["准备", "加工", "加工", "联动"]),
])
def test_same_process_and_step_names_keep_distinct_id_trigger_paths(downstream_engine, first, second, expected):
    value = package(fields=[bool_field("first"), bool_field("second")], processes=[
        {"process_id": "base", "display_name": "准备", "main": True, "default_sequence": 1},
        {"process_id": "first", "display_name": "加工", "default_sequence": 2,
         "steps": [{"step_id": "first.step", "name": "通用工步"}]},
        {"process_id": "second", "display_name": "加工", "default_sequence": 3,
         "steps": [{"step_id": "second.step", "name": "通用工步"}]},
        {"process_id": "follow", "display_name": "联动", "default_sequence": 4},
    ], rules=[rule("first", leaf("first"), include=["first"]), rule("second", leaf("second"), include=["second"])],
        relations=[{"relation_id": "follow-first-only", "relation_type": "trigger_after",
                    "source_process_ids": ["first"], "target_process_ids": ["follow"]}])
    route = route_for(value)
    route[1]["steps"][0]["candidates"] = {}
    route[2]["steps"][0]["candidates"] = {}
    tables = compile_demo_tables(value, route)
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    actual = engine.run({"input_json": [], "factor_overrides": {"first": first, "second": second}})
    assert [process["process_name"] for process in actual["route"]] == expected
    assert ("follow" in plan_route(value, {"first": first, "second": second}).selected_process_ids) is first


@pytest.mark.parametrize("mutation,code", [
    (lambda t: t["factor_table"][0].update(visible=1), "invalid_factor_flags"),
    (lambda t: t["factor_table"][0].update(required=[]), "invalid_factor_flags"),
    (lambda t: t["factor_table"][0].update(type={}, default=None), "invalid_factor_type"),
    (lambda t: t["factor_table"][0].update(options=[None]), "invalid_factor_options"),
    (lambda t: t["factor_table"][0].update(default=[]), "invalid_factor_default"),
    (lambda t: t["factor_table"][1].update(type="number", default=float("nan")), "invalid_factor_default"),
    (lambda t: t["full_route_table"][0].update(process_id=[]), "invalid_node_id"),
    (lambda t: t["full_route_table"][0].update(process_type={}), "invalid_process_type"),
    (lambda t: t["full_route_table"][0].update(precision=[]), "missing_process_precision"),
    (lambda t: t["full_route_table"][0].update(steps={}), "invalid_steps"),
    (lambda t: t["full_route_table"][0]["steps"][0].update(candidates={"孔": [None]}), "invalid_candidates"),
    (lambda t: t["full_route_table"][0]["steps"][0].update(candidates={"孔": ["孔", "孔"]}), "invalid_candidates"),
    (lambda t: t["rule_table"][0].update(target=[]), "unknown_target"),
    (lambda t: t["rule_table"][0].update(required=1), "invalid_rule"),
    (lambda t: t["rule_table"][0].update(when={"field": {}, "op": "eq", "value": "孔"}), "unknown_factor"),
    (lambda t: t["rule_table"][0].update(when={"all": []}), "invalid_condition"),
    (lambda t: t["rule_table"][0].update(when={"not": None}), "invalid_condition"),
    (lambda t: t["rule_table"][0].update(when={"some": [], "all": []}), "invalid_condition"),
    (lambda t: t["rule_table"][0].update(when=leaf("feature_rank", float("inf"), "gte")), "invalid_condition_type"),
    (lambda t: t["rule_table"][0].update(when=leaf("selected_processes", "s", "contains")), "unknown_process_dependency"),
])
def test_public_json_invalid_value_matrix_reports_contract_issue(mutation, code):
    tables = demo_tables()
    mutation(tables)
    with pytest.raises(DemoTableError) as caught:
        validate_demo_tables(tables)
    assert code in {issue["code"] for issue in caught.value.issues}
