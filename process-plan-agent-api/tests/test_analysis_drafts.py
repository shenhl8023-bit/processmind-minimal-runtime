from app.services.analysis_drafts import (
    AnalysisRuleDraft,
    RuleDraftProvenance,
    build_rule_draft_source_text,
    validate_rule_draft,
)


PROCESS = [{"process_id": "grind-1", "display_name": "磨外圆"}]


def test_draft_requires_scope_object_and_rule_condition():
    issues = validate_rule_draft(AnalysisRuleDraft(), PROCESS, "grind-1")

    assert issues == ["请确认规则适用范围。", "请确认规则对应的加工对象。", "请补充工序保留条件。"]


def test_draft_source_preserves_scope_and_object():
    draft = AnalysisRuleDraft(
        scope="用户确认的轴类零件",
        object="A侧外圆",
        condition_text="当该对象满足图纸精度要求时，保留磨外圆。",
        provenance=[RuleDraftProvenance(kind="user", label="用户回答")],
    )

    assert build_rule_draft_source_text(draft) == (
        "适用范围：用户确认的轴类零件。加工对象：A侧外圆。"
        "当该对象满足图纸精度要求时，保留磨外圆。"
    )


def test_confirmed_draft_with_missing_fields_is_rejected():
    draft = AnalysisRuleDraft(
        scope="当前项目样本",
        object="A侧外圆",
        condition_text="精度达到阈值时保留磨外圆。",
        missing=["精度阈值"],
        status="confirmed",
    )

    issues = validate_rule_draft(draft, PROCESS, "grind-1", require_confirmation=True)

    assert "精度阈值" in issues
    assert "仍有未补充的信息，不能确认规则。" in issues


def test_confirmed_draft_requires_explicit_user_confirmation():
    draft = AnalysisRuleDraft(
        scope="当前项目样本",
        object="A侧外圆",
        condition_text="存在该外圆时保留磨外圆。",
        status="ready",
    )

    assert "第三步规则草稿尚未由用户确认。" in validate_rule_draft(
        draft, PROCESS, "grind-1", require_confirmation=True
    )
