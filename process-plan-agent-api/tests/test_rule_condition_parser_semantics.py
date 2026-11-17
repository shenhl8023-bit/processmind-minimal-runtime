"""Regressions for authored conditions retaining their complete meaning."""

import json

import pytest

from app.services.rule_packages import condition_parser
from app.services.rule_packages.condition_contracts import RuleConditionProcessOption
from app.services.rule_packages.expression_engine import evaluate_condition


PROCESSES = [
    RuleConditionProcessOption(process_id="copper", display_name="镀铜"),
    RuleConditionProcessOption(process_id="quench", display_name="淬火"),
    RuleConditionProcessOption(process_id="strip", display_name="除铜"),
]


@pytest.fixture(autouse=True)
def no_external_model(monkeypatch):
    async def unavailable_model(*args, **kwargs):
        return ""

    monkeypatch.setattr(condition_parser, "call_llm", unavailable_model)


async def parse(clause):
    return await condition_parser.parse_rule_condition(clause, "strip", "除铜", PROCESSES)


@pytest.mark.asyncio
@pytest.mark.parametrize("comparison", ["不大于", "不超过", "小于等于", "<=", "≤"])
@pytest.mark.parametrize("label,path,limit,values", [
    ("硬度", ("mechanical", "hardness_hrc"), "HRC58", [50, 58, 60]),
    ("圆柱度", ("tolerance", "cylindricity_mm"), "0.01", [0.005, 0.01, 0.02]),
    ("粗糙度", ("surface", "roughness_ra"), "Ra0.8", [0.4, 0.8, 1.6]),
])
async def test_upper_bounds_include_equality_without_reversing_direction(comparison, label, path, limit, values):
    candidate, _, issues = await parse("当{}{}{}时，纳入除铜工序".format(label, comparison, limit))
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {path[0]: {path[1]: value}}).matched for value in values] == [True, True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("comparison,expected", [
    ("不低于", [False, True, True]), ("不少于", [False, True, True]),
    ("大于等于", [False, True, True]), (">=", [False, True, True]),
    ("大于", [False, False, True]), ("小于", [True, False, False]),
])
async def test_lower_bounds_and_strict_bounds_preserve_equality(comparison, expected):
    candidate, _, issues = await parse("当硬度{}HRC58时，纳入除铜工序".format(comparison))
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"mechanical": {"hardness_hrc": value}}).matched for value in [50, 58, 60]] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("comparison,expected", [
    ("不低于", [True, True, False]), ("高于", [True, False, False]),
    ("低于", [False, False, True]), ("达到", [True, True, False]),
    ("不大于", [True, True, False]),
])
async def test_it_precision_uses_inverse_numeric_order(comparison, expected):
    candidate, _, issues = await parse("当外圆精度{}IT8时，纳入除铜工序".format(comparison))
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"precision": {"outer_diameter_it": value}}).matched for value in [7, 8, 9]] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("joiner", ["和", "并且", "，", ",", "；"])
async def test_conjunction_retains_material_and_hardness(joiner):
    candidate, _, issues = await parse("当材料为9Cr18{}硬度不低于HRC58时，纳入除铜工序".format(joiner))
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"material": {"grade": grade}, "mechanical": {"hardness_hrc": hardness}}).matched
            for grade, hardness in [("6061", 60), ("9Cr18", 50), ("9Cr18", 58)]] == [False, False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize("joiner", ["和", "且", "，"])
async def test_feature_conjunction_requires_both_features(joiner):
    candidate, _, issues = await parse("当零件具有内孔{}键槽时，纳入除铜工序".format(joiner))
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"cad": {"features": values}}).matched
            for values in [["普通孔/辅助孔"], ["槽类特征"], ["普通孔/辅助孔", "槽类特征"]]] == [False, False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize("joiner", ["或", " 或 ", "或者", "或是"])
async def test_cross_field_disjunction_requires_clarification(joiner):
    candidate, _, issues = await parse("当材料为9Cr18{}硬度不低于HRC58时，纳入除铜工序".format(joiner))
    assert candidate is None
    assert any("或" in issue or "任一" in issue for issue in issues)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    "当材料为9Cr18且前面有镀铜工序时，安排除铜工序",
    "当材料类别为不锈钢，镀铜完成后安排除铜工序",
    "当前面有镀铜工序且有无损检测要求时，安排除铜工序",
])
async def test_field_gate_and_process_trigger_cannot_discard_either_mode(source):
    candidate, _, issues = await parse(source)
    assert candidate is None
    assert any("关联" in issue and "条件" in issue for issue in issues)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    "镀铜和淬火完成后安排除铜", "除铜必须在镀铜之后", "除铜之前必须完成镀铜",
    "除铜与镀铜不能同时出现", "当零件无中心孔时，纳入除铜工序",
    "当硬度不低于HRC58时，排除除铜工序",
])
async def test_unsupported_authored_modes_return_issues(source):
    candidate, _, issues = await parse(source)
    assert candidate is None
    assert issues


