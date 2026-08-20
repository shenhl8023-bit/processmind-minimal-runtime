"""Compatibility exports for the condition-review workflow.

Application code should import the focused repository, state, and service
modules directly. This module remains for existing integrations during the
transition.
"""

from app.services.llm_client import get_llm_config
from app.services.rule_packages.condition_parser import (
    CONDITION_PARSER_VERSION,
    parse_rule_condition,
    validate_candidate,
)
from app.services.rule_packages.condition_review_repository import (
    candidate_json,
    loads_candidate,
    loads_issues,
    load_route_and_review,
    review_response,
    route_process_options,
    serialize_condition_review,
)
from app.services.rule_packages.condition_review_service import (
    confirm_condition_review,
    execute_condition_parse,
    complete_condition_parse,
    invalidate_legacy_nondestructive_relation_reviews,
    migrate_legacy_condition_reviews,
    migrate_legacy_standard_factor_reviews,
    parse_condition_review,
    prepare_condition_parse,
    save_condition_draft,
    set_manual_condition_review,
)
from app.services.rule_packages.condition_review_state import (
    condition_source_hash,
    manual_process_field_key,
)

__all__ = [
    "CONDITION_PARSER_VERSION",
    "candidate_json",
    "complete_condition_parse",
    "condition_source_hash",
    "confirm_condition_review",
    "execute_condition_parse",
    "get_llm_config",
    "invalidate_legacy_nondestructive_relation_reviews",
    "loads_candidate",
    "loads_issues",
    "load_route_and_review",
    "manual_process_field_key",
    "migrate_legacy_condition_reviews",
    "migrate_legacy_standard_factor_reviews",
    "parse_condition_review",
    "parse_rule_condition",
    "prepare_condition_parse",
    "review_response",
    "route_process_options",
    "save_condition_draft",
    "serialize_condition_review",
    "set_manual_condition_review",
    "validate_candidate",
]
