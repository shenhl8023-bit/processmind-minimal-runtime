"""The exported files must be executable Demo configuration, not internal V2 JSON."""

from copy import deepcopy
import importlib.util
from itertools import product
import json
from pathlib import Path

import pytest

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.demo_tables import (
    DemoTableError,
    compile_demo_tables,
    validate_demo_tables,
)
from app.services.rule_packages.condition_registry import condition_field_map
from app.services.rule_packages.planner import plan_route


def package(*, fields=None, processes=None, rules=None, relations=None):
    return RulePackageV2.model_validate({
        "manifest": {"package_name": "test", "project_id": 1, "scope": {"key": "1"}},
        "input_schema": {"fields": fields or []},
        "route_catalog": {"processes": processes or [
            {"process_id": "clean_before", "display_name": "清洗", "main": True},
            {"process_id": "turn", "display_name": "车削", "steps": [
                {"step_id": "turn_outer", "name": "车外圆"},
            ]},
            {"process_id": "clean_after", "display_name": "清洗", "main": True},
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
    assert factors[2]["key"] == "feature_type"
    assert factors[2]["source"] == "input_json[].features[].feature_select"
    assert factors[2]["type"] == "enum"
    assert factors[2]["visible"] is False
    assert factors[3]["source"] == "manual_defaults.project_factor.manual_process_a"
    assert factors[3]["type"] == "bool"
    assert all("default" not in f for f in factors)


def test_rule_fields_are_renamed_with_factors_and_extended_operators_are_lowered():
    value = package(fields=[
        {"key": "material.grade", "label": "材料", "type": "single_select", "options": [{"value": "9Cr18", "label": "9Cr18"}]},
        {"key": "tags", "label": "标签", "type": "multi_select", "options": [{"value": k, "label": k} for k in ("a", "b", "x", "y")]},
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
    assert match(compiled, {"feature_type": ["槽类特征"]})
    assert not match(compiled, {"feature_type": ["复杂槽类特征"]})


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
        {"key": "material", "label": "材料", "type": "single_select",
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
    route[1]["steps"][0]["candidates"] = {"槽": ["槽类特征"]}
    tables = compile_demo_tables(value, route)
    engine = downstream_engine(tables["factor_table"], tables["full_route_table"], tables["rule_table"])

    def route_for_feature(feature):
        return engine.run({"input_json": [{
            "group_path": "槽/", "features": [{"feature_select": feature}],
        }]})["route"]

    assert "车削" in [process["process_name"] for process in route_for_feature("槽类特征")]
    assert "车削" not in [process["process_name"] for process in route_for_feature("复杂槽类特征")]


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
