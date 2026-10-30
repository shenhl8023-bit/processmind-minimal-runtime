import pytest

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


@pytest.mark.parametrize("op,wanted,expected", [
    ("eq", 9007199254740992, False),
    ("eq", 9007199254740992.0, False),
    ("neq", 9007199254740992, True),
    ("in", [9007199254740992], False),
])
def test_numeric_equality_tolerance_does_not_round_distinct_integer_inputs(op, wanted, expected):
    condition = ConditionNode.model_validate({"field": "quantity", "op": op, "value": wanted})
    assert evaluate_condition(condition, {"quantity": 9007199254740993}).matched is expected


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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 10 ** 1000])
def test_number_inputs_reject_non_finite_or_unrepresentable_values_without_overflow(value):
    schema = InputSchemaV2.model_validate({"fields": [{"key": "quantity", "label": "数量", "type": "number"}]})
    issues = validate_inputs(schema, {"quantity": value})
    assert len(issues) == 1
    assert issues[0].code == "input_number_not_finite"
    assert issues[0].field == "quantity"


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1" + "0" * 1000])
def test_simulation_api_returns_numeric_input_issue_instead_of_json_serialization_error(token):
    from fastapi.testclient import TestClient
    from app.main import app

    package_json = (
        '{"manifest":{"package_name":"numbers","project_id":1,"scope":{"key":"1"}},'
        '"input_schema":{"fields":[{"key":"quantity","label":"数量","type":"number"}]},'
        '"route_catalog":{"processes":[{"process_id":"base","display_name":"准备","main":true}]},'
        '"route_rules":{"rules":[]}}'
    )
    response = TestClient(app).post(
        "/api/extract/finalized-rule-packages/simulate",
        content=(f'{{"package":{package_json},"inputs":{{"quantity":{token}}}}}').encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["code"] == "input_number_not_finite"


@pytest.mark.parametrize("value", [-(10 ** 100), 0, 9007199254740993, 10 ** 100, 1e308])
def test_large_finite_number_inputs_keep_their_original_precision(value):
    schema = InputSchemaV2.model_validate({"fields": [{"key": "quantity", "label": "数量", "type": "number"}]})
    assert validate_inputs(schema, {"quantity": value}) == []
    canonical, issues = canonicalize_inputs(schema, {"quantity": value})
    assert issues == []
    assert canonical["quantity"] == value
    assert type(canonical["quantity"]) is type(value)
