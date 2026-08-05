from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.kmai_export_conditions import (
    condition_dnf,
    condition_expansion_size,
)
from app.services.rule_packages.kmai_export_context import (
    FactorRegistry,
    KmaiExportContext,
)


def _material_grade_leaf(value: str) -> dict[str, str]:
    return {
        "field": "material.grade",
        "op": "eq",
        "value": value,
        "factor_id": "material.grade",
    }


def test_condition_translation_estimates_and_materializes_two_by_two_any_groups(
    rule_package_v2,
):
    node = ConditionNode.model_validate(
        {
            "all": [
                {"any": [_material_grade_leaf("45#"), _material_grade_leaf("20#")]},
                {"any": [_material_grade_leaf("A"), _material_grade_leaf("B")]},
            ]
        }
    )

    assert condition_expansion_size(node) == (4, 8)

    clauses = condition_dnf(
        rule_package_v2,
        node,
        FactorRegistry(),
        [],
        "route_rules.rules[0].when",
        None,
    )

    assert len(clauses) == 4
    assert all(len(clause) == 2 for clause in clauses)


def test_condition_translation_with_context_records_dynamic_factor_warning(
    rule_package_v2,
):
    from app.services.rule_packages.kmai_export_conditions import (
        condition_dnf_with_context,
    )

    context = KmaiExportContext.create(
        rule_package_v2,
        max_combinations=10,
        max_condition_objects=20,
    )
    node = ConditionNode.model_validate(
        {
            "field": "project_factor.manual_process_heat_treatment",
            "op": "eq",
            "value": True,
        }
    )

    clauses = condition_dnf_with_context(context, node, "route_rules.rules[0].when")

    assert clauses == [[
        {
            "factor_key": "project_factor_manual_process_heat_treatment",
            "op": "=",
            "value": True,
        }
    ]]
    assert [item["factor_key"] for item in context.registry.values()] == [
        "project_factor_manual_process_heat_treatment"
    ]
    assert [issue.code for issue in context.warnings] == [
        "kmai_manual_override_required"
    ]
