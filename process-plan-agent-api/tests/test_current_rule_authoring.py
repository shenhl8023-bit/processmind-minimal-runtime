"""Regressions for the current editor contract across persistence boundaries."""

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services.analysis_drafts import AnalysisRuleDraft
from app.services.rule_packages import condition_reviews
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest, ManualRuleConditionRequest, ParseRuleConditionRequest,
    RuleConditionCandidate, RuleConditionProcessOption,
)
from app.services.rule_packages.confirmation_validation import require_confirmed_user_rule_sources
from app.services.rule_packages.contracts import RulePackageV2


LEAF = {"field": "material.grade", "op": "eq", "value": "6061"}
SOURCE = "当材料满足要求时，纳入检验工序。"
PROCESSES = [RuleConditionProcessOption(process_id="prepare", display_name="准备", main=True),
             RuleConditionProcessOption(process_id="inspect", display_name="检验")]
INVALID_CONDITIONS = [
    {"any": [LEAF, {**LEAF, "value": "9Cr18"}]}, {"not": LEAF},
    {"field": "special.requirements", "op": "contains_all", "value": []},
    {"field": "special.requirements", "op": "contains_any", "value": [""]},
    {**LEAF, "value": "  "},
]


def condition(when=LEAF):
    return RuleConditionCandidate.model_validate({"when": when, "then": {"include_process_ids": ["inspect"]}})


def relation(kind="trigger_after"):
    return {"relation_type": kind, "source_process_ids": ["prepare"], "target_process_ids": ["inspect"]}


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all([Project(id=7, name="隔离编写校验"), NormalizedRouteVersion(
            id=1, project_id=7, version=1,
            route_json='[{"id":"prepare","normalized_step_name":"准备"},{"id":"inspect","normalized_step_name":"检验"}]',
        )])
        await db.commit()
        yield db
    await engine.dispose()


async def pending(db, candidate):
    row = NormalizedRouteSegmentRuleReview(
        project_id=7, route_version_id=1, segment_id="inspect", decision="accepted",
        condition_source_text=SOURCE, condition_source_hash=condition_reviews.condition_source_hash(SOURCE),
        condition_status="pending_confirmation", condition_candidate_json=candidate.model_dump_json(by_alias=True),
    )
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("when", INVALID_CONDITIONS)
async def test_confirmation_rejects_unsupported_or_incomplete_current_candidates(session, when):
    candidate = condition(when)
    row = await pending(session, candidate)
    with pytest.raises(HTTPException) as error:
        await condition_reviews.confirm_condition_review(ConfirmRuleConditionRequest(
            project_id=7, route_id=1, segment_id="inspect", source_text=SOURCE,
            source_hash=row.condition_source_hash, candidate=candidate, processes=PROCESSES,
        ), session)
    assert error.value.status_code == 422
    assert row.condition_status == "pending_confirmation"
    assert row.condition_confirmed_json is None


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [
    {"occurrence": "conditional", "when": INVALID_CONDITIONS[0], "relations": []},
    {"occurrence": "conditional", "when": LEAF, "relations": [relation()]},
    {"occurrence": "always", "relations": [relation("order_after")]},
])
async def test_configuration_save_rejects_mixed_or_unsupported_modes(session, config):
    candidate = RuleConditionCandidate.model_validate({"kind": "process_configuration", "configuration": {"process_id": "inspect", **config}})
    with pytest.raises(HTTPException) as error:
        await condition_reviews.set_process_configuration_review(ManualRuleConditionRequest(
            project_id=7, route_id=1, segment_id="inspect", process_id="inspect",
            source_text=SOURCE, candidate=candidate, processes=PROCESSES,
        ), session)
    assert error.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("when", INVALID_CONDITIONS[:3])
