import json

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion
from app.services.rule_packages import condition_parser
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionProcessOption,
    SaveRuleConditionDraftRequest,
)
from app.services.rule_packages.condition_registry import condition_fields, validate_condition_tree
from app.services.rule_packages.condition_reviews import (
    condition_source_hash,
    confirm_condition_review,
    invalidate_legacy_nondestructive_relation_reviews,
    migrate_legacy_boolean_requirement_reviews,
    parse_condition_review,
    save_condition_draft,
)


PROCESSES = [
    RuleConditionProcessOption(process_id="process_prepare", display_name="准备"),
    RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆"),
    RuleConditionProcessOption(process_id="process_inspect", display_name="检验"),
]

RELATION_PROCESSES = [
    *PROCESSES,
    RuleConditionProcessOption(process_id="process_quench", display_name="淬火"),
    RuleConditionProcessOption(process_id="process_burn_inspect", display_name="烧伤检查"),
]


def test_parse_request_only_accepts_the_controlled_field_registry():
    with pytest.raises(ValidationError, match="known_dynamic_fields"):
        ParseRuleConditionRequest.model_validate({
            "project_id": 7,
            "route_id": 1,
            "segment_id": "process_grind_outer",
            "source_text": "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序",
            "process_id": "process_grind_outer",
            "process_name": "磨外圆",
            "processes": [{"process_id": "process_grind_outer", "display_name": "磨外圆"}],
            "known_dynamic_fields": [],
        })


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    async def empty_llm(*args, **kwargs):
        return ""

    monkeypatch.setattr(condition_parser, "call_llm", empty_llm)


@pytest.mark.asyncio
async def test_parses_it_grade_into_controlled_numeric_field():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当外圆尺寸精度达到 IT8 时，纳入“磨外圆”工序",
        "process_grind_outer",
        "磨外圆",
        PROCESSES,
    )

    assert candidate is not None
    assert candidate.when.field == "precision.outer_diameter_it"
    assert candidate.when.op == "lte"
    assert candidate.when.value == 8
    assert candidate.then.include_process_ids == ["process_grind_outer"]
    assert confidence == 0.65
    assert issues == []


@pytest.mark.asyncio
async def test_parses_compound_and_condition():
    candidate, _, _ = await condition_parser.parse_rule_condition(
        "材料为9Cr18并且硬度不低于HRC58时，纳入检验工序",
        "process_inspect",
        "检验",
        PROCESSES,
    )

    assert candidate is not None
    assert candidate.when.all_conditions is not None
    assert [child.field for child in candidate.when.all_conditions] == ["material.grade", "mechanical.hardness_hrc"]


@pytest.mark.asyncio
async def test_parses_process_relation_before_parameter_condition():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "前面存在淬火工序，就出现烧伤检查",
        "process_burn_inspect",
        "烧伤检查",
        RELATION_PROCESSES,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert candidate.relation is not None
    assert candidate.relation.relation_type == "trigger_after"
    assert candidate.relation.source_process_ids == ["process_quench"]
    assert candidate.relation.target_process_ids == ["process_burn_inspect"]
    assert "纳入烧伤检查" in candidate.preview
    assert confidence == 0.9
    assert issues == []


@pytest.mark.asyncio
async def test_parses_front_has_process_as_trigger_after_relation():
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "前面有淬火时，安排此工序",
        "process_burn_inspect",
        "烧伤检查",
        RELATION_PROCESSES,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert candidate.relation is not None
    assert candidate.relation.relation_type == "trigger_after"
    assert candidate.relation.source_process_ids == ["process_quench"]
    assert candidate.relation.target_process_ids == ["process_burn_inspect"]
    assert issues == []


@pytest.mark.asyncio
async def test_parses_traceability_requirement_as_existing_special_requirement():
    mark_processes = [*PROCESSES, RuleConditionProcessOption(process_id="process_mark", display_name="标记")]
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当零件需要追溯、编号或批次标识时，安排标记工序",
        "process_mark",
        "标记",
        mark_processes,
    )

    assert candidate is not None
    assert candidate.kind == "condition"
    assert candidate.when is not None
    assert candidate.when.field == "special.requirements"
    assert candidate.when.op == "contains"
    assert candidate.when.value == "追溯标印"
    assert candidate.then is not None
    assert candidate.then.include_process_ids == ["process_mark"]
    assert candidate.field_definitions == []
    assert confidence == 0.65
    assert issues == []


@pytest.mark.asyncio
async def test_parses_generic_surface_requirement_as_special_requirement():
    processes = [RuleConditionProcessOption(process_id="process_copper", display_name="镀铜")]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "当防护、防腐蚀、绝缘或表面稳定性要求满足时，安排镀铜工序",
        "process_copper",
        "镀铜",
        processes,
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.field == "special.requirements"
    assert candidate.when.op == "contains"
    assert candidate.when.value == "镀铜要求"
    assert candidate.field_definitions == []
    assert issues == []


