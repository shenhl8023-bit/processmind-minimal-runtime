from app.services.rule_packages.condition_contracts import (
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_semantics import (
    bind_candidate_factors,
    validate_candidate,
    with_source_evidence,
)


def _candidate(process_id="process_grind_outer"):
    return RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"field": "cad.features", "op": "contains", "value": "顶尖孔"},
        "then": {"include_process_ids": [process_id], "exclude_process_ids": []},
    })


def test_semantics_binds_unambiguous_factor_and_replaces_nonliteral_evidence():
    candidate = with_source_evidence(_candidate(), "当存在顶尖孔时，纳入磨外圆工序")
    bound, issues = bind_candidate_factors(candidate)

    assert bound.when.factor_id == "feature.center_hole_location"
    assert bound.evidence == "存在顶尖孔"
    assert issues == []


def test_semantics_rejects_action_that_references_a_missing_route_process():
    issues = validate_candidate(
        _candidate("process_missing"),
        [RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
    )

    assert issues == ["规则引用了当前路线中不存在的工序：process_missing"]
