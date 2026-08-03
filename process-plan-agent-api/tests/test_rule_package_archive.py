import json
import zipfile
from copy import deepcopy
from io import BytesIO

import pytest

from app.models.models import FinalizedRulePackage
from app.services.finalized_rule_package_helpers import json_dumps, json_dumps_list
from app.services.rule_packages.archive import (
    RulePackageArchiveError,
    build_finalized_rule_package_archive,
)
from app.services.rule_packages import archive as archive_module
from app.services.rule_packages.contracts import KmaiCompatibilityExport
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.contracts import RulePackageV2


def _published_v2_row(payload: dict, *, validation_report: dict | None = None) -> FinalizedRulePackage:
    package = RulePackageV2.model_validate(payload)
    return FinalizedRulePackage(
        id=41,
        project_id=package.manifest.project_id,
        route_version_id=package.manifest.route_version_id,
        version=3,
        package_name=package.manifest.package_name,
        schema_version="2.0",
        status="published",
        manifest_json=json_dumps(payload["manifest"]),
        input_schema_json=json_dumps(payload["input_schema"]),
        route_catalog_json=json_dumps(payload["route_catalog"]),
        route_rules_json=json_dumps(payload["route_rules"]),
        test_cases_json=json_dumps_list(payload["test_cases"]),
        rule_report_md="# Rule Report\n\nPersisted report.",
        validation_report_json=json_dumps(validation_report or {"valid": True, "issues": []}),
        content_hash=rule_package_content_hash(package),
        created_by="tester",
        published_by="tester",
    )


