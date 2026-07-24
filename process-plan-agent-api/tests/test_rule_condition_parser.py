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
from app.services.rule_packages import condition_reviews


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

NATURAL_RELATION_PROCESSES = [
    RuleConditionProcessOption(process_id="process_rough", display_name="车削加工（A侧）"),
    RuleConditionProcessOption(process_id="process_stress_relief", display_name="去应力"),
    RuleConditionProcessOption(process_id="process_copper_plate", display_name="镀铜"),
    RuleConditionProcessOption(process_id="process_strip_copper", display_name="除铜"),
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
async def test_creates_project_factor_for_unregistered_categorical_field():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当材料类别为不锈钢时，纳入渗氮工序",
        "process_nitriding",
        "渗氮",
        [RuleConditionProcessOption(process_id="process_nitriding", display_name="渗氮")],
    )

    assert candidate is not None
    assert candidate.kind == "condition"
    assert candidate.when is not None
    assert candidate.when.op == "eq"
    assert candidate.when.value == "不锈钢"
    assert candidate.when.field.startswith("project_factor.")
    assert candidate.then is not None
    assert candidate.then.include_process_ids == ["process_nitriding"]
    assert len(candidate.field_definitions) == 1
    definition = candidate.field_definitions[0]
    assert definition.key == candidate.when.field
    assert definition.label == "材料类别"
    assert definition.type == "single_select"
    assert definition.operators == ["eq", "neq", "in"]
    assert definition.options == [{"value": "不锈钢", "label": "不锈钢"}]
    assert definition.allow_custom is True
    assert "材料类别" in candidate.preview
    assert "不锈钢" in candidate.preview
    assert confidence == 0.9
    assert issues == []


@pytest.mark.asyncio
async def test_creates_one_project_factor_with_multiple_user_authored_categories():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当材料类别为不锈钢或高温合金时，纳入渗氮工序",
        "process_nitriding",
        "渗氮",
        [RuleConditionProcessOption(process_id="process_nitriding", display_name="渗氮")],
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.op == "in"
    assert candidate.when.value == ["不锈钢", "高温合金"]
    assert candidate.field_definitions[0].options == [
        {"value": "不锈钢", "label": "不锈钢"},
        {"value": "高温合金", "label": "高温合金"},
    ]
    assert confidence == 0.9
    assert issues == []


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
async def test_parses_join_process_after_explicit_predecessor():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "淬火之后，需要加入该工序",
        "process_burn_inspect",
        "烧伤检查",
        RELATION_PROCESSES,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert candidate.relation is not None
    assert candidate.relation.source_process_ids == ["process_quench"]
    assert candidate.relation.target_process_ids == ["process_burn_inspect"]
    assert confidence == 0.9
    assert issues == []


@pytest.mark.asyncio
async def test_process_check_point_does_not_turn_into_a_generic_inspection_dependency():
    processes = [
        RuleConditionProcessOption(process_id="process_turn", display_name="车削加工"),
        RuleConditionProcessOption(process_id="process_mill", display_name="铣槽"),
        RuleConditionProcessOption(process_id="process_inspect", display_name="检验"),
        RuleConditionProcessOption(process_id="process_burn_inspect", display_name="烧伤检查"),
    ]
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当车削后或周边加工后过程检验点满足时，设置烧伤检查作为质量确认节点。",
        "process_burn_inspect",
        "烧伤检查",
        processes,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert candidate.relation is not None
    assert candidate.relation.source_process_ids == ["process_turn", "process_mill"]
    assert "process_inspect" not in candidate.relation.source_process_ids
    assert confidence == 0.9
    assert issues == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_text", "target_id", "target_name", "source_id"),
    [
        ("当粗加工后释放应力，避免后续精加工变形", "process_stress_relief", "去应力", "process_rough"),
        ("前面出现镀铜这个工序时，需要安排此工序", "process_strip_copper", "除铜", "process_copper_plate"),
    ],
)
async def test_parses_clear_natural_language_process_relations_locally(
    source_text, target_id, target_name, source_id, monkeypatch,
):
    async def llm_must_not_run(*args, **kwargs):
        raise AssertionError("明确的工序关系不应等待大模型")

    monkeypatch.setattr(condition_parser, "call_llm", llm_must_not_run)
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        source_text,
        target_id,
        target_name,
        NATURAL_RELATION_PROCESSES,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert candidate.relation is not None
    assert candidate.relation.relation_type == "trigger_after"
    assert candidate.relation.source_process_ids == [source_id]
    assert candidate.relation.target_process_ids == [target_id]
    assert confidence == 0.9
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
async def test_maps_unseen_structural_feature_to_extensible_cad_tag():
    processes = [RuleConditionProcessOption(process_id="process_mill_boss", display_name="铣凸台")]
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当零件存在异形凸台结构时，安排铣凸台工序",
        "process_mill_boss",
        "铣凸台",
        processes,
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.field == "cad.features"
    assert candidate.when.op == "contains"
    assert candidate.when.value == "异形凸台"
    assert candidate.then is not None
    assert candidate.then.include_process_ids == ["process_mill_boss"]
    assert confidence == 0.65
    assert issues == []


