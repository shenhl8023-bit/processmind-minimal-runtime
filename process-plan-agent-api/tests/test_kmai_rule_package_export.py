import os
from copy import deepcopy
from unittest.mock import patch

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_export import (
    LegacyFactorAdapterEntry,
    build_kmai_compatibility_export,
)
from app.services.rule_packages.standard_factors import STANDARD_FACTOR_CATALOG_VERSION


def test_fixed_export_uses_bound_factor_id_not_source_value_mapping(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    rule = next(rule for rule in package.route_rules.rules if rule.rule_id == "feature.slot.mill")
    rule.when.field = "precision.grades"
    rule.when.op = "contains"
    rule.when.value = "\u5b54\u7cbe\u52a0\u5de5"
    rule.when.factor_id = "precision.hole_finish"

    exported = build_kmai_compatibility_export(package)

    condition = next(
        item for item in exported.files["route_rules.json"]["rules"]
        if item["rule_id"] == "feature.slot.mill"
    )["when"]["all"][0]
    assert condition == {
        "factor_key": "has_hole_finish_machining",
        "op": "=",
        "value": True,
    }
    assert exported.factor_catalog_version == STANDARD_FACTOR_CATALOG_VERSION


def test_unbound_or_mismatched_leaf_is_blocked_without_mapping(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    rule = next(rule for rule in package.route_rules.rules if rule.rule_id == "feature.slot.mill")
    rule.when.field = "precision.grades"
    rule.when.op = "contains"
    rule.when.value = "\u5b54\u7cbe\u52a0\u5de5"
    rule.when.factor_id = None

    unbound = build_kmai_compatibility_export(package)

    assert unbound.valid is False
    assert [issue.code for issue in unbound.errors] == ["standard_factor_unbound"]
    assert all(issue.code != "kmai_mapping_required" for issue in unbound.errors)

    rule.when.factor_id = "feature.center_hole_location"
    mismatched = build_kmai_compatibility_export(package)
    assert mismatched.valid is False
    assert [issue.code for issue in mismatched.errors] == ["standard_factor_mismatch"]


def test_manual_process_boolean_exports_as_manual_override(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    field_key = "project_factor.manual_process_0123456789ab"
    payload["input_schema"]["fields"].append({
        "key": field_key,
        "label": "manual process",
        "type": "boolean",
        "required": False,
        "source": "user",
        "options": [],
        "allow_custom": False,
    })
    payload["route_rules"]["rules"].append({
        "rule_id": "manual.process",
        "priority": 1000,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": field_key, "op": "eq", "value": True},
        "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
    })

    exported = build_kmai_compatibility_export(RulePackageV2.model_validate(payload))

    assert exported.valid is True
    rule = next(item for item in exported.files["route_rules.json"]["rules"] if item["rule_id"] == "manual.process")
    factor_key = "project_factor_manual_process_0123456789ab"
    assert rule["when"]["all"] == [{"factor_key": factor_key, "op": "=", "value": True}]
    factor = next(item for item in exported.files["factor_schema.json"]["factors"] if item["factor_key"] == factor_key)
    assert factor["value_type"] == "boolean"
    assert factor["source_mode"] == "manual_override"
    assert any(issue.code == "kmai_manual_override_required" and factor_key in issue.message for issue in exported.warnings)


def test_historical_unbound_leaf_uses_only_explicit_snapshot(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "legacy.manual",
        "priority": 10,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": "cad.features", "op": "contains", "value": "legacy feature"},
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
    })
    snapshot = LegacyFactorAdapterEntry(
        source_field="cad.features",
        source_value="legacy feature",
        mapping_mode="manual_factor",
        target_factor_key="processmind_manual_abc123def456",
        target_factor_name="Legacy feature",
        target_factor_category="custom",
    )

    exported = build_kmai_compatibility_export(
        RulePackageV2.model_validate(payload),
        legacy_mapping_snapshot=[snapshot],
    )

    assert exported.valid is True
    rule = next(item for item in exported.files["route_rules.json"]["rules"] if item["rule_id"] == "legacy.manual")
    assert rule["when"]["all"] == [{
        "factor_key": "processmind_manual_abc123def456",
        "op": "=",
        "value": True,
    }]
    factor = next(item for item in exported.files["factor_schema.json"]["factors"] if item["factor_key"] == "processmind_manual_abc123def456")
    assert factor["name"] == "Legacy feature"
    assert factor["category"] == "custom"
    assert factor["source_mode"] == "manual_override"
def test_kmai_export_has_drop_in_runtime_contract(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)

    assert exported.valid is True
    assert set(exported.files) == {
        "factor_schema.json",
        "factor_expansion_rules.json",
        "route_catalog.json",
        "route_rules.json",
    }
    rules = exported.files["route_rules.json"]["rules"]
    material_rule = next(rule for rule in rules if rule["rule_id"] == "material.9cr18.quench")
    assert material_rule["when"]["all"][0] == {
        "factor_key": "material_grade",
        "op": "in",
        "value": ["9Cr18", "95Cr18"],
    }
    slot_rule = next(rule for rule in rules if rule["rule_id"] == "feature.slot.mill")
    assert slot_rule["when"]["all"] == [{"factor_key": "has_slot_feature", "op": "=", "value": True}]
    assert any(item["factor_key"] == "has_center_through_hole" for item in exported.files["factor_schema.json"]["factors"])


def test_kmai_export_preserves_template_group_aliases_as_optional_metadata(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    process = next(item for item in payload["route_catalog"]["processes"] if item["process_id"] == "process_mill_slot")
    process["template_group_aliases"] = [{
        "source_operation_id": 100,
        "alias": "\u94e3\u69fd (A side)",
        "template_group_id": "3358f0f62d04abb99d35dec48ef73e1",
        "template_group_path": ["A side", "outer groove"],
    }]

    exported = build_kmai_compatibility_export(RulePackageV2.model_validate(payload))

    kmai_process = next(
        item for item in exported.files["route_catalog.json"]["processes"]
        if item["process_key"] == "process_mill_slot"
    )
    assert kmai_process["template_group_aliases"] == process["template_group_aliases"]


def test_kmai_export_rejects_not_condition(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"][0]["when"] = {
        "not": {"field": "material.grade", "op": "eq", "value": "9Cr18"}
    }

    exported = build_kmai_compatibility_export(RulePackageV2.model_validate(payload))

    assert exported.valid is False
    assert exported.errors[0].code == "kmai_condition_unsupported"


def _expanded_rule(any_width: int, all_depth: int):
    return {
        "rule_id": "explosive.rule",
        "priority": 100,
        "enabled": True,
        "when": {
            "all": [
                {"any": [
                    {
                        "field": "target_hardness_hrc",
                        "op": "eq",
                        "value": value,
                        "factor_id": "measurement.hardness_hrc",
                    }
                    for value in range(any_width)
                ]}
                for _ in range(all_depth)
            ]
        },
        "then": {"include_process_ids": ["process_quench"], "exclude_process_ids": []},
    }


def test_kmai_export_preserves_dnf_limits(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"] = [_expanded_rule(any_width=2, all_depth=2)]
    package = RulePackageV2.model_validate(payload)

    exported = build_kmai_compatibility_export(package, max_combinations=4, max_condition_objects=8)

    assert exported.valid is True
    assert len(exported.files["route_rules.json"]["rules"]) == 4


def test_kmai_export_applies_condition_object_limit_across_rules(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    first_rule = _expanded_rule(any_width=2, all_depth=2)
    second_rule = _expanded_rule(any_width=2, all_depth=2)
    first_rule["rule_id"] = "expanded.first"
    second_rule["rule_id"] = "expanded.second"
    payload["route_rules"]["rules"] = [first_rule, second_rule]

    exported = build_kmai_compatibility_export(
        RulePackageV2.model_validate(payload),
        max_combinations=8,
        max_condition_objects=15,
    )

    assert exported.valid is False
    rules = exported.files["route_rules.json"]["rules"]
    assert len(rules) == 4
    assert all(rule["rule_id"].startswith("expanded.first.") for rule in rules)
    issue = next(error for error in exported.errors if error.code == "kmai_condition_object_limit_exceeded")
    assert "expanded.second" in issue.message
    assert "16" in issue.message


def test_kmai_export_rejects_dnf_before_materializing(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"] = [_expanded_rule(any_width=10, all_depth=6)]
    package = RulePackageV2.model_validate(payload)

    with patch("app.services.rule_packages.kmai_export._condition_dnf") as condition_dnf:
        exported = build_kmai_compatibility_export(package, max_combinations=1_000)

    condition_dnf.assert_not_called()
    assert exported.valid is False
    assert [issue.code for issue in exported.errors] == ["kmai_combination_limit_exceeded"]


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
    assert [issue.code for issue in exported.errors] == ["kmai_combination_limit_exceeded"]
