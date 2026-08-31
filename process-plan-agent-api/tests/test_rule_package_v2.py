import json
from copy import deepcopy

import pytest

from app.schemas.schemas import RouteStep
from app.services.generate_route_result_builder import build_generate_output_json
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.validator import validate_rule_package


def test_valid_package_runs_embedded_cases(rule_package_v2):
    report = validate_rule_package(rule_package_v2)

    assert report.valid is True
    assert [result.passed for result in report.test_results] == [True]


def test_validator_requires_an_action_assertion_for_each_enabled_rule(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["test_cases"][0]["expect"] = {
        "included_process_ids": ["process_prepare"],
        "excluded_process_ids": [],
    }

    report = validate_rule_package(RulePackageV2.model_validate(payload))

    assert report.valid is False
    assert "uncovered_conditional_rule" in {issue.code for issue in report.errors}


def test_plan_uses_stable_ids_and_dependency_order(rule_package_v2):
    plan = plan_route(
        rule_package_v2,
        {"material": {"grade": "9Cr18"}, "cad": {"features": ["槽类特征"]}, "target_hardness_hrc": 58},
    )

    assert plan.selected_process_ids == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]
    assert plan.steps[-1].process_steps == ["执行淬火"]
    assert [trace.rule_id for trace in plan.traces if trace.matched] == [
        "material.9cr18.quench",
        "feature.slot.mill",
    ]


def test_display_name_change_does_not_change_selection(rule_package_v2_payload):
    renamed = deepcopy(rule_package_v2_payload)
    process = next(item for item in renamed["route_catalog"]["processes"] if item["process_id"] == "process_quench")
    process["display_name"] = "真空淬火（新名称）"
    package = RulePackageV2.model_validate(renamed)

    plan = plan_route(package, {"material": {"grade": "9Cr18"}, "target_hardness_hrc": 58})

    assert "process_quench" in plan.selected_process_ids
    assert next(step.name for step in plan.steps if step.process_id == "process_quench") == "真空淬火（新名称）"


