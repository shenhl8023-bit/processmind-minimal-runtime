"""Internal executable revision APIs, separate from immutable exports."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.product_profile import get_product_profile
from app.database import get_db
from app.schemas.schemas import FinalizedRulePackageSaveRequest, GroupTemplateStepMappingsUpdateRequest
from app.services.project_workflow_lifecycle import acquire_workflow_revision
from app.services.rule_packages.executable_revisions import (current_revision, export_revision, latest_revision,
    require_generation, save_revision, serialize_revision)


router = APIRouter(prefix="/api/extract/executable-rule-revisions", tags=["内部可执行规则版本"])


class ExecutableRevisionSaveRequest(FinalizedRulePackageSaveRequest):
    model_config = ConfigDict(extra="forbid")
    expected_executable_revision: int = Field(ge=0)


class ExecutableRevisionExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int
    expected_workflow_revision: int = Field(default=0, ge=0)
    expected_content_hash: str
    include_template_mapping: bool = False
    template_mapping: Optional[dict] = None


@router.post("")
async def save_executable_revision(body: ExecutableRevisionSaveRequest, db: AsyncSession = Depends(get_db)):
    try:
        project = await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
        row = await save_revision(db, project, body)
        result = await serialize_revision(db, row)
        await db.commit()
        return result
    except ValidationError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        await db.rollback()
        raise


@router.get("/latest")
async def get_latest_executable_revision(project_id: int, db: AsyncSession = Depends(get_db)):
    row = await latest_revision(db, project_id)
    if row is None:
        raise HTTPException(404, {"message": "当前任务尚未保存可执行规则版本。", "executable_revision": 0})
    return await serialize_revision(db, row)


@router.post("/{revision_id}/export")
async def export_executable_revision(revision_id: int, body: ExecutableRevisionExportRequest,
                                     db: AsyncSession = Depends(get_db)):
    from app.services.project_group_templates import replace_project_group_step_mappings
    from app.services.rule_packages.demo_tables import DemoTableError
    from app.services.rule_packages.native_publication import NativePublicationError

    try:
        project = await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
        row = await require_generation(db, project.id, revision_id)
        if body.expected_content_hash != row.content_hash:
            raise HTTPException(409, "可执行规则内容已变化，请刷新后重新导出。")
        if body.include_template_mapping and not get_product_profile().template_mapping_enabled:
            raise HTTPException(409, "当前版本不提供模板映射。")
        if body.template_mapping is not None:
            if not body.include_template_mapping:
                raise HTTPException(422, "保存模板映射时必须选择附加模板映射。")
            mapping = GroupTemplateStepMappingsUpdateRequest.model_validate({
                **body.template_mapping, "project_id": project.id,
                "expected_workflow_revision": body.expected_workflow_revision})
            await replace_project_group_step_mappings(db, project.id, mapping.mappings,
                mapping.expected_template_revision, mapping.operations, replace_all=mapping.replace_all,
                step_order_by_process=mapping.step_order_by_process,
                expected_route_version_id=mapping.expected_route_version_id,
                hidden_step_keys=mapping.hidden_step_keys, waived_group_paths=mapping.waived_group_paths)
        result = await export_revision(db, project, row, include_template_mapping=body.include_template_mapping)
        await db.commit()
        return result
    except (DemoTableError, NativePublicationError, ValidationError) as exc:
        await db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        await db.rollback()
        raise