@pytest.mark.asyncio
@pytest.mark.parametrize("clause", [
    "材料类别为不锈钢且有无损检测要求",
    "材料为9Cr18且客户见证已完成",
    "材料为9Cr18和零件具有复杂异形轮廓",
])
async def test_failed_compound_parse_does_not_fall_back_to_one_clause(clause):
    candidate, _, issues = await parse("当{}时，纳入除铜工序".format(clause))
    assert candidate is None
    assert issues


def model_payload(monkeypatch, candidate):
    async def model(*args, **kwargs):
        return json.dumps({"candidate": candidate, "confidence": 0.96, "warnings": [], "unresolved": []}, ensure_ascii=False)

    monkeypatch.setattr(condition_parser, "call_llm", model)


@pytest.mark.asyncio
async def test_complete_model_conjunction_keeps_dynamic_material_and_requirement(monkeypatch):
    model_payload(monkeypatch, {
        "when": {"all": [
            {"field": "project_factor.material_category", "op": "eq", "value": "不锈钢"},
            {"all": [{"field": "special.requirements", "op": "contains", "value": "无损检测要求"}]},
        ]},
        "then": {"include_process_ids": ["strip"]},
        "field_definitions": [{
            "key": "project_factor.material_category", "label": "材料类别", "category": "材料", "type": "single_select",
            "operators": ["eq"], "options": [{"value": "不锈钢", "label": "不锈钢"}], "allow_custom": True, "source": "用户条件",
        }],
    })
    candidate, confidence, issues = await parse("当材料类别为不锈钢并且有无损检测要求时，纳入除铜工序")
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"project_factor": {"material_category": category}, "special": {"requirements": requirements}}).matched
            for category, requirements in [("铝合金", ["无损检测要求"]), ("不锈钢", []), ("不锈钢", ["无损检测要求"])]] == [False, False, True]
    assert confidence == 0.96
    assert issues == []


@pytest.mark.asyncio
@pytest.mark.parametrize("nullable_key", ["warnings", "unresolved"])
async def test_model_nullable_status_lists_are_treated_as_empty(monkeypatch, nullable_key):
    payload = {
        "candidate": {
            "when": {"field": "special.requirements", "op": "contains", "value": "客户见证要求"},
            "then": {"include_process_ids": ["strip"]},
        },
        "confidence": 0.96,
        "warnings": [],
        "unresolved": [],
    }
    payload[nullable_key] = None

    async def model(*args, **kwargs):
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(condition_parser, "call_llm", model)

    candidate, confidence, issues = await condition_parser._parse_with_llm(
        "需要人工补充的复杂条件", "strip", "除铜", PROCESSES,
    )

    assert candidate is not None
    assert candidate.when.field == "special.requirements"
    assert confidence == 0.96
    assert issues == []


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed_key", ["warnings", "unresolved"])
async def test_model_non_list_status_fields_fall_back_without_raising(monkeypatch, malformed_key):
    payload = {
        "candidate": {
            "when": {"field": "special.requirements", "op": "contains", "value": "客户见证要求"},
            "then": {"include_process_ids": ["strip"]},
        },
        "confidence": 0.96,
        "warnings": [],
        "unresolved": [],
    }
    payload[malformed_key] = "invalid"

    async def model(*args, **kwargs):
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(condition_parser, "call_llm", model)

    candidate, confidence, issues = await condition_parser._parse_with_llm(
        "需要人工补充的复杂条件", "strip", "除铜", PROCESSES,
    )

    assert candidate is None
    assert confidence is None
    assert any("结构未通过格式校验" in issue for issue in issues)


@pytest.mark.asyncio
@pytest.mark.parametrize("unresolved", [[], ["缺少可靠阈值"]])
@pytest.mark.parametrize("confidence", ["high", [0.9], {"value": 0.9}, True,
                                        float("nan"), float("inf"), 10 ** 1000],
                         ids=["text", "list", "object", "bool", "nan", "inf", "overflow"])
