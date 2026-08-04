import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services.rule_packages import condition_parser
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ManualRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionProcessOption,
    SaveRuleConditionDraftRequest,
)
from app.services.rule_packages.condition_registry import condition_fields, validate_condition_tree
from app.services.rule_packages.condition_reviews import (
    condition_source_hash,
    confirm_condition_review,
    invalidate_legacy_nondestructive_relation_reviews,
    migrate_legacy_standard_factor_reviews,
    serialize_condition_review,
    set_manual_condition_review,
    parse_condition_review,
    save_condition_draft,
)
from app.services.rule_packages import condition_reviews
from app.services.route_analysis import build_saved_normalized_route_response


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
    assert "IT8" in candidate.evidence
    assert confidence == 0.9
    assert issues == []


@pytest.mark.asyncio
async def test_parser_binds_an_exact_standard_factor():
    """A parser regression that drops catalog IDs would make the candidate unconfirmable."""
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当存在顶尖孔时，纳入磨外圆工序",
        "process_grind_outer",
        "磨外圆",
        PROCESSES,
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.factor_id == "feature.center_hole_location"
    assert confidence >= 0.85
    assert issues == []


@pytest.mark.asyncio
async def test_deterministic_standard_condition_does_not_wait_for_llm(monkeypatch):
    async def llm_must_not_run(*args, **kwargs):
        raise AssertionError("标准数值条件应由本地解析器直接处理")

    monkeypatch.setattr(condition_parser, "call_llm", llm_must_not_run)
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序",
        "process_grind_outer",
        "磨外圆",
        PROCESSES,
    )

    assert candidate is not None
    assert candidate.when.field == "precision.outer_diameter_it"
    assert confidence == 0.9
    assert issues == []


@pytest.mark.asyncio
async def test_complex_condition_uses_rule_specific_llm_time_budget(monkeypatch):
    captured = {}

    async def capture_llm(*args, **kwargs):
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(condition_parser, "call_llm", capture_llm)
    await condition_parser.parse_rule_condition(
        "当零件具有复杂异形轮廓时，安排检验工序",
        "process_inspect",
        "检验",
        PROCESSES,
    )

    assert captured["timeout_seconds"] == 45.0
    assert captured["max_retries"] == 1


@pytest.mark.asyncio
async def test_partially_recognized_vague_condition_still_uses_llm(monkeypatch):
    calls = 0

    async def capture_llm(*args, **kwargs):
        nonlocal calls
        calls += 1
        return ""

    monkeypatch.setattr(condition_parser, "call_llm", capture_llm)
    candidate, confidence, _ = await condition_parser.parse_rule_condition(
        "当零件存在内孔、通孔或中心孔，以及不同结构类型下工艺安排存在差异时，纳入珩孔工序",
        "process_hone",
        "珩孔",
        [RuleConditionProcessOption(process_id="process_hone", display_name="珩孔")],
    )

    assert calls == 1
    assert candidate is None
    assert confidence is None


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
async def test_partial_compound_condition_uses_llm_instead_of_dropping_unknown_clause(monkeypatch):
    calls = 0

    async def compound_llm(*args, **kwargs):
        nonlocal calls
        calls += 1
        return """{
          "candidate": {
            "kind": "condition",
            "when": {"all": [
              {"field": "precision.outer_diameter_it", "op": "lte", "value": 8},
              {"field": "cad.features", "op": "contains", "value": "复杂异形轮廓"}
            ]},
            "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
            "preview": "外圆尺寸精度 IT <= 8 并且 CAD 特征包含复杂异形轮廓",
            "evidence": "外圆尺寸精度达到 IT8 并且具有复杂异形轮廓"
          },
          "confidence": 0.9,
          "warnings": [],
          "unresolved": []
        }"""

    monkeypatch.setattr(condition_parser, "call_llm", compound_llm)
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当外圆尺寸精度达到 IT8 并且具有复杂异形轮廓时，纳入磨外圆工序",
        "process_grind_outer",
        "磨外圆",
        PROCESSES,
    )

    assert calls == 1
    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.all_conditions is not None
    assert [child.field for child in candidate.when.all_conditions] == [
        "precision.outer_diameter_it",
        "cad.features",
    ]
    assert confidence == 0.9
    assert any("标准因子" in issue for issue in issues)


