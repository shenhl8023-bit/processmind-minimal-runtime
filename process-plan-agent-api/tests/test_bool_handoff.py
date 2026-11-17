"""Regressions for PM-029 using project 5 node identities and guided DTOs."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services import rule_preprocessing
from app.services.analysis_drafts import AnalysisRuleDraft
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.route_analysis import save_segment_rule_review_record
from app.services.rule_packages import condition_parser, condition_reviews
from app.services.rule_packages.compiler import compile_rule_package
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest, RuleConditionProcessOption, RulePreprocessItem,
)
from app.services.rule_packages.contracts import CompileRulePackageRequest, InputField
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.validator import validate_rule_package


NODES = [
    ("split-900027", "镀铜", "project_factor.manual_process_8336b02c"),
    ("split-900040", "研顶尖孔", "project_factor.manual_process_8645bf6f"),
    ("split-900044", "检验", "project_factor.manual_process_8245b923"),
]


@pytest_asyncio.fixture
async def sessions(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bool-handoff.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await ensure_project_schema(connection)

    async def parser_context():
        return condition_parser.CONDITION_PARSER_VERSION + ":test", {}

    monkeypatch.setattr(rule_preprocessing, "async_session", factory)
    monkeypatch.setattr(rule_preprocessing, "_active_condition_parser_context", parser_context)
    monkeypatch.setattr(condition_reviews, "_active_condition_parser_context", parser_context)
    try:
        yield factory
    finally:
        await engine.dispose()


def manual_candidate(process_id, name, field_key):
    return {
        "kind": "process_configuration",
        "configuration": {
            "process_id": process_id, "occurrence": "manual",
            "when": {"field": field_key, "op": "eq", "value": True}, "relations": [],
        },
        "field_definitions": [{
            "key": field_key, "label": "是否需要" + name, "category": "可选工序",
            "type": "boolean", "operators": ["eq", "neq"], "aliases": [],
            "required": False, "source": "用户直接设定", "options": [], "allow_custom": False,
        }],
        "preview": name + "由用户每次决定是否安排。", "evidence": "用户确认的第三步回答",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("process_id,name,field_key", NODES)
@pytest.mark.parametrize("entry", ["manual_answer", "recommended_answer", "text_reidentify"])
async def test_bool_survives_preprocessing_confirmation_compile_and_execution(
    sessions, monkeypatch, process_id, name, field_key, entry,
):
    # A missing text/manual branch must fail here; a valid guided draft must
    # bypass inference entirely. Both UI answer producers save the same DTO.
    source_text = name + "由用户每次决定是否安排。"
    processes = [
        RuleConditionProcessOption(process_id="split-900015", display_name="检验", main=True),
        RuleConditionProcessOption(process_id=process_id, display_name=name),
    ]
    async with sessions() as db:
        db.add_all([
            Project(id=5, name="Bool 交接回归", workflow_revision=7),
            NormalizedRouteVersion(id=1, project_id=5, version=1, route_json=json.dumps([
                {"id": "split-900015", "export_process_id": "split-900015", "sequence": 130, "normalized_step_name": "检验"},
                {"id": process_id, "export_process_id": process_id, "sequence": 400, "normalized_step_name": name},
            ], ensure_ascii=False)),
        ])
        await db.commit()
        if entry != "text_reidentify":
            await save_segment_rule_review_record(
                project_id=5, route_id=1, segment_id=process_id, decision="accepted", note="",
                summary_lines=[], question_trail=[{
                    "nodeId": "guided_mode", "value": "manual",
                    "label": "做不做，到时由我来定" if entry == "manual_answer" else "由用户决定是否出现",
                }],
                analysis_draft=AnalysisRuleDraft(
                    scope="当前工序：" + name, object=name, condition_text=source_text,
                    candidate=manual_candidate(process_id, name, field_key), status="confirmed",
                    provenance=[{"kind": "user", "label": "第三步确认", "evidence": "项目配置版本1"}],
                ), db=db,
            )

    if entry != "text_reidentify":
        async def forbidden_parser(*args, **kwargs):
            raise AssertionError("结构化 Bool 不能降级为自然语言重识别")

        monkeypatch.setattr(condition_reviews, "parse_rule_condition", forbidden_parser)
    else:
        async def unavailable_model(*args, **kwargs):
            return None, None, ["测试模型不可用"]

        monkeypatch.setattr(condition_parser, "_parse_with_llm", unavailable_model)
    await rule_preprocessing._run_job(
        project_id=5, route_id=1, workflow_revision=7, processes=processes,
        items=[RulePreprocessItem(segment_id=process_id, process_id=process_id,
                                  process_name=name, source_text=source_text)],
    )
    async with sessions() as db:
        row = (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalar_one()
        assert row.condition_status == "pending_confirmation", row.condition_issues_json
        assert row.condition_confirmed_json is None
        candidate = condition_reviews.serialize_condition_review(row).candidate
        assert candidate.kind == "process_configuration"
        assert candidate.configuration.occurrence == "manual"
        assert candidate.configuration.process_id == process_id
        assert candidate.configuration.when.field == field_key
        assert candidate.configuration.when.value is True
        assert candidate.field_definitions[0].type == "boolean"
        assert candidate.field_definitions[0].source == "用户直接设定"
        assert candidate.field_definitions[0].allow_custom is False
        assert condition_parser.validate_candidate(candidate, processes, current_process_id=process_id) == []

        confirmed = await condition_reviews.confirm_condition_review(ConfirmRuleConditionRequest(
            project_id=5, route_id=1, segment_id=process_id, source_text=source_text,
            source_hash=row.condition_source_hash, candidate=candidate, processes=processes,
        ), db)
        assert confirmed.review.status == "confirmed"
        candidate = confirmed.review.confirmed
        field = candidate.field_definitions[0]
        package = compile_rule_package(CompileRulePackageRequest(
            project_id=5, route_version_id=1, package_name="Bool 交接回归",
            fields=[InputField(**{key: value for key, value in field.model_dump().items()
                                 if key in InputField.model_fields})],
            processes=[{"process_id": "split-900015", "display_name": "检验", "main": True, "default_sequence": 130},
                       {"process_id": process_id, "display_name": name, "main": False, "default_sequence": 400}],
            process_configurations=[candidate.configuration.model_dump(by_alias=True)],
        ))
        assert validate_rule_package(package).valid
        assert plan_route(package, {}).selected_process_ids == ["split-900015"]
        assert plan_route(package, {field_key: False}).selected_process_ids == ["split-900015"]
        assert plan_route(package, {field_key: True}).selected_process_ids == ["split-900015", process_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_text", [
    "镀铜由用户每次决定是否安排，且材料为9Cr18。",
    "当需要镀铜时，由用户每次决定是否安排。",
    "检验由用户每次决定是否安排。",
    "镀铜不是由用户每次决定是否安排。",
    "根据工艺要求决定是否安排镀铜。",
])
async def test_manual_words_do_not_override_additional_conditions_or_another_node(monkeypatch, source_text):
    async def unavailable_model(*args, **kwargs):
        return None, None, []

    monkeypatch.setattr(condition_parser, "_parse_with_llm", unavailable_model)
    candidate, _, _ = await condition_parser.parse_rule_condition(
        source_text, "split-900027", "镀铜",
        [RuleConditionProcessOption(process_id="split-900027", display_name="镀铜")],
    )
    assert candidate is None or candidate.kind != "process_configuration" or candidate.configuration.occurrence != "manual"