def test_template_group_aliases_do_not_change_display_name_and_follow_plan(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    process = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_mill_slot")
    process["display_name"] = "铣槽"
    process["template_group_aliases"] = [{
        "source_operation_id": 100,
        "alias": "铣槽（A侧/外环槽）",
        "template_group_id": "3358f0f62d04abb99d35dec48ef73e1",
        "template_group_path": ["A侧", "外环槽"],
    }]
    package = RulePackageV2.model_validate(payload)

    plan = plan_route(package, {"cad": {"features": ["槽类特征"]}})
    step = next(item for item in plan.steps if item.process_id == "process_mill_slot")

    assert step.name == "铣槽"
    assert [alias.model_dump() for alias in step.template_group_aliases] == process["template_group_aliases"]
    output = json.loads(build_generate_output_json(
        12,
        "finalized_rule_package_v2",
        [RouteStep(**step.model_dump())],
    ))
    assert output["route"][0]["process_name"] == "铣槽"
    assert output["route"][0]["template_group_aliases"] == process["template_group_aliases"]


def test_generated_route_json_keeps_full_route_structure():
    full_route_structure = [{
        "process_name": "调质",
        "process_type": "辅助工序",
        "precision": "",
        "technical_requirements": ["35HRC"],
        "steps": [],
    }]

    output = json.loads(build_generate_output_json(
        12,
        "finalized_rule_package_v2",
        [RouteStep(name="车削加工", op_type="MAIN", reason="主线工序")],
        full_route_structure=full_route_structure,
    ))

    assert output["full_route_structure"] == full_route_structure


def test_hash_is_stable_and_changes_with_semantics(rule_package_v2_payload):
    first = RulePackageV2.model_validate(rule_package_v2_payload)
    reordered = deepcopy(rule_package_v2_payload)
    reordered["manifest"] = dict(reversed(list(reordered["manifest"].items())))
    second = RulePackageV2.model_validate(reordered)
    changed = deepcopy(rule_package_v2_payload)
    changed["route_catalog"]["processes"][0]["display_name"] = "准备工序"
    third = RulePackageV2.model_validate(changed)

    assert rule_package_content_hash(first) == rule_package_content_hash(second)
    assert rule_package_content_hash(first) != rule_package_content_hash(third)


def test_validator_rejects_unknown_process_reference(rule_package_v2_payload):
    invalid = deepcopy(rule_package_v2_payload)
    invalid["route_rules"]["rules"][0]["then"]["include_process_ids"] = ["missing_process"]
    package = RulePackageV2.model_validate(invalid)

    report = validate_rule_package(package)

    assert report.valid is False
    assert "unknown_process_action" in {issue.code for issue in report.errors}


def test_validator_rejects_dependency_cycle(rule_package_v2_payload):
    invalid = deepcopy(rule_package_v2_payload)
    prepare = invalid["route_catalog"]["processes"][0]
    prepare["constraints"]["requires"] = ["process_quench"]
    package = RulePackageV2.model_validate(invalid)

    report = validate_rule_package(package)

    assert report.valid is False
    assert "dependency_cycle" in {issue.code for issue in report.errors}


def test_validator_requires_main_process(rule_package_v2_payload):
    invalid = deepcopy(rule_package_v2_payload)
    for process in invalid["route_catalog"]["processes"]:
        process["main"] = False
    package = RulePackageV2.model_validate(invalid)

    report = validate_rule_package(package)

    assert report.valid is False
    assert "missing_main_process" in {issue.code for issue in report.errors}


def _manual_boolean_pair_payload(payload, process_id="process_nitriding"):
    manual_field = f"project_factor.manual_process_{process_id.removeprefix('process_')}"
    payload["input_schema"]["fields"].append({
        "key": manual_field,
        "label": "是否需要渗氮",
        "type": "boolean",
        "required": False,
        "source": "用户直接设定",
        "options": [],
        "allow_custom": False,
    })
    audit = {
        "priority": 2000,
        "source": "user_confirmed",
        "source_segment_id": process_id,
        "source_text": "用户直接设定是否需要渗氮",
        "confirmed_by": "测试用户",
        "confirmed_at": "2026-08-06T10:00:00+00:00",
    }
    payload["route_rules"]["rules"].extend([
        {
            **audit,
            "rule_id": f"user.{process_id}.manual.true",
            "when": {"field": manual_field, "op": "eq", "value": True},
            "then": {
                "include_process_ids": [process_id],
                "exclude_process_ids": [],
                "reason": "用户选择需要",
            },
        },
        {
            **audit,
            "rule_id": f"user.{process_id}.manual.false",
            "when": {"field": manual_field, "op": "eq", "value": False},
            "then": {
                "include_process_ids": [],
                "exclude_process_ids": [process_id],
                "reason": "用户选择不需要",
            },
        },
    ])
    payload["test_cases"].extend([
        {
            "case_id": f"{process_id}-manual-true",
            "input": {
                "material": {"grade": "其他材料"},
                "cad": {"features": ["无槽"]},
                "target_hardness_hrc": 0,
                "project_factor": {manual_field.removeprefix("project_factor."): True},
            },
            "expect": {"included_process_ids": [process_id], "excluded_process_ids": []},
        },
        {
            "case_id": f"{process_id}-manual-false",
            "input": {
                "material": {"grade": "其他材料"},
                "cad": {"features": ["无槽"]},
                "target_hardness_hrc": 0,
                "project_factor": {manual_field.removeprefix("project_factor."): False},
            },
            "expect": {"included_process_ids": [], "excluded_process_ids": [process_id]},
        },
    ])
    return payload


def test_validator_accepts_exact_manual_boolean_pair(rule_package_v2_payload):
    package = RulePackageV2.model_validate(_manual_boolean_pair_payload(rule_package_v2_payload))

    report = validate_rule_package(package)

    assert report.valid is True
    assert "same_priority_action_conflict" not in {issue.code for issue in report.errors}


def test_validator_rejects_user_condition_that_targets_another_process(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "user.process_quench.cross_target",
        "priority": 1000,
        "enabled": True,
        "source": "user_confirmed",
        "source_segment_id": "process_quench",
        "source_text": "当材料为 9Cr18 时，纳入淬火工序。",
        "confirmed_by": "tester",
        "confirmed_at": "2026-08-07T00:00:00+00:00",
        "when": {"field": "material.grade", "op": "eq", "value": "9Cr18"},
        "then": {
            "include_process_ids": ["process_quench", "process_mill_slot"],
            "exclude_process_ids": [],
            "reason": "test",
        },
    })

    report = validate_rule_package(RulePackageV2.model_validate(payload))

    assert report.valid is False
    assert "user_rule_target_mismatch" in {issue.code for issue in report.errors}


