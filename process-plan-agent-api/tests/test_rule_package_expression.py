from app.services.rule_packages.contracts import ConditionNode, InputSchemaV2
from app.services.rule_packages.expression_engine import evaluate_condition
from app.services.rule_packages.input_validation import canonicalize_inputs, validate_inputs


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


def _canonical_input_schema():
    return InputSchemaV2.model_validate({
        "fields": [
            {
                "key": "material.grade",
                "label": "材料牌号",
                "type": "single_select",
                "options": [{
                    "value": "W6Mo5Cr4V2",
                    "label": "W6Mo5Cr4V2",
                    "aliases": ["M2"],
                }],
                "allow_custom": False,
            },
            {
                "key": "tolerance.roundness_mm",
                "label": "圆度公差",
                "type": "number",
                "unit": "mm",
            },
        ],
    })


def test_canonicalizes_closed_option_aliases_before_planning():
    values, errors = canonicalize_inputs(
        _canonical_input_schema(),
        {"material": {"grade": "M2"}},
    )

    assert errors == []
    assert values == {"material": {"grade": "W6Mo5Cr4V2"}}


def test_rejects_unknown_nested_input_factor():
    errors = validate_inputs(
        _canonical_input_schema(),
        {
            "material": {"grade": "W6Mo5Cr4V2"},
            "geometry": {"diameter_mm": 12},
        },
    )

    assert any(issue.code == "unknown_input_field" and issue.field == "geometry.diameter_mm" for issue in errors)
