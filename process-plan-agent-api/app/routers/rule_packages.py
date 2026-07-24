"""Rule package V2 compile, validate, and draft simulation APIs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from app.services.rule_packages import (
    compile_rule_package,
    plan_route,
    rule_package_content_hash,
    validate_rule_package,
)
from app.services.rule_packages.contracts import (
    CompileRulePackageRequest,
    CompileRulePackageResponse,
    KmaiCompatibilityTestRequest,
    KmaiCompatibilityTestResponse,
    RulePackageV2,
    RulePackageValidationReport,
    SimulateRulePackageRequest,
    SimulateRulePackageResponse,
)
from app.services.rule_packages.planner import RoutePlanningError
from app.services.rule_packages.input_validation import validate_inputs
from app.services.rule_packages.loader import load_published_rule_package
from app.services.rule_packages.lifecycle import v2_package_from_row
from app.services.rule_packages.kmai_compatibility_runner import compare_kmai_v1
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.condition_contracts import (
    ConditionFieldRegistryResponse,
    ConfirmRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionReviewResponse,
    SaveRuleConditionDraftRequest,
)
from app.services.rule_packages.condition_registry import FIELD_REGISTRY_VERSION, condition_fields
from app.services.rule_packages.condition_reviews import (
    confirm_condition_review,
    parse_condition_review,
    save_condition_draft,
)


router = APIRouter(prefix="/api/extract/finalized-rule-packages", tags=["规则包 V2"])


@router.get("/condition-fields", response_model=ConditionFieldRegistryResponse)
async def get_condition_fields():
    return ConditionFieldRegistryResponse(version=FIELD_REGISTRY_VERSION, fields=condition_fields())


@router.post("/rule-conditions/draft", response_model=RuleConditionReviewResponse)
async def save_rule_condition_draft(
    body: SaveRuleConditionDraftRequest,
    db: AsyncSession = Depends(get_db),
):
    return await save_condition_draft(body, db)


@router.post("/rule-conditions/parse", response_model=RuleConditionReviewResponse)
async def parse_user_rule_condition(
    body: ParseRuleConditionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await parse_condition_review(body, db)


@router.post("/rule-conditions/confirm", response_model=RuleConditionReviewResponse)
async def confirm_user_rule_condition(
    body: ConfirmRuleConditionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await confirm_condition_review(body, db)


@router.post("/compile", response_model=CompileRulePackageResponse)
async def compile_v2_rule_package(body: CompileRulePackageRequest):
    package = compile_rule_package(body)
    return CompileRulePackageResponse(
        package=package,
        content_hash=rule_package_content_hash(package),
        validation=validate_rule_package(package),
        kmai_compatibility=build_kmai_compatibility_export(package),
    )


@router.post("/validate", response_model=RulePackageValidationReport)
async def validate_v2_rule_package(body: RulePackageV2):
    return validate_rule_package(body)


@router.post("/simulate", response_model=SimulateRulePackageResponse)
async def simulate_v2_rule_package(body: SimulateRulePackageRequest):
    validation = validate_rule_package(body.package)
    content_hash = rule_package_content_hash(body.package)
    if not validation.valid:
        return SimulateRulePackageResponse(content_hash=content_hash, validation=validation)
    input_errors = validate_inputs(body.package.input_schema, body.inputs)
    if input_errors:
        raise HTTPException(
            status_code=422,
            detail=[issue.model_dump(mode="json") for issue in input_errors],
        )
    try:
        plan = plan_route(body.package, body.inputs)
    except RoutePlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SimulateRulePackageResponse(content_hash=content_hash, validation=validation, plan=plan)


@router.post("/compatibility-test", response_model=KmaiCompatibilityTestResponse)
async def test_kmai_compatibility(
    body: KmaiCompatibilityTestRequest,
    db: AsyncSession = Depends(get_db),
):
    package_row = await load_published_rule_package(body.project_id, db)
    if not package_row:
        raise HTTPException(404, "当前任务没有已发布的规则包。")
    if str(package_row.schema_version or "") != "2.0":
        raise HTTPException(422, "KmAI 可视化兼容测试仅支持 V2 规则包。")
    package = v2_package_from_row(package_row)
    validation = validate_rule_package(package)
    if not validation.valid:
        raise HTTPException(422, detail=validation.model_dump(mode="json"))
    input_errors = validate_inputs(package.input_schema, body.inputs)
    if input_errors:
        raise HTTPException(422, detail=[issue.model_dump(mode="json") for issue in input_errors])
    comparison = compare_kmai_v1(package, body.inputs)
    return KmaiCompatibilityTestResponse(
        project_id=body.project_id,
        package_id=package_row.id,
        package_version=package_row.version,
        **comparison,
    )