@pytest.mark.asyncio
async def test_unregistered_categorical_field_stays_unresolved():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当材料类别为不锈钢时，纳入渗氮工序",
        "process_nitriding",
        "渗氮",
        [RuleConditionProcessOption(process_id="process_nitriding", display_name="渗氮")],
    )

    assert candidate is None
    assert confidence is None
    assert any("无法可靠映射" in issue for issue in issues)


@pytest.mark.asyncio
async def test_unregistered_categorical_values_do_not_create_project_factor():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当材料类别为不锈钢或高温合金时，纳入渗氮工序",
        "process_nitriding",
        "渗氮",
        [RuleConditionProcessOption(process_id="process_nitriding", display_name="渗氮")],
    )

    assert candidate is None
    assert confidence is None
    assert any("无法可靠映射" in issue for issue in issues)


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
async def test_process_name_inside_requirement_is_not_treated_as_relation():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当零件存在镀铜要求时，安排除铜工序",
        "process_strip_copper",
        "除铜",
        NATURAL_RELATION_PROCESSES,
    )

    assert candidate is not None
    assert candidate.kind == "condition"
    assert candidate.when is not None
    assert candidate.when.field == "special.requirements"
    assert candidate.when.value == "镀铜要求"
    assert confidence == 0.65
    assert any("标准因子" in issue for issue in issues)


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
    assert any("标准因子" in issue for issue in issues)


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
    assert candidate.when.factor_id is None
    assert confidence == 0.65
    assert any("标准因子" in issue for issue in issues)


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
    assert candidate.when.factor_id is None
    assert any("标准因子" in issue for issue in issues)


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
async def test_unknown_part_category_stays_unresolved_instead_of_creating_project_factor():
    processes = [RuleConditionProcessOption(process_id="process_optional", display_name="辅助加工")]
    candidate, _, issues = await condition_parser.parse_rule_condition(
        "当零件属于A类时，安排辅助加工工序",
        "process_optional",
        "辅助加工",
        processes,
    )

    assert candidate is None
    assert any("无法可靠映射" in issue for issue in issues)


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
async def test_llm_evidence_is_replaced_when_it_is_not_an_exact_source_excerpt(monkeypatch):
    async def hallucinated_evidence_llm(*args, **kwargs):
        return """{
          "candidate": {
            "kind": "condition",
            "when": {"field": "cad.features", "op": "contains", "value": "复杂异形轮廓"},
            "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
            "preview": "CAD 特征集合包含复杂异形轮廓",
            "evidence": "图纸明确标注复杂异形轮廓"
          },
          "confidence": 0.92,
          "warnings": [],
          "unresolved": []
        }"""

    monkeypatch.setattr(condition_parser, "call_llm", hallucinated_evidence_llm)
    source_text = "当零件具有复杂异形轮廓时，纳入磨外圆工序"
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        source_text,
        "process_grind_outer",
        "磨外圆",
        PROCESSES,
    )

    assert candidate is not None
    assert candidate.evidence
    assert candidate.evidence in source_text
    assert candidate.evidence != "图纸明确标注复杂异形轮廓"
    assert confidence == 0.92
    assert any("标准因子" in issue for issue in issues)


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
async def test_manual_boolean_rule_is_confirmed_without_model_parsing():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    candidate = condition_parser.RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"field": "project_factor.manual_process_487e1c0a", "op": "eq", "value": True},
        "then": {"include_process_ids": ["process_mark"], "exclude_process_ids": []},
        "field_definitions": [{
            "key": "project_factor.manual_process_487e1c0a",
            "label": "是否需要标记",
            "category": "可选工序",
            "type": "boolean",
            "operators": ["eq", "neq"],
            "source": "用户直接设定",
            "allow_custom": False,
        }],
        "preview": "是否需要标记 等于 是",
    })

    async with session_factory() as session:
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_mark"}]',
        ))
        await session.commit()
        response = await set_manual_condition_review(
            ManualRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_mark",
                process_id="process_mark",
                source_text="用户直接决定是否纳入标记工序",
                candidate=candidate,
                processes=[RuleConditionProcessOption(process_id="process_mark", display_name="标记")],
                confirmed_by="用户直接设定",
            ),
            session,
        )

        assert response.review.status == "confirmed"
        assert response.review.confirmed is not None
        assert response.review.confirmed.when is not None
        assert response.review.confirmed.when.field == "project_factor.manual_process_487e1c0a"
        assert response.review.confirmed.when.factor_id is None
        assert response.review.confirmed_by == "用户直接设定"

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_rejects_unknown_unbound_standard_value():
    """Changing confirmation to skip binding checks would permit an unmapped condition."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source_text = "当精度等级包含未知精加工时，纳入磨外圆工序"
    candidate = condition_parser.RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"field": "precision.grades", "op": "contains", "value": "未知精加工"},
        "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
    })

    async with session_factory() as session:
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind_outer"}]',
        ))
        session.add(NormalizedRouteSegmentRuleReview(
            project_id=7,
            route_version_id=1,
            segment_id="process_grind_outer",
            decision="accepted",
            note="",
            summary_json="[]",
            question_trail_json="[]",
            condition_status="pending_confirmation",
            condition_source_text=source_text,
            condition_source_hash=condition_source_hash(source_text),
            condition_candidate_json=json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False),
        ))
        await session.commit()

        with pytest.raises(HTTPException) as error:
            await confirm_condition_review(
                ConfirmRuleConditionRequest(
                    project_id=7,
                    route_id=1,
                    segment_id="process_grind_outer",
                    source_text=source_text,
                    source_hash=condition_source_hash(source_text),
                    candidate=candidate,
                    processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
                    confirmed_by="测试用户",
                ),
                session,
            )

    assert error.value.status_code == 422
    assert "标准因子" in str(error.value.detail)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("boolean_value", [True, False], ids=["eq_true", "eq_false"])
async def test_confirm_rejects_custom_boolean_without_guessing_semantics(boolean_value):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source_text = "当零件需要保留批次链路时，安排标记工序"
    candidate = condition_parser.RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {
            "field": "custom.requirements.traceability_marking_required",
            "op": "eq",
            "value": boolean_value,
        },
        "then": {"include_process_ids": ["process_mark"], "exclude_process_ids": []},
        "field_definitions": [{
            "key": "custom.requirements.traceability_marking_required",
            "label": "是否需要追溯标识",
            "category": "特殊要求",
            "type": "boolean",
            "operators": ["eq", "neq"],
            "aliases": ["追溯", "编号"],
            "source": "模型候选",
            "options": [],
            "allow_custom": False,
        }],
    })

    async with session_factory() as session:
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_mark"}]',
        ))
        session.add(NormalizedRouteSegmentRuleReview(
            project_id=7,
            route_version_id=1,
            segment_id="process_mark",
            decision="accepted",
            note="",
            summary_json="[]",
            question_trail_json="[]",
            condition_status="pending_confirmation",
            condition_source_text=source_text,
            condition_source_hash=condition_source_hash(source_text),
            condition_candidate_json=json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False),
        ))
        await session.commit()

        with pytest.raises(HTTPException) as error:
            await confirm_condition_review(
                ConfirmRuleConditionRequest(
                    project_id=7,
                    route_id=1,
                    segment_id="process_mark",
                    source_text=source_text,
                    source_hash=condition_source_hash(source_text),
                    candidate=candidate,
                    processes=[RuleConditionProcessOption(process_id="process_mark", display_name="标记")],
                    confirmed_by="测试用户",
                ),
                session,
            )

        assert error.value.status_code == 422
        assert "标准因子" in str(error.value.detail)
        review = (await session.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.segment_id == "process_mark",
            )
        )).scalars().one()
        assert review.condition_status == "pending_confirmation"
        assert review.condition_confirmed_json is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_rejects_the_second_unbound_compound_leaf():
    """The second branch must not be hidden when the first branch is bound."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source_text = "孔精加工且未知精加工时，纳入磨外圆工序"
    candidate = condition_parser.RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"all": [
            {"field": "precision.grades", "op": "contains", "value": "孔精加工", "factor_id": "precision.hole_finish"},
            {"field": "precision.grades", "op": "contains", "value": "未知精加工"},
        ]},
        "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
    })

    async with session_factory() as session:
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind_outer"}]',
        ))
        session.add(NormalizedRouteSegmentRuleReview(
            project_id=7,
            route_version_id=1,
            segment_id="process_grind_outer",
            decision="accepted",
            note="",
            summary_json="[]",
            question_trail_json="[]",
            condition_status="pending_confirmation",
            condition_source_text=source_text,
            condition_source_hash=condition_source_hash(source_text),
            condition_candidate_json=json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False),
        ))
        await session.commit()

        with pytest.raises(HTTPException) as error:
            await confirm_condition_review(
                ConfirmRuleConditionRequest(
                    project_id=7,
                    route_id=1,
                    segment_id="process_grind_outer",
                    source_text=source_text,
                    source_hash=condition_source_hash(source_text),
                    candidate=candidate,
                    processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
                    confirmed_by="测试用户",
                ),
                session,
            )

    assert error.value.status_code == 422
    assert error.value.detail["issues"][0]["path"] == "all[1]"
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_boolean_rule_rejects_wrong_target_and_spoofed_shape():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    candidate = condition_parser.RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"field": "project_factor.some_other_switch", "op": "eq", "value": True},
        "then": {"include_process_ids": ["process_other"], "exclude_process_ids": []},
        "field_definitions": [{
            "key": "project_factor.some_other_switch",
            "label": "伪造字段",
            "category": "可选工序",
            "type": "boolean",
            "operators": ["eq"],
            "source": "伪造来源",
            "allow_custom": True,
        }],
    })

    async with session_factory() as session:
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_mark"},{"id":"process_other"}]',
        ))
        await session.commit()
        with pytest.raises(HTTPException, match="人工 Bool"):
            await set_manual_condition_review(
                ManualRuleConditionRequest(
                    project_id=7,
                    route_id=1,
                    segment_id="process_mark",
                    process_id="process_mark",
                    source_text="用户决定是否纳入标记工序",
                    candidate=candidate,
                    processes=[
                        RuleConditionProcessOption(process_id="process_mark", display_name="标记"),
                        RuleConditionProcessOption(process_id="process_other", display_name="其他"),
                    ],
                    confirmed_by="攻击者",
                ),
                session,
            )

    await engine.dispose()


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
        session.add_all([Project(id=7, name="条件解析测试"), route])
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
        session.add_all([Project(id=7, name="条件解析测试"), route])
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
async def test_parse_review_reuses_current_candidate_without_calling_parser(monkeypatch):
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
            route_json='[{"id":"process_grind_outer"}]',
        )
        session.add_all([Project(id=7, name="条件解析测试"), route])
        await session.commit()

        first = await parse_condition_review(
            ParseRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text=source_text,
                process_id="process_grind_outer",
                process_name="磨外圆",
                processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
            ),
            session,
        )
        assert first.review.status == "pending_confirmation"

        async def unexpected_parse(*args, **kwargs):
            raise AssertionError("同一原文不应重复调用解析器")

        monkeypatch.setattr(condition_reviews, "parse_rule_condition", unexpected_parse)
        cached = await condition_reviews.parse_condition_review(
            ParseRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text=source_text,
                process_id="process_grind_outer",
                process_name="磨外圆",
                processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
            ),
            session,
        )

        assert cached.review.status == "pending_confirmation"
        assert cached.review.candidate == first.review.candidate

    await engine.dispose()


