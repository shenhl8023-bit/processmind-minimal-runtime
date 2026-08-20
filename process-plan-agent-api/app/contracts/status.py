"""Stable status values shared by persistence-backed API responses."""

from enum import Enum


class _Status(str, Enum):
    def __str__(self) -> str:
        return self.value

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(item.value for item in cls)


class ProjectStatus(_Status):
    CREATED = "CREATED"
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    ROUTE_SET_READY = "ROUTE_SET_READY"
    GENERATED = "GENERATED"
    EXTRACT_ERROR = "EXTRACT_ERROR"
    FAILED = "FAILED"


class DocumentStatus(_Status):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    ERROR = "error"


class ExtractionTaskStatus(_Status):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationReviewStatus(_Status):
    STABLE = "stable"
    PENDING_CONFIRM = "pending_confirm"
    EXCEPTION = "exception"
    EVIDENCE = "evidence"
    DATA_ISSUE = "data_issue"


class RouteMergeReviewStatus(_Status):
    PENDING = "pending"
    MERGED = "merged"
    KEPT = "kept"
    CONFLICT = "conflict"


class AnalysisStatus(_Status):
    PENDING = "pending"
    REVIEWED = "reviewed"


class FactorReviewDecision(_Status):
    CONFIRMED = "confirmed"
    EXCLUDED = "excluded"


class ConditionReviewStatus(_Status):
    DRAFT = "draft"
    PARSING = "parsing"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    INVALID = "invalid"


class RouteReviewDecision(_Status):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PENDING = "pending"


class RulePackageStatus(_Status):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class WorkflowCapability(_Status):
    PUBLISH = "publish"
    GENERATE = "generate"


class RulePackageStatusBlockerCode(_Status):
    PROJECT_NOT_READY = "project_not_ready"
    ROUTE_MISSING = "route_missing"
    PENDING_RULE_REVIEWS = "pending_rule_reviews"
    INVALID_FACTOR_BINDINGS = "invalid_factor_bindings"
    NO_PUBLISHED_PACKAGE = "no_published_package"
    PUBLISHED_PACKAGE_ROUTE_CHANGED = "published_package_route_changed"
    PUBLISHED_RULE_SOURCES_CHANGED = "published_rule_sources_changed"
    PUBLISHED_PACKAGE_INVALID = "published_package_invalid"
    KMAI_INCOMPATIBLE = "kmai_incompatible"


PROJECT_STATUS_VALUES = ProjectStatus.values()
DOCUMENT_STATUS_VALUES = DocumentStatus.values()
EXTRACTION_TASK_STATUS_VALUES = ExtractionTaskStatus.values()
OPERATION_REVIEW_STATUS_VALUES = OperationReviewStatus.values()
ROUTE_MERGE_REVIEW_STATUS_VALUES = RouteMergeReviewStatus.values()
ANALYSIS_STATUS_VALUES = AnalysisStatus.values()
CONDITION_REVIEW_STATUS_VALUES = ConditionReviewStatus.values()
RULE_PACKAGE_STATUS_VALUES = RulePackageStatus.values()
FACTOR_REVIEW_DECISION_VALUES = FactorReviewDecision.values()
ROUTE_REVIEW_DECISION_VALUES = RouteReviewDecision.values()
WORKFLOW_CAPABILITY_VALUES = WorkflowCapability.values()
RULE_PACKAGE_STATUS_BLOCKER_CODE_VALUES = RulePackageStatusBlockerCode.values()

STATUS_ENUMS: dict[str, tuple[str, ...]] = {
    "AnalysisStatus": ANALYSIS_STATUS_VALUES,
    "ConditionReviewStatus": CONDITION_REVIEW_STATUS_VALUES,
    "DocumentStatus": DOCUMENT_STATUS_VALUES,
    "ExtractionTaskStatus": EXTRACTION_TASK_STATUS_VALUES,
    "FactorReviewDecision": FACTOR_REVIEW_DECISION_VALUES,
    "OperationReviewStatus": OPERATION_REVIEW_STATUS_VALUES,
    "ProjectStatus": PROJECT_STATUS_VALUES,
    "RouteMergeReviewStatus": ROUTE_MERGE_REVIEW_STATUS_VALUES,
    "RouteReviewDecision": ROUTE_REVIEW_DECISION_VALUES,
    "RulePackageStatus": RULE_PACKAGE_STATUS_VALUES,
    "RulePackageStatusBlockerCode": RULE_PACKAGE_STATUS_BLOCKER_CODE_VALUES,
    "WorkflowCapability": WORKFLOW_CAPABILITY_VALUES,
}
