"""
规则提炼 API —— AI 提取工序与影响因素 + 弱相关确认
第二步严格依赖大模型，但会先把文档压缩成候选工序摘要再送给模型，
避免一次发送整批长文档导致限流或超时。
"""
import asyncio
from dataclasses import asdict
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from typing import Callable, List

from app.database import get_db, async_session
from app.models.models import (
    Document,
    DocumentOperationDetail,
    FinalizedRulePackage,
    NormalizedRouteVersion,
    Operation,
    Project,
)
from app.schemas.schemas import (
    DocumentOperationDetailListOut,
    ExtractionTaskStartOut,
    ExtractionTaskStatusOut,
    FinalizedRulePackageListItemOut,
    FinalizedRulePackageOut,
    FinalizedRulePackageSaveRequest,
    GroupTemplateCommitOut,
    GroupTemplateMappingsUpdateRequest,
    GroupTemplateStepMappingsUpdateRequest,
    GroupTemplatePreviewOut,
    MergeSuggestionListOut,
    MergeSuggestionReviewRequest,
    NormalizedSupersetRouteOut,
    OperationOut,
    ProjectGroupTemplateOut,
    SegmentRuleReviewSaveOut,
    SavedNormalizedRouteVersionOut,
    SaveSegmentRuleReviewRequest,
    SaveNormalizedSupersetRouteRequest,
    SupersetRouteOut,
    TemplateGroupMappingSuggestRequest,
    TemplateGroupMappingSuggestResponse,
    WorkflowResetOut,
    WorkflowResetRequest,
)
from app.services.extraction_pipeline import (
    queue_extraction_job,
    resolve_extraction_task_status,
    run_extraction_pipeline,
)
from app.services.finalized_rule_package_helpers import (
    json_dumps,
    json_dumps_list,
    json_loads,
    json_loads_list,
    serialize_finalized_rule_package,
)
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import (
    legacy_rule_package_content_hash,
    rule_package_content_hash,
)
from app.services.rule_packages.lifecycle import publish_rule_package
from app.services.rule_packages.confirmation_validation import require_confirmed_user_rule_sources
from app.services.rule_packages.loader import load_published_rule_package
from app.services.rule_packages.validator import validate_rule_package
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_mapping_store import (
    record_mapping_usage,
)
from app.services.rule_packages.kmai_mapping_registry import load_effective_mapping_registry
from app.services.process_tree_builder import build_superset_process_tree
from app.services.route_merge.config import ROUTE_MERGE_ALGO_VERSION
from app.services.extraction_tasks import set_extraction_task_state
from app.services.route_rules_runtime import (
    ensure_document_operation_details as ensure_route_rules_document_operation_details,
    extract_document_operation_details as extract_route_rules_document_operation_details,
    extract_route_set_with_llm as extract_route_set_with_llm_runtime,
    save_ops as save_route_rules_ops,
)
from app.services.route_rules_parsing import (
    _detail_row_normalized_names,
    _infer_operation_chain,
    _merge_serialized_operations,
    _normalize_operation_name,
    _preserve_sequence_slot,
    _serialize_operation,
)
from app.services.route_rules_aggregation import (
    _build_route_set_ops_from_candidates,
    _collect_candidate_summary,
    _merge_document_detail_rows_into_candidate_summary,
)
from app.services.route_merge.review import (
    apply_merge_suggestion_review,
)
from app.services.route_merge.workspace import (
    ensure_route_merge_snapshot,
    persist_normalized_superset_route,
    save_route_merge_snapshot,
)
from app.services.route_analysis import (
    build_saved_normalized_route_response,
    ensure_saved_normalized_route_version,
    get_latest_normalized_route_version,
    save_normalized_route_version,
    save_segment_rule_review_record,
)
from app.services.operation_review_meta import get_project_sample_count
from app.services.project_workflow_lifecycle import (
    acquire_workflow_revision,
    invalidate_project_workflow,
)
from app.services.template_group_mapping import resolve_template_group_mappings
from app.services.group_template_xml import MAX_GROUP_TEMPLATE_BYTES, parse_group_template_xml
from app.services.project_group_templates import (
    commit_project_group_template,
    get_project_group_template,
    replace_project_group_mappings,
    replace_project_group_step_mappings,
    serialize_project_group_template,
)

