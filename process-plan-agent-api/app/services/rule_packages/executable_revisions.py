"""Transaction-owned executable cores and their current validation eligibility."""

from __future__ import annotations

import json
import re

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update

from app.models.models import (ExecutableRuleRevision, FinalizedRulePackage, GeneratedRoute,
                               NormalizedRouteSegmentRuleReview, NormalizedRouteVersion)
from app.services.rule_packages.confirmation_validation import require_confirmed_user_rule_sources
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.native_publication import snapshot_hash
from app.services.rule_packages.mother_route import MotherRouteError, load_mother_route, require_mother_catalog
from app.services.rule_packages.validator import validate_rule_package


REVIEW_SOURCE_FIELDS = ("segment_id", "decision", "analysis_draft_json", "condition_source_text",
                        "condition_source_hash", "condition_status", "condition_confirmed_json",
                        "condition_confirmed_by", "condition_confirmed_at", "question_trail_json")


def native_route(value):
    segments = json.loads(value or "[]")
    if not isinstance(segments, list):
        raise ValueError("标准化路线格式错误")
    for segment in segments:
        segment.pop("template_group_aliases", None)
    return segments


async def latest_route(db, project_id):
    return (await db.execute(select(NormalizedRouteVersion).where(
        NormalizedRouteVersion.project_id == project_id).order_by(
        NormalizedRouteVersion.version.desc(), NormalizedRouteVersion.id.desc()))).scalars().first()


async def source_hash(db, route):
    reviews = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
        NormalizedRouteSegmentRuleReview.route_version_id == route.id).order_by(
        NormalizedRouteSegmentRuleReview.segment_id, NormalizedRouteSegmentRuleReview.id))).scalars().all()
    return snapshot_hash({"route": native_route(route.route_json), "reviews": [
        {field: str(getattr(row, field) or "") for field in REVIEW_SOURCE_FIELDS} for row in reviews]})


async def latest_revision(db, project_id):
    return (await db.execute(select(ExecutableRuleRevision).where(
        ExecutableRuleRevision.project_id == project_id).order_by(
        ExecutableRuleRevision.revision.desc()).execution_options(populate_existing=True))).scalars().first()


async def current_revision(db, project_id, revision_id=None, *, required=True):
    row = await latest_revision(db, project_id)
    route = await latest_route(db, project_id)
    valid = row is not None and row.status == "current" and route is not None and row.route_version_id == route.id
    if valid:
        try:
            package = RulePackageV2.model_validate_json(row.package_json)
            valid = (package.manifest.project_id == project_id
                     and package.manifest.route_version_id == route.id
                     and row.content_hash == rule_package_content_hash(package)
                     and row.source_hash == await source_hash(db, route)
                     and json.loads(row.normalized_route_json) == native_route(route.route_json))
            if valid:
                require_mother_catalog(package, await load_mother_route(db, project_id, native_route(route.route_json)))
        except (ValueError, TypeError):
            valid = False
    if not valid or (revision_id is not None and (row is None or row.id != revision_id)):
        if not required:
            return None
        raise HTTPException(409 if row or revision_id else 404,
                            "当前可执行规则版本不存在或已失效，请返回第四步重新保存并校验。")
    return row


async def has_generation(db, row):
    return (await db.execute(select(GeneratedRoute.id).where(
        GeneratedRoute.project_id == row.project_id,
        GeneratedRoute.executable_revision_id == row.id).limit(1))).scalar_one_or_none() is not None


async def require_generation(db, project_id, revision_id=None):
    row = await current_revision(db, project_id, revision_id)
    if not await has_generation(db, row):
        raise HTTPException(409, "请先在第五步使用当前可执行规则版本成功生成路线。")
    return row


async def serialize_revision(db, row):
    current = await current_revision(db, row.project_id, required=False)
    ready = current is not None and current.id == row.id
    return {"id": row.id, "project_id": row.project_id, "route_version_id": row.route_version_id,
            "revision": row.revision, "content_hash": row.content_hash,
            "package": json.loads(row.package_json), "validation": json.loads(row.validation_json),
            "generation_ready": ready, "has_current_generation": ready and await has_generation(db, row)}


async def invalidate_executable(db, project_id, *, detach_route=False):
    values = {"status": "invalid"}
    if detach_route:
        values["route_version_id"] = None
    await db.execute(update(ExecutableRuleRevision).where(
        ExecutableRuleRevision.project_id == project_id).values(**values))
    await db.execute(delete(GeneratedRoute).where(GeneratedRoute.project_id == project_id))


