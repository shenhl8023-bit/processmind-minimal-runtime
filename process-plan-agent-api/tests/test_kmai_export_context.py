from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_export_context import (
    ConditionBudget,
    FactorRegistry,
    KmaiExportContext,
)


def test_export_context_keeps_issue_and_factor_state_per_export(
    rule_package_v2: RulePackageV2,
):
    first = KmaiExportContext.create(
        rule_package_v2,
        max_combinations=10,
        max_condition_objects=20,
    )
    second = KmaiExportContext.create(
        rule_package_v2,
        max_combinations=10,
        max_condition_objects=20,
    )

    first.warning("first_warning", "only first")
    first.registry.register("first_factor", {"factor_key": "first_factor"})

    assert [issue.code for issue in second.warnings] == []
    assert second.registry.values() == []


def test_factor_registry_keeps_first_payload_and_registration_order():
    registry = FactorRegistry()
    first = {"factor_key": "first"}
    replacement = {"factor_key": "replacement"}
    second = {"factor_key": "second"}

    assert registry.register("first", first) is first
    assert registry.register("first", replacement) is first
    registry.register("second", second)

    assert len(registry) == 2
    assert "first" in registry
    assert registry.get("first") is first
    assert registry.values() == [first, second]


def test_condition_budget_projects_without_mutating_and_records_materialized_clauses():
    budget = ConditionBudget(max_combinations=10, max_condition_objects=20)

    assert budget.project(4, 8) == (4, 8)
    assert budget.generated_combinations == 0
    assert budget.generated_condition_objects == 0

    budget.record(
        [
            [{"factor_key": "one"}],
            [{"factor_key": "two"}, {"factor_key": "three"}],
        ]
    )

    assert budget.project(1, 1) == (3, 4)
