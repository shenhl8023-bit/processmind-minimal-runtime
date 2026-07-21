"""Rule package V2 compile, validate, and draft simulation APIs."""

from fastapi import APIRouter, HTTPException

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
from app.services.rule_packages.input_validation import validate_inputs
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export


router = APIRouter(prefix="/api/extract/finalized-rule-packages", tags=["规则包 V2"])


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
