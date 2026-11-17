"""Project-local analysis guidance; changes apply to subsequent answers only."""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.analysis_guidance import (
    get_analysis_guidance, save_analysis_guidance, validate_guidance_update,
)


router = APIRouter(prefix="/api/projects", tags=["项目分析配置"])


@router.post("/{project_id}/analysis-guidance/generate")
async def generate_project_analysis_guidance(project_id: int, retry_recommendations: bool = False, db: AsyncSession = Depends(get_db)):
    from app.services.analysis_guidance_generation import generate_analysis_guidance
    return await generate_analysis_guidance(db, project_id, retry_recommendations)


@router.get("/{project_id}/analysis-guidance")
async def read_project_analysis_guidance(project_id: int, db: AsyncSession = Depends(get_db)):
    return await get_analysis_guidance(db, project_id)


@router.put("/{project_id}/analysis-guidance")
async def update_project_analysis_guidance(
    project_id: int, body: Dict[str, Any], db: AsyncSession = Depends(get_db),
):
    update = validate_guidance_update(body)
    # Compatibility writes are not a freshly generated file/model result.
    update.configuration.generation_version = None
    update.configuration.generation_route_id = None
    return await save_analysis_guidance(db, project_id, update)
