from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.expression_engine import evaluate_condition


def test_nested_condition_and_missing_field_trace():
    condition = ConditionNode.model_validate({
        "all": [
            {"field": "material.grade", "op": "eq", "value": "9Cr18"},
            {
                "any": [
                    {"field": "cad.features", "op": "contains", "value": "槽类特征"},
                    {"field": "roughness", "op": "lte", "value": 0.8}
                ]
            }
        ]
    })

    trace = evaluate_condition(
        condition,
        {"material": {"grade": "9cr18"}, "cad": {"features": ["槽类特征"]}},
    )

    assert trace.matched is True
    assert trace.children[1].children[1].reason == "missing_field:roughness"


def test_missing_field_only_matches_not_exists():
    exists = ConditionNode.model_validate({"field": "unknown", "op": "exists"})
    not_exists = ConditionNode.model_validate({"field": "unknown", "op": "not_exists"})

    assert evaluate_condition(exists, {}).matched is False
    assert evaluate_condition(not_exists, {}).matched is True


def test_not_does_not_turn_missing_field_into_match():
    condition = ConditionNode.model_validate({
        "not": {"field": "unknown", "op": "eq", "value": "x"}
    })

    trace = evaluate_condition(condition, {})

    assert trace.matched is False
    assert trace.reason == "nested condition used a missing field"
