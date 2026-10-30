"""The exported files must be executable Demo configuration, not internal V2 JSON."""

from copy import deepcopy
import importlib.util
from itertools import product
import json
from pathlib import Path

import pytest

from app.services.rule_packages.contracts import ProcessConfigurationV2, ProcessRelationV2, RulePackageV2
from app.services.rule_packages.demo_tables import (
    DemoTableError,
    compile_demo_tables,
    validate_demo_tables,
    validate_publication_input_constraints,
)
from app.services.rule_packages.condition_registry import condition_field_map
from app.services.rule_packages.planner import plan_route


def package(*, fields=None, processes=None, rules=None, relations=None):
    return RulePackageV2.model_validate({
        "manifest": {"package_name": "test", "project_id": 1, "scope": {"key": "1"}},
        "input_schema": {"fields": fields or []},
        "route_catalog": {"processes": processes or [
            {"process_id": "clean_before", "display_name": "清洗", "main": True, "default_sequence": 1},
            {"process_id": "turn", "display_name": "车削", "default_sequence": 2, "steps": [
                {"step_id": "turn_outer", "name": "车外圆"},
            ]},
            {"process_id": "clean_after", "display_name": "清洗", "main": True, "default_sequence": 3},
        ]},
        "route_rules": {"rules": rules or [], "process_relations": relations or []},
    })


def route_for(value):
    return [
        {"process_name": p.display_name,
         "process_type": "加工工序" if p.steps else "辅助工序",
         "precision": "粗加工" if p.steps else "辅助工序",
         "steps": [
             {"step_name": s.name, "candidates": {"A侧/外圆": ["外圆柱面"]}, "step_id": s.step_id}
             for s in p.steps
         ], "process_id": p.process_id}
        for p in value.route_catalog.processes
    ]


def leaf(field, value=True, op="eq"):
    return {"field": field, "op": op, "value": value}


def rule(rule_id, condition, *, include=(), exclude=(), priority=100, **extra):
    return {"rule_id": rule_id, "priority": priority, "when": condition,
            "then": {"include_process_ids": list(include), "exclude_process_ids": list(exclude)}, **extra}


def bool_field(key, **extra):
    return {"key": key, "label": key, "type": "boolean", "source": "用户直接设定", **extra}


def match(condition, inputs):
    """Small expression assertion helper; real downstream integration is tested separately."""
    if type(condition) is bool:
        return condition
    if "all" in condition:
        return all(match(c, inputs) for c in condition["all"])
    if "any" in condition:
        return any(match(c, inputs) for c in condition["any"])
    if "not" in condition:
        return not match(condition["not"], inputs)
    actual = inputs[condition["field"]]
    wanted = condition["value"]
    return {"eq": lambda: actual == wanted, "neq": lambda: actual != wanted,
            "contains": lambda: wanted in actual, "in": lambda: actual in wanted,
            "exists": lambda: (actual is not None and actual != "" and actual != []) == wanted,
            "gte": lambda: actual is not None and actual >= wanted,
            "lte": lambda: actual is not None and actual <= wanted}[condition["op"]]()


def enabled(rules, pid, inputs):
    r = next(r for r in rules if r["target"] == pid)
    return r.get("required", False) or match(r["when"], inputs)


def test_exports_arrays_from_final_route_and_keeps_repeated_names_and_order():
    value = package()
    source = route_for(value)
    snapshot = deepcopy(source)
    tables = compile_demo_tables(value, source)
    assert set(tables) == {"factor_table", "full_route_table", "rule_table"}
    assert all(isinstance(table, list) for table in tables.values())
    assert tables["full_route_table"] == snapshot
    assert source == snapshot
    assert tables["rule_table"] == [
        {"target": "clean_before", "required": True},
        {"target": "turn", "when": False},
        {"target": "clean_after", "required": True},
    ]
    tables["full_route_table"][0]["process_name"] = "changed"
    assert source == snapshot


def test_material_binding_and_manual_factors_use_real_scalar_prefill_paths():
    value = package(fields=[
        {"key": "material.grade", "label": "材料", "type": "single_select", "required": True,
         "source": "CAD/PLM", "options": [{"value": "9Cr18", "label": "不输出此标签"}]},
        {"key": "surface.roughness_ra", "label": "Ra", "type": "number", "source": "CAD/工艺要求"},
        {"key": "cad.features", "label": "粗分类特征", "type": "multi_select", "source": "CAD"},
        bool_field("project_factor.manual_process_a"),
    ])
    factors = compile_demo_tables(value, route_for(value))["factor_table"]
    assert factors[0] == {
        "key": "material", "label": "材料", "type": "enum", "source": "manual_defaults.material_grade",
        "visible": True, "options": ["9Cr18"], "required": True,
    }
    assert factors[1]["source"] == "manual_defaults.surface.roughness_ra"
    assert factors[1]["visible"] is True
    assert factors[2]["key"] == "cad.features"
    assert factors[2]["source"] == "manual_defaults.cad.features"
    assert factors[2]["type"] == "multi_enum"
    assert factors[2]["visible"] is True
    assert factors[3]["source"] == "manual_defaults.project_factor.manual_process_a"
    assert factors[3]["type"] == "bool"
    assert factors[3]["default"] is None
    assert all("default" not in f for f in factors[:3])
    legacy_factor = compile_demo_tables(value, route_for(value), _legacy_snapshot=True)["factor_table"][2]
    assert legacy_factor == {
        "key": "feature_type", "label": "粗分类特征", "type": "enum",
        "source": "input_json[].features[].feature_select", "visible": False,
    }