async def save_revision(db, project, body):
    from app.services.workflow_progress import _analysis_is_complete

    previous = await latest_revision(db, project.id)
    actual = int(previous.revision if previous else 0)
    if body.expected_executable_revision != actual:
        raise HTTPException(409, {"message": "可执行规则版本已更新，请刷新后重试。", "executable_revision": actual})
    route = await latest_route(db, project.id)
    if route is None or body.route_version_id != route.id:
        raise HTTPException(409, "请基于当前标准化路线保存可执行规则版本。")
    if not await _analysis_is_complete(db, route, native_route(route.route_json)):
        raise HTTPException(409, "第三步工序分析尚未完成。")
    package = RulePackageV2.model_validate({key: getattr(body, key) for key in
        ("manifest", "factor_dictionary", "input_schema", "route_catalog", "route_rules", "test_cases")})
    for field in package.input_schema.fields:
        if field.key == "project_factor.material_grade" and (field.type != "single_select" or field.allow_custom):
            raise HTTPException(422, "项目材料牌号必须从已配置候选中单选，不能允许新增材料。")
        if (re.fullmatch(r"project_factor\.operation_[^.]+\.(it|ra|hardness_min|hardness_max)", field.key)
                and field.type != "number"):
            raise HTTPException(422, "工序范围内的 IT、Ra 和硬度必须使用数值字段。")
    # Template aliases belong to an optional export attachment, never the core.
    package.manifest.compiled_from.template_ids = []
    for process in package.route_catalog.processes:
        process.template_group_aliases = []
    if (package.manifest.project_id != project.id or package.manifest.route_version_id != route.id
            or package.manifest.package_name != body.package_name):
        raise HTTPException(422, "规则包任务、路线版本或名称与请求不一致。")
    try:
        require_mother_catalog(package, await load_mother_route(db, project.id, native_route(route.route_json)))
    except MotherRouteError as exc:
        raise HTTPException(422, str(exc)) from exc
    validation = validate_rule_package(package)
    if not validation.valid:
        raise HTTPException(422, {"message": "可执行规则校验未通过。", "validation": validation.model_dump(mode="json")})
    await require_confirmed_user_rule_sources(package, project_id=project.id, route_version_id=route.id, db=db)
    content_hash = rule_package_content_hash(package)
    sources = await source_hash(db, route)
    if previous and previous.status == "current" and previous.content_hash == content_hash and previous.source_hash == sources:
        return previous
    await invalidate_executable(db, project.id)
    await db.execute(update(FinalizedRulePackage).where(FinalizedRulePackage.project_id == project.id,
        FinalizedRulePackage.status == "published").values(status="superseded"))
    row = ExecutableRuleRevision(project_id=project.id, route_version_id=route.id, revision=actual + 1,
        status="current", package_json=package.model_dump_json(by_alias=True, exclude_none=True),
        normalized_route_json=json.dumps(native_route(route.route_json), ensure_ascii=False),
        content_hash=content_hash, source_hash=sources, validation_json=validation.model_dump_json(),
        rule_report_md=body.rule_report_md, created_by=body.created_by)
    db.add(row)
    await db.flush()
    return row


async def export_revision(db, project, row, *, include_template_mapping=False):
    from app.services.finalized_rule_package_helpers import serialize_finalized_rule_package
    from app.services.rule_packages.lifecycle import publish_rule_package
    from app.services.rule_packages.native_publication import compile_native_snapshot
    from app.services.rule_packages.template_mapping_requirements import validate_rule_package_template_mapping

    await require_generation(db, project.id, row.id)
    package = RulePackageV2.model_validate_json(row.package_json)
    mapping = None
    if include_template_mapping:
        blockers = await validate_rule_package_template_mapping(db, package)
        if blockers:
            from dataclasses import asdict
            raise HTTPException(422, {"message": "模板映射未完成。", "blockers": [asdict(b) for b in blockers]})
        from dataclasses import asdict
        from app.services.project_group_templates import get_project_group_template, serialize_project_group_template
        template = await get_project_group_template(db, project.id)
        saved = asdict(serialize_project_group_template(template))
        mapping = {key: saved[key] for key in ("template_revision", "content_hash", "tree",
                   "mapping_output", "mappings", "step_mappings", "hidden_step_keys", "waived_group_paths")}
        if saved["mapping_context"]:
            mapping.update({key: saved[key] for key in ("step_order_by_process", "mapping_context", "mapping_operations")})
    mother_route = await load_mother_route(db, project.id, json.loads(row.normalized_route_json))
    sources = compile_native_snapshot(package, json.loads(row.normalized_route_json), int(project.workflow_revision or 0),
                                      template_mapping=mapping, mother_route=mother_route)
    sources.update(executable_revision_id=row.id, executable_revision=row.revision, executable_content_hash=row.content_hash)
    version = (await db.execute(select(func.max(FinalizedRulePackage.version)).where(
        FinalizedRulePackage.project_id == project.id))).scalar_one_or_none() or 0
    payload = package.model_dump(mode="json", by_alias=True, exclude_none=True)
    exported = FinalizedRulePackage(project_id=project.id, route_version_id=row.route_version_id,
        version=version + 1, package_name=package.manifest.package_name, schema_version="2.0", status="draft",
        **{key + "_json": json.dumps(payload[key], ensure_ascii=False) for key in
           ("manifest", "factor_dictionary", "input_schema", "route_catalog", "route_rules", "test_cases")},
        demo_tables_json="null", export_sources_json=json.dumps(sources, ensure_ascii=False),
        rule_report_md=row.rule_report_md, validation_report_json=row.validation_json, content_hash=row.content_hash,
        created_by=row.created_by)
    db.add(exported)
    await db.flush()
    await publish_rule_package(exported, db, actor=row.created_by)
    result = serialize_finalized_rule_package(exported)
    if result.export_error:
        raise HTTPException(422, result.export_error)
    return result
