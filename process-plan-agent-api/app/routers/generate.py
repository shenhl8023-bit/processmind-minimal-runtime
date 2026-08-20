"""HTTP boundary for route generation and factor-schema reads."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import GeneratedRoute
from app.schemas.schemas import FactorFieldOut, GenerateRequest, GenerateResponse
from app.services.generate_route_result_builder import (
    build_generate_output_json,
    build_generate_summary,
)
from app.services.project_workflow_lifecycle import acquire_workflow_revision
from app.services.route_generation import (
    RouteGenerationNoExecutableRoute,
    RouteGenerationInvalidPackage,
    RouteGenerationNoPublishedPackage,
    RouteGenerationProjectNotFound,
    RouteGenerationV2ValueError,
    generate_published_route,
    load_project_factor_schema,
    normalize_input_values as _normalize_input_values,
)
from app.services.rule_packages.execution import (
    PublishedRulePackageChanged,
    PublishedRulePackageInputInvalid,
    PublishedRulePackageSourcesChanged,
)
from app.services.rule_packages.input_validation import input_validation_error_detail
from app.services.rule_packages.lifecycle import RulePackageLifecycleError
from app.services.rule_packages.planner import RoutePlanningError


router = APIRouter(prefix="/api/generate", tags=["工艺路线生成"])


@router.get("/factor-schema", response_model=list[FactorFieldOut])
async def get_factor_schema(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await load_project_factor_schema(project_id, db)
    except RouteGenerationProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/", response_model=GenerateResponse)
async def generate_route(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate only from the currently valid published package."""
    if not body.project_id:
        raise HTTPException(status_code=400, detail="project_id 不能为空")

    await acquire_workflow_revision(
        db,
        body.project_id,
        body.expected_workflow_revision,
    )
    try:
        result = await generate_published_route(body, db)
    except PublishedRulePackageSourcesChanged as exc:
        # The execution guard archived a stale package; persist that state before
        # returning its stable conflict payload.
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except PublishedRulePackageChanged as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except RouteGenerationProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RouteGenerationNoPublishedPackage as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RouteGenerationInvalidPackage as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"已发布规则包 V{exc.version} 校验未通过，无法生成",
                "validation": exc.validation.model_dump(mode="json"),
            },
        ) from exc
    except PublishedRulePackageInputInvalid as exc:
        raise HTTPException(
            status_code=422,
            detail=input_validation_error_detail(exc.issues),
        ) from exc
    except RulePackageLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RouteGenerationNoExecutableRoute, RouteGenerationV2ValueError, RoutePlanningError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    project = result.project
    if project is None:
        raise RuntimeError("路线生成服务未返回项目实体")

    route = GeneratedRoute(
        project_id=body.project_id,
        input_factors=body.model_dump_json(),
        result_json=json.dumps(
            {
                "steps": [step.model_dump() for step in result.steps],
                "rule_package_id": result.rule_package_id,
                "rule_package_version": result.rule_package_version,
                "rule_package_hash": result.rule_package_hash,
                "schema_version": result.schema_version,
                "matched_rule_ids": result.matched_rule_ids,
                "selected_process_ids": result.selected_process_ids,
                "output_mode": result.output_mode,
            },
            ensure_ascii=False,
        ),
    )
    db.add(route)
    project.status = "GENERATED"
    await db.commit()
    await db.refresh(route)

    return GenerateResponse(
        id=route.id,
        steps=result.steps,
        summary=build_generate_summary(result.steps, result.summary),
        output_json_text=build_generate_output_json(body.project_id, result.output_mode, result.steps),
        output_mode=result.output_mode,
        rule_package_id=result.rule_package_id,
        rule_package_version=result.rule_package_version,
        rule_package_hash=result.rule_package_hash,
        schema_version=result.schema_version,
        matched_rule_ids=result.matched_rule_ids,
        selected_process_ids=result.selected_process_ids,
    )