def test_rule_fields_are_renamed_with_factors_and_extended_operators_are_lowered():
    value = package(fields=[
        {"key": "material.grade", "label": "材料", "type": "single_select", "options": [{"value": "9Cr18", "label": "9Cr18"}]},
        {"key": "tags", "label": "标签", "type": "multi_select", "required": True, "options": [{"value": k, "label": k} for k in ("a", "b", "x", "y")]},
        {"key": "rank", "label": "等级", "type": "number"},
    ], rules=[rule("choose", {"all": [leaf("material.grade", "9Cr18"),
        leaf("tags", ["a", "b"], "contains_all"), leaf("rank", [5, 9], "between"),
        {"not": leaf("tags", ["x", "y"], "contains_any")},
    ]}, include=["turn"])])
    tables = compile_demo_tables(value, route_for(value))
    compiled = next(r for r in tables["rule_table"] if r["target"] == "turn")["when"]
    assert match(compiled, {"material": "9Cr18", "tags": ["a", "b"], "rank": 8}) is True
    assert match(compiled, {"material": "9Cr18", "tags": ["a", "b", "x"], "rank": 8}) is False
    assert match(compiled, {"material": "9Cr18", "tags": ["a", "b"], "rank": 10}) is False
    validate_demo_tables(tables)


def test_high_priority_include_and_exclude_preserve_v2_decisions_for_all_boolean_inputs():
    value = package(fields=[bool_field(k) for k in ("low", "reject", "override")], rules=[
        rule("base", leaf("low"), include=["turn"], priority=10),
        rule("reject", leaf("reject"), exclude=["turn"], priority=20),
        rule("override", leaf("override"), include=["turn"], priority=30),
    ])
    tables = compile_demo_tables(value, route_for(value))
    for bits in product([False, True], repeat=3):
        inputs = dict(zip(("low", "reject", "override"), bits))
        expected = "turn" in plan_route(value, inputs).selected_process_ids
        assert enabled(tables["rule_table"], "turn", inputs) is expected


def test_manual_false_can_disable_a_main_process_without_turning_it_required():
    key = "project_factor.manual_process_turn"
    value = package(fields=[bool_field(key)], rules=[
        rule("manual.true", leaf(key), include=["turn"], source="user_confirmed"),
        rule("manual.false", leaf(key, False), exclude=["turn"], source="user_confirmed"),
    ])
    value.route_catalog.processes[1].main = True
    tables = compile_demo_tables(value, route_for(value))
    for answer in (False, True):
        assert enabled(tables["rule_table"], "turn", {key: answer}) is answer


def test_same_priority_opposing_rules_are_rejected_instead_of_silently_or_combined():
    value = package(fields=[bool_field("a"), bool_field("b")], rules=[
        rule("add", leaf("a"), include=["turn"]),
        rule("remove", leaf("b"), exclude=["turn"]),
    ])
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value))
    assert caught.value.issues[0]["code"] == "same_priority_action_conflict"
    assert "turn" in str(caught.value)


def test_trigger_dependencies_use_ids_and_keep_the_final_route_order():
    value = package(fields=[bool_field("choose")], rules=[
        rule("pick", leaf("choose"), include=["turn"]),
    ], relations=[{"relation_id": "after", "relation_type": "trigger_after",
                   "source_process_ids": ["turn"], "target_process_ids": ["clean_after"]}])
    value.route_catalog.processes[2].main = False
    tables = compile_demo_tables(value, route_for(value))
    assert tables["rule_table"][-1] == {
        "target": "clean_after", "when": leaf("selected_processes", "turn", "contains")}


def test_optional_required_process_diagnostic_uses_names_and_points_to_configured_relation():
    value = package(
        fields=[bool_field("needs_quench")],
        processes=[
            {"process_id": "split-900025", "display_name": "淬火", "main": False, "default_sequence": 1},
            {"process_id": "segment-nondestructive_inspection_merge", "display_name": "无损检查", "main": True, "default_sequence": 2},
        ],
        rules=[rule("quench-if-needed", leaf("needs_quench"), include=["split-900025"])],
    )
    value.route_rules.process_configurations = [ProcessConfigurationV2(
        process_id="segment-nondestructive_inspection_merge",
        occurrence="always",
        relations=[{
            "relation_type": "requires",
            "source_process_ids": ["split-900025"],
            "target_process_ids": ["segment-nondestructive_inspection_merge"],
        }],
    )]

    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value))

    issue = next(item for item in caught.value.issues if item["code"] == "unsupported_requires")
    assert issue["process_id"] == "segment-nondestructive_inspection_merge"
    assert issue["process_name"] == "无损检查"
    assert issue["prerequisite_process_ids"] == ["split-900025"]
    assert issue["prerequisite_process_names"] == ["淬火"]
    assert issue["relation_index"] == 0
    assert "第 1 项" in issue["message"]
    assert "split-900025" not in issue["message"]


def test_unknown_required_constraint_returns_a_diagnostic_instead_of_raising_key_error():
    value = package()
    value.route_catalog.processes[1].constraints.requires = ["missing_process"]

    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value))

    assert any(issue["code"] == "unknown_process_dependency" for issue in caught.value.issues)


@pytest.mark.parametrize("constraint,code", [
    ({"requires": ["turn"]}, "unsupported_requires"),
    ({"conflicts_with": ["turn"]}, "unsupported_conflicts"),
    ({"must_run_before": ["turn"]}, "route_order_conflict"),
])
def test_unrepresentable_constraints_and_wrong_fixed_order_have_specific_diagnostics(constraint, code):
    value = package()
    value.route_catalog.processes[2].constraints = value.route_catalog.processes[2].constraints.model_validate(constraint)
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value))
    assert any(i["code"] == code for i in caught.value.issues)


def test_required_dependency_already_main_is_safe_if_fixed_route_order_matches():
    value = package()
    value.route_catalog.processes[1].constraints.requires = ["clean_before"]
    validate_demo_tables(compile_demo_tables(value, route_for(value)))


def test_route_identity_is_not_guessed_from_names():
    value = package()
    route = route_for(value)
    route[0]["process_id"] = "other_clean"
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route)
    assert any(i["code"] == "stale_catalog_identity" for i in caught.value.issues)


@pytest.mark.parametrize("sequences", [(20, 10), (10, 10)])
def test_stale_mapping_process_order_cannot_publish_a_different_native_order(sequences):
    value = package(processes=[
        {"process_id": "custom_b", "display_name": "准备", "main": True, "default_sequence": sequences[0]},
        {"process_id": "custom_a", "display_name": "处理", "main": True, "default_sequence": sequences[1]},
    ])
    route = route_for(value)
    assert plan_route(value, {}).selected_process_ids == ["custom_a", "custom_b"]
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route)
    assert any(i["code"] == "stale_catalog_order" for i in caught.value.issues)


