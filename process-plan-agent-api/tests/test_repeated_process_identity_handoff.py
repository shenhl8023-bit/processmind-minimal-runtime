"""Repeated route nodes keep their saved identities across rule consumers."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services import rule_preprocessing
from app.services.analysis_drafts import AnalysisRuleDraft
from app.services.analysis_guidance_generation import _project_reference_configuration
from app.services.route_analysis import save_segment_rule_review_record
from app.services.route_merge.saved_route_segments import build_saved_route_version_segments
from app.services.rule_packages import condition_reviews
from app.services.rule_packages.compiler import compile_rule_package
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest, RuleConditionProcessOption, RulePreprocessItem,
)
from app.services.rule_packages.contracts import CompileRulePackageRequest, InputField
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.project_conditions import project_condition_scope
from app.services.rule_packages.validator import validate_rule_package
from test_bool_handoff import manual_candidate, sessions


def repeated_route():
    return build_saved_route_version_segments([
        {"id": "seg-quench-1", "normalized_step_name": "淬火", "source_operation_ids": [1]},
        {"id": "seg-quench-2", "normalized_step_name": "淬火", "source_operation_ids": [2]},
    ], [], 1)


@pytest.mark.parametrize("reverse", [False, True])
def test_saved_guide_recommendations_follow_repeated_node_identity(reverse):
    saved = repeated_route()
    previous = {"generation_route_id": 3, "generation_operation_ids": {
        "淬火#1": saved[0]["export_process_id"], "淬火#2": saved[1]["export_process_id"],
    }, "operation_guidance": {
        "淬火#1": {"recommendation": {"mode": "manual"}},
        "淬火#2": {"recommendation": {"mode": "mainline"}},
    }}
    current = build_saved_route_version_segments(list(reversed(saved)) if reverse else saved, [], 1)
    names = ["淬火#1", "淬火#2"]
    reference = _project_reference_configuration(
        {"operation_guidance": {}}, previous, names, 3,
        dict(zip(names, [item["export_process_id"] for item in current])),
    )
    expected = ["mainline", "manual"] if reverse else ["manual", "mainline"]
    assert [reference["operation_guidance"][name]["recommendation"]["mode"] for name in names] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_repeated_bool_drafts_confirm_and_execute_independently(sessions, monkeypatch, reverse):
    saved = repeated_route()
    source_text = "淬火由用户每次决定是否安排。"
    processes = [RuleConditionProcessOption(
        process_id=item["export_process_id"], display_name="淬火",
    ) for item in saved]
    expected_ids = ["seg-quench-1", "seg-quench-2"]
    keys = {pid: condition_reviews._manual_process_field_key(pid) for pid in expected_ids}
    assert len(set(keys.values())) == 2
    assert len({project_condition_scope(item["export_process_id"]) for item in saved}) == 2
    async with sessions() as db:
        db.add_all([
            Project(id=5, name="重复淬火 Bool 回归", workflow_revision=7),
            NormalizedRouteVersion(id=1, project_id=5, version=1, route_json=json.dumps(saved, ensure_ascii=False)),
        ])
        await db.commit()
        for pid in expected_ids:
            await save_segment_rule_review_record(
                project_id=5, route_id=1, segment_id=pid, decision="accepted", note="",
                summary_lines=[], question_trail=[{"nodeId": "guided_mode", "value": "manual", "label": "由用户决定"}],
                analysis_draft=AnalysisRuleDraft(
                    scope="当前工序", object="淬火", condition_text=source_text, status="confirmed",
                    candidate=manual_candidate(pid, "淬火", keys[pid]),
                ), db=db,
            )
        if reverse:
            route = await db.get(NormalizedRouteVersion, 1)
            saved = build_saved_route_version_segments(list(reversed(saved)), [], 1)
            route.route_json = json.dumps(saved, ensure_ascii=False)
            await db.commit()

    async def forbidden_parser(*args, **kwargs):
        raise AssertionError("已保存的同名 Bool 草稿必须按节点复用")

    monkeypatch.setattr(condition_reviews, "parse_rule_condition", forbidden_parser)
    await rule_preprocessing._run_job(
        project_id=5, route_id=1, workflow_revision=7, processes=processes,
        items=[RulePreprocessItem(segment_id=item["id"], process_id=item["export_process_id"],
                                  process_name="淬火", source_text=source_text) for item in saved],
    )
    confirmed = []
    async with sessions() as db:
        rows = (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalars().all()
        assert {row.segment_id for row in rows} == set(expected_ids)
        for row in rows:
            assert row.condition_status == "pending_confirmation", row.condition_issues_json
            candidate = condition_reviews.serialize_condition_review(row).candidate
            assert candidate.configuration.process_id == row.segment_id
            assert candidate.configuration.when.field == keys[row.segment_id]
            response = await condition_reviews.confirm_condition_review(ConfirmRuleConditionRequest(
                project_id=5, route_id=1, segment_id=row.segment_id, source_text=source_text,
                source_hash=row.condition_source_hash, candidate=candidate, processes=processes,
            ), db)
            confirmed.append(response.review.confirmed)

    package = compile_rule_package(CompileRulePackageRequest(
        project_id=5, route_version_id=1, package_name="重复淬火 Bool 回归",
        fields=[InputField(**{key: value for key, value in candidate.field_definitions[0].model_dump().items()
                             if key in InputField.model_fields}) for candidate in confirmed],
        processes=[{"process_id": "process_prepare", "display_name": "准备", "main": True}] + [
                   {"process_id": item["export_process_id"], "display_name": "淬火",
                    "default_sequence": item["sequence"]} for item in saved],
        process_configurations=[candidate.configuration.model_dump(by_alias=True) for candidate in confirmed],
    ))
    assert validate_rule_package(package).valid
    assert plan_route(package, {}).selected_process_ids == ["process_prepare"]
    assert plan_route(package, {keys[expected_ids[0]]: True}).selected_process_ids == ["process_prepare", "seg-quench-1"]
    assert plan_route(package, {keys[expected_ids[1]]: True}).selected_process_ids == ["process_prepare", "seg-quench-2"]
    both = ["seg-quench-2", "seg-quench-1"] if reverse else expected_ids
    assert plan_route(package, {key: True for key in keys.values()}).selected_process_ids == ["process_prepare"] + both


def test_same_name_relation_keeps_distinct_source_and_target():
    saved = repeated_route()
    source, target = [item["export_process_id"] for item in saved]
    key = condition_reviews._manual_process_field_key(source)
    candidate = manual_candidate(source, "淬火", key)
    package = compile_rule_package(CompileRulePackageRequest(
        project_id=5, route_version_id=1, package_name="重复淬火关联回归",
        fields=[InputField(**{key: value for key, value in candidate["field_definitions"][0].items()
                             if key in InputField.model_fields})],
        processes=[{"process_id": "process_prepare", "display_name": "准备", "main": True}] + [
                   {"process_id": item["export_process_id"], "display_name": "淬火",
                    "default_sequence": item["sequence"]} for item in saved],
        process_configurations=[candidate["configuration"], {
            "process_id": target, "occurrence": "associated", "relations": [{
                "relation_type": "trigger_after", "source_process_ids": [source],
                "target_process_ids": [target], "source_match": "any",
            }],
        }],
    ))
    assert validate_rule_package(package).valid
    assert plan_route(package, {key: False}).selected_process_ids == ["process_prepare"]
    assert plan_route(package, {key: True}).selected_process_ids == ["process_prepare", "seg-quench-1", "seg-quench-2"]