def _zip_files(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_archive_contains_persisted_v2_and_kmai_files(rule_package_v2_payload):
    row = _published_v2_row(rule_package_v2_payload)

    archive = build_finalized_rule_package_archive(row)
    files = _zip_files(archive.content)

    assert archive.filename == "shaft_rules_v3.zip"
    assert set(files) == {
        "manifest.json",
        "input_schema.json",
        "route_catalog.json",
        "route_rules.json",
        "test_cases.json",
        "rule_report.md",
        "validation_report.json",
        "kmai-v1/factor_schema.json",
        "kmai-v1/factor_expansion_rules.json",
        "kmai-v1/route_catalog.json",
        "kmai-v1/route_rules.json",
        "kmai-v1/README-替换说明.txt",
    }
    assert json.loads(files["manifest.json"]) == rule_package_v2_payload["manifest"]
    assert json.loads(files["test_cases.json"]) == rule_package_v2_payload["test_cases"]
    assert files["rule_report.md"].decode("utf-8") == "# Rule Report\n\nPersisted report."
    assert json.loads(files["validation_report.json"]) == {"valid": True, "issues": []}

    expected_kmai = build_kmai_compatibility_export(RulePackageV2.model_validate(rule_package_v2_payload))
    assert json.loads(files["kmai-v1/factor_schema.json"]) == expected_kmai.files["factor_schema.json"]
    assert json.loads(files["kmai-v1/factor_expansion_rules.json"]) == expected_kmai.files["factor_expansion_rules.json"]
    assert json.loads(files["kmai-v1/route_catalog.json"]) == expected_kmai.files["route_catalog.json"]
    assert json.loads(files["kmai-v1/route_rules.json"]) == expected_kmai.files["route_rules.json"]
    assert "KmMpsMcpServer" in files["kmai-v1/README-替换说明.txt"].decode("utf-8")


def test_archive_uses_historical_mapping_snapshot_from_persisted_validation(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append({
        "rule_id": "legacy.manual",
        "priority": 10,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": "cad.features", "op": "contains", "value": "legacy feature"},
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
    })
    validation_report = {
        "valid": True,
        "issues": [],
        "kmai_compatibility": {
            "mapping_snapshot": [
                {
                    "source_field": "cad.features",
                    "source_value": "legacy feature",
                    "mapping_mode": "manual_factor",
                    "target_factor_key": "processmind_manual_abc123def456",
                    "target_factor_name": "Legacy feature",
                    "target_factor_category": "custom",
                }
            ]
        },
    }
    row = _published_v2_row(payload, validation_report=validation_report)

    archive = build_finalized_rule_package_archive(row)
    files = _zip_files(archive.content)

    kmai_rule = next(
        item
        for item in json.loads(files["kmai-v1/route_rules.json"])["rules"]
        if item["rule_id"] == "legacy.manual"
    )
    assert kmai_rule["when"]["all"] == [{
        "factor_key": "processmind_manual_abc123def456",
        "op": "=",
        "value": True,
    }]


def test_archive_readme_lists_manual_boolean_factors_and_replacement_steps(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    manual_factor_key = "project_factor.manual_process_0123456789ab"
    payload["input_schema"]["fields"].append({
        "key": manual_factor_key,
        "label": "是否需要渗氮",
        "type": "boolean",
        "required": False,
        "source": "用户直接设定",
        "options": [],
        "allow_custom": False,
    })
    payload["route_rules"]["rules"].append({
        "rule_id": "manual.process",
        "priority": 1000,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": manual_factor_key, "op": "eq", "value": True},
        "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
    })

    archive = build_finalized_rule_package_archive(_published_v2_row(payload))
    readme = _zip_files(archive.content)["kmai-v1/README-替换说明.txt"].decode("utf-8")

    assert "先停止 KmAI Agent" in readme
    assert "备份目标目录中同名的四个 JSON 文件" in readme
    assert "group_match_rules.json" in readme
    assert "重新启动 KmAI Agent" in readme
    assert "project_factor_manual_process_0123456789ab" in readme
    assert "是否需要渗氮" in readme


def test_archive_bytes_are_deterministic_for_one_persisted_snapshot(rule_package_v2_payload):
    row = _published_v2_row(rule_package_v2_payload)

    first = build_finalized_rule_package_archive(row)
    second = build_finalized_rule_package_archive(row)

    assert first == second


def test_archive_rejects_non_v2_persisted_package(rule_package_v2_payload):
    row = _published_v2_row(rule_package_v2_payload)
    row.schema_version = "1.0"

    with pytest.raises(RulePackageArchiveError, match="V2"):
        build_finalized_rule_package_archive(row)


def test_archive_readme_lists_manual_boolean_factors_and_replacement_guidance(rule_package_v2_payload):
    payload = deepcopy(rule_package_v2_payload)
    field_key = "project_factor.manual_process_0123456789ab"
    payload["input_schema"]["fields"].append({
        "key": field_key,
        "label": "Manual finishing",
        "type": "boolean",
        "required": False,
        "source": "user",
        "options": [],
        "allow_custom": False,
    })
    payload["route_rules"]["rules"].append({
        "rule_id": "manual.process",
        "priority": 1000,
        "enabled": True,
        "source": "user_confirmed",
        "when": {"field": field_key, "op": "eq", "value": True},
        "then": {"include_process_ids": ["process_nitriding"], "exclude_process_ids": []},
    })

    files = _zip_files(build_finalized_rule_package_archive(_published_v2_row(payload)).content)
    readme = files["kmai-v1/README-替换说明.txt"].decode("utf-8")

    assert "1. 先停止 KmAI Agent。" in readme
    assert "2. 备份目标目录中同名的四个 JSON 文件。" in readme
    assert "3. 将本目录中的 factor_schema.json、factor_expansion_rules.json、route_catalog.json、route_rules.json 复制到目标目录并覆盖。" in readme
    assert "4. 不要删除或覆盖原有 group_match_rules.json。" in readme
    assert "5. 重新启动 KmAI Agent；后续工艺路线生成将使用本次导出的 ProcessMind 规则。" in readme
    assert "6. route_catalog.json 的 template_group_aliases 为 ProcessMind 附加元数据；KmAI v1 会忽略它，不影响路线生成。" in readme
    assert "- project_factor_manual_process_0123456789ab: Manual finishing" in readme


def test_archive_bytes_are_deterministic(rule_package_v2_payload):
    row = _published_v2_row(rule_package_v2_payload)

    first = build_finalized_rule_package_archive(row)
    second = build_finalized_rule_package_archive(row)

    assert first.filename == second.filename
    assert first.content == second.content


def test_archive_rejects_missing_required_kmai_file(rule_package_v2_payload, monkeypatch):
    row = _published_v2_row(rule_package_v2_payload)
    incomplete = KmaiCompatibilityExport(
        valid=True,
        target_directory="KmMpsMcpServer/skills/process-route-generator/references/v1",
        files={"factor_schema.json": {"factors": []}},
    )
    monkeypatch.setattr(archive_module, "build_kmai_compatibility_export", lambda *args, **kwargs: incomplete)

    with pytest.raises(RulePackageArchiveError, match="factor_expansion_rules.json"):
        build_finalized_rule_package_archive(row)