@pytest.mark.asyncio
async def test_maps_unseen_process_requirement_to_extensible_special_tag():
    processes = [RuleConditionProcessOption(process_id="process_vacuum_clean", display_name="真空清洗")]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "当零件需要真空清洗时，安排真空清洗工序",
        "process_vacuum_clean",
        "真空清洗",
        processes,
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.field == "special.requirements"
    assert candidate.when.op == "contains"
    assert candidate.when.value == "真空清洗要求"
    assert issues == []


@pytest.mark.asyncio
async def test_does_not_invent_a_tag_for_vague_condition_text():
    processes = [RuleConditionProcessOption(process_id="process_optional", display_name="辅助加工")]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "根据不同结构类型决定是否安排该工序",
        "process_optional",
        "辅助加工",
        processes,
    )

    assert candidate is None
    assert any("无法可靠映射" in issue for issue in issues)


@pytest.mark.asyncio
async def test_creates_project_factor_for_unknown_part_category_instead_of_special_requirement():
    processes = [RuleConditionProcessOption(process_id="process_optional", display_name="辅助加工")]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "当零件属于A类时，安排辅助加工工序",
        "process_optional",
        "辅助加工",
        processes,
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.field.startswith("project_factor.")
    assert candidate.when.op == "eq"
    assert candidate.when.value == "A类"
    assert candidate.when.field != "special.requirements"
    assert candidate.field_definitions[0].label == "零件类型"
    assert candidate.field_definitions[0].options == [{"value": "A类", "label": "A类"}]
    assert issues == []


@pytest.mark.asyncio
async def test_explicit_process_order_takes_priority_over_nondestructive_inspection_category():
    processes = [
        RuleConditionProcessOption(process_id="process_quench", display_name="淬火"),
        RuleConditionProcessOption(process_id="process_ndt", display_name="无损检查"),
    ]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "淬火工序之后设置该工序",
        "process_ndt",
        "无损检查",
        processes,
    )

    assert candidate is not None
    assert candidate.kind == "process_relation"
    assert candidate.relation is not None
    assert candidate.relation.relation_type == "trigger_after"
    assert candidate.relation.source_process_ids == ["process_quench"]
    assert candidate.relation.target_process_ids == ["process_ndt"]
    assert issues == []


@pytest.mark.asyncio
async def test_nondestructive_requirement_is_parsed_as_special_requirement():
    processes = [RuleConditionProcessOption(process_id="process_ndt", display_name="无损检查")]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "当零件存在无损检测要求时，纳入无损检查工序",
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
    # Explicit, route-resolvable dependencies are deterministic and therefore
    # do not wait for a model response.
    assert confidence == 0.9
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
    assert issues == []


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


def test_registry_rejects_out_of_range_and_reversed_numeric_conditions():
    from app.services.rule_packages.contracts import ConditionNode

    assert validate_condition_tree(
        ConditionNode(field="precision.outer_diameter_it", op="lte", value=99)
    ) == ["字段“外圆尺寸精度 IT”不能大于 18"]
    assert validate_condition_tree(
        ConditionNode(field="mechanical.hardness_hrc", op="between", value=[70, 20])
    ) == ["字段“目标硬度 HRC”的区间下限不能大于上限"]


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
async def test_parse_result_does_not_overwrite_a_newer_condition_draft(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        route = NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind_outer"}]',
        )
        session.add(route)
        await session.commit()

        async def superseded_parse(*args, **kwargs):
            review = (await session.execute(
                select(NormalizedRouteSegmentRuleReview).where(
                    NormalizedRouteSegmentRuleReview.route_version_id == 1,
                    NormalizedRouteSegmentRuleReview.segment_id == "process_grind_outer",
                )
            )).scalars().one()
            review.condition_source_text = "新的条件文字"
            review.condition_source_hash = condition_source_hash("新的条件文字")
            review.condition_status = "draft"
            await session.commit()
            return None, None, []

        monkeypatch.setattr(condition_reviews, "parse_rule_condition", superseded_parse)
        response = await condition_reviews.parse_condition_review(
            ParseRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text="当外圆尺寸精度达到 IT8 时，纳入磨外圆工序",
                process_id="process_grind_outer",
                process_name="磨外圆",
                processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
            ),
            session,
        )

        assert response.review.source_text == "新的条件文字"
        assert response.review.status == "draft"
        assert response.review.candidate is None

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