@pytest.mark.asyncio
async def test_nondestructive_inspection_is_parsed_as_special_requirement_not_process_relation():
    processes = [
        RuleConditionProcessOption(process_id="process_inspect", display_name="检验"),
        RuleConditionProcessOption(process_id="process_ndt", display_name="无损检查"),
    ]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "当车削后或周边加工后过程检验点满足时，设置无损检查作为质量确认节点",
        "process_ndt",
        "无损检查",
        processes,
    )

    assert candidate is not None
    assert candidate.kind == "condition"
    assert candidate.when is not None
    assert candidate.when.field == "special.requirements"
    assert candidate.when.op == "contains"
    assert candidate.when.value == "无损检测要求"
    assert candidate.then is not None
    assert candidate.then.include_process_ids == ["process_ndt"]
    assert issues == []


@pytest.mark.asyncio
async def test_llm_candidate_takes_priority_when_it_passes_validation(monkeypatch):
    async def relation_llm(*args, **kwargs):
        return """{
          "candidate": {
            "kind": "process_relation",
            "relation": {
              "relation_type": "trigger_after",
              "source_process_ids": ["process_quench"],
              "target_process_ids": ["process_burn_inspect"],
              "source_match": "any"
            },
            "preview": "淬火进入路线 → 纳入烧伤检查，并排在淬火之后"
          },
          "confidence": 0.98,
          "warnings": [],
          "unresolved": []
        }"""

    monkeypatch.setattr(condition_parser, "call_llm", relation_llm)
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "前面有淬火时，安排此工序",
        "process_burn_inspect",
        "烧伤检查",
        RELATION_PROCESSES,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert confidence == 0.98
    assert issues == []


@pytest.mark.asyncio
async def test_explicit_process_relation_overrides_wrong_llm_condition(monkeypatch):
    async def wrong_condition_llm(*args, **kwargs):
        return """{
          "candidate": {
            "kind": "condition",
            "when": {"field": "special.requirements", "op": "contains", "value": "烧伤检查要求"},
            "then": {"include_process_ids": ["process_burn_inspect"], "exclude_process_ids": []},
            "preview": "特殊要求包含烧伤检查要求"
          },
          "confidence": 0.9,
          "warnings": [],
          "unresolved": []
        }"""

    monkeypatch.setattr(condition_parser, "call_llm", wrong_condition_llm)
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "前面有淬火时，安排此工序",
        "process_burn_inspect",
        "烧伤检查",
        RELATION_PROCESSES,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert any("工序关系语义不一致" in issue for issue in issues)


@pytest.mark.asyncio
async def test_unsupported_condition_is_blocked():
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "看情况决定是否增加磨外圆",
        "process_grind_outer",
        "磨外圆",
        PROCESSES,
    )

    assert candidate is None
    assert any("无法可靠映射" in issue for issue in issues)


def test_registry_covers_planned_condition_categories():
    keys = {field.key for field in condition_fields()}
    assert {
        "material.grade",
        "precision.outer_diameter_it",
        "surface.roughness_ra",
        "tolerance.roundness_mm",
        "cad.features",
        "special.requirements",
    }.issubset(keys)


def test_registry_rejects_unknown_field():
    from app.services.rule_packages.contracts import ConditionNode

    issues = validate_condition_tree(ConditionNode(field="custom.free_text", op="eq", value="x"))
    assert issues == ["条件字段不在标准字段库中：custom.free_text"]


