"""Real frozen publication DTOs remain readable across compiler revisions."""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest

from app.models.models import FinalizedRulePackage
from app.services.finalized_rule_package_helpers import _snapshot_hash, serialize_finalized_rule_package
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash


SNAPSHOTS = json.loads((Path(__file__).parent / "fixtures" / "finalized_v1_configuration_snapshots.json").read_text())


@pytest.mark.parametrize('name', SNAPSHOTS)
@pytest.mark.parametrize('compiler_version', ['demo-three-table/2', None])
def test_bound_v2_snapshot_remains_readable_without_projection(name, compiler_version):
    snapshot = deepcopy(SNAPSHOTS[name])
    if compiler_version is None:
        snapshot['export_sources'].pop('compiler_version')
    else:
        snapshot['export_sources']['compiler_version'] = compiler_version
    snapshot['export_sources']['rule_package_content_hash'] = snapshot['content_hash']
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables == snapshot['demo_tables'], result.export_error
    assert result.export_error is None


def _row(snapshot):
    values = {key: snapshot.get(key) for key in (
        "id", "project_id", "route_version_id", "version", "package_name", "schema_version", "status",
        "content_hash", "created_by", "published_by", "supersedes_id",
    )}
    for key in ("manifest", "factor_dictionary", "input_schema", "route_catalog", "route_rules",
                "test_cases", "demo_tables", "export_sources"):
        values[f"{key}_json"] = json.dumps(snapshot[key], ensure_ascii=False)
    for key in ("created_at", "published_at"):
        values[key] = datetime.fromisoformat(snapshot[key]) if snapshot.get(key) else None
    return FinalizedRulePackage(**values)


@pytest.mark.parametrize("name", SNAPSHOTS)
def test_real_configuration_v1_snapshots_keep_exact_frozen_tables_and_hashes(name):
    snapshot = SNAPSHOTS[name]
    package = RulePackageV2.model_validate({key: snapshot[key] for key in (
        "manifest", "factor_dictionary", "input_schema", "route_catalog", "route_rules", "test_cases",
    )})
    assert package.route_rules.process_configurations
    assert rule_package_content_hash(package) == snapshot["content_hash"]
    assert _snapshot_hash(snapshot["demo_tables"]) == snapshot["export_sources"]["demo_tables_hash"]
    assert _snapshot_hash(snapshot["demo_tables"]["full_route_table"]) == snapshot["export_sources"]["mapping_output_hash"]
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables == snapshot["demo_tables"], result.export_error
    assert result.content_hash == snapshot["content_hash"]
    assert result.export_sources == snapshot["export_sources"]
    assert result.export_error is None


@pytest.mark.parametrize("name", SNAPSHOTS)
@pytest.mark.parametrize("mutation", ["rule", "candidate", "factor_default", "compiler_version", "missing_v2_binding", "native"])
def test_real_configuration_v1_snapshots_reject_modified_content_even_after_table_rehash(name, mutation):
    snapshot = deepcopy(SNAPSHOTS[name])
    if mutation == "rule":
        snapshot["demo_tables"]["rule_table"][0] = {"target": snapshot["demo_tables"]["rule_table"][0]["target"], "when": False}
    elif mutation == "candidate":
        step = next(step for process in snapshot["demo_tables"]["full_route_table"] for step in process["steps"] if step["candidates"])
        group = next(iter(step["candidates"]))
        step["candidates"][group] = ["changed-frozen-candidate"]
    elif mutation == "factor_default":
        factor = next(factor for factor in snapshot["demo_tables"]["factor_table"] if factor["type"] == "bool")
        factor["default"] = False
    elif mutation == "compiler_version":
        snapshot["export_sources"]["compiler_version"] = "unknown"
    elif mutation == "missing_v2_binding":
        snapshot["export_sources"]["compiler_version"] = "demo-three-table/2"
    else:
        snapshot["route_catalog"]["processes"][0]["display_name"] += " changed"
    snapshot["export_sources"]["demo_tables_hash"] = _snapshot_hash(snapshot["demo_tables"])
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables is None
    assert result.export_error


@pytest.mark.parametrize("name", SNAPSHOTS)
@pytest.mark.parametrize("invalid_version", [[], {}])
def test_invalid_compiler_version_reports_export_error(name, invalid_version):
    snapshot = deepcopy(SNAPSHOTS[name])
    snapshot["export_sources"]["rule_package_content_hash"] = snapshot["content_hash"]
    snapshot["export_sources"]["compiler_version"] = invalid_version
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables is None
    assert result.export_error