async def test_publication_refuses_exactly_confirmed_but_unsupported_rules(session, when):
    candidate = condition(when)
    row = await pending(session, candidate)
    at = datetime.now(timezone.utc)
    row.condition_status = "confirmed"
    row.condition_confirmed_json = candidate.model_dump_json(by_alias=True)
    row.condition_confirmed_by = "审核员"
    row.condition_confirmed_at = at
    await session.commit()
    package = RulePackageV2.model_validate({
        "manifest": {"package_name": "审核", "project_id": 7, "route_version_id": 1, "scope": {"key": "7"}},
        "input_schema": {"fields": []}, "route_catalog": {"processes": [p.model_dump() for p in PROCESSES]},
        "route_rules": {"rules": [{"rule_id": "user.inspect", "when": when, "then": {"include_process_ids": ["inspect"]},
            "source": "user_confirmed", "source_segment_id": "inspect", "source_text": SOURCE,
            "confirmed_by": "审核员", "confirmed_at": at.isoformat()}]},
    })
    with pytest.raises(HTTPException) as error:
        await require_confirmed_user_rule_sources(package, project_id=7, route_version_id=1, db=session)
    assert error.value.status_code == 409
    assert "inspect" in error.value.detail["segment_ids"]
    assert json.loads(row.condition_confirmed_json)["when"] == candidate.when.model_dump(by_alias=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_parse_does_not_reuse_unsupported_analysis_or_pending_candidate(session, monkeypatch, cached):
    candidate = condition(INVALID_CONDITIONS[0])
    row = await pending(session, candidate)
    row.condition_field_registry_version = condition_reviews.FIELD_REGISTRY_VERSION
    row.condition_parser_version = "new-parser"
    if not cached:
        row.analysis_draft_json = AnalysisRuleDraft(scope="全部", object="检验", condition_text=SOURCE,
            candidate=candidate, status="confirmed").model_dump_json()
    await session.commit()
    calls = []
    async def context():
        return "new-parser", {}
    async def parse(*args, **kwargs):
        calls.append(args[0])
        return None, None, ["请明确设置全部满足的条件。"]
    monkeypatch.setattr(condition_reviews, "_active_condition_parser_context", context)
    monkeypatch.setattr(condition_reviews, "parse_rule_condition", parse)
    result = await condition_reviews.parse_condition_review(ParseRuleConditionRequest(
        project_id=7, route_id=1, segment_id="inspect", source_text=SOURCE, process_id="inspect",
        process_name="检验", processes=PROCESSES,
    ), session)
    assert calls == [SOURCE]
    assert result.review.status == "invalid"
    assert result.review.candidate is None
    assert result.review.issues


@pytest.mark.asyncio
async def test_background_recognition_does_not_skip_unsupported_pending_candidate(session):
    from app.services.rule_preprocessing import _review_is_current
    from app.services.rule_packages.condition_contracts import RulePreprocessItem
    row = await pending(session, condition(INVALID_CONDITIONS[0]))
    row.condition_field_registry_version = condition_reviews.FIELD_REGISTRY_VERSION
    row.condition_parser_version = "new-parser"
    await session.commit()
    assert not await _review_is_current(session, 7, 1, RulePreprocessItem(
        segment_id="inspect", process_id="inspect", process_name="检验", source_text=SOURCE,
    ), "new-parser", PROCESSES)


@pytest.mark.asyncio
async def test_persistence_rechecks_parser_output_before_marking_pending(session, monkeypatch):
    async def context():
        return "new-parser", {}
    async def parse(*args, **kwargs):
        return condition(INVALID_CONDITIONS[0]), .9, []
    monkeypatch.setattr(condition_reviews, "_active_condition_parser_context", context)
    monkeypatch.setattr(condition_reviews, "parse_rule_condition", parse)
    result = await condition_reviews.parse_condition_review(ParseRuleConditionRequest(
        project_id=7, route_id=1, segment_id="inspect", source_text=SOURCE, process_id="inspect",
        process_name="检验", processes=PROCESSES,
    ), session)
    assert result.review.status == "invalid"
    assert result.review.candidate is None
    assert result.review.issues


@pytest.mark.asyncio
@pytest.mark.parametrize("status_fields, expected_status", [
    ({"warnings": None, "unresolved": []}, "pending_confirmation"),
    ({"warnings": [], "unresolved": None}, "pending_confirmation"),
    ({"warnings": [], "unresolved": ["缺少阈值"], "confidence": "high"}, "invalid"),
])
async def test_model_response_status_fields_reach_a_saved_review_state(session, monkeypatch, status_fields, expected_status):
    from app.services.rule_packages import condition_parser
    from sqlalchemy import select

    async def context():
        return "response-format-regression", {}

    async def model(*args, **kwargs):
        return json.dumps({
            "candidate": {"when": LEAF, "then": {"include_process_ids": ["inspect"]}},
            "confidence": .96, **status_fields,
        }, ensure_ascii=False)

    monkeypatch.setattr(condition_reviews, "_active_condition_parser_context", context)
    monkeypatch.setattr(condition_parser, "call_llm", model)
    result = await condition_reviews.parse_condition_review(ParseRuleConditionRequest(
        project_id=7, route_id=1, segment_id="inspect", source_text="需要人工补充的复杂条件",
        process_id="inspect", process_name="检验", processes=PROCESSES,
    ), session)

    row = (await session.execute(select(NormalizedRouteSegmentRuleReview))).scalar_one()
    assert result.review.status == row.condition_status == expected_status
    assert row.condition_confirmed_json is None
    assert (row.condition_candidate_json is not None) == (expected_status == "pending_confirmation")
    expected_confidence = .96 if expected_status == "pending_confirmation" else None
    assert result.review.confidence == expected_confidence
    json.dumps(result.model_dump(mode="json"), allow_nan=False)


@pytest.mark.asyncio
async def test_quick_confirmation_rejects_association_cycle_before_saving(session):
    first = RuleConditionCandidate.model_validate({"kind": "process_relation", "relation": {
        "relation_type": "trigger_after", "source_process_ids": ["inspect"], "target_process_ids": ["prepare"],
    }})
    session.add(NormalizedRouteSegmentRuleReview(project_id=7, route_version_id=1, segment_id="prepare",
        decision="accepted", condition_status="confirmed", condition_confirmed_json=first.model_dump_json()))
    candidate = RuleConditionCandidate.model_validate({"kind": "process_relation", "relation": relation()})
    row = await pending(session, candidate)
    with pytest.raises(HTTPException) as error:
        await condition_reviews.confirm_condition_review(ConfirmRuleConditionRequest(
            project_id=7, route_id=1, segment_id="inspect", source_text=SOURCE,
            source_hash=row.condition_source_hash, candidate=candidate, processes=PROCESSES,
        ), session)
    assert error.value.status_code == 422
    assert "环" in str(error.value.detail)
    assert row.condition_status == "pending_confirmation"


@pytest.mark.asyncio
@pytest.mark.parametrize("bypass", ["static_include", "mainline", "extra_trigger", "extra_configuration", "prerequisite", "catalog_prerequisite", "configured_prerequisite", "disabled_configured_prerequisite", "disabled_static", "none"])
async def test_publication_preserves_confirmed_association_as_the_only_inclusion_mode(session, bypass):
    candidate = RuleConditionCandidate.model_validate({"kind": "process_relation", "relation": relation()})
    row = await pending(session, candidate)
    at = datetime.now(timezone.utc)
    row.condition_status = "confirmed"
    row.condition_confirmed_json = candidate.model_dump_json(by_alias=True)
    row.condition_confirmed_by = "审核员"
    row.condition_confirmed_at = at
    await session.commit()
    payload = {
        "manifest": {"package_name": "关联唯一出现方式", "project_id": 7, "route_version_id": 1, "scope": {"key": "7"}},
        "input_schema": {"fields": []},
        "route_catalog": {"processes": [p.model_dump() for p in PROCESSES] + [{"process_id": "other", "display_name": "其他"}]},
        "route_rules": {"rules": [], "process_relations": [{
            "relation_id": "user.inspect", **relation(), "source": "user_confirmed", "source_segment_id": "inspect",
            "source_text": SOURCE, "confirmed_by": "审核员", "confirmed_at": at.isoformat(),
        }]},
    }
    if bypass in {"static_include", "disabled_static"}:
        payload["route_rules"]["rules"].append({"rule_id": "static.inspect", "enabled": bypass == "static_include",
            "when": LEAF, "then": {"include_process_ids": ["inspect"]}})
    elif bypass == "mainline":
        payload["route_catalog"]["processes"][1]["main"] = True
    elif bypass == "extra_trigger":
        payload["route_rules"]["process_relations"].append({"relation_id": "static.inspect.other", **relation(),
            "source_process_ids": ["other"]})
    elif bypass == "extra_configuration":
        payload["route_rules"]["process_configurations"] = [{"process_id": "inspect", "occurrence": "always"}]
    elif bypass == "prerequisite":
        payload["route_rules"]["process_relations"].append({"relation_id": "static.other.requires.inspect",
            "relation_type": "requires", "source_process_ids": ["inspect"], "target_process_ids": ["other"]})
    elif bypass == "catalog_prerequisite":
        payload["route_catalog"]["processes"][2]["constraints"] = {"requires": ["inspect"]}
    elif bypass in {"configured_prerequisite", "disabled_configured_prerequisite"}:
        payload["route_rules"]["process_configurations"] = [{"process_id": "prepare", "occurrence": "always",
            "enabled": bypass == "configured_prerequisite", "relations": [{"relation_type": "requires",
                "source_process_ids": ["inspect"], "target_process_ids": ["prepare"]}]}]
    package = RulePackageV2.model_validate(payload)
    if bypass in {"none", "disabled_static", "disabled_configured_prerequisite"}:
        await require_confirmed_user_rule_sources(package, project_id=7, route_version_id=1, db=session)
    else:
        with pytest.raises(HTTPException) as error:
            await require_confirmed_user_rule_sources(package, project_id=7, route_version_id=1, db=session)
        assert error.value.status_code == 409
        assert "inspect" in error.value.detail["segment_ids"]
        assert "关联工序" in error.value.detail["message"]


@pytest.mark.asyncio
async def test_four_modes_save_publish_and_generate_with_default_false_and_chaining(session):
    from sqlalchemy import select
    from app.services.rule_packages.condition_registry import input_field_for
    from app.services.rule_packages.planner import plan_route
    from app.services.rule_packages.validator import validate_rule_package
    processes = [RuleConditionProcessOption(process_id=pid, display_name=pid, main=pid == "prepare")
                 for pid in ["prepare", "copper", "drill", "strip", "inspect"]]
    route = (await session.execute(select(NormalizedRouteVersion))).scalar_one()
    route.route_json = json.dumps([{"id": p.process_id} for p in processes])
    await session.commit()
    key = condition_reviews._manual_process_field_key("copper")
    definition = {"key": key, "label": "是否镀铜", "category": "人工选择", "type": "boolean",
                  "operators": ["eq"], "allow_custom": False, "source": "用户直接设定"}
    configs = [
        {"process_id": "prepare", "occurrence": "always"},
        {"process_id": "copper", "occurrence": "manual", "when": {"field": key, "op": "eq", "value": True}},
        {"process_id": "drill", "occurrence": "conditional", "when": {"all": [LEAF,
            {"field": "mechanical.hardness_hrc", "op": "gte", "value": 58}]}},
        {"process_id": "strip", "occurrence": "associated", "relations": [{
            "relation_type": "trigger_after", "source_process_ids": ["copper"], "target_process_ids": ["strip"]}]},
        {"process_id": "inspect", "occurrence": "associated", "relations": [{
            "relation_type": "trigger_after", "source_process_ids": ["strip"], "target_process_ids": ["inspect"]}]},
    ]
    published = []
    for config in configs:
        candidate = {"kind": "process_configuration", "configuration": config,
                     "field_definitions": [definition] if config["occurrence"] == "manual" else []}
        result = await condition_reviews.set_process_configuration_review(ManualRuleConditionRequest(
            project_id=7, route_id=1, segment_id=config["process_id"], process_id=config["process_id"],
            source_text="明确设置的出现模式", candidate=candidate, processes=processes,
        ), session)
        published.append({**result.review.confirmed.configuration.model_dump(mode="json", by_alias=True),
            "source": "user_confirmed", "source_segment_id": config["process_id"],
            "source_text": result.review.source_text, "confirmed_by": result.review.confirmed_by,
            "confirmed_at": result.review.confirmed_at})
    fields = [input_field_for(name).model_dump(mode="json") for name in ["material.grade", "mechanical.hardness_hrc"]]
    fields.append({name: value for name, value in definition.items() if name not in {"category", "operators"}})
    package = RulePackageV2.model_validate({
        "manifest": {"package_name": "完整链路", "project_id": 7, "route_version_id": 1, "scope": {"key": "7"}},
        "input_schema": {"fields": fields}, "route_catalog": {"processes": [p.model_dump() for p in processes]},
        "route_rules": {"process_configurations": published},
    })
    assert validate_rule_package(package).valid
    await require_confirmed_user_rule_sources(package, project_id=7, route_version_id=1, db=session)
    inputs = {"material": {"grade": "6061"}, "mechanical": {"hardness_hrc": 60}}
    assert set(plan_route(package, inputs).selected_process_ids) == {"prepare", "drill"}
    with_copper = {**inputs, "project_factor": {key.split(".", 1)[1]: True}}
    selected = plan_route(package, with_copper).selected_process_ids
    assert set(selected) == {p.process_id for p in processes}
    assert selected.index("copper") < selected.index("strip") < selected.index("inspect")
    assert "drill" not in plan_route(package, {**with_copper, "mechanical": {"hardness_hrc": 50}}).selected_process_ids
    assert "copper" not in plan_route(package, {**inputs, "project_factor": {key.split(".", 1)[1]: False}}).selected_process_ids