def test_plan_disambiguates_repeated_process_names_by_phase(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    quench = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_quench")
    quench["display_name"] = "准备"
    quench["phase"] = "热处理"
    package = RulePackageV2.model_validate(payload)

    plan = plan_route(package, {"material": {"grade": "9Cr18"}, "target_hardness_hrc": 58})
    names = {step.process_id: step.name for step in plan.steps}

    assert names["process_prepare"] == "准备（prepare）"
    assert names["process_quench"] == "准备（热处理）"
    assert next(step.phase for step in plan.steps if step.process_id == "process_quench") == "热处理"


def test_validator_rejects_manual_pair_with_extra_same_priority_rule(rule_package_v2_payload):
    payload = _manual_boolean_pair_payload(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "user.process_nitriding.manual.extra",
        "priority": 2000,
        "source": "user_confirmed",
        "source_segment_id": "process_nitriding",
        "source_text": "重复的用户设定",
        "confirmed_by": "测试用户",
        "confirmed_at": "2026-08-06T10:00:00+00:00",
        "when": {
            "field": "project_factor.manual_process_nitriding",
            "op": "eq",
            "value": True,
        },
        "then": {
            "include_process_ids": ["process_nitriding"],
            "exclude_process_ids": [],
            "reason": "重复包含",
        },
    })
    package = RulePackageV2.model_validate(payload)

    report = validate_rule_package(package)

    assert "same_priority_action_conflict" in {issue.code for issue in report.errors}


def _relation(relation_type, source_ids, target_ids, *, source_match="any"):
    return {
        "relation_id": f"relation.{relation_type}",
        "relation_type": relation_type,
        "source_process_ids": source_ids,
        "target_process_ids": target_ids,
        "source_match": source_match,
        "enabled": True,
    }


