import json
from copy import deepcopy

import pytest

from app.schemas.schemas import RouteStep
from app.services.generate_route_result_builder import build_generate_output_json
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages import validator as rule_package_validator
from app.services.rule_packages.validator import validate_rule_package


def test_valid_package_runs_embedded_cases(rule_package_v2):
    report = validate_rule_package(rule_package_v2)

    assert report.valid is True
    assert [result.passed for result in report.test_results] == [True]


def test_historical_package_without_factor_ids_still_deserializes(rule_package_v2_payload):
    """Binding enforcement belongs to new compile/save boundaries, not historical reads."""
    historical = deepcopy(rule_package_v2_payload)
    historical["route_rules"]["rules"][0]["when"]["all"][0].pop("factor_id", None)
    historical["route_rules"]["rules"][0]["when"]["all"][1].pop("factor_id", None)
    historical["route_rules"]["rules"][1]["when"].pop("factor_id", None)

    package = RulePackageV2.model_validate(historical)

    assert package.manifest.schema_version == "2.0"


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
    payload["test_cases"] = []
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


_MANUAL_PROCESS_CASES = [
    ("process_quench", "淬火"),
    ("process_nitriding", "渗氮"),
    ("process_ndt", "无损检查"),
    ("process_deburr", "去毛刺"),
]


def _manual_process_field_key(process_id: str) -> str:
    hash_value = 0x811C9DC5
    for character in process_id:
        hash_value ^= ord(character)
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    return f"project_factor.manual_process_{hash_value:08x}"


def _manual_pair_payload(rule_package_v2_payload, process_id: str, label: str = "手工工序"):
    payload = deepcopy(rule_package_v2_payload)
    payload["test_cases"] = []
    if not any(item["process_id"] == process_id for item in payload["route_catalog"]["processes"]):
        payload["route_catalog"]["processes"].append({
            "process_id": process_id,
            "process_code": process_id.removeprefix("process_").upper(),
            "display_name": label,
            "phase": "manual",
            "default_sequence": 500,
            "main": False,
            "steps": [],
            "constraints": {
                "requires": [],
                "must_run_after": [],
                "must_run_before": [],
                "conflicts_with": [],
            },
        })

    manual_field = _manual_process_field_key(process_id)
    payload["input_schema"]["fields"].append({
        "key": manual_field,
        "label": f"是否需要{label}",
        "type": "boolean",
        "required": False,
        "source": "用户直接设定",
        "options": [],
        "allow_custom": False,
    })
    audit = {
        "priority": 2000,
        "enabled": True,
        "source": "user_confirmed",
        "source_segment_id": process_id,
        "source_text": f"用户确认是否需要{label}",
        "confirmed_by": "用户直接设定",
        "confirmed_at": "2026-07-30T10:00:00+00:00",
    }
    payload["route_rules"]["rules"].extend([
        {
            **audit,
            "rule_id": f"user.{process_id}.manual.true",
            "when": {"field": manual_field, "op": "eq", "value": True},
            "then": {
                "include_process_ids": [process_id],
                "exclude_process_ids": [],
                "reason": f"用户选择需要{label}",
            },
        },
        {
            **audit,
            "rule_id": f"user.{process_id}.manual.false",
            "when": {"field": manual_field, "op": "eq", "value": False},
            "then": {
                "include_process_ids": [],
                "exclude_process_ids": [process_id],
                "reason": f"用户选择不需要{label}",
            },
        },
    ])
    return payload, manual_field


@pytest.mark.parametrize(("process_id", "label"), _MANUAL_PROCESS_CASES)
def test_confirmed_manual_true_false_pair_is_not_a_conflict(
    rule_package_v2_payload,
    process_id,
    label,
):
    payload, manual_field = _manual_pair_payload(rule_package_v2_payload, process_id, label)
    package = RulePackageV2.model_validate(payload)

    report = validate_rule_package(package)
    yes_plan = plan_route(package, {"project_factor": {manual_field.removeprefix("project_factor."): True}})
    no_plan = plan_route(package, {"project_factor": {manual_field.removeprefix("project_factor."): False}})

    assert "same_priority_action_conflict" not in [issue.code for issue in report.errors]
    assert process_id in yes_plan.selected_process_ids
    assert process_id not in no_plan.selected_process_ids