async def test_model_invalid_confidence_falls_back_without_crashing_or_auto_confirmation(
    monkeypatch, unresolved, confidence,
):
    async def model(*args, **kwargs):
        return json.dumps({
            "candidate": {
                "when": {"field": "special.requirements", "op": "contains", "value": "客户见证要求"},
                "then": {"include_process_ids": ["strip"]},
            },
            "confidence": confidence, "warnings": [], "unresolved": unresolved,
        }, ensure_ascii=False)

    monkeypatch.setattr(condition_parser, "call_llm", model)

    candidate, parsed_confidence, issues = await parse("需要人工补充的复杂条件")

    assert candidate is None
    assert parsed_confidence is None
    assert any("结构未通过格式校验" in issue for issue in issues)


@pytest.mark.asyncio
@pytest.mark.parametrize("when", [
    {"any": [{"field": "special.requirements", "op": "contains", "value": "客户见证要求"}]},
    {"not": {"field": "cad.features", "op": "contains", "value": "顶尖孔"}},
    {"field": "special.requirements", "op": "contains_all", "value": []},
    {"field": "material.grade", "op": "in", "value": []},
    {"field": "special.requirements", "op": "contains", "value": " "},
])
async def test_model_outputs_are_subject_to_authored_condition_rules(monkeypatch, when):
    model_payload(monkeypatch, {"when": when, "then": {"include_process_ids": ["strip"]}})
    candidate, _, issues = await parse("需要人工补充的复杂条件")
    assert candidate is None
    assert issues


@pytest.mark.asyncio
@pytest.mark.parametrize("action", [
    {"include_process_ids": ["copper"]}, {"include_process_ids": ["strip", "copper"]},
    {"exclude_process_ids": ["strip"]},
])
async def test_model_condition_can_only_include_the_current_process(monkeypatch, action):
    model_payload(monkeypatch, {"when": {"field": "cad.features", "op": "contains", "value": "复杂异形轮廓"}, "then": action})
    candidate, _, issues = await parse("需要人工补充的复杂条件")
    assert candidate is None
    assert issues


@pytest.mark.asyncio
@pytest.mark.parametrize("relation_type,sources,target", [
    ("order_after", ["copper"], "strip"), ("requires", ["copper"], "strip"),
    ("conflicts", ["copper"], "strip"), ("trigger_after", ["copper", "quench"], "strip"),
    ("trigger_after", ["quench"], "copper"),
])
async def test_model_relations_require_one_source_trigger_for_self(monkeypatch, relation_type, sources, target):
    model_payload(monkeypatch, {"kind": "process_relation", "relation": {
        "relation_type": relation_type, "source_process_ids": sources, "target_process_ids": [target],
    }})
    candidate, _, issues = await parse("需要人工补充的复杂条件")
    assert candidate is None
    assert issues


@pytest.mark.asyncio
@pytest.mark.parametrize("clause,context,expected", [
    ("材料为9Cr18或6061且硬度不低于HRC58", {"material": {"grade": "6061"}, "mechanical": {"hardness_hrc": 58}}, True),
    ("材料为9Cr18或6061且硬度不低于HRC58", {"material": {"grade": "6061"}, "mechanical": {"hardness_hrc": 50}}, False),
    ("零件具有内孔或中心孔且键槽", {"cad": {"features": ["普通孔/辅助孔", "槽类特征"]}}, True),
    ("零件具有内孔或中心孔且键槽", {"cad": {"features": ["普通孔/辅助孔"]}}, False),
])
async def test_single_field_list_disjunction_stays_inside_its_conjunction(clause, context, expected):
    candidate, _, issues = await parse("当{}时，纳入除铜工序".format(clause))
    assert candidate is not None, issues
    assert evaluate_condition(candidate.when, context).matched is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("clause", [
    "材料为9Cr18或客户见证已完成", "材料类别为不锈钢或硬度满足客户规定",
    "零件不具备中心孔", "零件不存在中心孔",
])
async def test_unmapped_or_negated_branch_cannot_become_a_positive_partial_rule(clause):
    candidate, _, issues = await parse("当{}时，纳入除铜工序".format(clause))
    assert candidate is None
    assert issues