def test_trigger_after_includes_target_and_orders_it_after_source(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    nitriding = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_nitriding")
    nitriding["constraints"]["conflicts_with"] = []
    payload["route_rules"]["process_relations"] = [
        _relation("trigger_after", ["process_quench"], ["process_nitriding"]),
    ]
    payload["test_cases"] = []
    package = RulePackageV2.model_validate(payload)

    plan = plan_route(package, {"material": {"grade": "9Cr18"}, "target_hardness_hrc": 58})

    assert "process_nitriding" in plan.selected_process_ids
    assert plan.selected_process_ids.index("process_quench") < plan.selected_process_ids.index("process_nitriding")


def test_order_after_only_constrains_selected_processes(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    mill_slot = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_mill_slot")
    mill_slot["constraints"]["must_run_before"] = []
    payload["route_rules"]["process_relations"] = [
        _relation("order_after", ["process_quench"], ["process_mill_slot"]),
    ]
    package = RulePackageV2.model_validate(payload)

    plan = plan_route(
        package,
        {"material": {"grade": "9Cr18"}, "cad": {"features": ["槽类特征"]}, "target_hardness_hrc": 58},
    )

    assert plan.selected_process_ids.index("process_quench") < plan.selected_process_ids.index("process_mill_slot")


def test_requires_adds_source_process_when_target_is_selected(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    nitriding = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_nitriding")
    nitriding["constraints"]["conflicts_with"] = []
    payload["route_rules"]["rules"].append(
        {
            "rule_id": "material.include.nitriding",
            "priority": 110,
            "when": {"field": "material.grade", "op": "eq", "value": "9Cr18"},
            "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
        },
    )
    payload["route_rules"]["process_relations"] = [
        _relation("requires", ["process_quench"], ["process_nitriding"]),
    ]
    package = RulePackageV2.model_validate(payload)

    plan = plan_route(package, {"material": {"grade": "9Cr18"}, "target_hardness_hrc": 40})

    assert "process_nitriding" in plan.selected_process_ids
    assert "process_quench" in plan.selected_process_ids
    assert plan.selected_process_ids.index("process_quench") < plan.selected_process_ids.index("process_nitriding")


def test_conflicts_stops_route_with_incompatible_processes(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    nitriding = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_nitriding")
    nitriding["constraints"]["conflicts_with"] = []
    payload["route_rules"]["rules"].append(
        {
            "rule_id": "material.include.nitriding",
            "priority": 110,
            "when": {"field": "material.grade", "op": "eq", "value": "9Cr18"},
            "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
        },
    )
    payload["route_rules"]["process_relations"] = [
        _relation("conflicts", ["process_quench"], ["process_nitriding"]),
    ]
    package = RulePackageV2.model_validate(payload)

    with pytest.raises(ValueError, match="不能同时进入路线"):
        plan_route(package, {"material": {"grade": "9Cr18"}, "target_hardness_hrc": 58})


def test_manual_boolean_false_overrides_mainline_and_trigger_inclusion(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    target = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_nitriding")
    target["main"] = True
    target["constraints"]["conflicts_with"] = []
    payload["input_schema"]["fields"].append({
        "key": "project_factor.manual_process_nitriding",
        "label": "是否需要渗氮",
        "type": "boolean",
        "required": False,
        "source": "用户直接设定",
        "options": [],
        "allow_custom": False,
    })
    payload["route_rules"]["rules"].append({
        # This is the exact identifier shape emitted by finalizeRulePackage.ts.
        "rule_id": "user.process_nitriding.manual.false",
        "priority": 2000,
        "source": "user_confirmed",
        "source_segment_id": "process_nitriding",
        "source_text": "当用户选择是否需要渗氮为否时，排除渗氮工序",
        "confirmed_by": "用户直接设定",
        "confirmed_at": "2026-07-28T10:00:00+00:00",
        "when": {"field": "project_factor.manual_process_nitriding", "op": "eq", "value": False},
        "then": {
            "include_process_ids": [],
            "exclude_process_ids": ["process_nitriding"],
            "reason": "用户选择否",
        },
    })
    payload["route_rules"]["process_relations"] = [
        _relation("trigger_after", ["process_quench"], ["process_nitriding"]),
    ]
    for case in payload["test_cases"]:
        case["input"]["project_factor"] = {"manual_process_nitriding": False}
    payload["test_cases"].append({
        "case_id": "manual-nitriding-false",
        "input": {
            "material": {"grade": "其他材料"},
            "cad": {"features": ["无槽"]},
            "target_hardness_hrc": 0,
            "project_factor": {"manual_process_nitriding": False},
        },
        "expect": {"included_process_ids": [], "excluded_process_ids": ["process_nitriding"]},
    })
    package = RulePackageV2.model_validate(payload)
    report = validate_rule_package(package)

    plan = plan_route(package, {
        "material": {"grade": "9Cr18"},
        "cad": {"features": []},
        "target_hardness_hrc": 58,
        "project_factor": {"manual_process_nitriding": False},
    })

    assert report.valid is True
    assert "process_nitriding" not in plan.selected_process_ids
