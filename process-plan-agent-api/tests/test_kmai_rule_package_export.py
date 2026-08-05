import hashlib
import json
import os
from copy import deepcopy
from unittest.mock import patch

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_export import (
    KMAI_MAX_COMBINATIONS_ENV,
    KMAI_MAX_CONDITION_OBJECTS_ENV,
    LegacyFactorAdapterEntry,
    StandardFactorExportError,
    build_kmai_compatibility_export,
)
from app.services.rule_packages.standard_factors import STANDARD_FACTOR_CATALOG_VERSION


def test_kmai_export_facade_preserves_condition_compatibility_symbols():
    assert KMAI_MAX_COMBINATIONS_ENV == "PROCESSMIND_KMAI_MAX_COMBINATIONS"
    assert KMAI_MAX_CONDITION_OBJECTS_ENV == "PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS"
    assert issubclass(StandardFactorExportError, ValueError)


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


def test_kmai_export_full_facade_characterization(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)
    payload = {
        "valid": exported.valid,
        "target_directory": exported.target_directory,
        "errors": [issue.model_dump(mode="json") for issue in exported.errors],
        "warnings": [issue.model_dump(mode="json") for issue in exported.warnings],
        "files": exported.files,
        "factor_catalog_version": exported.factor_catalog_version,
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert hashlib.sha256(serialized.encode("utf-8")).hexdigest() == (
        "d15479cd1a7e7ae8463c442b8240dc7252a7ead64f8166ac0e176c63b8244603"
    )


def test_kmai_export_preserves_fixed_factor_schema_metadata(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)

    factors = exported.files["factor_schema.json"]["factors"]
    assert [
        (
            factor["factor_id"],
            factor["factor_key"],
            factor["name"],
            factor["category"],
            factor["value_type"],
        )
        for factor in factors
        if factor["factor_id"].startswith("F0")
    ] == [
        ("F001", "material_grade", "\u6750\u6599\u724c\u53f7", "material", "enum"),
        ("F002", "part_type", "\u96f6\u4ef6\u7c7b\u578b", "part", "enum"),
        ("F003", "has_flat_or_plane", "\u6241\u4f4d/\u5e73\u9762", "feature", "boolean"),
        ("F004", "has_slot_feature", "\u69fd\u7c7b\u7279\u5f81", "feature", "boolean"),
        ("F005", "has_standard_or_aux_hole", "\u666e\u901a\u5b54/\u8f85\u52a9\u5b54", "feature", "boolean"),
        ("F005A", "has_center_through_hole", "\u4e2d\u95f4\u901a\u5b54", "feature", "boolean"),
        ("F006", "has_reamed_or_precision_hole", "\u94f0\u5b54/\u7cbe\u5b54", "feature", "boolean"),
        ("F007", "has_shaped_hole_or_cut_flat", "\u578b\u5b54/\u5272\u6241", "feature", "boolean"),
        ("F008", "has_post_stage_added_hole", "\u540e\u6bb5\u8865\u5145\u5b54", "feature", "boolean"),
        ("F009", "has_hole_finish_machining", "\u5b54\u7cbe\u52a0\u5de5", "precision", "boolean"),
        ("F010", "requires_honing", "\u73e9\u5b54\u8981\u6c42", "precision", "boolean"),
        ("F011", "requires_hole_lapping", "\u7814\u5b54\u8981\u6c42", "precision", "boolean"),
        ("F012", "requires_outer_diameter_grinding", "\u5916\u5706\u78e8\u524a", "precision", "boolean"),
        ("F013", "requires_end_face_grinding", "\u7aef\u9762\u78e8\u524a", "precision", "boolean"),
        ("F014", "requires_slot_grinding", "\u69fd\u78e8\u524a", "precision", "boolean"),
        ("F015", "requires_outer_diameter_lapping", "\u7814\u5916\u5706", "precision", "boolean"),
        ("F016", "uses_center_hole_location", "\u9876\u5c16\u5b54\u5b9a\u4f4d", "precision", "boolean"),
        ("F017", "needs_stress_relief", "\u53bb\u5e94\u529b", "heat_treatment", "boolean"),
        ("F018", "needs_quenching", "\u6dec\u706b", "heat_treatment", "boolean"),
        ("F019", "needs_vacuum_quenching", "\u771f\u7a7a\u6dec\u706b", "heat_treatment", "boolean"),
        ("F020", "has_nitrided_layer", "\u6e17\u6c2e\u5c42", "heat_treatment", "boolean"),
        ("F021", "needs_chromic_acid_anodizing", "\u94ec\u9178\u9633\u6781\u5316", "surface_treatment", "boolean"),
        ("F022", "needs_hard_anodizing", "\u786c\u8d28\u9633\u6781\u5316", "surface_treatment", "boolean"),
        ("F023", "needs_marking", "\u6807\u5370/\u6807\u523b", "inspection_marking", "boolean"),
        ("F024", "needs_crack_inspection", "\u88c2\u7eb9\u68c0\u6d4b", "inspection_marking", "boolean"),
        ("F025", "needs_burn_inspection", "\u70e7\u4f24\u68c0\u67e5", "inspection_marking", "boolean"),
        ("F026", "needs_ndt_inspection", "\u65e0\u635f\u68c0\u6d4b", "inspection_marking", "boolean"),
    ]


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
