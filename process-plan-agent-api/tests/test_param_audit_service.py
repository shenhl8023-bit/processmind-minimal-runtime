from __future__ import annotations

from app.models.models import ParamAuditAnswer
from app.schemas.schemas import (
    FactorFieldOption,
    FactorFieldOut,
    ParamJsonStageOut,
    ParamJsonStepOut,
)
from app.services.param_audit import (
    build_param_audit_overview,
    build_param_operation_reviews,
)


def _factor_fields() -> list[FactorFieldOut]:
    return [
        FactorFieldOut(
            key="material",
            label="材料",
            group="基础因素",
            input_type="select",
            required=True,
            options=[
                FactorFieldOption(value="钢", label="钢"),
                FactorFieldOption(value="铝", label="铝"),
            ],
        )
    ]


def _stage(evidence_count: int = 2) -> list[ParamJsonStageOut]:
    return [
        ParamJsonStageOut(
            stage="粗加工",
            occurrence_index=1,
            evidence_count=evidence_count,
            steps=[ParamJsonStepOut(name="车外圆", evidence_count=evidence_count)],
        )
    ]


def _rule() -> list[dict[str, object]]:
    return [
        {
            "stage": "粗加工",
            "occurrence_index": 1,
            "step_name": "车外圆",
            "include_when": "material=钢",
            "candidate_factors": ["material=钢"],
            "strength": "STRONG",
        }
    ]


def _pair(material: str) -> dict[str, object]:
    return {
        "attrs": {"material": material},
        "stages": _stage(),
    }


def test_param_audit_service_marks_zero_counterexample_operation_stable():
    reviews = build_param_operation_reviews(
        _factor_fields(),
        _rule(),
        [_pair("钢"), _pair("钢")],
        _stage(),
    )

    assert len(reviews) == 1
    assert reviews[0].review_status == "stable"
    assert reviews[0].pending_factors == []
    assert reviews[0].resolved_factors[0].factor_key == "material"


def test_param_audit_service_keeps_counterexample_operation_pending():
    reviews = build_param_operation_reviews(
        _factor_fields(),
        _rule(),
        [_pair("钢"), _pair("铝")],
        _stage(),
    )

    assert reviews[0].review_status == "pending_confirm"
    assert [factor.factor_key for factor in reviews[0].pending_factors] == ["material"]
    assert reviews[0].current_question is not None


def test_param_audit_service_reports_data_issue_answer_and_overview_counts():
    operation_key = "粗加工__1__车外圆"
    answer = ParamAuditAnswer(
        project_id=1,
        operation_key=operation_key,
        stage="粗加工",
        occurrence_index=1,
        step_name="车外圆",
        factor_key="material",
        question_type="material_scope_select",
        selected_value="data_issue",
        selected_label="样本/数据需核查",
        answer_kind="data_issue",
    )
    reviews = build_param_operation_reviews(
        _factor_fields(),
        _rule(),
        [_pair("钢"), _pair("铝")],
        _stage(),
        answer_map={operation_key: {"material": answer}},
    )

    overview = build_param_audit_overview(
        [
            reviews[0],
            *build_param_operation_reviews(_factor_fields(), _rule(), [_pair("钢"), _pair("钢")], _stage()),
        ],
        sample_pair_count=2,
    )

    assert reviews[0].review_status == "data_issue"
    assert reviews[0].auxiliary_factors[0].reason_type == "data_issue"
    assert overview.stable_operation_count == 1
    assert overview.data_issue_operation_count == 1
    assert overview.pending_operation_count == 0