@pytest.mark.parametrize("ordering", ["constraint", "legacy_relation", "configuration_relation"])
def test_valid_dependency_order_overrides_base_sequence_in_published_mapping(downstream_engine, ordering):
    value = package(processes=[
        {"process_id": "custom_before", "display_name": "前置", "main": True, "default_sequence": 20},
        {"process_id": "custom_after", "display_name": "后置", "main": True, "default_sequence": 10,
         "constraints": {"must_run_after": ["custom_before"]} if ordering == "constraint" else {}},
    ])
    if ordering != "constraint":
        relation = {"relation_type": "order_after", "source_process_ids": ["custom_before"], "target_process_ids": ["custom_after"]}
        if ordering == "legacy_relation":
            value.route_rules.process_relations = [
                ProcessRelationV2(relation_id="sequence", **relation)
            ]
        else:
            value.route_rules.process_configurations = [
                ProcessConfigurationV2(
                    process_id="custom_after", occurrence="always", relations=[relation],
                )
            ]
    assert plan_route(value, {}).selected_process_ids == ["custom_before", "custom_after"]
    tables = compile_demo_tables(value, route_for(value))
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    assert [p["process_name"] for p in engine.run({"input_json": []})["route"]] == ["前置", "后置"]


def test_auxiliary_process_has_no_steps_even_if_other_fields_are_valid():
    value = package()
    route = route_for(value)
    route[1]["process_type"] = "辅助工序"
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route)
    assert any(i["code"] == "auxiliary_steps" for i in caught.value.issues)


@pytest.mark.parametrize("precision,code", [("", "missing_process_precision"), ("未分类", "invalid_process_precision")])
def test_machining_process_precision_must_be_confirmed_before_compilation(precision, code):
    value = package()
    route = route_for(value)
    route[1]["precision"] = precision
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route)
    assert any(issue["code"] == code for issue in caught.value.issues)
    assert "车削" in str(caught.value)


def test_auxiliary_process_precision_must_use_auxiliary_label():
    tables = demo_tables()
    tables["full_route_table"][1]["precision"] = "粗加工"
    with pytest.raises(DemoTableError) as caught:
        validate_demo_tables(tables)
    assert any(issue["code"] == "invalid_auxiliary_precision" for issue in caught.value.issues)


def demo_tables():
    return {
        "factor_table": [
            {"key": "feature_type", "label": "特征", "type": "enum", "source": "input_json[].features[].feature_select", "visible": False},
            {"key": "feature_rank", "label": "精度", "type": "int", "source": "input_json[].features[].feat_rank", "visible": False},
        ],
        "full_route_table": [
            {"process_id": "p", "process_name": "加工", "process_type": "加工工序", "precision": "精加工",
             "steps": [{"step_id": "s", "step_name": "铰孔", "candidates": {"*/孔": ["孔"]}}]},
            {"process_id": "pack", "process_name": "包装", "process_type": "辅助工序", "precision": "辅助工序", "steps": []},
        ],
        "rule_table": [
            {"target": "p", "when": {"some": {"all": [leaf("feature_type", ["孔"], "in"), leaf("feature_rank", 9, "lte")]}}},
            {"target": "s", "when": True},
            {"target": "pack", "when": leaf("selected_processes", "p", "contains")},
        ],
    }


def test_strict_validator_accepts_demo_some_step_rules_and_forward_dependencies():
    tables = demo_tables()
    tables["full_route_table"].reverse()
    validate_demo_tables(tables)


@pytest.mark.parametrize("change,code", [
    (lambda t: t["factor_table"][0].update(visible=True), "invalid_factor_source"),
    (lambda t: t["factor_table"][0].update(type="boolean"), "invalid_factor_type"),
    (lambda t: t["factor_table"][0].update(options=[{"value": "孔"}]), "invalid_factor_options"),
    (lambda t: t["factor_table"][0].update(source="CAD/PLM"), "invalid_factor_source"),
    (lambda t: t["factor_table"][0].update(key="selected_processes"), "reserved_factor"),
    (lambda t: t["full_route_table"][0].update(technical_requirements=[]), "unexpected_fields"),
    (lambda t: t["full_route_table"][0]["steps"][0].update(is_last=True), "unexpected_fields"),
    (lambda t: t["full_route_table"][0]["steps"][0].update(step_id="p"), "duplicate_node_id"),
    (lambda t: t["rule_table"].append({"target": "p", "when": True}), "duplicate_target"),
    (lambda t: t["rule_table"][0].update(target="missing"), "unknown_target"),
    (lambda t: t["rule_table"][0].update(when=leaf("missing", 9)), "unknown_factor"),
    (lambda t: t["rule_table"][0].update(when=leaf("feature_type", 9, "lt")), "invalid_condition_type"),
    (lambda t: t["rule_table"][0].update(when=leaf("feature_rank", True, "gte")), "invalid_condition_type"),
    (lambda t: t["rule_table"][0].update(when=leaf("feature_rank", 9, "between")), "invalid_operator"),
    (lambda t: t["rule_table"][0].update(when=leaf("feature_rank", "yes", "exists")), "invalid_condition_type"),
    (lambda t: t["rule_table"][0].update(when=leaf("selected_processes", "missing", "contains")), "unknown_process_dependency"),
    (lambda t: t["rule_table"][0].update(when=leaf("selected_processes", "pack", "contains")), "dependency_cycle"),
])
def test_strict_validator_rejects_invalid_or_ambiguous_protocol(change, code):
    tables = demo_tables()
    change(tables)
    with pytest.raises(DemoTableError) as caught:
        validate_demo_tables(tables)
    assert any(issue["code"] == code for issue in caught.value.issues)


