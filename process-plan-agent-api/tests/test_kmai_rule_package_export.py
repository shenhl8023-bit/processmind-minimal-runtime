from copy import deepcopy

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export


def test_kmai_export_has_drop_in_runtime_contract(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)

    assert exported.valid is True
    assert set(exported.files) == {
        "factor_schema.json",
        "factor_expansion_rules.json",
        "route_catalog.json",
        "route_rules.json",
    }

    catalog = exported.files["route_catalog.json"]
    process_keys = {process["process_key"] for process in catalog["processes"]}
    assert "process_prepare" in process_keys
    assert next(process for process in catalog["processes"] if process["process_key"] == "process_prepare")[
        "default_included"
    ] is True

    rules = exported.files["route_rules.json"]["rules"]
    material_rule = next(rule for rule in rules if rule["rule_id"] == "material.9cr18.quench")
    assert material_rule["when"]["all"][0] == {
        "factor_key": "material_grade",
        "op": "in",
        "value": ["9Cr18", "95Cr18"],
    }
    assert material_rule["then"]["include_process_keys"] == ["process_quench"]

    slot_rule = next(rule for rule in rules if rule["rule_id"] == "feature.slot.mill")
    assert slot_rule["when"]["all"] == [
        {"factor_key": "has_slot_feature", "op": "=", "value": True}
    ]

    factors = exported.files["factor_schema.json"]["factors"]
    factor_keys = {factor["factor_key"] for factor in factors}
    assert {"material_grade", "has_slot_feature", "target_hardness_hrc"} <= factor_keys
    assert any(issue.code == "kmai_manual_override_required" for issue in exported.warnings)


def test_kmai_export_rejects_not_condition(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"][0]["when"] = {
        "not": {"field": "material.grade", "op": "eq", "value": "9Cr18"}
    }
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(package)

    assert exported.valid is False
    assert exported.errors[0].code == "kmai_condition_unsupported"


def test_kmai_export_preserves_trigger_after_relation(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["process_relations"] = [{
        "relation_id": "relation.quench.inspect",
        "relation_type": "trigger_after",
        "source_process_ids": ["process_quench"],
        "target_process_ids": ["process_nitriding"],
        "enabled": True,
    }]
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(package)

    catalog = exported.files["route_catalog.json"]
    assert catalog["process_relations"][0]["relation_type"] == "trigger_after"
    assert catalog["post_stage_bundles"] == [{
        "bundle_id": "relation.quench.inspect",
        "trigger_mode": "any",
        "trigger_process_keys": ["process_quench"],
        "include_process_keys": ["process_nitriding"],
        "must_run_after_process_keys": ["process_quench"],
        "enabled": True,
        "note": "",
    }]


def test_kmai_export_keeps_custom_special_requirement_as_manual_boolean_factor(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["input_schema"]["fields"].append({
        "key": "special.requirements",
        "label": "特殊要求",
        "type": "multi_select",
        "required": False,
        "source": "人工补充/图样技术要求",
        "options": [{"value": "镀铜要求", "label": "镀铜要求"}],
        "allow_custom": True,
    })
    payload["route_rules"]["rules"].append({
        "rule_id": "user.copper",
        "priority": 1000,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": "special.requirements", "op": "contains", "value": "镀铜要求"},
        "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
    })
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(package)

    assert exported.valid is True
    dynamic_factor = next(
        factor for factor in exported.files["factor_schema.json"]["factors"]
        if factor["name"] == "特殊要求：镀铜要求"
    )
    assert dynamic_factor["value_type"] == "boolean"
    assert dynamic_factor["source_mode"] == "manual_override"
    rule = next(rule for rule in exported.files["route_rules.json"]["rules"] if rule["rule_id"] == "user.copper")
    assert rule["when"]["all"] == [{"factor_key": dynamic_factor["factor_key"], "op": "=", "value": True}]


def test_kmai_export_maps_nondestructive_testing_to_its_fixed_factor(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "special.ndt",
        "priority": 70,
        "enabled": True,
        "source": "system_static",
        "when": {"field": "special.requirements", "op": "contains", "value": "无损检测要求"},
        "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
    })
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(package)

    assert exported.valid is True
    assert any(
        factor["factor_key"] == "needs_ndt_inspection"
        for factor in exported.files["factor_schema.json"]["factors"]
    )
    rule = next(rule for rule in exported.files["route_rules.json"]["rules"] if rule["rule_id"] == "special.ndt")
    assert rule["when"]["all"] == [{"factor_key": "needs_ndt_inspection", "op": "=", "value": True}]


def test_kmai_export_keeps_project_categorical_factor_as_manual_enum(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    field_key = "project_factor.0123456789ab"
    payload["input_schema"]["fields"].append({
        "key": field_key,
        "label": "材料类别",
        "type": "single_select",
        "required": False,
        "source": "用户条件",
        "options": [
            {"value": "不锈钢", "label": "不锈钢"},
            {"value": "高温合金", "label": "高温合金"},
        ],
        "allow_custom": True,
    })
    payload["route_rules"]["rules"].append({
        "rule_id": "user.material-category.nitriding",
        "priority": 1000,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": field_key, "op": "eq", "value": "不锈钢"},
        "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
    })
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(package)

    assert exported.valid is True
    factor = next(
        item for item in exported.files["factor_schema.json"]["factors"]
        if item["name"] == "材料类别"
    )
    assert factor["value_type"] == "enum"
    assert factor["options"] == ["不锈钢", "高温合金"]
    assert factor["source_mode"] == "manual_override"
    rule = next(
        item for item in exported.files["route_rules.json"]["rules"]
        if item["rule_id"] == "user.material-category.nitriding"
    )
    assert rule["when"]["all"] == [{
        "factor_key": factor["factor_key"],
        "op": "=",
        "value": "不锈钢",
    }]
