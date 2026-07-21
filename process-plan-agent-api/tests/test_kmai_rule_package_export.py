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
