"""
Third-step question Harness hooks.

Hooks are small, deterministic checkpoints around question generation. They do
not decide business rules; they record whether the current question flow follows
the user-question contract before and after a question is built.
"""

from __future__ import annotations

from typing import Any

from app.schemas.schemas import QuestionHarnessHookOut
from app.services.harness_validators import validate_followup_answer, validate_route_followup_questions


def _issue_dicts(result: Any) -> list[dict[str, str]]:
    return [issue.to_dict() for issue in getattr(result, "issues", [])]


def _hook(hook: str, *, status: str = "pass", message: str = "", issues: list[dict[str, str]] | None = None) -> QuestionHarnessHookOut:
    return QuestionHarnessHookOut(
        hook=hook,
        status=status,
        message=message,
        issues=issues or [],
    )


def _question_key(question: Any) -> str:
    if isinstance(question, dict):
        return str(question.get("key") or question.get("question_key") or question.get("tree_node_id") or "")
    return str(getattr(question, "key", "") or getattr(question, "tree_node_id", "") or "")


def _question_prompt(question: Any) -> str:
    if isinstance(question, dict):
        return str(question.get("prompt") or question.get("question_text") or "")
    return str(getattr(question, "prompt", "") or "")


def _payload_from_questions(questions: list[Any]) -> dict[str, Any]:
    return {
        "questions": [
            {
                "question_key": _question_key(question),
                "prompt": _question_prompt(question),
            }
            for question in questions
            if _question_key(question)
        ]
    }


def _rows_from_questions(questions: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "question_key": _question_key(question),
            "question_text": _question_prompt(question),
        }
        for question in questions
        if _question_key(question)
    ]


def _has_question(questions: list[Any]) -> bool:
    return any(_question_key(question) and _question_prompt(question) for question in questions)


def build_question_harness_hooks(
    *,
    operation_name: str,
    coverage_count: int,
    sample_count: int,
    is_combination: bool,
    questions: list[Any],
) -> list[QuestionHarnessHookOut]:
    hooks: list[QuestionHarnessHookOut] = []
    has_question = _has_question(questions)
    full_coverage = sample_count > 0 and coverage_count >= sample_count
    non_full_coverage = sample_count > 0 and coverage_count < sample_count

    if full_coverage and not is_combination and has_question:
        hooks.append(_hook(
            "before_question_build",
            status="fail",
            message="全覆盖单工序不应继续生成存在条件问题。",
            issues=[{
                "level": "error",
                "code": "FULL_COVERAGE_SHOULD_SKIP_QUESTION",
                "message": "全覆盖单工序不应继续生成存在条件问题。",
                "target": operation_name,
                "suggested_action": "跳过第三步存在条件追问，直接按稳定工序沉淀。",
            }],
        ))
    elif non_full_coverage and not has_question:
        hooks.append(_hook(
            "before_question_build",
            status="fail",
            message="非全覆盖工序必须生成存在条件问题。",
            issues=[{
                "level": "error",
                "code": "NON_FULL_COVERAGE_MISSING_QUESTION",
                "message": "非全覆盖工序必须生成存在条件问题。",
                "target": operation_name,
                "suggested_action": "生成第一问，确认该工序存在条件依赖哪类因素。",
            }],
        ))
    else:
        hooks.append(_hook(
            "before_question_build",
            message="问答入口与覆盖状态一致。",
        ))

    if is_combination and has_question:
        first_key = _question_key(questions[0])
        first_prompt = _question_prompt(questions[0])
        if first_key != "merge_name_root" and "统一名称" not in first_prompt:
            hooks.append(_hook(
                "after_question_build",
                status="fail",
                message="组合名工序必须先确认统一名称。",
                issues=[{
                    "level": "error",
                    "code": "COMBINATION_MISSING_NAME_CONFIRM",
                    "message": "组合名工序必须先确认统一名称。",
                    "target": operation_name,
                    "suggested_action": "先生成统一名称确认题，再根据覆盖情况决定是否追问存在条件。",
                }],
            ))
            return hooks

    if not has_question:
        hooks.append(_hook(
            "after_question_build",
            message="当前无需展示问题。",
        ))
        return hooks

    result = validate_route_followup_questions(
        payload=_payload_from_questions(questions),
        rows=_rows_from_questions(questions),
    )
    hooks.append(_hook(
        "after_question_build",
        status="pass" if result.ok else "fail",
        message="问题文本通过 Harness 校验。" if result.ok else "问题文本未通过 Harness 校验。",
        issues=_issue_dicts(result),
    ))
    return hooks


def build_answer_harness_hooks(
    *,
    selected_values: list[str],
    allowed_values: list[str] | None = None,
    note: str = "",
    final_rule: str = "",
    can_continue: bool = False,
) -> list[QuestionHarnessHookOut]:
    hooks: list[QuestionHarnessHookOut] = []
    result = validate_followup_answer(
        selected_values=selected_values,
        allowed_values=allowed_values,
        note=note,
        final_rule=final_rule,
        can_continue=can_continue,
    )
    before_issues = [
        issue.to_dict()
        for issue in result.issues
        if issue.level == "error" or issue.code in {
            "ANSWER_NOTE_TOO_SHORT",
            "ANSWER_NOTE_UNCERTAIN",
            "ANSWER_NEEDS_FOLLOWUP_OR_AUDIT",
        }
    ]

    before_status = "pass"
    if any(issue["level"] == "error" for issue in before_issues):
        before_status = "fail"
    elif before_issues:
        before_status = "warning"

    hooks.append(_hook(
        "before_answer_save",
        status=before_status,
        message="回答保存前检查通过。" if not before_issues else "回答保存前检查发现需关注项。",
        issues=before_issues,
    ))

    rule_text = str(final_rule or "").strip()
    has_rule_sentence = rule_text.startswith("当") and "时" in rule_text and ("保留" in rule_text or "纳入" in rule_text)
    if has_rule_sentence:
        hooks.append(_hook(
            "after_answer_save",
            message="回答已能沉淀为规则句。",
        ))
    elif can_continue:
        hooks.append(_hook(
            "after_answer_save",
            status="warning",
            message="回答已保存，但仍需要继续沿当前方向追问。",
            issues=[{
                "level": "warning",
                "code": "ANSWER_SAVED_NEEDS_FOLLOWUP",
                "message": "当前回答还不足以沉淀为规则句。",
                "target": "",
                "suggested_action": "继续追问到具体材料、结构、精度、阶段或转序边界。",
            }],
        ))
    else:
        hooks.append(_hook(
            "after_answer_save",
            status="warning",
            message="回答已保存，但尚未形成标准规则句。",
            issues=[{
                "level": "warning",
                "code": "ANSWER_SAVED_WITHOUT_RULE_SENTENCE",
                "message": "当前回答还不能直接写成“当 xxx 成立时，这个工序保留”。",
                "target": rule_text,
                "suggested_action": "补充更具体的存在条件或例外边界。",
            }],
        ))
    return hooks
