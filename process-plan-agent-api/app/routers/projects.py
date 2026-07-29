"""
项目 / 任务管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.paths import UPLOAD_DIR
from app.database import get_db
from app.models.models import (
    Document,
    DocumentOperationDetail,
    Factor,
    FinalizedRulePackage,
    GeneratedRoute,
    KmaiFactorMapping,
    KmaiFactorMappingEvent,
    NormalizedRouteVersion,
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    Operation,
    ParamAuditAnswer,
    ParamRuleSnapshot,
    Project,
    Reference,
    RouteMergeSnapshot,
)
from app.schemas.schemas import ProjectCreate, ProjectOut, ProjectProfileOut, ProjectRuleEngineUpdate
from app.services.extraction_tasks import cancel_extraction_task, delete_extraction_task_state
from app.services.profile_registry import list_profiles, normalize_profile

router = APIRouter(prefix="/api/projects", tags=["项目管理"])


async def _legacy_table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
        {"table_name": table_name},
    )
    return result.first() is not None


async def _delete_legacy_rule_asset_rows(project_id: int, db: AsyncSession) -> None:
    """Clean old rule-asset rows without keeping their retired ORM models alive."""
    tables = {
        name: await _legacy_table_exists(db, name)
        for name in (
            "operation_rules",
            "route_template_operations",
            "route_templates",
            "factor_definition_options",
            "factor_definitions",
        )
    }

    if tables["operation_rules"]:
        if tables["route_template_operations"] and tables["route_templates"]:
            await db.execute(text("""
                DELETE FROM operation_rules
                WHERE project_id = :project_id
                   OR template_operation_id IN (
                       SELECT route_template_operations.id
                       FROM route_template_operations
                       JOIN route_templates
                         ON route_templates.id = route_template_operations.template_id
                       WHERE route_templates.project_id = :project_id
                   )
            """), {"project_id": project_id})
        else:
            await db.execute(
                text("DELETE FROM operation_rules WHERE project_id = :project_id"),
                {"project_id": project_id},
            )

    if tables["route_template_operations"] and tables["route_templates"]:
        await db.execute(text("""
            DELETE FROM route_template_operations
            WHERE template_id IN (
                SELECT id FROM route_templates WHERE project_id = :project_id
            )
        """), {"project_id": project_id})

    if tables["route_templates"]:
        await db.execute(
            text("DELETE FROM route_templates WHERE project_id = :project_id"),
            {"project_id": project_id},
        )

    if tables["factor_definition_options"] and tables["factor_definitions"]:
        await db.execute(text("""
            DELETE FROM factor_definition_options
            WHERE factor_definition_id IN (
                SELECT id FROM factor_definitions WHERE project_id = :project_id
            )
        """), {"project_id": project_id})

    if tables["factor_definitions"]:
        await db.execute(
            text("DELETE FROM factor_definitions WHERE project_id = :project_id"),
            {"project_id": project_id},
        )


@router.get("/", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.updated_at.desc(), Project.id.desc()))
    return result.scalars().all()


@router.get("/profiles", response_model=list[ProjectProfileOut])
async def list_project_profiles(mode: str | None = None):
    return [
        ProjectProfileOut(
            key=profile.key,
            mode=profile.mode,
            label=profile.label,
            short_label=profile.short_label,
            description=profile.description,
        )
        for profile in list_profiles(mode)
    ]


@router.post("/", response_model=ProjectOut)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    mode = "route_rules"
    profile = normalize_profile(mode, body.profile)
    sequence_result = await db.execute(
        text("INSERT INTO project_id_sequence DEFAULT VALUES RETURNING id")
    )
    project_id = int(sequence_result.scalar_one())
    project = Project(
        id=project_id,
        name=body.name,
        mode=mode,
        profile=profile,
        rule_engine="auto",
        status="CREATED",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.patch("/{project_id}/rule-engine", response_model=ProjectOut)
async def update_project_rule_engine(
    project_id: int,
    body: ProjectRuleEngineUpdate,
    db: AsyncSession = Depends(get_db),
):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "任务不存在")
    normalized = str(body.rule_engine or "auto").strip().lower()
    if normalized not in {"auto", "v1", "v2"}:
        raise HTTPException(400, "规则引擎只支持 auto / v1 / v2")
    project.rule_engine = normalized
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "任务不存在")

    cancel_extraction_task(project_id)

    docs = (await db.execute(select(Document).where(Document.project_id == project_id))).scalars().all()
    refs = (await db.execute(select(Reference).where(Reference.project_id == project_id))).scalars().all()
    ops = (await db.execute(select(Operation).where(Operation.project_id == project_id))).scalars().all()
    detail_rows = (await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == project_id))).scalars().all()
    routes = (await db.execute(select(GeneratedRoute).where(GeneratedRoute.project_id == project_id))).scalars().all()
    param_answers = (await db.execute(select(ParamAuditAnswer).where(ParamAuditAnswer.project_id == project_id))).scalars().all()
    param_snapshots = (await db.execute(select(ParamRuleSnapshot).where(ParamRuleSnapshot.project_id == project_id))).scalars().all()
    route_merge_snapshots = (await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == project_id))).scalars().all()
    normalized_route_versions = (await db.execute(select(NormalizedRouteVersion).where(NormalizedRouteVersion.project_id == project_id))).scalars().all()
    segment_factor_reviews = (await db.execute(select(NormalizedRouteSegmentFactorReview).where(NormalizedRouteSegmentFactorReview.project_id == project_id))).scalars().all()
    segment_rule_reviews = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(NormalizedRouteSegmentRuleReview.project_id == project_id))).scalars().all()
    finalized_rule_packages = (await db.execute(select(FinalizedRulePackage).where(FinalizedRulePackage.project_id == project_id))).scalars().all()
    kmai_factor_mappings = (await db.execute(select(KmaiFactorMapping).where(KmaiFactorMapping.project_id == project_id))).scalars().all()
    mapping_ids = [mapping.id for mapping in kmai_factor_mappings]
    mapping_events = []
    if mapping_ids:
        mapping_events = (
            await db.execute(
                select(KmaiFactorMappingEvent).where(KmaiFactorMappingEvent.mapping_id.in_(mapping_ids))
            )
        ).scalars().all()
    file_paths = [
        UPLOAD_DIR / doc.filename
        for doc in docs
        if doc.filename
    ] + [
        UPLOAD_DIR / ref.filename
        for ref in refs
        if ref.ref_type == "uploaded" and ref.filename
    ]

    for row in detail_rows:
        await db.delete(row)

    for ref in refs:
        await db.delete(ref)

    for doc in docs:
        await db.delete(doc)

    for op in ops:
        factors = (await db.execute(select(Factor).where(Factor.operation_id == op.id))).scalars().all()
        for factor in factors:
            await db.delete(factor)
        await db.delete(op)

    for route in routes:
        await db.delete(route)

    for package in finalized_rule_packages:
        await db.delete(package)

    # Flush package deletes first so SQLite applies the usage cascade before
    # project mapping rows are deleted with their RESTRICT usage reference.
    await db.flush()

    for event in mapping_events:
        await db.delete(event)

    # Explicitly remove project-owned mappings after package usages. This also
    # works for legacy SQLite databases where ORM-level deletes are used.
    for mapping in kmai_factor_mappings:
        await db.delete(mapping)

    await _delete_legacy_rule_asset_rows(project_id, db)

    for answer in param_answers:
        await db.delete(answer)

    for snapshot in param_snapshots:
        await db.delete(snapshot)

    for snapshot in route_merge_snapshots:
        await db.delete(snapshot)

    for review in segment_factor_reviews:
        await db.delete(review)

    for review in segment_rule_reviews:
        await db.delete(review)

    for version in normalized_route_versions:
        await db.delete(version)

    await delete_extraction_task_state(db, project_id)

    await db.delete(project)
    await db.commit()
    for path in file_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True}