router = APIRouter(prefix="/api/extract", tags=["规则提炼"])


@router.post("/template-group-mappings/suggest", response_model=TemplateGroupMappingSuggestResponse)
async def suggest_template_group_mappings(
    body: TemplateGroupMappingSuggestRequest,
    db: AsyncSession = Depends(get_db),
):
    return await resolve_template_group_mappings(db, body)


async def _ensure_project_exists(project_id: int, db: AsyncSession) -> Project:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "任务不存在")
    return project


def _group_template_preview_payload(parsed):
    return {
        "original_filename": parsed.original_filename,
        "source_encoding": parsed.source_encoding,
        "part_filename": parsed.part_filename,
        "content_hash": parsed.content_hash,
        "feature_dictionary_version": parsed.feature_dictionary_version,
        "tree": parsed.tree,
        "validation_issues": [asdict(issue) for issue in parsed.issues],
        "group_count": parsed.group_count,
        "feature_selection_count": parsed.feature_selection_count,
        "can_confirm": parsed.can_confirm,
    }


def _invalid_group_template(parsed):
    return HTTPException(
        422,
        {
            "message": "分组模板校验未通过。",
            "issues": [asdict(issue) for issue in parsed.issues],
        },
    )


@router.post("/group-templates/preview", response_model=GroupTemplatePreviewOut)
async def preview_group_template(file: UploadFile = File(...)):
    payload = await file.read(MAX_GROUP_TEMPLATE_BYTES + 1)
    parsed = parse_group_template_xml(file.filename or "", payload)
    return _group_template_preview_payload(parsed)


