"""
规则定稿导出包的轻量序列化辅助。
"""

from __future__ import annotations

import json
import hashlib

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.schemas.schemas import FinalizedRulePackageOut
from app.services.project_group_templates import get_project_group_template, serialize_project_group_template
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.publication_projection import (
    PROJECTED_COMPILER_VERSIONS,
    PUBLICATION_COMPILER_VERSION,
    project_publication_tables,
)


def _snapshot_hash(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def compile_publication_snapshot(
    package: RulePackageV2,
    project: Project,
    db: AsyncSession,
) -> tuple[dict, dict]:
    """Compile all exports from one transaction's mapped route, never a browser cache."""
    from app.services.rule_packages.demo_tables import (
        DemoTableError,
        compile_demo_tables,
        validate_publication_input_constraints,
    )

    row = await get_project_group_template(db, project.id)
    if row is None:
        raise DemoTableError([{
            "code": "mapped_route_missing", "path": "full_route_table",
            "message": "模板映射后的全集路线表尚未保存，请进入模板映射保存后重新预检。",
        }])
    template = serialize_project_group_template(row)
    if not template.mapping_output:
        raise DemoTableError([{
            "code": "mapped_route_missing", "path": "full_route_table",
            "message": "模板映射后的全集路线表为空，请进入模板映射保存最终工艺树后重新预检。",
        }])
    current_targets = {
        (process.get("process_id"), step.get("step_id"))
        for process in template.mapping_output
        if isinstance(process, dict) and isinstance(process.get("steps"), list)
        for step in process["steps"]
        if isinstance(step, dict)
    }
    step_reviews = json_loads_list(row.step_mappings_json)
    step_states = {}
    for review in step_reviews:
        if (not isinstance(review, dict) or review.get("status") != "not_applicable"
                or review.get("source") != "user_confirmed"):
            continue
        for target in review.get("final_targets", []):
            if not isinstance(target, dict):
                continue
            identity = (target.get("process_id"), target.get("step_id"))
            if identity in current_targets:
                step_states[identity[1]] = "general"
    compiled = compile_demo_tables(package, template.mapping_output, step_states=step_states)
    tables, projection_report = project_publication_tables(compiled, package)
    validate_publication_input_constraints(package, tables)
    route = await db.get(NormalizedRouteVersion, package.manifest.route_version_id)
    sources = {
        "compiler_version": PUBLICATION_COMPILER_VERSION,
        "project_id": project.id,
        "route_version_id": package.manifest.route_version_id,
        "rule_package_content_hash": rule_package_content_hash(package),
        "route_content_hash": _snapshot_hash(json_loads_list(route.route_json) if route else []),
        "workflow_revision": int(project.workflow_revision or 0),
        "template_revision": template.template_revision,
        "template_content_hash": template.content_hash,
        "mapping_output_hash": _snapshot_hash(template.mapping_output),
        "source_full_route_table": template.mapping_output,
        "exported_route_hash": _snapshot_hash(tables["full_route_table"]),
        "projection_report": projection_report,
        "step_mapping_review_hash": _snapshot_hash(step_reviews),
        "demo_tables_hash": _snapshot_hash(tables),
    }
    return tables, sources


def json_dumps(value: object) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def json_dumps_list(value: object) -> str:
    return json.dumps(value or [], ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def json_loads_list(value: str | None) -> list:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def serialize_finalized_rule_package(
    row: FinalizedRulePackage,
) -> FinalizedRulePackageOut:
    from app.services.rule_packages.demo_tables import DemoTableError, compile_demo_tables, validate_demo_tables

    demo_tables = json_loads(getattr(row, "demo_tables_json", None)) or None
    export_sources = json_loads(getattr(row, "export_sources_json", None))
    export_error = None
    if demo_tables is None:
        export_error = "此历史规则包没有三文件快照，请重新发布后下载；不会使用当前映射拼接旧版本。"
    else:
        try:
            validate_demo_tables(demo_tables)
        except DemoTableError as exc:
            demo_tables = None
            export_error = f"此规则包的三文件快照无效，请重新发布：{exc}"
        if demo_tables is not None and export_sources.get("demo_tables_hash") != _snapshot_hash(demo_tables):
            demo_tables = None
            export_error = "此规则包的三文件快照完整性校验未通过，请重新发布后下载。"
        if demo_tables is not None:
            try:
                package = RulePackageV2.model_validate({
                    "manifest": json_loads(row.manifest_json),
                    "factor_dictionary": json_loads(row.factor_dictionary_json) or None,
                    "input_schema": json_loads(row.input_schema_json),
                    "route_catalog": json_loads(row.route_catalog_json),
                    "route_rules": json_loads(row.route_rules_json),
                    "test_cases": json_loads_list(row.test_cases_json),
                })
                content_hash = rule_package_content_hash(package)
                bound_hash = export_sources.get("rule_package_content_hash")
                compiler_version = export_sources.get("compiler_version")
                valid_compiler_type = compiler_version is None or isinstance(compiler_version, str)
                projected_snapshot = isinstance(compiler_version, str) and compiler_version in PROJECTED_COMPILER_VERSIONS
                has_projection_sources = any(key in export_sources for key in (
                    "source_full_route_table", "exported_route_hash", "projection_report",
                ))
                detached_historical_route = row.route_version_id is None and row.status in {"archived", "superseded"}
                sources_match = (
                    valid_compiler_type
                    and export_sources.get("project_id") == row.project_id == package.manifest.project_id
                    and export_sources.get("route_version_id") == package.manifest.route_version_id
                    and (detached_historical_route or row.route_version_id == package.manifest.route_version_id)
                    and package.manifest.package_name == row.package_name
                    and row.content_hash == content_hash
                    and (not has_projection_sources or projected_snapshot)
                    and (projected_snapshot
                         or export_sources.get("mapping_output_hash") is None
                         or export_sources["mapping_output_hash"] == _snapshot_hash(demo_tables["full_route_table"]))
                )
                if sources_match:
                    if bound_hash is None:
                        # Only known v1 snapshots predate the package binding.
                        # Reproduce their exact semantics using their own frozen
                        # route; never upgrade them or borrow today's mapping.
                        sources_match = False
                        if export_sources.get("compiler_version") == "demo-three-table/1":
                            # V1 was deployed with two known scalar-default
                            # profiles. Each must reproduce every frozen cell;
                            # never infer compatibility by patching that table.
                            for optional_defaults in (False, True):
                                try:
                                    rebuilt = compile_demo_tables(
                                        package, demo_tables["full_route_table"], _legacy_snapshot=True,
                                        _legacy_optional_defaults=optional_defaults,
                                    )
                                except DemoTableError:
                                    continue
                                if rebuilt == demo_tables:
                                    sources_match = True
                                    break
                    else:
                        sources_match = bound_hash == content_hash
                        if projected_snapshot:
                            source_route = export_sources.get("source_full_route_table")
                            sources_match = sources_match and isinstance(source_route, list)
                            if sources_match:
                                compiled = compile_demo_tables(
                                    package, source_route, _v3_snapshot=compiler_version == "demo-three-table/3",
                                    _v4_snapshot=compiler_version == "demo-three-table/4",
                                )
                                rebuilt, report = project_publication_tables(compiled, package)
                                sources_match = (
                                    rebuilt == demo_tables
                                    and report == export_sources.get("projection_report")
                                    and export_sources.get("mapping_output_hash") == _snapshot_hash(source_route)
                                    and export_sources.get("exported_route_hash") == _snapshot_hash(demo_tables["full_route_table"])
                                )
                        # Bound historical snapshots can predate the version
                        # marker. Preserve them without accepting unknown versions.
                        elif compiler_version not in {None, "demo-three-table/1", "demo-three-table/2"}:
                            sources_match = False
            except (ValidationError, DemoTableError):
                sources_match = False
            if not sources_match:
                demo_tables = None
                export_error = "此三文件快照与规则包的项目、路线或内容不一致，请重新发布后下载。"
    return FinalizedRulePackageOut(
        id=row.id,
        project_id=row.project_id,
        route_version_id=row.route_version_id,
        version=row.version,
        package_name=row.package_name,
        schema_version="2.0",
        status=row.status or "published",
        manifest=json_loads(row.manifest_json),
        factor_dictionary=json_loads(row.factor_dictionary_json),
        input_schema=json_loads(row.input_schema_json),
        route_catalog=json_loads(row.route_catalog_json),
        route_rules=json_loads(row.route_rules_json),
        demo_tables=demo_tables,
        export_sources=export_sources,
        export_error=export_error,
        test_cases=json_loads_list(row.test_cases_json),
        rule_report_md=row.rule_report_md or "",
        validation_report=json_loads(row.validation_report_json),
        content_hash=row.content_hash or "",
        created_by=row.created_by or "默认用户",
        created_at=row.created_at,
        published_by=row.published_by,
        published_at=row.published_at,
        supersedes_id=row.supersedes_id,
    )


__all__ = [
    "json_dumps",
    "json_dumps_list",
    "json_loads",
    "json_loads_list",
    "serialize_finalized_rule_package",
    "compile_publication_snapshot",
]