@pytest.mark.asyncio
async def test_repeated_material_field_in_disjunction_preserves_both_values():
    candidate, _, issues = await parse("当材料为9Cr18或材料为6061时，纳入除铜工序")
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"material": {"grade": grade}}).matched for grade in ["9Cr18", "6061", "95Cr18"]] == [True, True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", [False, True])
async def test_model_cannot_drop_compound_gate_by_returning_partial_or_always(monkeypatch, configuration):
    body = {"when": {"field": "special.requirements", "op": "contains", "value": "无损检测要求"}, "then": {"include_process_ids": ["strip"]}}
    if configuration:
        body = {"kind": "process_configuration", "configuration": {"process_id": "strip", "occurrence": "always"}}
    model_payload(monkeypatch, body)
    candidate, _, issues = await parse("当材料类别为不锈钢并且有无损检测要求时，纳入除铜工序")
    assert candidate is None
    assert issues


@pytest.mark.asyncio
async def test_special_requirement_disjunction_retains_each_alternative():
    candidate, _, issues = await parse("当零件有无损检测要求或追溯标印要求时，纳入除铜工序")
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"special": {"requirements": values}}).matched
            for values in [["无损检测要求"], ["追溯标印"], []]] == [True, True, False]


@pytest.mark.asyncio
async def test_disjunctive_numeric_comparisons_are_not_reduced_to_first_comparison():
    candidate, _, issues = await parse("当硬度大于HRC58或硬度小于HRC50时，纳入除铜工序")
    assert candidate is None
    assert issues


@pytest.mark.asyncio
async def test_repeated_dynamic_field_list_retains_both_categories():
    candidate, _, issues = await parse("当材料类别为不锈钢或材料类别为高温合金时，纳入除铜工序")
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"project_factor": {"material_category": value}}).matched
            for value in ["不锈钢", "高温合金", "铝合金"]] == [True, True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("clause", [
    "零件没有无损检测要求", "零件无无损检测要求", "零件不需要无损检测要求",
    "零件不存在追溯标印要求", "零件无需客户见证要求", "无损检测要求不存在",
])
@pytest.mark.parametrize("positive_model", [False, True])
async def test_requirement_negation_cannot_become_positive_locally_or_from_model(monkeypatch, clause, positive_model):
    if positive_model:
        model_payload(monkeypatch, {
            "when": {"field": "special.requirements", "op": "contains", "value": "无损检测要求"},
            "then": {"include_process_ids": ["strip"]},
        })
    candidate, _, issues = await parse("当{}时，纳入除铜工序".format(clause))
    assert candidate is None
    assert any("否定" in issue for issue in issues)


@pytest.mark.asyncio
@pytest.mark.parametrize("joiner", ["及", "与"])
async def test_additional_conjunctions_preserve_both_field_predicates(joiner):
    candidate, _, issues = await parse("当材料为9Cr18{}硬度不低于HRC58时，纳入除铜工序".format(joiner))
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"material": {"grade": grade}, "mechanical": {"hardness_hrc": hardness}}).matched
            for grade, hardness in [("6061", 60), ("9Cr18", 50), ("9Cr18", 58)]] == [False, False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize("joiner", ["及", "与"])
async def test_additional_conjunctions_do_not_salvage_unknown_clause(joiner):
    candidate, _, issues = await parse("当材料为9Cr18{}客户见证已完成时，纳入除铜工序".format(joiner))
    assert candidate is None
    assert issues


@pytest.mark.asyncio
async def test_it_grade_fixed_phrase_is_not_split_as_conjunction():
    candidate, _, issues = await parse("当外圆精度达到IT8及以上精度时，纳入除铜工序")
    assert candidate is not None, issues
    assert [evaluate_condition(candidate.when, {"precision": {"outer_diameter_it": value}}).matched for value in [7, 8, 9]] == [True, True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("clause", [
    "镀铜完成后且客户见证已完成", "客户见证已完成且镀铜完成后",
    "镀铜完成后，客户见证已完成", "镀铜完成后及客户见证已完成",
    "镀铜完成后与客户见证已完成", "前面有镀铜工序且外部审批已结束",
])
async def test_unknown_residual_gate_cannot_be_dropped_from_relation(clause):
    candidate, _, issues = await parse("{}时安排除铜工序".format(clause))
    assert candidate is None
    assert any("关联" in issue and "条件" in issue for issue in issues)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    "镀铜完成后安排除铜工序", "前面有镀铜工序时安排除铜工序",
    "镀铜之后，需要加入该工序", "前面出现镀铜这个工序时，需要安排此工序",
])
async def test_plain_single_source_relation_still_parses_without_extra_gate(source):
    candidate, _, issues = await parse(source)
    assert candidate is not None, issues
    assert candidate.kind == "process_relation"
    assert candidate.relation.relation_type == "trigger_after"
    assert candidate.relation.source_process_ids == ["copper"]
    assert candidate.relation.target_process_ids == ["strip"]
    assert issues == []
