"""Numeric candidates must retain thresholds, units and every required gate."""

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services.rule_packages import condition_parser, condition_reviews
from app.services.rule_packages.authoring_validation import validate_authored_candidate
from app.services.rule_packages.condition_contracts import ConfirmRuleConditionRequest, RuleConditionProcessOption
from app.services.rule_packages.expression_engine import evaluate_condition


PROCESSES = [RuleConditionProcessOption(process_id="inspect", display_name="检验")]


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    async def empty_model(*args, **kwargs):
        return ""

    monkeypatch.setattr(condition_parser, "call_llm", empty_model)


async def parse(clause):
    return await condition_parser.parse_rule_condition(
        "当{}时，纳入检验工序".format(clause), "inspect", "检验", PROCESSES,
    )


def matches(node, field, values):
    return [evaluate_condition(node, {field: value}).matched for value in values]


@pytest.mark.asyncio
@pytest.mark.parametrize("clause,field,values,expected", [
    ("硬度达到HRC58", "mechanical.hardness_hrc", [50, 58, 60], [False, True, True]),
    ("粗糙度达到Ra0.8", "surface.roughness_ra", [0.4, 0.8, 1.6], [True, True, False]),
    ("圆柱度达到0.01mm", "tolerance.cylindricity_mm", [0.005, 0.01, 0.02], [True, True, False]),
    ("外圆精度达到IT8", "precision.outer_diameter_it", [7, 8, 9], [True, True, False]),
    ("硬度不低于HRC58", "mechanical.hardness_hrc", [50, 58, 60], [False, True, True]),
])
async def test_achieving_numeric_requirement_uses_the_field_direction(clause, field, values, expected):
    candidate, _, issues = await parse(clause)
    assert candidate is not None, issues
    assert issues == []
    assert matches(candidate.when, field, values) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("clause,field,limits,values", [
    ("硬度在HRC58到62之间", "mechanical.hardness_hrc", [58, 62], [57, 58, 60, 62, 63]),
    ("硬度为HRC58～62", "mechanical.hardness_hrc", [58, 62], [57, 58, 60, 62, 63]),
    ("硬度在58至62HRC之间", "mechanical.hardness_hrc", [58, 62], [57, 58, 60, 62, 63]),
    ("硬度HRC58-HRC62", "mechanical.hardness_hrc", [58, 62], [57, 58, 60, 62, 63]),
    ("硬度HRC58~62", "mechanical.hardness_hrc", [58, 62], [57, 58, 60, 62, 63]),
    ("硬度HRC58—62", "mechanical.hardness_hrc", [58, 62], [57, 58, 60, 62, 63]),
    ("粗糙度在Ra0.4到0.8之间", "surface.roughness_ra", [0.4, 0.8], [0.2, 0.4, 0.6, 0.8, 1.6]),
    ("粗糙度Ra0.4～Ra0.8", "surface.roughness_ra", [0.4, 0.8], [0.2, 0.4, 0.6, 0.8, 1.6]),
    ("外圆精度IT7至IT9", "precision.outer_diameter_it", [7, 9], [6, 7, 8, 9, 10]),
    ("圆柱度在5到10微米之间", "tolerance.cylindricity_mm", [0.005, 0.01], [0.001, 0.005, 0.007, 0.01, 0.02]),
    ("圆柱度在5微米至0.01mm之间", "tolerance.cylindricity_mm", [0.005, 0.01], [0.001, 0.005, 0.007, 0.01, 0.02]),
])
async def test_complete_interval_includes_both_boundaries(clause, field, limits, values):
    candidate, _, issues = await parse(clause)
    assert candidate is not None, issues
    assert issues == []
    assert candidate.when.op == "between"
    assert candidate.when.value == limits
    assert matches(candidate.when, field, values) == [False, True, True, True, False]
    assert validate_authored_candidate(candidate, "inspect") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("label,field", [
    ("圆柱度", "tolerance.cylindricity_mm"), ("同轴度", "tolerance.coaxiality_mm"),
    ("同心度", "tolerance.coaxiality_mm"), ("圆跳动", "tolerance.runout_mm"),
    ("全跳动", "tolerance.runout_mm"), ("位置度", "tolerance.position_mm"),
    ("平面度", "tolerance.flatness_mm"), ("垂直度", "tolerance.perpendicularity_mm"),
    ("圆度", "tolerance.roundness_mm"),
])
@pytest.mark.parametrize("quantity", ["10微米", "10 um", "10 μm", "10 µm", "0.01mm", "0.01毫米"])
async def test_tolerance_explicit_units_are_converted_before_evaluation(label, field, quantity):
    candidate, _, issues = await parse("{}不超过{}".format(label, quantity))
    assert candidate is not None, issues
    assert candidate.when.value == pytest.approx(0.01)
    assert matches(candidate.when, field, [0.005, 0.01, 0.02, 5]) == [True, True, False, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("clause,field,value", [
    ("粗糙度不超过0.0008mm", "surface.roughness_ra", 0.8),
    ("粗糙度不超过0.8微米", "surface.roughness_ra", 0.8),
    ("硬度不低于58HRC", "mechanical.hardness_hrc", 58),
    ("硬度不低于hrc58", "mechanical.hardness_hrc", 58),
    ("圆柱度不超过0.01", "tolerance.cylindricity_mm", 0.01),
])
async def test_field_units_and_unitless_controls(clause, field, value):
    candidate, _, issues = await parse(clause)
    assert candidate is not None, issues
    assert candidate.when.field == field
    assert candidate.when.value == pytest.approx(value)
    assert validate_authored_candidate(candidate, "inspect") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("clause", [
    "圆柱度不超过10英寸", "圆柱度不超过10furlong", "圆柱度不超过10nm",
    "粗糙度不超过0.8未知单位", "硬度不低于HB200", "硬度不低于200HV",
    "硬度在HRC58到62HB之间", "圆柱度在5微米到10英寸之间",
    "圆柱度不超过英寸10", "圆柱度不超过微米10", "里氏硬度不低于58",
    "HB200", "HRB90", "Rz3.2",
])
@pytest.mark.parametrize("model_supplies_candidate", [False, True])
async def test_unsupported_units_require_clarification_even_with_model_output(monkeypatch, clause, model_supplies_candidate):
    if model_supplies_candidate:
        async def unsafe_model(*args, **kwargs):
            return json.dumps({"candidate": {
                "when": {"field": "mechanical.hardness_hrc", "op": "gte", "value": 58},
                "then": {"include_process_ids": ["inspect"]},
            }, "confidence": 0.99, "warnings": [], "unresolved": []})

        monkeypatch.setattr(condition_parser, "call_llm", unsafe_model)
    candidate, _, issues = await parse(clause)
    assert candidate is None
    assert any("单位" in issue or "量表" in issue for issue in issues)


@pytest.mark.asyncio
@pytest.mark.parametrize("clause", [
    "硬度HRC58到", "硬度HRC58～", "硬度HRC62到58", "硬度HRC58到60到62",
    "硬度大于HRC58小于HRC62", "粗糙度Ra0.8到0.4", "圆柱度在10微米到0.005mm之间",
    "硬度HRC到62", "硬度大于HRC58到62", "外圆精度高于IT7至9",
    "硬度不在HRC58到62之间", "硬度未达到HRC58",
])
async def test_incomplete_reversed_or_noninclusive_interval_is_not_truncated(clause):
    candidate, _, issues = await parse(clause)
    assert candidate is None
    assert issues


@pytest.mark.asyncio
async def test_numeric_conjunction_can_be_confirmed_and_requires_every_gate():
    source = "当材料为9Cr18且硬度在HRC58到62之间且圆柱度不超过10微米时，纳入检验工序"
    candidate, confidence, issues = await condition_parser.parse_rule_condition(source, "inspect", "检验", PROCESSES)
    assert candidate is not None, issues
    assert validate_authored_candidate(candidate, "inspect") == []
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            row = NormalizedRouteSegmentRuleReview(
                project_id=7, route_version_id=1, segment_id="inspect", decision="accepted",
                condition_source_text=source, condition_source_hash=condition_reviews.condition_source_hash(source),
                condition_status="pending_confirmation", condition_candidate_json=candidate.model_dump_json(by_alias=True),
                condition_confidence=confidence,
            )
            db.add_all([Project(id=7, name="数值解析回归"), NormalizedRouteVersion(
                id=1, project_id=7, version=1, route_json='[{"id":"inspect","normalized_step_name":"检验"}]',
            ), row])
            await db.commit()
            saved = await condition_reviews.confirm_condition_review(ConfirmRuleConditionRequest(
                project_id=7, route_id=1, segment_id="inspect", source_text=source,
                source_hash=row.condition_source_hash, candidate=candidate, processes=PROCESSES,
            ), db)
            assert saved.review.status == "confirmed"
            confirmed = json.loads(row.condition_confirmed_json)
            when = candidate.when.model_validate(confirmed["when"])
            contexts = [
                {"material.grade": "9Cr18", "mechanical.hardness_hrc": 60, "tolerance.cylindricity_mm": 0.01},
                {"material.grade": "6061", "mechanical.hardness_hrc": 60, "tolerance.cylindricity_mm": 0.01},
                {"material.grade": "9Cr18", "mechanical.hardness_hrc": 57, "tolerance.cylindricity_mm": 0.01},
                {"material.grade": "9Cr18", "mechanical.hardness_hrc": 63, "tolerance.cylindricity_mm": 0.01},
                {"material.grade": "9Cr18", "mechanical.hardness_hrc": 60, "tolerance.cylindricity_mm": 0.02},
            ]
            assert [evaluate_condition(when, context).matched for context in contexts] == [True, False, False, False, False]
    finally:
        await engine.dispose()
