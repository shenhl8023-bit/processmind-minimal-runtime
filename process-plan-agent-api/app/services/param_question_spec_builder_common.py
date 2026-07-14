"""参数确认问题规格构造器的通用辅助。"""

from __future__ import annotations

from app.models.models import ParamAuditAnswer
from app.schemas.schemas import ParamConfirmOptionOut, ParamReviewedFactorOut


def _sample_pair_attr_rows(sample_pairs: list[dict[str, object]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pair in sample_pairs:
        attrs = pair.get("attrs")
        if isinstance(attrs, dict):
            rows.append({str(key): str(value or "").strip() for key, value in attrs.items()})
    return rows


def _should_continue_param_operation_questions(
    *,
    pending_factors: list[ParamReviewedFactorOut],
    has_data_issue: bool,
    stop_due_to_unsure: bool,
    stop_due_to_round_limit: bool,
) -> bool:
    return bool(pending_factors) and not (has_data_issue or stop_due_to_unsure or stop_due_to_round_limit)


def _factor_review_display_label(factor: ParamReviewedFactorOut) -> str:
    label = str(factor.factor_label or factor.factor_key or "").strip()
    expected = str(factor.expected_value or "").strip()
    if expected and expected not in label:
        return f"{label}={expected}"
    return label or str(factor.factor_key or "").strip()


def _factor_review_option(factor: ParamReviewedFactorOut) -> ParamConfirmOptionOut:
    return ParamConfirmOptionOut(
        value=f"factor::{factor.factor_key}",
        label=_factor_review_display_label(factor),
        count=max(int(factor.coverage_count or 0), 0),
    )


def _selected_factor_key_from_answer(answer: ParamAuditAnswer | None) -> str:
    if answer is None or answer.answer_kind != "selected":
        return ""
    value = str(answer.selected_value or "").strip()
    if not value.startswith("factor::"):
        return ""
    return value.split("::", 1)[1].strip()


__all__ = [
    "_factor_review_display_label",
    "_factor_review_option",
    "_sample_pair_attr_rows",
    "_selected_factor_key_from_answer",
    "_should_continue_param_operation_questions",
]
