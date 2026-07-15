from copy import deepcopy

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.validator import validate_rule_package


def test_valid_package_runs_embedded_cases(rule_package_v2):
    report = validate_rule_package(rule_package_v2)

    assert report.valid is True
    assert [result.passed for result in report.test_results] == [True]


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
