from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.contracts.openapi import render_frontend_status_contract, validate_openapi_contract
from app.contracts.status import (
    CONDITION_REVIEW_STATUS_VALUES,
    EXTRACTION_TASK_STATUS_VALUES,
    PROJECT_STATUS_VALUES,
    RULE_PACKAGE_STATUS_VALUES,
    STATUS_ENUMS,
    ProjectStatus,
    RouteReviewDecision,
)
from app.schemas.schemas import ExtractionTaskStatusOut, ProjectOut


def _schema(openapi: dict, name: str) -> dict:
    return openapi["components"]["schemas"][name]


def _property_schema(openapi: dict, schema_name: str, property_name: str) -> dict:
    property_schema = _schema(openapi, schema_name)["properties"][property_name]
    ref = property_schema.get("$ref")
    if ref:
        return openapi["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    return property_schema


def test_shared_status_contracts_are_explicit_and_stable():
    assert STATUS_ENUMS == {
        "AnalysisStatus": ("pending", "reviewed"),
        "ConditionReviewStatus": (
            "draft",
            "parsing",
            "pending_confirmation",
            "confirmed",
            "invalid",
        ),
        "DocumentStatus": ("uploaded", "parsing", "parsed", "error"),
        "ExtractionTaskStatus": ("idle", "running", "completed", "failed"),
        "FactorReviewDecision": ("confirmed", "excluded"),
        "OperationReviewStatus": (
            "stable",
            "pending_confirm",
            "exception",
            "evidence",
            "data_issue",
        ),
        "ProjectStatus": (
            "CREATED",
            "UPLOADED",
            "EXTRACTING",
            "ROUTE_SET_READY",
            "GENERATED",
            "EXTRACT_ERROR",
            "FAILED",
        ),
        "RouteMergeReviewStatus": ("pending", "merged", "kept", "conflict"),
        "RouteReviewDecision": ("accepted", "rejected", "pending"),
        "RulePackageStatus": ("draft", "published", "superseded", "archived"),
        "RulePackageStatusBlockerCode": (
            "project_not_ready",
            "route_missing",
            "pending_rule_reviews",
            "invalid_factor_bindings",
            "no_published_package",
            "published_package_route_changed",
            "published_rule_sources_changed",
            "published_package_invalid",
            "kmai_incompatible",
        ),
        "WorkflowCapability": ("publish", "generate"),
    }
    assert str(RouteReviewDecision.ACCEPTED) == "accepted"


def test_legacy_failed_project_status_is_accepted_by_response_models():
    now = datetime.now(timezone.utc)
    project = ProjectOut.model_validate(
        {
            "id": 1,
            "name": "legacy",
            "mode": "route_rules",
            "profile": "default",
            "status": "FAILED",
            "created_at": now,
            "updated_at": now,
        }
    )
    task = ExtractionTaskStatusOut(
        project_id=1,
        task_status="failed",
        stage="failed",
        project_status="FAILED",
    )

    assert project.status is ProjectStatus.FAILED
    assert task.project_status is ProjectStatus.FAILED


def test_extraction_task_status_exposes_execution_and_lease_state():
    task = ExtractionTaskStatusOut(
        project_id=1,
        task_status="running",
        stage="extracting_operations",
        local_execution_active=True,
        lease_valid=True,
    )

    payload = task.model_dump()
    assert payload["local_execution_active"] is True
    assert payload["lease_valid"] is True


def test_projects_endpoint_serializes_legacy_failed_status():
    now = datetime.now(timezone.utc)

    class _ProjectResult:
        def scalars(self):
            return self

        def all(self):
            return [
                SimpleNamespace(
                    id=1,
                    name="legacy",
                    mode="route_rules",
                    profile="default",
                    rule_engine="auto",
                    workflow_revision=0,
                    status="FAILED",
                    created_at=now,
                    updated_at=now,
                )
            ]

    class _ProjectDb:
        async def execute(self, _statement):
            return _ProjectResult()

    async def override_get_db():
        yield _ProjectDb()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        response = client.get("/api/projects/")
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()[0]["status"] == "FAILED"


def test_openapi_exposes_workflow_status_enums_and_revision_contract():
    openapi = app.openapi()

    assert _property_schema(openapi, "ProjectOut", "status")["enum"] == list(PROJECT_STATUS_VALUES)
    assert _property_schema(openapi, "ExtractionTaskStatusOut", "task_status")["enum"] == list(EXTRACTION_TASK_STATUS_VALUES)
    assert _property_schema(openapi, "RulePackageStatusPackage", "status")["enum"] == list(RULE_PACKAGE_STATUS_VALUES)
    assert _property_schema(openapi, "RuleConditionReview", "status")["enum"] == list(CONDITION_REVIEW_STATUS_VALUES)

    project_schema = _schema(openapi, "ProjectOut")
    workflow_reset_schema = _schema(openapi, "WorkflowResetRequest")
    extraction_task_schema = _schema(openapi, "ExtractionTaskStatusOut")
    assert "status" in set(project_schema.get("required", []))
    assert project_schema["properties"]["workflow_revision"]["type"] == "integer"
    assert workflow_reset_schema["properties"]["expected_workflow_revision"]["type"] == "integer"
    assert extraction_task_schema["properties"]["local_execution_active"]["type"] == "boolean"
    assert extraction_task_schema["properties"]["lease_valid"]["type"] == "boolean"


def test_contract_validator_accepts_current_openapi_and_reports_drift():
    openapi = app.openapi()
    assert validate_openapi_contract(openapi) == []

    drifted = deepcopy(openapi)
    drifted["components"]["schemas"]["ProjectStatus"]["enum"].append("READY")
    del drifted["components"]["schemas"]["RulePackageStatusResponse"]["properties"]["can_generate"]

    errors = validate_openapi_contract(drifted)
    assert any("ProjectStatus" in error and "READY" in error for error in errors)
    assert any("RulePackageStatusResponse.can_generate" in error for error in errors)


@pytest.mark.parametrize(
    ("schema_name", "property_name"),
    (
        ("ProjectOut", "workflow_revision"),
        ("RulePackageStatusResponse", "can_generate"),
    ),
)
def test_contract_validator_reports_primitive_type_drift(schema_name, property_name):
    drifted = deepcopy(app.openapi())
    drifted["components"]["schemas"][schema_name]["properties"][property_name]["type"] = "string"

    errors = validate_openapi_contract(drifted)

    assert any(f"{schema_name}.{property_name}" in error for error in errors)


def test_contract_validator_reports_required_nullable_and_default_drift():
    drifted = deepcopy(app.openapi())
    drifted["components"]["schemas"]["ProjectOut"]["required"].remove("status")
    drifted["components"]["schemas"]["OperationOut"]["properties"]["review_status"] = {
        "$ref": "#/components/schemas/OperationReviewStatus"
    }
    drifted["components"]["schemas"]["MergeSuggestionOut"]["properties"]["status"][
        "default"
    ] = "kept"

    errors = validate_openapi_contract(drifted)

    assert any("required drift at ProjectOut.status" in error for error in errors)
    assert any("nullable drift at OperationOut.review_status" in error for error in errors)
    assert any("default drift at MergeSuggestionOut.status" in error for error in errors)


@pytest.mark.parametrize(
    ("schema_name", "property_name"),
    (
        ("ProjectOut", "status"),
        ("DocumentOut", "status"),
        ("OperationOut", "review_status"),
        ("MergeSuggestionOut", "status"),
        ("NormalizedRouteSegmentOut", "review_status"),
        ("NormalizedRouteSegmentSaveItem", "review_status"),
        ("SegmentFactorReviewOut", "decision"),
        ("SegmentRuleReviewOut", "decision"),
        ("SaveSegmentRuleReviewRequest", "decision"),
        ("SavedNormalizedRouteSegmentOut", "analysis_status"),
        ("SegmentRuleReviewSaveOut", "analysis_status"),
        ("ExtractionTaskStartOut", "task_status"),
        ("ExtractionTaskStatusOut", "task_status"),
        ("ExtractionTaskStatusOut", "project_status"),
        ("RuleConditionReview", "status"),
        ("FinalizedRulePackageOut", "status"),
        ("FinalizedRulePackageListItemOut", "status"),
        ("RulePackageStatusPackage", "status"),
        ("RulePackageStatusResponse", "project_status"),
        ("RulePackageStatusBlocker", "code"),
        ("RulePackageStatusBlocker", "blocks"),
    ),
)
def test_contract_validator_reports_missing_enum_attachment(schema_name, property_name):
    drifted = deepcopy(app.openapi())
    property_schema = drifted["components"]["schemas"][schema_name]["properties"][property_name]
    if "anyOf" in property_schema:
        property_schema["anyOf"] = [{"type": "string"}, {"type": "null"}]
    elif property_schema.get("type") == "array":
        property_schema["items"] = {"type": "string"}
    else:
        default = property_schema.get("default")
        property_schema.clear()
        property_schema["type"] = "string"
        if default is not None:
            property_schema["default"] = default

    errors = validate_openapi_contract(drifted)

    assert any(f"{schema_name}.{property_name}" in error for error in errors)


def test_generated_frontend_status_contract_matches_openapi():
    generated_path = (
        Path(__file__).resolve().parents[2]
        / "process-plan-agent-ui"
        / "src"
        / "api"
        / "generated"
        / "status.ts"
    )
    assert generated_path.read_text(encoding="utf-8") == render_frontend_status_contract(app.openapi())