@pytest.mark.parametrize("kind,default", [("bool", False), ("multi_enum", []), ("string", ""), ("number", 0)])
def test_explicit_empty_defaults_are_preserved_and_type_checked(kind, default):
    tables = demo_tables()
    tables["factor_table"].append({"key": "custom", "label": "自定义", "type": kind,
        "source": "manual_defaults.custom", "visible": True, "default": default})
    validate_demo_tables(tables)
    assert tables["factor_table"][-1]["default"] == default


def test_catalog_with_stale_step_identity_is_rejected_even_if_names_match():
    value = package()
    route = route_for(value)
    route[1]["steps"][0]["step_id"] = "renamed_id"
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route)
    assert any(i["code"] == "stale_catalog_identity" for i in caught.value.issues)


def test_invalid_condition_on_required_process_is_not_hidden_by_main_rule_simplification():
    value = package(fields=[bool_field("choice")], rules=[
        rule("invalid", leaf("choice", 2, "lt"), include=["clean_before"]),
    ])
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value))
    assert any(i["code"] == "invalid_condition_type" for i in caught.value.issues)


def test_multi_enum_equal_conditions_are_not_assumed_disjoint_across_values():
    value = package(fields=[{"key": "tags", "label": "tags", "type": "multi_select"}], rules=[
        rule("add", leaf("tags", "x"), include=["turn"]),
        rule("remove", leaf("tags", "y"), exclude=["turn"]),
    ])
    # V2 compares whole lists for eq, whereas Demo eq on an array matches any
    # element.  This input has no lossless direct conversion and must not pass.
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value))
    assert any(i["code"] == "unsupported_collection_equality" for i in caught.value.issues)


@pytest.mark.parametrize("change", [
    lambda t: t["factor_table"][0].update(type=[], options=[]),
    lambda t: t["full_route_table"][0].update(process_type=[]),
    lambda t: t["rule_table"][0].update(when={"field": "feature_type", "op": [], "value": 9}),
    lambda t: t["rule_table"][0].update(when={"field": [], "op": "eq", "value": 9}),
])
def test_malformed_json_types_report_publication_issues_instead_of_crashing(change):
    tables = demo_tables()
    change(tables)
    with pytest.raises(DemoTableError):
        validate_demo_tables(tables)


def test_unmapped_optional_step_is_not_forced_closed_by_a_step_rule():
    value = package()
    route = route_for(value)
    route[1]["steps"][0]["candidates"] = {}
    tables = compile_demo_tables(value, route)
    assert tables["full_route_table"][1]["steps"][0]["candidates"] == {}
    assert not any(rule["target"] == "turn_outer" for rule in tables["rule_table"])


@pytest.mark.parametrize("main,confirmed", [(True, False), (False, True)])
def test_enabled_process_with_unmapped_step_does_not_block_publication(main, confirmed):
    value = package(fields=[bool_field("choose")], rules=[
        rule("choose", leaf("choose"), include=["turn"], source="user_confirmed"),
    ] if confirmed else [])
    value.route_catalog.processes[1].main = main
    route = route_for(value)
    route[1]["steps"][0]["candidates"] = {}
    tables = compile_demo_tables(value, route)
    assert tables["full_route_table"][1]["steps"][0]["candidates"] == {}
    assert {item["target"]: item for item in tables["rule_table"]}["turn"] == (
        {"target": "turn", "required": True} if main else {"target": "turn", "when": leaf("choose")}
    )
    assert not any(item["target"] == "turn_outer" for item in tables["rule_table"])


def test_explicitly_reviewed_general_step_is_preserved_without_internal_status_leaking():
    value = package()
    value.route_catalog.processes[1].main = True
    route = route_for(value)
    route[1]["steps"][0]["candidates"] = {}
    tables = compile_demo_tables(value, route, step_states={"turn_outer": "general"})
    assert tables["full_route_table"][1] == route[1]
    assert not any(r["target"] == "turn_outer" for r in tables["rule_table"])
    assert tables["rule_table"][1] == {"target": "turn", "required": True}


def test_unknown_general_step_identity_cannot_authorize_an_unmapped_step():
    value = package()
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value), step_states={"old_step": "general"})
    assert any(i["code"] == "unknown_step_review" for i in caught.value.issues)


@pytest.mark.parametrize("op,value", [("eq", "9cr18"), ("neq", " 9Cr18 "), ("in", ["9Cr18"]), ("contains", "Cr")])
def test_open_text_comparison_is_not_exported_with_silently_changed_case_and_space_semantics(op, value):
    data = package(fields=[{"key": "free_text", "label": "自由文本", "type": "string"}], rules=[
        rule("compare", leaf("free_text", value, op), include=["turn"]),
    ])
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(data, route_for(data))
    assert any(i["code"] == "unsupported_text_comparison" for i in caught.value.issues)


def test_open_text_presence_check_has_identical_semantics_and_remains_supported():
    data = package(fields=[{"key": "free_text", "label": "自由文本", "type": "string"}], rules=[
        rule("present", {"field": "free_text", "op": "exists"}, include=["turn"]),
    ])
    validate_demo_tables(compile_demo_tables(data, route_for(data)))


def test_material_grade_is_a_reviewed_closed_enum_for_lossless_demo_export():
    definition = condition_field_map()["material.grade"]
    assert definition.type == "single_select"
    assert definition.options
    assert definition.allow_custom is False

    data = package(fields=[{
        "key": definition.key,
        "label": definition.label,
        "type": definition.type,
        "options": definition.options,
        "allow_custom": definition.allow_custom,
    }], rules=[rule("grade", leaf(definition.key, " 4cr14ni14w2mo "), include=["turn"])])
    tables = compile_demo_tables(data, route_for(data))
    compiled = next(item for item in tables["rule_table"] if item["target"] == "turn")["when"]
    assert match(compiled, {"material": "4Cr14Ni14W2Mo"})
    assert not match(compiled, {"material": "unreviewed-grade"})


