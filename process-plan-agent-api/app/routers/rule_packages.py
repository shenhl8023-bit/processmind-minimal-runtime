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
    RulePackageV2,
    RulePackageValidationReport,
    SimulateRulePackageRequest,
    SimulateRulePackageResponse,
)
from app.services.rule_packages.planner import RoutePlanningError
from app.services.rule_packages.input_validation import canonicalize_inputs, input_validation_error_detail, validate_inputs
from app.services.rule_packages.condition_contracts import (
    ConditionFieldRegistryResponse,
    ConfirmRuleConditionRequest,
    ManualRuleConditionRequest,
    ParseRuleConditionRequest,
    RulePreprocessStartRequest,
    RulePreprocessStatusResponse,
    RuleConditionReviewResponse,
    SaveRuleConditionDraftRequest,
)
from app.services.rule_packages.condition_registry import FIELD_REGISTRY_VERSION, condition_fields
from app.services.rule_packages.condition_reviews import (
    confirm_condition_review,
    set_manual_condition_review,
    parse_condition_review,
    save_condition_draft,
)
from app.services.project_workflow_lifecycle import acquire_workflow_revision
from app.services.rule_preprocessing import get_rule_preprocessing_status, start_rule_preprocessing


router = APIRouter(prefix="/api/extract/finalized-rule-packages", tags=["规则包 V2"])


@router.get("/condition-fields", response_model=ConditionFieldRegistryResponse)
async def get_condition_fields():
    return ConditionFieldRegistryResponse(version=FIELD_REGISTRY_VERSION, fields=condition_fields())


@router.post("/rule-conditions/draft", response_model=RuleConditionReviewResponse)
async def save_rule_condition_draft(
    body: SaveRuleConditionDraftRequest,
    db: AsyncSession = Depends(get_db),
):
    await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
    return await save_condition_draft(body, db)


@router.post("/rule-conditions/parse", response_model=RuleConditionReviewResponse)
async def parse_user_rule_condition(
    body: ParseRuleConditionRequest,
    db: AsyncSession = Depends(get_db),
):
    await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
    return await parse_condition_review(body, db)


@router.post("/rule-conditions/confirm", response_model=RuleConditionReviewResponse)
async def confirm_user_rule_condition(
    body: ConfirmRuleConditionRequest,
    db: AsyncSession = Depends(get_db),
):
    await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
    return await confirm_condition_review(body, db)


@router.post("/rule-conditions/manual", response_model=RuleConditionReviewResponse)
async def set_manual_user_rule_condition(
    body: ManualRuleConditionRequest,
    db: AsyncSession = Depends(get_db),
):
    await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
    return await set_manual_condition_review(body, db)


@router.post("/preprocess/start", response_model=RulePreprocessStatusResponse)
async def start_rule_preprocess_task(
    body: RulePreprocessStartRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await start_rule_preprocessing(body, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/preprocess/status", response_model=RulePreprocessStatusResponse)
async def get_rule_preprocess_task_status(
    project_id: int,
    route_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await get_rule_preprocessing_status(project_id, route_id, db)


@router.post("/compile", response_model=CompileRulePackageResponse)
async def compile_v2_rule_package(
    body: CompileRulePackageRequest,
    db: AsyncSession = Depends(get_db),
):
    package = compile_rule_package(body)
    return CompileRulePackageResponse(
        package=package,
        content_hash=rule_package_content_hash(package),
        validation=validate_rule_package(package),
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
    canonical_inputs, canonicalization_errors = canonicalize_inputs(body.package.input_schema, body.inputs)
    input_errors = [*canonicalization_errors, *validate_inputs(body.package.input_schema, canonical_inputs)]
    if input_errors:
        raise HTTPException(
            status_code=422,
            detail=input_validation_error_detail(input_errors),
        )
    try:
        plan = plan_route(body.package, canonical_inputs)
    except RoutePlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SimulateRulePackageResponse(content_hash=content_hash, validation=validation, plan=plan)
