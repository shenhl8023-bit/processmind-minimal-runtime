from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_export_context import ConditionBudget, FactorRegistry
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

    result = build_route_rules(
        package,
        process_keys,
        FactorRegistry(),
        ConditionBudget(10_000, 100_000),
        None,
        condition_dnf_fn=lambda *_args: [[]],
        condition_expansion_size_fn=lambda _node: (1, 1),
    )

    assert result.payload["rules"] == []
    assert result.errors[0].code == "kmai_process_reference_missing"