@pytest.mark.asyncio
async def test_confirmed_rule_is_invalidated_when_source_text_changes():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source_text = "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序"

    async with session_factory() as session:
        route = NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_prepare"},{"id":"process_grind_outer"},{"id":"process_inspect"}]',
        )
        session.add(route)
        await session.commit()

        parsed = await parse_condition_review(
            ParseRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text=source_text,
                process_id="process_grind_outer",
                process_name="磨外圆",
                processes=PROCESSES,
            ),
            session,
        )
        assert parsed.review.status == "pending_confirmation"
        assert parsed.review.candidate is not None

        confirmed = await confirm_condition_review(
            ConfirmRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text=source_text,
                source_hash=parsed.review.source_hash,
                candidate=parsed.review.candidate,
                processes=PROCESSES,
                confirmed_by="测试用户",
            ),
            session,
        )
        assert confirmed.review.status == "confirmed"
        assert confirmed.review.confirmed is not None

        changed = await save_condition_draft(
            SaveRuleConditionDraftRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text="当外圆尺寸精度达到 IT7 时，纳入磨外圆工序",
            ),
            session,
        )
        assert changed.review.status == "draft"
        assert changed.review.confirmed is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_invalidates_legacy_nondestructive_process_relation_for_re_review():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        route = NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_inspect","normalized_step_name":"检验"},{"id":"process_ndt","normalized_step_name":"无损检查"}]',
        )
        session.add(route)
        session.add(NormalizedRouteSegmentRuleReview(
            project_id=7,
            route_version_id=1,
            segment_id="process_ndt",
            decision="accepted",
            note="",
            summary_json="[]",
            question_trail_json="[]",
            condition_status="confirmed",
            condition_source_text="前面有检验时安排无损检查",
            condition_source_hash="a" * 64,
            condition_confirmed_json='{"kind":"process_relation","relation":{"relation_type":"trigger_after","source_process_ids":["process_inspect"],"target_process_ids":["process_ndt"]},"preview":"检验进入路线"}',
        ))
        await session.commit()

        assert await invalidate_legacy_nondestructive_relation_reviews(route, session) is True
        review = (await session.execute(
            select(NormalizedRouteSegmentRuleReview).where(NormalizedRouteSegmentRuleReview.segment_id == "process_ndt")
        )).scalars().one()
        assert review.condition_status == "draft"
        assert review.condition_confirmed_json is None
        assert review.condition_source_text == '当零件有无损检测要求时，纳入“无损检查”工序。'

    await engine.dispose()


@pytest.mark.asyncio
async def test_migrates_legacy_boolean_requirement_to_special_requirement():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        route = NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_mark","normalized_step_name":"标记"}]',
        )
        legacy_candidate = {
            "kind": "condition",
            "when": {"field": "custom.requirements.traceability_marking_required", "op": "eq", "value": True},
            "then": {"include_process_ids": ["process_mark"], "exclude_process_ids": []},
            "field_definitions": [{
                "key": "custom.requirements.traceability_marking_required",
                "label": "是否需要追溯标识",
                "category": "特殊要求",
                "type": "boolean",
                "operators": ["eq", "neq"],
                "aliases": ["追溯", "编号"],
                "source": "人工补充/图样技术要求",
                "options": [],
                "allow_custom": False,
            }],
            "preview": "是否需要追溯标识 等于 是",
        }
        session.add(route)
        session.add(NormalizedRouteSegmentRuleReview(
            project_id=7,
            route_version_id=1,
            segment_id="process_mark",
            decision="accepted",
            note="",
            summary_json="[]",
            question_trail_json="[]",
            condition_status="confirmed",
            condition_candidate_json=json.dumps(legacy_candidate, ensure_ascii=False),
            condition_confirmed_json=json.dumps(legacy_candidate, ensure_ascii=False),
        ))
        await session.commit()

        assert await migrate_legacy_boolean_requirement_reviews(route, session) is True
        review = (await session.execute(
            select(NormalizedRouteSegmentRuleReview).where(NormalizedRouteSegmentRuleReview.segment_id == "process_mark")
        )).scalars().one()
        migrated = json.loads(review.condition_confirmed_json)
        assert migrated["when"] == {"all": None, "any": None, "not": None, "field": "special.requirements", "op": "contains", "value": "追溯标印"}
        assert migrated["field_definitions"] == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_converts_legacy_llm_boolean_to_special_requirement(monkeypatch):
    async def legacy_boolean_llm(*args, **kwargs):
        return """{
          "candidate": {
            "kind": "condition",
            "when": {"field": "custom.requirements.traceability_marking_required", "op": "eq", "value": true},
            "then": {"include_process_ids": ["process_mark"], "exclude_process_ids": []},
            "field_definitions": [{
              "key": "custom.requirements.traceability_marking_required",
              "label": "是否需要追溯标识",
              "category": "特殊要求",
              "type": "boolean",
              "operators": ["eq", "neq"],
              "aliases": ["追溯", "编号"],
              "source": "人工补充/图样技术要求",
              "options": [],
              "allow_custom": false
            }],
            "preview": "是否需要追溯标识 等于 是"
          },
          "confidence": 0.9,
          "warnings": [],
          "unresolved": []
        }"""

    monkeypatch.setattr(condition_parser, "call_llm", legacy_boolean_llm)
    processes = [RuleConditionProcessOption(process_id="process_mark", display_name="标记")]
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当零件需要追溯、编号或批次标识时，安排标记工序",
        "process_mark",
        "标记",
        processes,
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.field == "special.requirements"
    assert candidate.when.op == "contains"
    assert candidate.when.value == "追溯标印"
    assert candidate.field_definitions == []
    assert confidence == 0.9
    assert issues == []