def _projected_contract_snapshot(compiler_version, variant):
    field = {"key": "choice", "label": "类别", "type": "single_select", "required": True,
             "options": [{"value": item, "label": item} for item in ["A", "B"]]}
    factor = {"key": "choice", "label": "类别", "type": "enum", "source": "manual_defaults.choice",
              "visible": True, "required": True,
              "options": ["A", "B"] if compiler_version == "demo-three-table/3" else ["A"]}
    if variant == "validation":
        field = {"key": "length", "label": "长度", "type": "number", "required": True,
                 "validation": {"min": 0, "max": 10}}
        factor = {"key": "length", "label": "长度", "type": "number", "source": "manual_defaults.length",
                  "visible": True, "required": True}
        if compiler_version == 'demo-three-table/5':
            factor['validation'] = {'min': 0, 'max': 10}
    active_field = deepcopy(field)
    if variant == "narrowed_options":
        active_field["options"] = active_field["options"][:1]
    package = RulePackageV2.model_validate({
        "manifest": {"package_name": "frozen-contract", "project_id": 12, "route_version_id": 31,
                     "scope": {"key": "12"}},
        "factor_dictionary": {"fields": [field]}, "input_schema": {"fields": [active_field]},
        "route_catalog": {"processes": [{"process_id": "clean", "display_name": "清洗", "main": True}]},
        "route_rules": {"rules": []},
    })
    route = [{"process_id": "clean", "process_name": "清洗", "process_type": "辅助工序",
              "precision": "辅助工序", "steps": []}]
    tables = {"factor_table": [factor], "full_route_table": route,
              "rule_table": [{"target": "clean", "required": True}]}
    content_hash = rule_package_content_hash(package)
    sources = {
        "compiler_version": compiler_version, "project_id": 12, "route_version_id": 31,
        "rule_package_content_hash": content_hash, "demo_tables_hash": _snapshot_hash(tables),
        "source_full_route_table": route, "mapping_output_hash": _snapshot_hash(route),
        "exported_route_hash": _snapshot_hash(route),
        "projection_report": {"original_process_count": 1, "exported_process_count": 1,
                              "original_step_count": 0, "exported_step_count": 0,
                              "excluded_processes": [], "excluded_steps": [], "removed_factor_keys": []},
    }
    return {**package.model_dump(mode="json", by_alias=True), "id": 1, "project_id": 12,
            "route_version_id": 31, "version": 1, "package_name": "frozen-contract", "schema_version": "2.0",
            "status": "published", "content_hash": content_hash, "created_at": "2026-10-29T12:00:00",
            "demo_tables": tables, "export_sources": sources}


@pytest.mark.parametrize("variant", ["narrowed_options", "validation"])
def test_v3_snapshot_keeps_original_dictionary_domain_and_validation_profile(variant):
    snapshot = _projected_contract_snapshot("demo-three-table/3", variant)
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables == snapshot["demo_tables"], result.export_error
    assert result.export_error is None


@pytest.mark.parametrize('compiler_version', ['demo-three-table/4', 'demo-three-table/5'])
@pytest.mark.parametrize('variant', ['narrowed_options', 'validation'])
def test_snapshot_rebuilds_its_original_option_and_validation_profile(compiler_version, variant):
    snapshot = _projected_contract_snapshot(compiler_version, variant)
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables == snapshot["demo_tables"], result.export_error
    assert result.export_error is None


@pytest.mark.parametrize('mutation', ['remove', 'change'])
def test_v5_snapshot_rejects_rehashed_validation_tampering(mutation):
    snapshot = _projected_contract_snapshot('demo-three-table/5', 'validation')
    factor = snapshot['demo_tables']['factor_table'][0]
    if mutation == 'remove':
        factor.pop('validation')
    else:
        factor['validation']['max'] = 100
    snapshot['export_sources']['demo_tables_hash'] = _snapshot_hash(snapshot['demo_tables'])
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables is None
    assert result.export_error


@pytest.mark.parametrize("compiler_version", ["demo-three-table/3", "demo-three-table/4"])
def test_projected_snapshot_cannot_switch_dictionary_and_active_option_profiles(compiler_version):
    snapshot = _projected_contract_snapshot(compiler_version, "narrowed_options")
    snapshot["demo_tables"]["factor_table"][0]["options"] = (
        ["A"] if compiler_version == "demo-three-table/3" else ["A", "B"]
    )
    snapshot["export_sources"]["demo_tables_hash"] = _snapshot_hash(snapshot["demo_tables"])
    result = serialize_finalized_rule_package(_row(snapshot))
    assert result.demo_tables is None
    assert result.export_error