@pytest.mark.asyncio
async def test_parse_review_invalidates_cache_when_parser_version_changes(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source_text = "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序"
    request = ParseRuleConditionRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text=source_text,
        process_id="process_grind_outer",
        process_name="磨外圆",
        processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
    )

    async with session_factory() as session:
        session.add(Project(id=7, name="条件解析测试"))
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind_outer"}]',
        ))
        await session.commit()
        first = await parse_condition_review(request, session)
        assert first.review.candidate is not None

        row = (await session.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == 1,
                NormalizedRouteSegmentRuleReview.segment_id == "process_grind_outer",
            )
        )).scalars().one()
        row.condition_parser_version = "outdated"
        await session.commit()

        calls = 0

        async def reparsed(*args, **kwargs):
            nonlocal calls
            calls += 1
            return first.review.candidate, 0.9, []

        monkeypatch.setattr(condition_reviews, "parse_rule_condition", reparsed)
        refreshed = await condition_reviews.parse_condition_review(request, session)

        assert calls == 1
        assert refreshed.review.parser_version
        assert refreshed.review.parser_version != "outdated"

    await engine.dispose()


@pytest.mark.asyncio
async def test_parse_review_uses_same_llm_config_for_version_and_inference(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    resolved_config = {"url": "https://example.test/v1/chat/completions", "key": "secret", "model": "model-a"}
    captured_config = None

    async def fixed_config():
        return resolved_config

    async def capture_llm(*args, config=None, **kwargs):
        nonlocal captured_config
        captured_config = config
        return ""

    monkeypatch.setattr(condition_reviews, "get_llm_config", fixed_config)
    monkeypatch.setattr(condition_parser, "call_llm", capture_llm)

    async with session_factory() as session:
        session.add(Project(id=7, name="条件解析测试"))
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind_outer"}]',
        ))
        await session.commit()
        await parse_condition_review(
            ParseRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text="复杂条件",
                process_id="process_grind_outer",
                process_name="磨外圆",
                processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
            ),
            session,
        )

    assert captured_config == resolved_config
    await engine.dispose()


