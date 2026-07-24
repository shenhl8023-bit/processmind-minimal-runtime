from app.services.rule_packages.contracts import ProcessRelationV2
from app.services.rule_packages.kmai_compatibility_runner import compare_kmai_v1


def test_kmai_compatibility_runner_compares_v2_and_v1(rule_package_v2):
    result = compare_kmai_v1(
        rule_package_v2,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["槽类特征"]},
            "target_hardness_hrc": 58,
        },
    )

    assert result["errors"] == []
    assert "process_prepare" in result["v2_process_ids"]
    assert "process_prepare" in result["kmai_process_ids"]
    assert "material.9cr18.quench" in result["v2_matched_rule_ids"]


def test_kmai_compatibility_runner_reports_relation_gap(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.process_relations.append(ProcessRelationV2(
        relation_id="test-relation",
        relation_type="order_after",
        source_process_ids=["process_prepare"],
        target_process_ids=["process_quench"],
        source="user_confirmed",
        source_segment_id="segment-1",
        source_text="淬火必须在准备之后",
        confirmed_by="tester",
        confirmed_at="2026-07-23T00:00:00Z",
    ))
    result = compare_kmai_v1(
        package,
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["槽类特征"]},
            "target_hardness_hrc": 58,
        },
    )

    assert result["semantic_gaps"]
