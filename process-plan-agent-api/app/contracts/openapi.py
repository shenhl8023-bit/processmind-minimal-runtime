"""Validation and frontend generation for the workflow OpenAPI contract."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from app.contracts.status import STATUS_ENUMS


FRONTEND_STATUS_TYPES = tuple(
    (schema_name, const_name)
    for schema_name, const_name in (
        ("AnalysisStatus", "ANALYSIS_STATUS_VALUES"),
        ("ConditionReviewStatus", "CONDITION_REVIEW_STATUS_VALUES"),
        ("DocumentStatus", "DOCUMENT_STATUS_VALUES"),
        ("ExtractionTaskStatus", "EXTRACTION_TASK_STATUS_VALUES"),
        ("FactorReviewDecision", "FACTOR_REVIEW_DECISION_VALUES"),
        ("OperationReviewStatus", "OPERATION_REVIEW_STATUS_VALUES"),
        ("ProjectStatus", "PROJECT_STATUS_VALUES"),
        ("RouteMergeReviewStatus", "ROUTE_MERGE_REVIEW_STATUS_VALUES"),
        ("RouteReviewDecision", "ROUTE_REVIEW_DECISION_VALUES"),
        ("RulePackageStatus", "RULE_PACKAGE_STATUS_VALUES"),
        ("RulePackageStatusBlockerCode", "RULE_PACKAGE_STATUS_BLOCKER_CODE_VALUES"),
        ("WorkflowCapability", "WORKFLOW_CAPABILITY_VALUES"),
    )
)

_NO_DEFAULT = object()


@dataclass(frozen=True)
class ApiPropertyContract:
    json_type: str
    required: bool
    nullable: bool = False
    default: Any = _NO_DEFAULT
    enum_name: str | None = None


API_PROPERTY_CONTRACTS: dict[tuple[str, str], ApiPropertyContract] = {
    ("ProjectOut", "status"): ApiPropertyContract("string", True, enum_name="ProjectStatus"),
    ("ProjectOut", "workflow_revision"): ApiPropertyContract("integer", False, default=0),
    ("DocumentOut", "status"): ApiPropertyContract("string", True, enum_name="DocumentStatus"),
    ("OperationOut", "review_status"): ApiPropertyContract(
        "string", False, nullable=True, enum_name="OperationReviewStatus"
    ),
    ("MergeSuggestionOut", "status"): ApiPropertyContract(
        "string", False, default="pending", enum_name="RouteMergeReviewStatus"
    ),
    ("NormalizedRouteSegmentOut", "review_status"): ApiPropertyContract(
        "string", False, default="pending", enum_name="RouteMergeReviewStatus"
    ),
    ("NormalizedRouteSegmentSaveItem", "review_status"): ApiPropertyContract(
        "string", False, default="merged", enum_name="RouteMergeReviewStatus"
    ),
    ("SegmentFactorReviewOut", "decision"): ApiPropertyContract(
        "string", True, enum_name="FactorReviewDecision"
    ),
    ("SegmentRuleReviewOut", "decision"): ApiPropertyContract(
        "string", True, enum_name="RouteReviewDecision"
    ),
    ("SaveSegmentRuleReviewRequest", "decision"): ApiPropertyContract(
        "string", False, default="accepted", enum_name="RouteReviewDecision"
    ),
    ("SavedNormalizedRouteSegmentOut", "analysis_status"): ApiPropertyContract(
        "string", False, default="pending", enum_name="AnalysisStatus"
    ),
    ("SegmentRuleReviewSaveOut", "analysis_status"): ApiPropertyContract(
        "string", False, default="pending", enum_name="AnalysisStatus"
    ),
    ("ExtractionTaskStartOut", "task_status"): ApiPropertyContract(
        "string", True, enum_name="ExtractionTaskStatus"
    ),
    ("ExtractionTaskStartOut", "workflow_revision"): ApiPropertyContract(
        "integer", False, default=0
    ),
    ("ExtractionTaskStatusOut", "task_status"): ApiPropertyContract(
        "string", True, enum_name="ExtractionTaskStatus"
    ),
    ("ExtractionTaskStatusOut", "project_status"): ApiPropertyContract(
        "string", False, nullable=True, enum_name="ProjectStatus"
    ),
    ("WorkflowResetRequest", "expected_workflow_revision"): ApiPropertyContract(
        "integer", False, default=0
    ),
    ("WorkflowResetOut", "workflow_revision"): ApiPropertyContract("integer", True),
    ("SaveNormalizedSupersetRouteRequest", "expected_workflow_revision"): ApiPropertyContract(
        "integer", False, default=0
    ),
    ("SaveSegmentRuleReviewRequest", "expected_workflow_revision"): ApiPropertyContract(
        "integer", False, default=0
    ),
    ("GenerateRequest", "expected_workflow_revision"): ApiPropertyContract(
        "integer", False, default=0
    ),
    ("RuleConditionReview", "status"): ApiPropertyContract(
        "string", False, default="draft", enum_name="ConditionReviewStatus"
    ),
    ("FinalizedRulePackageOut", "status"): ApiPropertyContract(
        "string", False, default="published", enum_name="RulePackageStatus"
    ),
    ("FinalizedRulePackageListItemOut", "status"): ApiPropertyContract(
        "string", False, default="published", enum_name="RulePackageStatus"
    ),
    ("RulePackageStatusPackage", "status"): ApiPropertyContract(
        "string", True, enum_name="RulePackageStatus"
    ),
    ("RulePackageStatusResponse", "project_status"): ApiPropertyContract(
        "string", True, enum_name="ProjectStatus"
    ),
    ("RulePackageStatusResponse", "workflow_revision"): ApiPropertyContract("integer", True),
    ("RulePackageStatusResponse", "can_publish"): ApiPropertyContract("boolean", True),
    ("RulePackageStatusResponse", "can_generate"): ApiPropertyContract("boolean", True),
    ("RulePackageStatusResponse", "package_executable"): ApiPropertyContract("boolean", True),
    ("RulePackageStatusResponse", "blockers"): ApiPropertyContract("array", False),
    ("RulePackageStatusBlocker", "code"): ApiPropertyContract(
        "string", True, enum_name="RulePackageStatusBlockerCode"
    ),
    ("RulePackageStatusBlocker", "blocks"): ApiPropertyContract(
        "array", True, enum_name="WorkflowCapability"
    ),
}


def _schemas(openapi: dict[str, Any]) -> dict[str, Any]:
    return openapi.get("components", {}).get("schemas", {})


def _non_null_schema(schema: dict[str, Any]) -> dict[str, Any]:
    for candidate in schema.get("anyOf", []):
        if candidate.get("type") != "null":
            return candidate
    return schema


def _resolve_schema(openapi: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    schema = _non_null_schema(schema)
    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = _schemas(openapi).get(ref.rsplit("/", 1)[-1], {})
        return _resolve_schema(openapi, resolved)
    return schema


def _enum_ref_name(property_schema: dict[str, Any]) -> str | None:
    enum_schema = _non_null_schema(property_schema)
    if enum_schema.get("type") == "array":
        enum_schema = _non_null_schema(enum_schema.get("items", {}))
    ref = enum_schema.get("$ref")
    if not isinstance(ref, str):
        return None
    return ref.rsplit("/", 1)[-1]


def _is_nullable(property_schema: dict[str, Any]) -> bool:
    if property_schema.get("nullable") is True:
        return True
    schema_type = property_schema.get("type")
    if isinstance(schema_type, list) and "null" in schema_type:
        return True
    return any(candidate.get("type") == "null" for candidate in property_schema.get("anyOf", []))


def validate_openapi_contract(openapi: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schemas = _schemas(openapi)

    for enum_name, expected_values in STATUS_ENUMS.items():
        enum_schema = schemas.get(enum_name, {})
        actual_values = enum_schema.get("enum")
        if enum_schema.get("type") != "string" or actual_values != list(expected_values):
            errors.append(
                f"OpenAPI enum schema drift at {enum_name}: expected string values "
                f"{list(expected_values)!r}, got type={enum_schema.get('type')!r}, values={actual_values!r}"
            )

    for (schema_name, property_name), contract in API_PROPERTY_CONTRACTS.items():
        schema = schemas.get(schema_name, {})
        properties = schema.get("properties", {})
        property_schema = properties.get(property_name)
        path = f"{schema_name}.{property_name}"
        if not isinstance(property_schema, dict):
            errors.append(f"missing OpenAPI property {path}")
            continue

        actual_type = _resolve_schema(openapi, property_schema).get("type")
        if actual_type != contract.json_type:
            errors.append(
                f"OpenAPI type drift at {path}: expected {contract.json_type!r}, got {actual_type!r}"
            )

        actual_required = property_name in set(schema.get("required", []))
        if actual_required != contract.required:
            errors.append(
                f"OpenAPI required drift at {path}: expected {contract.required!r}, got {actual_required!r}"
            )

        actual_nullable = _is_nullable(property_schema)
        if actual_nullable != contract.nullable:
            errors.append(
                f"OpenAPI nullable drift at {path}: expected {contract.nullable!r}, got {actual_nullable!r}"
            )

        if contract.default is _NO_DEFAULT:
            if "default" in property_schema:
                errors.append(
                    f"OpenAPI default drift at {path}: expected no default, "
                    f"got {property_schema['default']!r}"
                )
        elif property_schema.get("default", _NO_DEFAULT) != contract.default:
            actual_default = property_schema.get("default", "<missing>")
            errors.append(
                f"OpenAPI default drift at {path}: expected {contract.default!r}, got {actual_default!r}"
            )

        if contract.enum_name is not None:
            actual_enum_name = _enum_ref_name(property_schema)
            if actual_enum_name != contract.enum_name:
                errors.append(
                    f"OpenAPI enum attachment drift at {path}: "
                    f"expected {contract.enum_name!r}, got {actual_enum_name!r}"
                )

    return errors


def render_frontend_status_contract(openapi: dict[str, Any]) -> str:
    lines = [
        "// Generated by scripts/check_api_contract.py --write. Do not edit by hand.",
        "",
    ]
    schemas = _schemas(openapi)
    for schema_name, const_name in FRONTEND_STATUS_TYPES:
        values = schemas.get(schema_name, {}).get("enum")
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError(f"OpenAPI schema {schema_name} does not expose a string enum")
        lines.append(f"export const {const_name} = [")
        lines.extend(f"  {json.dumps(value)}," for value in values)
        lines.append("] as const")
        lines.append(f"export type {schema_name} = typeof {const_name}[number]")
        lines.append("")
    return "\n".join(lines)