@pytest.mark.asyncio
async def test_older_parse_does_not_overwrite_newer_parser_version(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(Project(id=7, name="条件解析测试"))
        session.add(NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind_outer"}]',
        ))
        await session.commit()

        async def superseded_parser(*args, **kwargs):
            row = (await session.execute(
                select(NormalizedRouteSegmentRuleReview).where(
                    NormalizedRouteSegmentRuleReview.route_version_id == 1,
                    NormalizedRouteSegmentRuleReview.segment_id == "process_grind_outer",
                )
            )).scalars().one()
            row.condition_parser_version = "newer-parser-version"
            row.condition_status = "draft"
            row.condition_candidate_json = None
            await session.commit()
            candidate = condition_parser.RuleConditionCandidate.model_validate({
                "kind": "condition",
                "when": {"field": "precision.outer_diameter_it", "op": "lte", "value": 8},
                "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
                "preview": "旧解析结果",
            })
            return candidate, 0.9, []

        monkeypatch.setattr(condition_reviews, "parse_rule_condition", superseded_parser)
        response = await parse_condition_review(
            ParseRuleConditionRequest(
                project_id=7,
                route_id=1,
                segment_id="process_grind_outer",
                source_text="复杂条件",
                process_id="process_grind_outer",
                process_name="磨外圆",
                processes=[RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
            ),
            session,
        )

        assert response.review.parser_version == "newer-parser-version"
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
@pytest.mark.parametrize("boolean_value", [True, False], ids=["eq_true", "eq_false"])
async def test_saved_route_reopens_confirmed_custom_boolean_without_rewriting_semantics(boolean_value):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(Project(id=7, name="自定义 Bool 迁移"))
        route = NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            segment_count=1,
            route_json='[{"id":"process_mark","sequence":10,"normalized_step_name":"标记"}]',
        )
        legacy_candidate = {
            "kind": "condition",
            "when": {
                "field": "custom.requirements.traceability_marking_required",
                "op": "eq",
                "value": boolean_value,
            },
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
            "preview": f"是否需要追溯标识 等于 {'是' if boolean_value else '否'}",
        }
        session.add(route)
        row = NormalizedRouteSegmentRuleReview(
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
            condition_confirmed_by="旧确认用户",
        )
        session.add(row)
        await session.commit()

        response = await build_saved_normalized_route_response(route, session)
        condition_review = response.segments[0].rule_review.condition_review

        assert condition_review.status == "pending_confirmation"
        assert condition_review.confirmed is None
        assert condition_review.confirmed_by == ""
        assert condition_review.candidate is not None
        assert condition_review.candidate.when is not None
        assert condition_review.candidate.when.field == "custom.requirements.traceability_marking_required"
        assert condition_review.candidate.when.op == "eq"
        assert condition_review.candidate.when.value is boolean_value
        assert condition_review.candidate.when.factor_id is None
        assert len(condition_review.candidate.field_definitions) == 1
        assert condition_review.candidate.field_definitions[0].key == "custom.requirements.traceability_marking_required"
        assert any("标准因子" in issue for issue in condition_review.issues)

    await engine.dispose()