def test_cad_feature_categories_are_a_reviewed_closed_enum_for_lossless_demo_export():
    definition = condition_field_map()["cad.features"]
    assert definition.allow_custom is False

    data = package(fields=[{
        "key": definition.key,
        "label": definition.label,
        "type": definition.type,
        "options": definition.options,
        "allow_custom": definition.allow_custom,
        "source": "CAD",
    }], rules=[rule("feature", leaf(definition.key, "槽类特征", "contains"), include=["turn"])])
    tables = compile_demo_tables(data, route_for(data))
    compiled = next(item for item in tables["rule_table"] if item["target"] == "turn")["when"]
    assert match(compiled, {"cad.features": ["槽类特征"]})
    assert not match(compiled, {"cad.features": ["复杂槽类特征"]})


def test_static_requirement_enums_are_closed_and_export_as_exact_membership():
    definitions = condition_field_map()
    for key in ("precision.grades", "special.requirements"):
        assert definitions[key].options
        assert definitions[key].allow_custom is False


@pytest.mark.parametrize("field_type,op,value,code", [
    ("single_select", "eq", "x", "unsupported_text_comparison"),
    ("multi_select", "contains", "x", "unsupported_text_comparison"),
    ("number", "eq", 1.0, "unsupported_numeric_equality"),
    ("number", "neq", 1.0, "unsupported_numeric_equality"),
    ("number", "in", [1.0], "unsupported_numeric_equality"),
])
def test_unbounded_text_and_tolerant_numeric_equality_need_explicit_review(field_type, op, value, code):
    data = package(fields=[{"key": "custom", "label": "自定义", "type": field_type}], rules=[
        rule("compare", leaf("custom", value, op), include=["turn"]),
    ])
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(data, route_for(data))
    assert any(i["code"] == code for i in caught.value.issues)


def test_controlled_enum_conditions_are_canonicalized_using_existing_v2_semantics():
    data = package(fields=[
        {"key": "material.grade", "label": "材料", "type": "single_select",
         "options": [{"value": "9Cr18", "label": "9Cr18"}, {"value": "6061", "label": "6061"}]},
        {"key": "tags", "label": "标签", "type": "multi_select",
         "options": [{"value": "TAG", "label": "TAG"}, {"value": "other", "label": "other"}]},
    ], rules=[rule("compare", {"all": [leaf("material.grade", " 9cr18 "), leaf("tags", "tag", "contains")]}, include=["turn"])])
    tables = compile_demo_tables(data, route_for(data))
    for material in ("9Cr18", "6061", ""):
        for tags in ([], ["TAG"], ["other"], ["TAG", "other"]):
            expected = "turn" in plan_route(data, {"material.grade": material, "tags": tags}).selected_process_ids
            assert enabled(tables["rule_table"], "turn", {"material": material, "tags": tags}) is expected


def test_same_priority_enum_aliases_cannot_be_mistaken_for_disjoint_conditions():
    data = package(fields=[
        {"key": "material", "label": "材料", "type": "single_select",
         "options": [{"value": "9Cr18", "label": "9Cr18"}]},
    ], rules=[
        rule("add", leaf("material", "9Cr18"), include=["turn"]),
        rule("remove", leaf("material", " 9cr18 "), exclude=["turn"]),
    ])
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(data, route_for(data))
    assert any(i["code"] == "same_priority_action_conflict" for i in caught.value.issues)


@pytest.mark.parametrize("op,value", [("neq", " 9cr18 "), ("in", ["9cr18"]), ("contains", "CR")])
def test_controlled_scalar_enum_operators_preserve_normalized_v2_semantics(op, value):
    data = package(fields=[
        {"key": "material", "label": "材料", "type": "single_select", "required": True,
         "options": [{"value": "9Cr18", "label": "9Cr18"}, {"value": "6061", "label": "6061"}]},
    ], rules=[rule("choose", leaf("material", value, op), include=["turn"])])
    tables = compile_demo_tables(data, route_for(data))
    for actual in ("9Cr18", "6061", "", None):
        expected = "turn" in plan_route(data, {"material": actual}).selected_process_ids
        assert enabled(tables["rule_table"], "turn", {"material": actual}) is expected


ENGINE_PATH = Path("/Users/zhaoyongwei/Desktop/KmAI-Win7-SP1-x64-20261018-r24/KmMpsMcpServer/skills/process-route-generator/scripts/config_route_engine.py")
DEMO_PATH = Path("/Users/zhaoyongwei/Desktop/中地4步工艺生成Demo")


