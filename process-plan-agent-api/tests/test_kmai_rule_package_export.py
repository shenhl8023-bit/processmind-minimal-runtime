import os
from copy import deepcopy
from unittest.mock import patch

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_mapping_contracts import KmaiMappingSnapshot
from app.services.rule_packages.kmai_mapping_registry import (
    KmaiMappingRegistry,
    builtin_mapping_registry,
)


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
    builtin_registry = builtin_mapping_registry()
    assert exported.mapping_signature == builtin_registry.signature
    assert any(
        usage.mapping_identity
        == builtin_registry.resolve("cad.features", "槽类特征").mapping_identity
        for usage in exported.mapping_usages
    )


def test_kmai_export_preserves_template_group_aliases_as_optional_metadata(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    process = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_mill_slot")
    process["template_group_aliases"] = [{
        "source_operation_id": 100,
        "alias": "铣槽（A侧/外环槽）",
        "template_group_id": "3358f0f62d04abb99d35dec48ef73e1",
        "template_group_path": ["A侧", "外环槽"],
    }]

    exported = build_kmai_compatibility_export(RulePackageV2.model_validate(payload))

    kmai_process = next(
        item for item in exported.files["route_catalog.json"]["processes"]
        if item["process_key"] == "process_mill_slot"
    )
    assert kmai_process["process_name"] == "铣槽"
    assert kmai_process["template_group_aliases"] == process["template_group_aliases"]


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


def test_kmai_export_keeps_nondestructive_testing_as_manual_boolean_factor(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    rule_index = len(payload["route_rules"]["rules"])
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
    rule = next(rule for rule in exported.files["route_rules.json"]["rules"] if rule["rule_id"] == "special.ndt")
    factor_key = rule["when"]["all"][0]["factor_key"]
    assert factor_key.startswith("processmind_special_")
    factor = next(
        item for item in exported.files["factor_schema.json"]["factors"]
        if item["factor_key"] == factor_key
    )
    assert factor["source_mode"] == "manual_override"
    assert factor["name"] == "特殊要求：无损检测要求"
    assert any(
        issue.code == "kmai_manual_override_required"
        and issue.path == f"route_rules.rules[{rule_index}].when"
        and factor_key in issue.message
        for issue in exported.warnings
    )


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
def _expanded_rule(any_width: int, all_depth: int):
    return {
        "rule_id": "explosive.rule",
        "priority": 100,
        "enabled": True,
        "when": {
            "all": [
                {
                    "any": [
                        {"field": "target_hardness_hrc", "op": "eq", "value": value}
                        for value in range(any_width)
                    ]
                }
                for _ in range(all_depth)
            ]
        },
        "then": {
            "include_process_ids": ["process_quench"],
            "exclude_process_ids": [],
            "reason": "组合上限测试",
        },
    }


def test_kmai_export_rejects_cartesian_product_before_materializing(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"] = [_expanded_rule(any_width=10, all_depth=6)]
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(package, max_combinations=1_000)

    assert exported.valid is False
    assert exported.files["route_rules.json"]["rules"] == []
    issue = next(error for error in exported.errors if error.code == "kmai_combination_limit_exceeded")
    assert "1000000" in issue.message
    assert "1000" in issue.message


def test_kmai_export_expands_all_combinations_within_limit(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"] = [_expanded_rule(any_width=2, all_depth=2)]
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(
        package,
        max_combinations=4,
        max_condition_objects=8,
    )

    assert exported.valid is True
    rules = exported.files["route_rules.json"]["rules"]
    assert len(rules) == 4
    assert {rule["rule_id"] for rule in rules} == {
        "explosive.rule.1",
        "explosive.rule.2",
        "explosive.rule.3",
        "explosive.rule.4",
    }
    assert sum(len(rule["when"]["all"]) for rule in rules) == 8


def test_kmai_export_rejects_wide_all_any_condition_cost_before_materializing(
    rule_package_v2_payload,
):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"] = [_expanded_rule(any_width=3, all_depth=8)]
    package = RulePackageV2.model_validate(payload)

    with patch("app.services.rule_packages.kmai_export._condition_dnf") as condition_dnf:
        exported = build_kmai_compatibility_export(
            package,
            max_combinations=10_000,
            max_condition_objects=50_000,
        )

    condition_dnf.assert_not_called()
    assert exported.valid is False
    assert exported.files["route_rules.json"]["rules"] == []
    issue = next(
        error
        for error in exported.errors
        if error.code == "kmai_condition_object_limit_exceeded"
    )
    assert issue.path == "route_rules.rules[0].when"
    assert "52488" in issue.message
    assert "50000" in issue.message


def test_kmai_export_applies_condition_object_limit_across_rules(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    first_rule = _expanded_rule(any_width=2, all_depth=2)
    second_rule = _expanded_rule(any_width=2, all_depth=2)
    first_rule["rule_id"] = "expanded.first"
    second_rule["rule_id"] = "expanded.second"
    payload["route_rules"]["rules"] = [first_rule, second_rule]
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(
        package,
        max_combinations=8,
        max_condition_objects=15,
    )

    assert exported.valid is False
    rules = exported.files["route_rules.json"]["rules"]
    assert len(rules) == 4
    assert all(rule["rule_id"].startswith("expanded.first.") for rule in rules)
    issue = next(
        error
        for error in exported.errors
        if error.code == "kmai_condition_object_limit_exceeded"
    )
    assert "expanded.second" in issue.message
    assert "8" in issue.message
    assert "16" in issue.message
    assert "15" in issue.message


def test_kmai_export_reads_condition_object_limit_from_environment(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"] = [_expanded_rule(any_width=2, all_depth=3)]
    package = RulePackageV2.model_validate(payload)
    previous = os.environ.get("PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS")
    os.environ["PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS"] = "23"
    try:
        exported = build_kmai_compatibility_export(package, max_combinations=8)
    finally:
        if previous is None:
            os.environ.pop("PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS", None)
        else:
            os.environ["PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS"] = previous

    assert exported.valid is False
    issue = next(
        error
        for error in exported.errors
        if error.code == "kmai_condition_object_limit_exceeded"
    )
    assert "24" in issue.message
    assert "23" in issue.message


def test_kmai_export_reads_combination_limit_from_environment(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"] = [_expanded_rule(any_width=2, all_depth=2)]
    package = RulePackageV2.model_validate(payload)
    previous = os.environ.get("PROCESSMIND_KMAI_MAX_COMBINATIONS")
    os.environ["PROCESSMIND_KMAI_MAX_COMBINATIONS"] = "3"
    try:
        exported = build_kmai_compatibility_export(package)
    finally:
        if previous is None:
            os.environ.pop("PROCESSMIND_KMAI_MAX_COMBINATIONS", None)
        else:
            os.environ["PROCESSMIND_KMAI_MAX_COMBINATIONS"] = previous

    assert exported.valid is False
    issue = next(error for error in exported.errors if error.code == "kmai_combination_limit_exceeded")
    assert "4" in issue.message
    assert "3" in issue.message


def test_unmapped_cad_values_are_grouped_with_rule_refs(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "unmapped.cad.nested",
        "priority": 10,
        "enabled": True,
        "source": "user_confirmed",
        "when": {
            "all": [
                {"field": "cad.features", "op": "contains", "value": " unmapped   feature "},
                {
                    "any": [
                        {"field": "cad.features", "op": "contains", "value": "unmapped feature"},
                        {"field": "cad.features", "op": "contains", "value": "unmapped feature"},
                    ]
                },
            ]
        },
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
    })

    exported = build_kmai_compatibility_export(RulePackageV2.model_validate(payload))

    issue = next(error for error in exported.errors if error.code == "kmai_mapping_required")
    assert issue.field == "cad.features"
    assert issue.value == "unmapped feature"
    assert issue.occurrences == 3
    assert issue.rule_refs == ["unmapped.cad.nested"]
    assert issue.can_create_manual_factor is True
    assert not any(
        rule["rule_id"].startswith("unmapped.cad.nested")
        for rule in exported.files["route_rules.json"]["rules"]
    )


def test_unmapped_cad_value_inside_not_is_reported_as_mapping_required(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "unmapped.cad.not",
        "priority": 10,
        "enabled": True,
        "source": "user_confirmed",
        "when": {
            "not": {
                "field": "cad.features",
                "op": "contains",
                "value": "unknown under not",
            }
        },
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
    })

    exported = build_kmai_compatibility_export(RulePackageV2.model_validate(payload))

    issue = next(
        error
        for error in exported.errors
        if error.code == "kmai_mapping_required" and error.value == "unknown under not"
    )
    assert issue.field == "cad.features"
    assert issue.occurrences == 1
    assert issue.rule_refs == ["unmapped.cad.not"]


def test_unmapped_precision_skips_rule_before_special_fallback(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    rule_index = len(payload["route_rules"]["rules"])
    payload["route_rules"]["rules"].append({
        "rule_id": "unmapped.precision.with-special",
        "priority": 10,
        "enabled": True,
        "source": "user_confirmed",
        "when": {
            "all": [
                {
                    "field": "special.requirements",
                    "op": "contains",
                    "value": "special value in skipped rule",
                },
                {
                    "field": "precision.grades",
                    "op": "contains",
                    "value": "unmapped precision",
                },
            ]
        },
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
    })

    exported = build_kmai_compatibility_export(RulePackageV2.model_validate(payload))

    issue = next(
        error
        for error in exported.errors
        if error.code == "kmai_mapping_required" and error.value == "unmapped precision"
    )
    assert issue.field == "precision.grades"
    assert issue.rule_refs == ["unmapped.precision.with-special"]
    assert not any(
        factor["name"] == "特殊要求：special value in skipped rule"
        for factor in exported.files["factor_schema.json"]["factors"]
    )
    assert not any(
        warning.path.startswith(f"route_rules.rules[{rule_index}].when")
        for warning in exported.warnings
    )


def test_existing_mapping_replaces_builtin_lookup_and_records_usage(rule_package_v2_payload):
    registry = KmaiMappingRegistry([
        KmaiMappingSnapshot(
            mapping_id=7,
            mapping_identity="project:7",
            revision=3,
            scope="project",
            project_id=12,
            source_field="cad.features",
            source_value="\u69fd\u7c7b\u7279\u5f81",
            mapping_mode="existing_factor",
            target_factor_key="has_flat_or_plane",
            target_factor_name="Flat",
            target_factor_category="feature",
        )
    ])

    exported = build_kmai_compatibility_export(
        RulePackageV2.model_validate(rule_package_v2_payload),
        mapping_registry=registry,
    )

    slot_rule = next(rule for rule in exported.files["route_rules.json"]["rules"] if rule["rule_id"] == "feature.slot.mill")
    assert slot_rule["when"]["all"] == [{"factor_key": "has_flat_or_plane", "op": "=", "value": True}]
    assert exported.mapping_signature == registry.signature
    assert [type(usage).__name__ for usage in exported.mapping_usages] == [
        "KmaiMappingUsageSnapshot"
    ]
    assert [usage.model_dump(mode="json") for usage in exported.mapping_usages] == [
        registry.resolve("cad.features", "\u69fd\u7c7b\u7279\u5f81").model_dump(mode="json")
    ]


def test_existing_mapping_to_historical_enum_target_blocks_export(rule_package_v2_payload):
    registry = KmaiMappingRegistry([
        KmaiMappingSnapshot(
            mapping_id=17,
            mapping_identity="project:17",
            revision=4,
            scope="project",
            project_id=12,
            source_field="cad.features",
            source_value="\u69fd\u7c7b\u7279\u5f81",
            mapping_mode="existing_factor",
            target_factor_key="material_grade",
            target_factor_name="Material grade",
            target_factor_category="material",
        )
    ])

    exported = build_kmai_compatibility_export(
        RulePackageV2.model_validate(rule_package_v2_payload),
        mapping_registry=registry,
    )

    assert exported.valid is False
    issue = next(
        error
        for error in exported.errors
        if error.code == "kmai_mapping_factor_type_incompatible"
    )
    assert issue.field == "cad.features"
    assert issue.value == "\u69fd\u7c7b\u7279\u5f81"
    assert "material_grade" in issue.message
    assert not any(
        rule["rule_id"] == "feature.slot.mill"
        for rule in exported.files["route_rules.json"]["rules"]
    )


def test_kmai_export_accepts_mapping_registry_as_second_positional_argument(
    rule_package_v2,
):
    registry = builtin_mapping_registry()

    exported = build_kmai_compatibility_export(rule_package_v2, registry)

    assert exported.valid is True
    assert exported.mapping_signature == registry.signature


def test_manual_mapping_adds_boolean_factor_and_usage_snapshot(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "manual.feature",
        "priority": 10,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": "cad.features", "op": "contains", "value": "manual feature"},
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
    })
    snapshot = KmaiMappingSnapshot(
        mapping_id=8,
        mapping_identity="project:8",
        revision=1,
        scope="project",
        project_id=12,
        source_field="cad.features",
        source_value="manual feature",
        mapping_mode="manual_factor",
        target_factor_key="processmind_manual_abc123def456",
        target_factor_name="Manual feature",
        target_factor_category="custom",
    )

    exported = build_kmai_compatibility_export(
        RulePackageV2.model_validate(payload),
        mapping_registry=KmaiMappingRegistry([snapshot]),
    )

    factor = next(
        item
        for item in exported.files["factor_schema.json"]["factors"]
        if item["factor_key"] == "processmind_manual_abc123def456"
    )
    assert factor["value_type"] == "boolean"
    assert factor["source_mode"] == "manual_override"
    assert factor["category"] == "manual_override"
    rule = next(item for item in exported.files["route_rules.json"]["rules"] if item["rule_id"] == "manual.feature")
    assert rule["when"]["all"] == [
        {"factor_key": "processmind_manual_abc123def456", "op": "=", "value": True}
    ]
    assert [usage.model_dump(mode="json") for usage in exported.mapping_usages] == [
        snapshot.model_dump(mode="json")
    ]


def test_persisted_special_mapping_uses_snapshot_without_dynamic_fallback(
    rule_package_v2_payload,
):
    payload = deepcopy(rule_package_v2_payload)
    rule_index = len(payload["route_rules"]["rules"])
    payload["route_rules"]["rules"].append({
        "rule_id": "special.persisted",
        "priority": 10,
        "enabled": True,
        "source": "user_confirmed",
        "when": {
            "field": "special.requirements",
            "op": "contains",
            "value": "persisted special",
        },
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
    })
    snapshot = KmaiMappingSnapshot(
        mapping_id=9,
        mapping_identity="project:9",
        revision=2,
        scope="project",
        project_id=12,
        source_field="special.requirements",
        source_value="persisted special",
        mapping_mode="manual_factor",
        target_factor_key="processmind_manual_special123",
        target_factor_name="Persisted special",
        target_factor_category="custom",
    )

    exported = build_kmai_compatibility_export(
        RulePackageV2.model_validate(payload),
        mapping_registry=KmaiMappingRegistry([snapshot]),
    )

    rule = next(
        item
        for item in exported.files["route_rules.json"]["rules"]
        if item["rule_id"] == "special.persisted"
    )
    assert rule["when"]["all"] == [
        {"factor_key": "processmind_manual_special123", "op": "=", "value": True}
    ]
    factors = exported.files["factor_schema.json"]["factors"]
    assert sum(
        factor["factor_key"] == "processmind_manual_special123"
        for factor in factors
    ) == 1
    assert not any(
        factor["name"] == "特殊要求：persisted special"
        for factor in factors
    )
    assert not any(
        warning.path.startswith(f"route_rules.rules[{rule_index}].when")
        for warning in exported.warnings
    )
    assert [usage.model_dump(mode="json") for usage in exported.mapping_usages] == [
        snapshot.model_dump(mode="json")
    ]
