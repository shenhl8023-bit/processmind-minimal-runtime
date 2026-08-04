"""Execution of published V2 rule packages."""

from __future__ import annotations

import json

import pytest

from app.models.models import FinalizedRulePackage
from app.services.rule_packages.execution import (
    PublishedRulePackageInputInvalid,
    execute_published_v2_rule_package,
)


def _published_v2_row(rule_package_v2_payload: dict) -> FinalizedRulePackage:
    return FinalizedRulePackage(
        project_id=rule_package_v2_payload["manifest"]["project_id"],
        route_version_id=rule_package_v2_payload["manifest"]["route_version_id"],
        version=1,
        package_name=rule_package_v2_payload["manifest"]["package_name"],
        schema_version="2.0",
        status="published",
        manifest_json=json.dumps(rule_package_v2_payload["manifest"], ensure_ascii=False),
        input_schema_json=json.dumps(rule_package_v2_payload["input_schema"], ensure_ascii=False),
        route_catalog_json=json.dumps(rule_package_v2_payload["route_catalog"], ensure_ascii=False),
        route_rules_json=json.dumps(rule_package_v2_payload["route_rules"], ensure_ascii=False),
        test_cases_json=json.dumps(rule_package_v2_payload["test_cases"], ensure_ascii=False),
        rule_report_md="# test",
        validation_report_json=json.dumps({"valid": True}),
        content_hash="test-content-hash",
        created_by="tester",
    )


def _valid_inputs() -> dict:
    return {
        "material": {"grade": "9Cr18"},
        "cad": {"features": ["槽类特征"]},
        "target_hardness_hrc": 58,
    }


def test_execute_published_v2_rule_package_plans_selected_processes(rule_package_v2_payload):
    execution = execute_published_v2_rule_package(
        _published_v2_row(rule_package_v2_payload),
        _valid_inputs(),
    )

    assert execution.plan.selected_process_ids == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]


def test_execute_published_v2_rule_package_includes_matched_traces(rule_package_v2_payload):
    execution = execute_published_v2_rule_package(
        _published_v2_row(rule_package_v2_payload),
        _valid_inputs(),
    )

    assert "material.9cr18.quench" in [
        trace.rule_id for trace in execution.plan.traces if trace.matched
    ]


def test_execute_published_v2_rule_package_rejects_empty_inputs(rule_package_v2_payload):
    with pytest.raises(PublishedRulePackageInputInvalid) as exc_info:
        execute_published_v2_rule_package(_published_v2_row(rule_package_v2_payload), {})

    assert any(issue.field == "material.grade" for issue in exc_info.value.issues)