@pytest.fixture
def downstream_engine():
    if not ENGINE_PATH.is_file():
        pytest.skip("The actual downstream CAD engine is not available in this checkout")
    spec = importlib.util.spec_from_file_location("readonly_downstream_config_route_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ConfigRouteEngine


@pytest.mark.parametrize('field,allowed,rejected', [
    ({'key': 'precision.hole_it', 'label': '内孔 IT', 'type': 'number',
      'validation': {'min': 5, 'max': 10}}, 5, 11),
    ({'key': 'text', 'label': '文本', 'type': 'string',
      'validation': {'min_length': 1, 'max_length': 3}}, '中文', '中文测试'),
    ({'key': 'choices', 'label': '多选', 'type': 'multi_select',
      'options': [{'value': v, 'label': v} for v in ['A', 'B', 'C']],
      'validation': {'min_length': 1, 'max_length': 2}}, ['A', 'B'], ['A', 'B', 'C']),
])
def test_exported_constraints_are_executed_by_actual_downstream_engine(downstream_engine, field, allowed, rejected):
    value = package(fields=[field])
    tables = compile_demo_tables(value, route_for(value))
    factor = tables['factor_table'][0]
    assert factor['validation'] == field['validation']
    validate_publication_input_constraints(value, tables)
    engine = downstream_engine(tables['factor_table'], tables['full_route_table'], tables['rule_table'])
    assert engine.run({'factor_overrides': {factor['key']: allowed}})['factors'][factor['key']] == allowed
    with pytest.raises(ValueError):
        engine.run({'factor_overrides': {factor['key']: rejected}})


def test_export_limits_follow_active_input_schema_instead_of_dictionary():
    value = package(fields=[{'key': 'length', 'label': '长度', 'type': 'number', 'validation': {'min': 0, 'max': 100}}])
    value.input_schema.fields[0].validation.max = 10
    tables = compile_demo_tables(value, route_for(value))
    assert tables['factor_table'][0]['validation'] == {'min': 0, 'max': 10}
    assert value.factor_dictionary.fields[0].validation.max == 100
    validate_publication_input_constraints(value, tables)
    tables['factor_table'][0]['validation']['max'] = 100
    with pytest.raises(DemoTableError, match='不能无损导出'):
        validate_publication_input_constraints(value, tables)


@pytest.mark.parametrize('kind,limits', [
    ('number', {'min': 0, 'max': 10}), ('int', {'min': -2.5}),
    ('string', {'min_length': 0, 'max_length': 3}),
    ('enum', {'min_length': 1}), ('multi_enum', {'max_length': 2}),
])
def test_public_factor_validator_accepts_typed_constraints(kind, limits):
    validate_demo_tables({'factor_table': [{'key': 'x', 'label': 'x', 'type': kind,
        'source': 'manual_defaults.x', 'visible': True, 'validation': limits}],
        'full_route_table': [], 'rule_table': []})


@pytest.mark.parametrize('kind,limits', [
    ('number', None), ('number', []), ('number', {'unknown': 1}),
    ('number', {'min': True}), ('number', {'max': float('inf')}),
    ('number', {'min': 10, 'max': 5}), ('number', {'min_length': 1}),
    ('bool', {'min': 1}), ('string', {'max': 1}),
    ('string', {'min_length': -1}), ('string', {'max_length': 1.5}),
    ('multi_enum', {'min_length': 3, 'max_length': 1}),
])
def test_public_factor_validator_rejects_invalid_constraint_metadata(kind, limits):
    with pytest.raises(DemoTableError) as exc:
        validate_demo_tables({'factor_table': [{'key': 'x', 'label': 'x', 'type': kind,
            'source': 'manual_defaults.x', 'visible': True, 'validation': limits}],
            'full_route_table': [], 'rule_table': []})
    assert any(issue['code'] == 'invalid_factor_validation' for issue in exc.value.issues)


def test_public_factor_validator_rejects_default_outside_constraints():
    with pytest.raises(DemoTableError) as exc:
        validate_demo_tables({'factor_table': [{'key': 'it', 'label': 'IT', 'type': 'number',
            'source': 'manual_defaults.it', 'visible': True,
            'validation': {'min': 5, 'max': 10}, 'default': 11}],
            'full_route_table': [], 'rule_table': []})
    assert any(issue['code'] == 'invalid_factor_default' for issue in exc.value.issues)


def public_route(route):
    result = deepcopy(route)
    for p in result:
        for s in p["steps"]:
            s.pop("candidate_details", None)
    return result


def test_actual_downstream_engine_reproduces_all_32_demo_operations(downstream_engine):
    if not DEMO_PATH.is_dir():
        pytest.skip("The reference Demo artifact is not available in this checkout")
    read = lambda name: json.loads((DEMO_PATH / name).read_text(encoding="utf-8"))
    tables = {key: read(f"{key}.json") for key in ("factor_table", "full_route_table", "rule_table")}
    validate_demo_tables(tables)
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    actual = public_route(engine.run(read("input.json"))["route"])
    assert len(actual) == 32
    assert actual == read("route_output.json")
    assert [p["process_name"] for p in actual[-3:]] == ["清洗", "检验", "包装"]


def test_actual_downstream_engine_accepts_compiled_material_and_manual_toggle(downstream_engine):
    key = "project_factor.manual_process_turn"
    value = package(fields=[
        {"key": "material.grade", "label": "材料", "type": "single_select", "required": True,
         "source": "CAD/PLM", "options": [{"value": "9Cr18", "label": "9Cr18"}]},
        bool_field(key),
    ], rules=[
        rule("manual.true", leaf(key), include=["turn"], source="user_confirmed"),
        rule("manual.false", leaf(key, False), exclude=["turn"], source="user_confirmed"),
    ])
    tables = compile_demo_tables(value, route_for(value))
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    request = {"input_json": [{"group_path": "A侧\\外圆/", "features": [{"feature_select": "外圆柱面", "feat_rank": 8}]}],
               "manual_defaults": {"material_grade": "9Cr18"}, "manual": {"factor_overrides": {key: True}}}
    actual = engine.run(request)
    assert [p["process_name"] for p in actual["route"]] == ["清洗", "车削", "清洗"]
    assert actual["route"][1]["steps"][0]["candidates"] == {"A侧/外圆": ["外圆柱面"]}
    assert actual["route"][1]["steps"][0]["is_last"] is True
    request["manual"]["factor_overrides"][key] = False
    assert [p["process_name"] for p in engine.run(request)["route"]] == ["清洗", "清洗"]


def test_actual_downstream_feature_category_uses_exact_membership(downstream_engine):
    value = package(fields=[{
        "key": "cad.features", "label": "CAD 特征集合", "type": "multi_select",
        "source": "CAD", "options": [
            {"value": "槽类特征", "label": "槽类特征"},
            {"value": "复杂槽类特征", "label": "复杂槽类特征"},
        ],
        "allow_custom": False,
    }], rules=[rule(
        "slot-feature", leaf("cad.features", "槽类特征", "contains"), include=["turn"],
    )])
    route = route_for(value)
    route[1]["steps"][0]["candidates"] = {"A侧/外圆": ["外圆柱面"]}
    tables = compile_demo_tables(value, route)
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])

    def route_for_feature(category):
        return engine.run({
            "input_json": [{"group_path": "A侧/外圆", "features": [{"feature_select": "外圆柱面"}]}],
            "manual_defaults": {"cad": {"features": [category]}},
        })["route"]

    assert "车削" in [process["process_name"] for process in route_for_feature("槽类特征")]
    assert "车削" not in [process["process_name"] for process in route_for_feature("复杂槽类特征")]