def _mutate_manual_pair_boundary(payload, boundary: str, process_id: str, manual_field: str):
    include_rule, exclude_rule = payload["route_rules"]["rules"][-2:]
    if boundary == "field":
        other_field = f"{manual_field}_other"
        payload["input_schema"]["fields"].append({
            **payload["input_schema"]["fields"][-1],
            "key": other_field,
        })
        exclude_rule["when"]["field"] = other_field
    elif boundary == "field_type":
        payload["input_schema"]["fields"][-1]["type"] = "string"
    elif boundary == "field_source":
        payload["input_schema"]["fields"][-1]["source"] = "CAD"
    elif boundary == "field_prefix":
        other_field = manual_field.replace("manual_process_", "optional_process_", 1)
        payload["input_schema"]["fields"][-1]["key"] = other_field
        include_rule["when"]["field"] = other_field
        exclude_rule["when"]["field"] = other_field
    elif boundary == "source_segment":
        exclude_rule["source_segment_id"] = "process_other_segment"
    elif boundary == "priority":
        exclude_rule["priority"] = include_rule["priority"] - 1
    elif boundary == "target_process":
        include_rule["then"]["include_process_ids"].append("process_rough_machine")
    elif boundary == "source":
        exclude_rule["source"] = "system_static"
    elif boundary == "compound_true":
        include_rule["when"] = {
            "all": [
                include_rule["when"],
                {"field": "material.grade", "op": "eq", "value": "9Cr18"},
            ],
        }
    elif boundary == "any_true":
        include_rule["when"] = {
            "any": [
                include_rule["when"],
                {"field": "material.grade", "op": "eq", "value": "9Cr18"},
            ],
        }
    elif boundary == "not_true":
        include_rule["when"] = {
            "not": {"field": manual_field, "op": "eq", "value": False},
        }
    elif boundary == "false_operator":
        exclude_rule["when"] = {"field": manual_field, "op": "neq", "value": True}
    elif boundary == "factor_id":
        include_rule["when"]["factor_id"] = "manual.factor.must_not_exist"
    elif boundary == "actions":
        exclude_rule["then"]["include_process_ids"] = ["process_rough_machine"]
    elif boundary == "extra_rule":
        extra_rule = deepcopy(include_rule)
        extra_rule["rule_id"] = f"{include_rule['rule_id']}.extra"
        payload["route_rules"]["rules"].append(extra_rule)
    else:
        raise AssertionError(f"unknown boundary: {boundary}")


@pytest.mark.parametrize(
    "boundary",
    [
        "field",
        "field_type",
        "field_source",
        "field_prefix",
        "source_segment",
        "target_process",
        "source",
        "compound_true",
        "any_true",
        "not_true",
        "false_operator",
        "factor_id",
        "actions",
        "extra_rule",
    ],
)
def test_non_exact_manual_pair_still_reports_same_priority_conflict(
    rule_package_v2_payload,
    boundary,
):
    process_id = "process_nitriding"
    payload, manual_field = _manual_pair_payload(rule_package_v2_payload, process_id, "渗氮")
    _mutate_manual_pair_boundary(payload, boundary, process_id, manual_field)

    report = validate_rule_package(RulePackageV2.model_validate(payload))
    conflicts = [issue for issue in report.errors if issue.code == "same_priority_action_conflict"]

    assert conflicts
    assert any(process_id in issue.message for issue in conflicts)


@pytest.mark.parametrize(
    "boundary",
    [
        "field",
        "field_type",
        "field_source",
        "field_prefix",
        "source_segment",
        "priority",
        "target_process",
        "source",
        "compound_true",
        "any_true",
        "not_true",
        "false_operator",
        "factor_id",
        "actions",
    ],
)
def test_manual_pair_predicate_rejects_every_non_exact_boundary(
    rule_package_v2_payload,
    boundary,
):
    process_id = "process_nitriding"
    payload, manual_field = _manual_pair_payload(rule_package_v2_payload, process_id, "渗氮")
    _mutate_manual_pair_boundary(payload, boundary, process_id, manual_field)
    package = RulePackageV2.model_validate(payload)
    include_rule, exclude_rule = package.route_rules.rules[-2:]
    predicate = getattr(rule_package_validator, "_is_mutually_exclusive_manual_pair", None)
    manual_field_keys = {
        field.key
        for field in package.input_schema.fields
        if (
            field.type == "boolean"
            and field.source == "用户直接设定"
            and field.key.startswith("project_factor.manual_process_")
        )
    }

    assert predicate is not None
    assert predicate(include_rule, exclude_rule, process_id, manual_field_keys) is False
