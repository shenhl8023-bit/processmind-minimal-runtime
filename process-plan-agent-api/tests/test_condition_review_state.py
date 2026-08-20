from app.services.rule_packages.condition_review_errors import ConditionReviewValidation
from app.services.rule_packages.condition_review_state import (
    condition_source_hash,
    manual_process_field_key,
    new_draft_update,
    parsing_update,
)


def test_draft_update_clears_confirmation_without_changing_prior_parser_metadata():
    update = new_draft_update(
        source_text="new condition text",
        source_hash=condition_source_hash("new condition text"),
        field_registry_version="2026.11",
    )

    assert update.values["condition_status"] == "draft"
    assert update.values["condition_candidate_json"] is None
    assert update.values["condition_confirmed_json"] is None
    assert update.values["condition_confirmed_by"] is None
    assert "condition_parser_version" not in update.values


def test_parsing_update_resets_duration_and_manual_key_is_stable():
    update = parsing_update("condition", condition_source_hash("condition"), "parser:v1", "2026.11")

    assert update.values["condition_status"] == "parsing"
    assert update.values["condition_parse_duration_ms"] is None
    assert manual_process_field_key("process_mark") == "project_factor.manual_process_487e1c0a"


def test_domain_error_exposes_detail_without_http_dependency():
    error = ConditionReviewValidation({"message": "candidate rejected", "issues": ["x"]})

    assert error.detail == {"message": "candidate rejected", "issues": ["x"]}