@pytest.mark.parametrize("real_feature_factor", [False, True])
@pytest.mark.parametrize("categories,expected,expected_names", [
    (["普通孔/辅助孔"], ["base", "drill"], ["准备", "钻孔"]),
    (["扁位/平面"], ["base"], ["准备"]),
])
def test_abstract_cad_categories_coexist_with_real_geometry_in_actual_engine(
    downstream_engine, real_feature_factor, categories, expected, expected_names,
):
    definition = condition_field_map()["cad.features"]
    fields = [{
        "key": definition.key, "label": definition.label, "type": definition.type,
        "source": definition.source, "options": definition.options,
        "required": True, "allow_custom": False,
    }]
    condition = leaf("cad.features", "普通孔/辅助孔", "contains")
    inputs = {"cad.features": categories}
    if real_feature_factor:
        fields.append({
            "key": "feature_type", "label": "实际几何特征", "type": "multi_select",
            "source": "input_json[].features[].feature_select", "required": True,
            "options": [{"value": name, "label": name} for name in ("孔", "外圆柱面")],
        })
        condition = {"all": [condition, leaf("feature_type", "孔", "contains")]}
        inputs["feature_type"] = ["孔", "外圆柱面"]
    value = package(fields=fields, processes=[
        {"process_id": "base", "display_name": "准备", "main": True, "default_sequence": 1},
        {"process_id": "drill", "display_name": "钻孔", "default_sequence": 2, "steps": [
            {"step_id": "drill_hole", "name": "钻辅助孔"},
        ]},
    ], rules=[rule("auxiliary-hole", condition, include=["drill"])])
    route = route_for(value)
    route[1]["steps"][0]["candidates"] = {"A侧/孔": ["孔"]}
    tables = {key: json.loads(json.dumps(table, ensure_ascii=False))
              for key, table in compile_demo_tables(value, route).items()}
    category_factor = next(factor for factor in tables["factor_table"] if factor["key"] == "cad.features")
    assert category_factor["source"] == "manual_defaults.cad.features"
    assert category_factor["type"] == "multi_enum"
    assert category_factor["visible"] is True
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    result = engine.run({
        "input_json": [
            {"group_path": "A侧/孔", "features": [{"feature_select": "孔"}]},
            {"group_path": "A侧/外圆", "features": [{"feature_select": "外圆柱面"}]},
        ],
        "manual_defaults": {"cad": {"features": categories}},
    })
    assert plan_route(value, inputs).selected_process_ids == expected
    assert [process["process_name"] for process in result["route"]] == expected_names
    assert result["factors"]["cad.features"] == categories
    if "drill" in expected:
        assert result["route"][1]["steps"][0]["candidates"] == {"A侧/孔": ["孔"]}
    if real_feature_factor:
        assert result["factors"]["feature_type"] == ["孔", "外圆柱面"]


def test_actual_downstream_some_does_not_combine_different_features(downstream_engine):
    tables = demo_tables()
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    request = {"input_json": [
        {"group_path": "A侧/孔", "features": [{"feature_select": "孔", "feat_rank": 12}]},
        {"group_path": "A侧/外圆", "features": [{"feature_select": "外圆柱面", "feat_rank": 7}]},
    ]}
    assert engine.run(request)["route"] == []
    request["input_json"][0]["features"][0]["feat_rank"] = 8
    assert [p["process_name"] for p in engine.run(request)["route"]] == ["加工", "包装"]


def test_actual_downstream_is_last_is_true_if_any_bound_feature_is_last(downstream_engine):
    value = package(processes=[
        {"process_id": "a", "display_name": "粗车", "main": True,
         "steps": [{"step_id": "sa", "name": "车外圆及倒圆"}]},
        {"process_id": "b", "display_name": "精车", "main": True,
         "steps": [{"step_id": "sb", "name": "精车外圆"}]},
    ])
    route = route_for(value)
    route[0]["steps"][0]["candidates"]["A侧/外圆"].append("回转面倒圆")
    tables = compile_demo_tables(value, route)
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    actual = engine.run({"input_json": [{"group_path": "A侧/外圆/", "features": [
        {"feature_select": "外圆柱面"}, {"feature_select": "回转面倒圆"},
    ]}]})["route"]
    assert [p["steps"][0]["is_last"] for p in actual] == [True, True]


@pytest.mark.parametrize("ordering", ["constraint", "legacy_relation", "configuration_relation"])
@pytest.mark.parametrize("choose,expected", [(False, ["c", "a"]), (True, ["c", "b", "a"])])
def test_optional_predecessor_keeps_native_route_in_published_parent_order(downstream_engine, ordering, choose, expected):
    value = package(fields=[bool_field("choose")], processes=[
        {"process_id": "a", "display_name": "后置", "main": True, "default_sequence": 1,
         "constraints": {"must_run_after": ["b"]} if ordering == "constraint" else {}},
        {"process_id": "b", "display_name": "可选前置", "default_sequence": 3},
        {"process_id": "c", "display_name": "准备", "main": True, "default_sequence": 2},
    ], rules=[rule("choose-b", leaf("choose"), include=["b"])])
    if ordering != "constraint":
        relation = {"relation_type": "order_after", "source_process_ids": ["b"], "target_process_ids": ["a"]}
        if ordering == "legacy_relation":
            value.route_rules.process_relations = [ProcessRelationV2(relation_id="order", **relation)]
        else:
            value.route_rules.process_configurations = [ProcessConfigurationV2(process_id="a", occurrence="always", relations=[relation])]
    route = route_for(value)
    tables = compile_demo_tables(value, [route[2], route[1], route[0]])
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    assert plan_route(value, {"choose": choose}).selected_process_ids == expected
    names = {p.process_id: p.display_name for p in value.route_catalog.processes}
    actual = engine.run({"input_json": [], "manual": {"factor_overrides": {"choose": choose}}})
    assert [p["process_name"] for p in actual["route"]] == [names[pid] for pid in expected]


def test_optional_boolean_uses_active_schema_requiredness_instead_of_dictionary(downstream_engine):
    value = package(fields=[bool_field("choose")], processes=[
        {"process_id": "base", "display_name": "准备", "main": True, "default_sequence": 1},
        {"process_id": "optional", "display_name": "可选", "default_sequence": 2},
    ], rules=[rule("false-choice", leaf("choose", False), include=["optional"])])
    value.factor_dictionary.fields[0].required = True
    tables = compile_demo_tables(value, route_for(value))
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    assert plan_route(value, {}).selected_process_ids == ["base"]
    assert [p["process_name"] for p in engine.run({"input_json": []})["route"]] == ["准备"]
    assert tables["factor_table"][0].get("required", False) is False