@pytest.mark.asyncio
async def test_migrates_only_valid_unpublished_standard_factor_reviews():
    """A migration regression must not retain confirmations for unmapped leaves or removed actions."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def condition(when, include_process_id):
        return {
            "kind": "condition",
            "when": when,
            "then": {"include_process_ids": [include_process_id], "exclude_process_ids": []},
        }

    async with session_factory() as session:
        project = Project(id=7, name="标准因子迁移")
        route = NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json=json.dumps([
                {"id": "process_keep", "normalized_step_name": "保留工序"},
                {"id": "process_unknown", "normalized_step_name": "未知条件工序"},
                {"id": "process_compound", "normalized_step_name": "复合条件工序"},
                {"id": "process_changed", "normalized_step_name": "目标已改变"},
            ], ensure_ascii=False),
        )
        known_payload = condition(
            {"field": "precision.grades", "op": "contains", "value": "孔精加工"},
            "process_keep",
        )
        unknown_payload = condition(
            {"field": "precision.grades", "op": "contains", "value": "未知精加工"},
            "process_unknown",
        )
        compound_payload = condition(
            {"all": [
                {"field": "precision.grades", "op": "contains", "value": "孔精加工"},
                {"field": "precision.grades", "op": "contains", "value": "未知精加工"},
            ]},
            "process_compound",
        )
        removed_target_payload = condition(
            {"field": "precision.grades", "op": "contains", "value": "孔精加工"},
            "process_removed",
        )

        def review(segment_id, payload):
            raw = json.dumps(payload, ensure_ascii=False)
            return NormalizedRouteSegmentRuleReview(
                project_id=7,
                route_version_id=1,
                segment_id=segment_id,
                decision="accepted",
                note="",
                summary_json="[]",
                question_trail_json="[]",
                condition_status="confirmed",
                condition_candidate_json=raw,
                condition_confirmed_json=raw,
                condition_confirmed_by="旧确认用户",
                condition_confirmed_at=None,
                condition_field_registry_version="2025.01",
            )

        known_row = review("process_keep", known_payload)
        unknown_row = review("process_unknown", unknown_payload)
        compound_row = review("process_compound", compound_payload)
        removed_target_row = review("process_changed", removed_target_payload)
        session.add_all([
            project,
            route,
            known_row,
            unknown_row,
            compound_row,
            removed_target_row,
        ])
        await session.commit()

        assert await migrate_legacy_standard_factor_reviews(route, session) is True
        assert await migrate_legacy_standard_factor_reviews(route, session) is False

        known = serialize_condition_review(known_row)
        unknown = serialize_condition_review(unknown_row)
        compound = serialize_condition_review(compound_row)
        removed_target = serialize_condition_review(removed_target_row)

    assert known.status == "confirmed"
    assert known.confirmed is not None
    assert known.confirmed.when is not None
    assert known.confirmed.when.factor_id == "precision.hole_finish"
    assert known.field_registry_version == "2026.11"
    for review in (unknown, compound, removed_target):
        assert review.status == "pending_confirmation"
        assert review.confirmed is None
        assert review.candidate is not None
        assert review.issues
    assert unknown.candidate.when is not None
    assert unknown.candidate.when.factor_id is None
    assert any("标准因子" in issue for issue in unknown.issues)
    assert any("all[1]" in issue for issue in compound.issues)
    assert any("当前路线中不存在" in issue for issue in removed_target.issues)
    await engine.dispose()


@pytest.mark.asyncio
async def test_standard_factor_migration_clears_stale_pending_issues_and_preserves_selected_ids():
    """Migration must clear repaired draft errors but invalidate a removed selected factor."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    confirmed_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    def candidate(factor_id=None):
        when = {"field": "precision.grades", "op": "contains", "value": "孔精加工"}
        if factor_id is not None:
            when["factor_id"] = factor_id
        return {
            "kind": "condition",
            "when": when,
            "then": {"include_process_ids": ["process_target"], "exclude_process_ids": []},
        }

    async with session_factory() as session:
        route = NormalizedRouteVersion(
            id=1,
            project_id=7,
            version=1,
            route_json='[{"id":"process_target","normalized_step_name":"目标工序"}]',
        )

        def review(segment_id, payload, *, status, confirmed, issues, confirmed_by=None, confirmed_time=None):
            raw = json.dumps(payload, ensure_ascii=False)
            return NormalizedRouteSegmentRuleReview(
                project_id=7,
                route_version_id=1,
                segment_id=segment_id,
                decision="accepted",
                note="",
                summary_json="[]",
                question_trail_json="[]",
                condition_status=status,
                condition_candidate_json=raw,
                condition_confirmed_json=raw if confirmed else None,
                condition_issues_json=json.dumps(issues, ensure_ascii=False),
                condition_field_registry_version="2025.01",
                condition_confirmed_by=confirmed_by,
                condition_confirmed_at=confirmed_time,
            )

        pending = review(
            "pending",
            candidate(),
            status="pending_confirmation",
            confirmed=False,
            issues=["条件尚未绑定标准因子"],
        )
        still_valid = review(
            "valid",
            candidate("precision.hole_finish"),
            status="confirmed",
            confirmed=True,
            issues=[],
            confirmed_by="旧确认用户",
            confirmed_time=confirmed_at,
        )
        removed = review(
            "removed",
            candidate("precision.removed_factor"),
            status="confirmed",
            confirmed=True,
            issues=[],
            confirmed_by="旧确认用户",
            confirmed_time=confirmed_at,
        )
        session.add_all([route, pending, still_valid, removed])
        await session.commit()

        assert await migrate_legacy_standard_factor_reviews(route, session) is True
        pending_view = serialize_condition_review(pending)
        valid_view = serialize_condition_review(still_valid)
        removed_view = serialize_condition_review(removed)

    assert pending_view.status == "pending_confirmation"
    assert pending_view.confirmed is None
    assert pending_view.candidate is not None
    assert pending_view.candidate.when is not None
    assert pending_view.candidate.when.factor_id == "precision.hole_finish"
    assert pending_view.issues == []
    assert pending_view.field_registry_version == "2026.11"

    assert valid_view.status == "confirmed"
    assert valid_view.confirmed is not None
    assert valid_view.confirmed.when is not None
    assert valid_view.confirmed.when.factor_id == "precision.hole_finish"
    assert valid_view.confirmed_by == "旧确认用户"
    assert valid_view.confirmed_at == confirmed_at.isoformat()
    assert valid_view.field_registry_version == "2026.11"

    assert removed_view.status == "pending_confirmation"
    assert removed_view.confirmed is None
    assert removed_view.candidate is not None
    assert removed_view.confirmed_by == ""
    assert removed_view.confirmed_at == ""
    assert any(issue.startswith("when:") for issue in removed_view.issues)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("boolean_value", [True, False], ids=["eq_true", "eq_false"])
