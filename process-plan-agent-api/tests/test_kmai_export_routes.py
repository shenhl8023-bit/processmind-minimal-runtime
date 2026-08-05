from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_export_context import KmaiExportContext
from app.services.rule_packages.kmai_export_routes import (
    build_route_catalog,
    build_route_rules,
)


def test_build_route_catalog_matches_facade_artifact(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)

    route_catalog, process_keys = build_route_catalog(rule_package_v2)

    assert route_catalog == exported.files["route_catalog.json"]
    assert process_keys == {
        process.process_id: process.process_id
        for process in rule_package_v2.route_catalog.processes
    }


def test_build_route_rules_reports_missing_process_reference(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.rules[0].then.include_process_ids.append("missing-process")
    package.route_rules.rules = [package.route_rules.rules[0]]
    _, process_keys = build_route_catalog(package)
    context = KmaiExportContext.create(
        package,
        max_combinations=10_000,
        max_condition_objects=100_000,
    )

    result = build_route_rules(
        context,
        process_keys,
        condition_dnf_fn=lambda *_args: [[]],
        condition_expansion_size_fn=lambda _node: (1, 1),
    )

    assert result.payload["rules"] == []
    assert result.errors[0].code == "kmai_process_reference_missing"


def test_route_rules_rejects_over_budget_before_materializing(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.rules = [package.route_rules.rules[0]]
    _, process_keys = build_route_catalog(package)
    context = KmaiExportContext.create(
        package,
        max_combinations=1,
        max_condition_objects=100,
    )
    calls = []

    def materialize(*_args):
        calls.append(True)
        raise AssertionError("condition materialization must not run")

    result = build_route_rules(
        context,
        process_keys,
        condition_dnf_fn=materialize,
        condition_expansion_size_fn=lambda _node: (2, 2),
    )

    assert calls == []
    assert context.registry.values() == []
    assert result.errors[0].code == "kmai_combination_limit_exceeded"


def test_route_rules_skips_condition_materialization_for_missing_process_reference(
    rule_package_v2,
):
    package = rule_package_v2.model_copy(deep=True)
    invalid_rule = package.route_rules.rules[0]
    invalid_rule.then.include_process_ids.append("missing-process")
    valid_rule = package.route_rules.rules[1]
    package.route_rules.rules = [invalid_rule, valid_rule]
    _, process_keys = build_route_catalog(package)
    context = KmaiExportContext.create(
        package,
        max_combinations=10_000,
        max_condition_objects=100_000,
    )
    calls = []

    def materialize(*_args):
        calls.append(True)
        return [[{"factor_key": "material_grade", "op": "=", "value": "A"}]]

    result = build_route_rules(
        context,
        process_keys,
        condition_dnf_fn=materialize,
        condition_expansion_size_fn=lambda _node: (1, 1),
    )

    assert len(calls) == 1
    assert result.errors[0].code == "kmai_process_reference_missing"
    assert [rule["rule_id"] for rule in result.payload["rules"]] == [valid_rule.rule_id]
    assert context.budget.generated_combinations == 1
    assert context.budget.generated_condition_objects == 1
