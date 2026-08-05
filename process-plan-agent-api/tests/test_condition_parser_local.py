from app.services.rule_packages.condition_contracts import RuleConditionProcessOption
from app.services.rule_packages.condition_parser_local import (
    parse_local_condition,
    parse_process_relation,
)


PROCESSES = [
    RuleConditionProcessOption(process_id="process_copper_plate", display_name="镀铜"),
    RuleConditionProcessOption(process_id="process_strip_copper", display_name="除铜"),
]


def test_local_condition_parses_it_grade_without_external_services():
    candidate = parse_local_condition(
        "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序",
        "process_grind_outer",
        "磨外圆",
        [RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
    )

    assert candidate.when.field == "precision.outer_diameter_it"
    assert candidate.when.op == "lte"
    assert candidate.when.value == 8


def test_local_relation_prefers_the_explicit_predecessor():
    candidate = parse_process_relation(
        "前面有镀铜时，安排除铜工序",
        "process_strip_copper",
        PROCESSES,
    )

    assert candidate.relation.relation_type == "trigger_after"
    assert candidate.relation.source_process_ids == ["process_copper_plate"]