async def test_model_custom_boolean_remains_explicit_and_unbound(monkeypatch, boolean_value):
    async def legacy_boolean_llm(*args, **kwargs):
        return json.dumps({
            "candidate": {
                "kind": "condition",
                "when": {
                    "field": "custom.requirements.traceability_marking_required",
                    "op": "eq",
                    "value": boolean_value,
                },
                "then": {"include_process_ids": ["process_mark"], "exclude_process_ids": []},
                "field_definitions": [{
                    "key": "custom.requirements.traceability_marking_required",
                    "label": "是否需要追溯标识",
                    "category": "特殊要求",
                    "type": "boolean",
                    "operators": ["eq", "neq"],
                    "aliases": ["追溯", "编号"],
                    "source": "模型候选",
                    "options": [],
                    "allow_custom": False,
                }],
                "preview": f"是否需要追溯标识 等于 {'是' if boolean_value else '否'}",
            },
            "confidence": 0.9,
            "warnings": [],
            "unresolved": [],
        }, ensure_ascii=False)

    monkeypatch.setattr(condition_parser, "call_llm", legacy_boolean_llm)
    processes = [RuleConditionProcessOption(process_id="process_mark", display_name="标记")]
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当零件需要保留批次链路时，安排标记工序",
        "process_mark",
        "标记",
        processes,
    )

    assert candidate is not None
    assert candidate.when is not None
    assert candidate.when.field == "custom.requirements.traceability_marking_required"
    assert candidate.when.op == "eq"
    assert candidate.when.value is boolean_value
    assert candidate.when.factor_id is None
    assert len(candidate.field_definitions) == 1
    assert candidate.field_definitions[0].key == "custom.requirements.traceability_marking_required"
    assert confidence == 0.9
    assert any("标准因子" in issue for issue in issues)