def test_active_schema_can_require_a_factor_optional_in_dictionary():
    value = package(fields=[bool_field("choose", required=True)])
    value.factor_dictionary.fields[0].required = False
    tables = compile_demo_tables(value, route_for(value))
    assert tables["factor_table"][0].get("required") is True


def test_required_boolean_rejects_missing_input_but_accepts_explicit_false(downstream_engine):
    value = package(fields=[bool_field("choose", required=True)], processes=[
        {"process_id": "base", "display_name": "准备", "main": True, "default_sequence": 1},
        {"process_id": "optional", "display_name": "可选", "default_sequence": 2},
    ], rules=[rule("false-choice", leaf("choose", False), include=["optional"])])
    tables = compile_demo_tables(value, route_for(value))
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    with pytest.raises(ValueError, match="required factor is empty"):
        engine.run({"input_json": []})
    result = engine.run({"input_json": [], "manual": {"factor_overrides": {"choose": False}}})
    assert [p["process_name"] for p in result["route"]] == ["准备", "可选"]


@pytest.mark.parametrize("op,wanted,expected", [
    ("gt", 9007199254740992, True),
    ("lte", 9007199254740992, False),
    ("between", [9007199254740992, 9007199254740992], False),
])
def test_integer_numeric_boundaries_do_not_lose_precision_in_native_route(downstream_engine, op, wanted, expected):
    value = package(fields=[{"key": "quantity", "label": "数量", "type": "number"}], processes=[
        {"process_id": "base", "display_name": "准备", "main": True, "default_sequence": 1},
        {"process_id": "optional", "display_name": "可选", "default_sequence": 2},
    ], rules=[rule("boundary", leaf("quantity", wanted, op), include=["optional"])])
    tables = compile_demo_tables(value, route_for(value))
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    inputs = {"quantity": 9007199254740993}
    assert ("optional" in plan_route(value, inputs).selected_process_ids) is expected
    actual = engine.run({"input_json": [], "factor_overrides": inputs})
    assert ("可选" in [process["process_name"] for process in actual["route"]]) is expected


@pytest.mark.parametrize("location", ["default", "condition"])
def test_extreme_numeric_json_reports_validation_issue_without_overflow(location):
    tables = demo_tables()
    if location == "default":
        tables["factor_table"][1].update(type="number", default=10 ** 1000)
    else:
        tables["rule_table"][0]["when"] = leaf("feature_rank", 10 ** 1000, "gte")
    with pytest.raises(DemoTableError) as caught:
        validate_demo_tables(tables)
    assert any(issue["code"] in {"invalid_factor_default", "invalid_condition_type"} for issue in caught.value.issues)


def test_custom_feature_collection_uses_scalar_items_for_repeated_cad_source(downstream_engine):
    value = package(fields=[{
        "key": "project_factor.feature_kinds", "label": "特征", "type": "multi_select",
        "source": "input_json[].features[].feature_select",
        "options": [{"value": name, "label": name} for name in ("孔", "外圆柱面")],
    }], processes=[
        {"process_id": "base", "display_name": "准备", "main": True, "default_sequence": 1},
        {"process_id": "optional", "display_name": "可选", "default_sequence": 2},
    ], rules=[rule("hole", leaf("project_factor.feature_kinds", "孔", "contains"), include=["optional"])])
    tables = compile_demo_tables(value, route_for(value))
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    assert plan_route(value, {"project_factor.feature_kinds": ["孔"]}).selected_process_ids == ["base", "optional"]
    result = engine.run({"input_json": [{"features": [{"feature_select": "孔"}]}]})
    assert [process["process_name"] for process in result["route"]] == ["准备", "可选"]


@pytest.mark.parametrize("source,option", [
    ("input_json[].features[].feature_select", "孔(盲孔)"),
    ("input_json[].features[].feature_select", "孔(通孔)"),
    ("input_json[].group_path", "/A侧/孔/"),
    ("input_json[].group_path", "A侧\\孔"),
])
def test_lossy_downstream_source_normalization_cannot_publish_distinct_enum_values(source, option):
    value = package(fields=[{
        "key": "project_factor.cad_items", "label": "CAD枚举", "type": "multi_select",
        "source": source, "options": [{"value": option, "label": option}],
    }], rules=[rule("choose-cad", leaf("project_factor.cad_items", option, "contains"), include=["turn"])])
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(value, route_for(value))
    assert any(issue["code"] == "unsupported_source_normalization" for issue in caught.value.issues)


@pytest.mark.parametrize("active,supplied,allowed", [
    (["A"], "B", False),
    ([], "C", True),
])
def test_export_uses_active_schema_option_domain(downstream_engine, active, supplied, allowed):
    from app.services.rule_packages.input_validation import validate_inputs
    from app.services.rule_packages.validator import validate_rule_package

    value = package(fields=[{
        "key": "choice", "label": "类别", "type": "single_select", "required": True,
        "options": [{"value": item, "label": item} for item in ["A", "B"]],
    }], processes=[{"process_id": "clean", "display_name": "清洗", "main": True}])
    value.input_schema.fields[0].options = [
        option for option in value.input_schema.fields[0].options if option.value in active
    ]
    value = RulePackageV2.model_validate(value.model_dump(mode="json", by_alias=True))
    assert validate_rule_package(value).valid
    assert bool(validate_inputs(value.input_schema, {"choice": supplied})) == (not allowed)
    tables = compile_demo_tables(value, route_for(value))
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])
    request = {"factor_overrides": {"choice": supplied}}
    if allowed:
        assert [p["process_name"] for p in engine.run(request)["route"]] == ["清洗"]
    else:
        with pytest.raises(ValueError, match="unknown option"):
            engine.run(request)
        assert [p["process_name"] for p in engine.run({"factor_overrides": {"choice": "A"}})["route"]] == ["清洗"]