@router.get("/group-templates/current", response_model=ProjectGroupTemplateOut)
async def current_group_template(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_exists(project_id, db)
    row = await get_project_group_template(db, project_id)
    if row is None:
        raise HTTPException(404, "当前项目尚未确认分组模板。")
    return asdict(serialize_project_group_template(row))


@router.put("/group-templates/current", response_model=GroupTemplateCommitOut)
async def save_current_group_template(
    project_id: int = Form(...),
    expected_content_hash: str = Form(...),
    expected_template_revision: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_exists(project_id, db)
    payload = await file.read(MAX_GROUP_TEMPLATE_BYTES + 1)
    parsed = parse_group_template_xml(file.filename or "", payload)
    if not parsed.can_confirm:
        raise _invalid_group_template(parsed)
    if parsed.content_hash != expected_content_hash:
        raise HTTPException(422, "确认文件与预览文件内容不一致，请重新预览。")
    try:
        result = await commit_project_group_template(
            db,
            project_id,
            parsed,
            expected_template_revision,
        )
        await db.commit()
        return asdict(result)
    except Exception:
        await db.rollback()
        raise


@router.put("/group-templates/mappings", response_model=ProjectGroupTemplateOut)
async def save_group_template_mappings(
    body: GroupTemplateMappingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_exists(body.project_id, db)
    try:
        result = await replace_project_group_mappings(
            db,
            body.project_id,
            body.mappings,
            body.expected_template_revision,
        )
        await db.commit()
        return asdict(result)
    except Exception:
        await db.rollback()
        raise


@router.put("/group-templates/step-mappings", response_model=ProjectGroupTemplateOut)
async def save_group_template_step_mappings(
    body: GroupTemplateStepMappingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_exists(body.project_id, db)
    try:
        result = await replace_project_group_step_mappings(
            db,
            body.project_id,
            body.mappings,
            body.expected_template_revision,
        )
        await db.commit()
        return asdict(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/workflow/reset", response_model=WorkflowResetOut)
async def reset_project_workflow(
    body: WorkflowResetRequest,
    db: AsyncSession = Depends(get_db),
):
    if body.from_step not in {3, 4}:
        raise HTTPException(400, "主动重置只支持第三步或第四步。")
    project = await _ensure_project_exists(body.project_id, db)
    result = await invalidate_project_workflow(
        db,
        project,
        from_step=body.from_step,
        expected_workflow_revision=body.expected_workflow_revision,
    )
    await db.commit()
    return WorkflowResetOut(**asdict(result))

async def _save_ops(db: AsyncSession, project_id: int, ops_data: list) -> None:
    await save_route_rules_ops(
        db,
        project_id,
        ops_data,
        normalize_operation_name=_normalize_operation_name,
        preserve_sequence_slot=_preserve_sequence_slot,
        infer_operation_chain=_infer_operation_chain,
    )


async def _extract_document_operation_details(
    db: AsyncSession,
    project_id: int,
    docs: list[Document] | None = None,
) -> list[DocumentOperationDetail]:
    return await extract_route_rules_document_operation_details(
        db,
        project_id,
        docs=docs,
        detail_row_normalized_names=_detail_row_normalized_names,
        normalize_operation_name=_normalize_operation_name,
    )


async def _ensure_document_operation_details(
    db: AsyncSession,
    project_id: int,
    progress_callback: Callable[[str, int], None] | None = None,
) -> list[DocumentOperationDetail]:
    return await ensure_route_rules_document_operation_details(
        db,
        project_id,
        extract_document_operation_details_fn=_extract_document_operation_details,
        progress_callback=progress_callback,
    )


async def _list_superset_route_tree(project_id: int, db: AsyncSession) -> list[dict]:
    detail_rows = await _ensure_document_operation_details(db, project_id)
    if not detail_rows:
        return await list_operations(project_id=project_id, db=db)

    operation_rows = (
        await db.execute(
            select(Operation)
            .where(Operation.project_id == project_id)
            .options(selectinload(Operation.factors))
            .order_by(Operation.sequence.asc(), Operation.id.asc())
        )
    ).scalars().all()
    sample_count = await get_project_sample_count(db, project_id)
    tree_items = build_superset_process_tree(
        operations=operation_rows,
        detail_rows=detail_rows,
        sample_count=sample_count,
    )
    if not tree_items:
        return await list_operations(project_id=project_id, db=db)
    return tree_items


async def _ensure_project_route_merge_snapshot(project_id: int, db: AsyncSession) -> dict:
    return await ensure_route_merge_snapshot(
        project_id,
        db,
        lambda: _list_superset_route_tree(project_id=project_id, db=db),
        lambda: _ensure_document_operation_details(db, project_id),
    )


async def _count_project_documents(project_id: int, db: AsyncSession) -> int:
    rows = (
        await db.execute(
            select(Document.id).where(Document.project_id == project_id)
        )
    ).all()
    return len(rows)


def _route_tree_operations_by_id(tree_operations: list[object]) -> dict[int, dict]:
    operations_by_id: dict[int, dict] = {}
    for op in tree_operations:
        if isinstance(op, dict):
            op_id = int(op.get("id") or 0)
            if op_id > 0:
                operations_by_id[op_id] = dict(op)
            continue
        op_id = int(getattr(op, "id", 0) or 0)
        if op_id <= 0:
            continue
        operations_by_id[op_id] = op.model_dump() if hasattr(op, "model_dump") else dict(op)
    return operations_by_id


async def _extract_route_set_with_llm(db: AsyncSession, project_id: int) -> List[OperationOut] | None:
    return await extract_route_set_with_llm_runtime(
        db,
        project_id,
        collect_candidate_summary=_collect_candidate_summary,
        ensure_document_operation_details_fn=_ensure_document_operation_details,
        merge_document_detail_rows_into_candidate_summary=_merge_document_detail_rows_into_candidate_summary,
        build_route_set_ops_from_candidates=_build_route_set_ops_from_candidates,
        set_extraction_task_state=set_extraction_task_state,
    )


@router.post("/start", response_model=ExtractionTaskStartOut)
async def start_extraction(
    project_id: int,
    force_reextract: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    触发 AI 提取。
    第二步规则提炼必须依赖大模型。
    如果大模型未配置、调用失败或返回结果无法解析，则直接报错。
    """
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "任务不存在")

    payload = await queue_extraction_job(
        project_id=project_id,
        force_reextract=force_reextract,
        db=db,
        project=project,
        job_factory=lambda: asyncio.create_task(
            run_extraction_pipeline(
                project_id=project_id,
                force_reextract=force_reextract,
                async_session_factory=async_session,
                extract_route_set_with_llm=_extract_route_set_with_llm,
                save_ops=_save_ops,
            )
        ),
    )
    return ExtractionTaskStartOut(**payload)


@router.get("/operations", response_model=List[OperationOut])
async def list_operations(project_id: int, db: AsyncSession = Depends(get_db)):
    """获取当前已提炼的工序列表"""
    result = await db.execute(
        select(Operation)
        .where(Operation.project_id == project_id)
        .options(selectinload(Operation.factors))
        .order_by(Operation.sequence)
    )
    operations = result.scalars().all()
    sample_count = await get_project_sample_count(db, project_id)
    serialized = [_serialize_operation(op, sample_count) for op in operations]
    return _merge_serialized_operations(serialized)


@router.get("/document-operation-details", response_model=DocumentOperationDetailListOut)
async def get_document_operation_details(
    project_id: int,
    document_id: int | None = None,
    operation_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_document_operation_details(db, project_id)
    stmt = select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == project_id)
    if document_id is not None:
        stmt = stmt.where(DocumentOperationDetail.document_id == document_id)
    if operation_name:
        stmt = stmt.where(DocumentOperationDetail.operation_name == operation_name.strip())
    stmt = stmt.order_by(
        DocumentOperationDetail.pdf_name.asc(),
        DocumentOperationDetail.operation_seq.asc(),
        DocumentOperationDetail.page_no.asc(),
        DocumentOperationDetail.id.asc(),
    )
    items = (await db.execute(stmt)).scalars().all()
    return {
        "project_id": project_id,
        "items": items,
    }


@router.get("/superset-route", response_model=SupersetRouteOut)
async def get_superset_route(project_id: int, db: AsyncSession = Depends(get_db)):
    ops = await _list_superset_route_tree(project_id=project_id, db=db)
    return {
        "project_id": project_id,
        "superset_route": ops,
    }


@router.get("/merge-suggestions", response_model=MergeSuggestionListOut)
async def get_merge_suggestions(project_id: int, db: AsyncSession = Depends(get_db)):
    snapshot = await _ensure_project_route_merge_snapshot(project_id, db)
    return {
        "project_id": project_id,
        "merge_suggestions": snapshot.get("merge_suggestions") or [],
        "source_signature": str(snapshot.get("source_signature") or ""),
        "algo_version": ROUTE_MERGE_ALGO_VERSION,
    }


@router.get("/normalized-superset-route", response_model=NormalizedSupersetRouteOut)
async def get_normalized_superset_route(project_id: int, db: AsyncSession = Depends(get_db)):
    snapshot = await _ensure_project_route_merge_snapshot(project_id, db)
    return {
        "project_id": project_id,
        "normalized_superset_route": snapshot.get("normalized_superset_route") or [],
        "source_signature": str(snapshot.get("source_signature") or ""),
        "algo_version": ROUTE_MERGE_ALGO_VERSION,
    }


@router.get("/saved-normalized-route", response_model=SavedNormalizedRouteVersionOut)
async def get_saved_normalized_route(project_id: int, db: AsyncSession = Depends(get_db)):
    # Check the parent first.  Otherwise a stale browser project_id reaches the
    # snapshot writer and SQLite reports a misleading foreign-key 500.
    await _ensure_project_exists(project_id, db)
    await _ensure_project_route_merge_snapshot(project_id, db)
    version_row = await ensure_saved_normalized_route_version(
        project_id,
        db,
        lambda: _ensure_document_operation_details(db, project_id),
    )
    if not version_row:
        raise HTTPException(404, "当前任务还没有已保存的标准化路线。")
    return await build_saved_normalized_route_response(version_row, db)


@router.post("/normalized-superset-route/save", response_model=NormalizedSupersetRouteOut)
async def save_normalized_superset_route(
    body: SaveNormalizedSupersetRouteRequest,
    db: AsyncSession = Depends(get_db),
):
    snapshot = await _ensure_project_route_merge_snapshot(body.project_id, db)
    detail_rows = await _ensure_document_operation_details(db, body.project_id)
    total_docs = await _count_project_documents(body.project_id, db)
    normalized_route = await persist_normalized_superset_route(
        project_id=body.project_id,
        db=db,
        snapshot=snapshot,
        items=list(body.normalized_superset_route or []),
        detail_rows=detail_rows,
        total_docs=total_docs,
    )
    latest_version = await get_latest_normalized_route_version(body.project_id, db)
    force_new_version = bool(
        latest_version
        and str(latest_version.source_signature or "") != str(snapshot.get("source_signature") or "")
    )
    version_row = await save_normalized_route_version(
        project_id=body.project_id,
        db=db,
        source_signature=str(snapshot.get("source_signature") or ""),
        total_docs=total_docs,
        normalized_route=normalized_route,
        force_new_version=force_new_version,
    )
    return {
        "project_id": body.project_id,
        "normalized_superset_route": normalized_route,
        "saved_route_version": version_row.version,
    }


@router.post("/segment-rule-reviews", response_model=SegmentRuleReviewSaveOut)
async def save_segment_rule_review(
    body: SaveSegmentRuleReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
    return await save_segment_rule_review_record(
        project_id=body.project_id,
        route_id=body.route_id,
        segment_id=body.segment_id,
        decision=str(body.decision or "accepted").strip().lower(),
        note=str(body.note or "").strip(),
        summary_lines=list(body.summary_lines or []),
        question_trail=list(body.question_trail or []),
        db=db,
    )


@router.post("/finalized-rule-packages", response_model=FinalizedRulePackageOut)
async def save_finalized_rule_package(
    body: FinalizedRulePackageSaveRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await acquire_workflow_revision(
        db,
        body.project_id,
        body.expected_workflow_revision,
    )
    # A project remains based on the same reviewed route after step 5 has run.
    # Allow publishing a corrected package in that state; the route-version
    # ownership check below still prevents cross-project or stale-route saves.
    if project.status not in {"ROUTE_SET_READY", "GENERATED"}:
        raise HTTPException(409, "当前资料已变更或尚未完成路线提炼，请重新完成第二至四步后再导出规则包。")
    if not body.input_schema:
        raise HTTPException(400, "input_schema.json 内容不能为空")
    if not body.route_catalog:
        raise HTTPException(400, "route_catalog.json 内容不能为空")
    if not body.route_rules:
        raise HTTPException(400, "route_rules.json 内容不能为空")
    if not (body.rule_report_md or "").strip():
        raise HTTPException(400, "rule_report.md 内容不能为空")

    schema_version = str(body.schema_version or "1.0").strip()
    if schema_version not in {"1.0", "2.0"}:
        raise HTTPException(400, f"不支持的规则包 schema_version：{schema_version}")
    package_name = (body.package_name or "process_route_rules").strip() or "process_route_rules"

    server_validation = dict(body.validation_report or {})
    manifest = dict(body.manifest or {})
    test_cases = list(body.test_cases or [])
    if schema_version == "2.0":
        try:
            package_v2 = RulePackageV2.model_validate({
                "manifest": manifest,
                "input_schema": body.input_schema,
                "route_catalog": body.route_catalog,
                "route_rules": body.route_rules,
                "test_cases": test_cases,
            })
        except ValidationError as exc:
            raise HTTPException(422, detail=exc.errors(include_url=False)) from exc
        if package_v2.manifest.project_id != body.project_id:
            raise HTTPException(422, "manifest.project_id 与请求 project_id 不一致")
        if package_v2.manifest.package_name != package_name:
            raise HTTPException(422, "manifest.package_name 与请求 package_name 不一致")
        validation = validate_rule_package(package_v2)
        server_validation = validation.model_dump(mode="json")
        if not validation.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "规则包校验未通过，无法导出。",
                    "validation": server_validation,
                },
            )
        if body.route_version_id is None:
            raise HTTPException(422, "V2 规则包必须关联当前路线版本")
        await require_confirmed_user_rule_sources(
            package_v2,
            project_id=body.project_id,
            route_version_id=body.route_version_id,
            db=db,
        )
        content_hash = rule_package_content_hash(package_v2)
        mapping_registry = await load_effective_mapping_registry(db, body.project_id)
        kmai_compatibility = build_kmai_compatibility_export(
            package_v2,
            mapping_registry=mapping_registry,
        )
        if not kmai_compatibility.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "KmAI compatibility validation failed; mapping resolution is required before publishing.",
                    "kmai_compatibility": kmai_compatibility.model_dump(mode="json"),
                },
            )
        server_validation["kmai_compatibility"] = {
            "mapping_signature": kmai_compatibility.mapping_signature,
            "mapping_snapshot": [
                snapshot.model_dump(mode="json")
                for snapshot in kmai_compatibility.mapping_usages
            ],
        }
    else:
        content_hash = legacy_rule_package_content_hash(
            package_name=package_name,
            input_schema=body.input_schema,
            route_catalog=body.route_catalog,
            route_rules=body.route_rules,
            rule_report_md=body.rule_report_md,
        )

    if body.route_version_id is not None:
        route_exists = (
            await db.execute(
                select(NormalizedRouteVersion.id).where(
                    NormalizedRouteVersion.id == body.route_version_id,
                    NormalizedRouteVersion.project_id == body.project_id,
                )
            )
        ).scalar_one_or_none()
        if not route_exists:
            raise HTTPException(422, "规则包关联的路线版本不属于当前任务")

    # The database owns the final uniqueness guarantee. Retry after a competing
    # export instead of leaking a raw unique-index error to the user.
    for _ in range(3):
        latest_version = (
            await db.execute(
                select(func.max(FinalizedRulePackage.version)).where(
                    FinalizedRulePackage.project_id == body.project_id
                )
            )
        ).scalar_one_or_none()
        row = FinalizedRulePackage(
            project_id=body.project_id,
            route_version_id=body.route_version_id,
            version=int(latest_version or 0) + 1,
            package_name=package_name,
            schema_version=schema_version,
            status="draft",
            manifest_json=json_dumps(manifest),
            input_schema_json=json_dumps(body.input_schema),
            route_catalog_json=json_dumps(body.route_catalog),
            route_rules_json=json_dumps(body.route_rules),
            test_cases_json=json_dumps_list(test_cases),
            rule_report_md=body.rule_report_md,
            validation_report_json=json_dumps(server_validation),
            content_hash=content_hash,
            created_by=(body.created_by or "默认用户").strip() or "默认用户",
        )
        db.add(row)
        try:
            await db.flush()
            if schema_version == "2.0":
                await record_mapping_usage(db, row.id, kmai_compatibility.mapping_usages)
            await publish_rule_package(row, db, actor=row.created_by)
            await db.commit()
            await db.refresh(row)
            return serialize_finalized_rule_package(
                row,
                kmai_compatibility=(
                    kmai_compatibility.model_dump(mode="json")
                    if schema_version == "2.0"
                    else None
                ),
            )
        except IntegrityError:
            await db.rollback()

    raise HTTPException(409, "规则包版本正在由其他请求导出，请稍后重试。")


@router.get("/finalized-rule-packages/latest", response_model=FinalizedRulePackageOut)
async def get_latest_finalized_rule_package(project_id: int, db: AsyncSession = Depends(get_db)):
    await _ensure_project_exists(project_id, db)
    row = await load_published_rule_package(project_id, db)
    if not row:
        raise HTTPException(404, "当前任务还没有导出的规则包。")
    return serialize_finalized_rule_package(row)


@router.get("/finalized-rule-packages", response_model=List[FinalizedRulePackageListItemOut])
async def list_finalized_rule_packages(project_id: int, db: AsyncSession = Depends(get_db)):
    await _ensure_project_exists(project_id, db)
    rows = (
        await db.execute(
            select(FinalizedRulePackage)
            .where(FinalizedRulePackage.project_id == project_id)
            .order_by(FinalizedRulePackage.version.desc(), FinalizedRulePackage.id.desc())
        )
    ).scalars().all()
    return [
        FinalizedRulePackageListItemOut(
            id=row.id,
            project_id=row.project_id,
            route_version_id=row.route_version_id,
            version=row.version,
            package_name=row.package_name,
            schema_version=row.schema_version or "1.0",
            status=row.status or "published",
            content_hash=row.content_hash or "",
            created_by=row.created_by or "默认用户",
            created_at=row.created_at,
            published_by=row.published_by,
            published_at=row.published_at,
            supersedes_id=row.supersedes_id,
            validation_report=json_loads(row.validation_report_json),
            test_case_count=len(json_loads_list(row.test_cases_json)),
        )
        for row in rows
    ]


@router.post("/merge-suggestions/review")
async def review_merge_suggestion(
    body: MergeSuggestionReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    snapshot = await _ensure_project_route_merge_snapshot(body.project_id, db)
    tree_operations = await _list_superset_route_tree(project_id=body.project_id, db=db)
    operations_by_id = _route_tree_operations_by_id(tree_operations)
    detail_rows = (
        await db.execute(
            select(DocumentOperationDetail)
            .where(DocumentOperationDetail.project_id == body.project_id)
            .order_by(
                DocumentOperationDetail.operation_seq.asc(),
                DocumentOperationDetail.page_no.asc(),
                DocumentOperationDetail.id.asc(),
            )
        )
    ).scalars().all()
    action = (body.action or "").strip().lower()
    try:
        snapshot = apply_merge_suggestion_review(
            snapshot=snapshot,
            suggestion_id=body.suggestion_id,
            action=action,
            manual_label=(body.manual_label or ""),
            operations_by_id=operations_by_id,
            detail_rows=detail_rows,
        )
    except ValueError:
        raise HTTPException(400, "不支持的审核动作")
    except KeyError as exc:
        if str(exc) == "'missing_suggestion'":
            raise HTTPException(404, "归并建议不存在")
        if str(exc) == "'missing_group'":
            raise HTTPException(404, "归并段不存在")
        raise
    await save_route_merge_snapshot(
        body.project_id,
        db,
        snapshot,
        review_state=dict(snapshot.get("review_state") or {}),
    )
    await db.commit()
    return {
        "ok": True,
        "project_id": body.project_id,
        "suggestion_id": body.suggestion_id,
        "action": action,
    }


@router.get("/task-status", response_model=ExtractionTaskStatusOut)
async def get_task_status(project_id: int, db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "任务不存在")
    payload = await resolve_extraction_task_status(
        project_id=project_id,
        project=project,
        db=db,
    )
    return ExtractionTaskStatusOut(**payload)
