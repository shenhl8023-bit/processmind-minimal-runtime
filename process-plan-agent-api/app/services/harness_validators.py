"""
Harness 约束校验器。

这一层只做可执行的边界检查，不替代业务归纳和人工审核。
调用方可以根据返回的 errors / warnings 决定放行、追问、人工接管或回退。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ValidationLevel = Literal["error", "warning"]
HARNESS_WARNING_FACTOR_PREFIX = "harness_warning="


def is_harness_warning_factor_name(name: object) -> bool:
    return str(name or "").strip().startswith(HARNESS_WARNING_FACTOR_PREFIX)


def harness_warning_factor_name(code: object) -> str:
    clean_code = str(code or "UNKNOWN").strip() or "UNKNOWN"
    return f"{HARNESS_WARNING_FACTOR_PREFIX}{clean_code}"


@dataclass(frozen=True)
class HarnessValidationIssue:
    level: ValidationLevel
    code: str
    message: str
    target: str = ""
    suggested_action: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "suggested_action": self.suggested_action,
        }


@dataclass
class HarnessValidationResult:
    issues: list[HarnessValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    @property
    def errors(self) -> list[HarnessValidationIssue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[HarnessValidationIssue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    def add(
        self,
        *,
        level: ValidationLevel,
        code: str,
        message: str,
        target: str = "",
        suggested_action: str = "",
    ) -> None:
        self.issues.append(
            HarnessValidationIssue(
                level=level,
                code=code,
                message=message,
                target=target,
                suggested_action=suggested_action,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }


class HarnessValidationError(ValueError):
    def __init__(self, *, stage: str, result: HarnessValidationResult):
        self.stage = stage
        self.result = result
        super().__init__(f"Harness 校验失败（{stage}）：{format_validation_errors(result)}")

    def to_payload(self) -> dict[str, Any]:
        payload = self.result.to_dict()
        payload["stage"] = self.stage
        return payload


EQUIPMENT_NAME_KEYWORDS = (
    "车床",
    "铣床",
    "磨床",
    "钻床",
    "镗床",
    "刨床",
    "拉床",
    "加工中心",
    "数控中心",
    "电火花",
    "线切割",
    "CNC",
    "NC",
    "机床",
    "设备",
    "工位",
    "夹具",
    "量具",
    "检具",
    "工装",
    "工具",
    "拉杆",
    "夹块",
    "底座",
    "接嘴",
    "丝堵",
    "试验器",
)

PROCESS_ACTION_KEYWORDS = (
    "粗车",
    "精车",
    "半精车",
    "车削",
    "车外",
    "车内",
    "车端",
    "车槽",
    "铣削",
    "铣面",
    "铣槽",
    "磨削",
    "粗磨",
    "精磨",
    "磨外",
    "磨内",
    "磨端",
    "钻孔",
    "镗孔",
    "铰孔",
    "攻丝",
    "攻螺纹",
    "刨削",
    "插齿",
    "拉削",
    "研磨",
    "珩磨",
    "滚齿",
    "抛光",
    "切割",
    "下料",
    "备料",
    "锻",
    "铸",
    "焊",
    "热处理",
    "调质",
    "淬火",
    "回火",
    "正火",
    "退火",
    "检验",
    "检查",
    "清洗",
    "去毛刺",
    "倒角",
    "标印",
    "包装",
)

YES_NO_QUESTION_PATTERNS = (
    "是否存在",
    "是否需要",
    "是否保留",
    "要不要",
    "需不需要",
    "需要吗",
    "保留吗",
)

UNCERTAIN_ANSWER_PATTERNS = (
    "不确定",
    "说不清",
    "不清楚",
    "可能",
    "大概",
    "应该",
    "看情况",
    "都可以",
    "随便",
)

LOW_INFORMATION_ANSWER_PATTERNS = (
    "是",
    "否",
    "需要",
    "不需要",
    "有",
    "没有",
    "同意",
    "确认",
)


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _operation_name(item: dict[str, Any]) -> str:
    return _as_text(item.get("operation_name") or item.get("name"))


def looks_like_equipment_name(name: str) -> bool:
    normalized = _as_text(name)
    if not normalized:
        return False
    has_equipment_word = any(keyword in normalized for keyword in EQUIPMENT_NAME_KEYWORDS)
    has_process_action = any(keyword in normalized for keyword in PROCESS_ACTION_KEYWORDS)
    return has_equipment_word and not has_process_action


def validate_llm_json_payload(payload: Any) -> HarnessValidationResult:
    result = HarnessValidationResult()
    if not isinstance(payload, (list, dict)):
        result.add(
            level="error",
            code="LLM_JSON_PAYLOAD_NOT_OBJECT_OR_ARRAY",
            message="LLM 输出必须解析为 JSON 对象或数组。",
            target=type(payload).__name__,
            suggested_action="重新生成、进入人工修复或使用本地回退逻辑。",
        )
    return result


def validate_extracted_operations(operations: list[dict[str, Any]]) -> HarnessValidationResult:
    result = HarnessValidationResult()
    for item in operations:
        name = _operation_name(item)
        if looks_like_equipment_name(name):
            result.add(
                level="error",
                code="EQUIPMENT_PROMOTED_TO_OPERATION",
                message="明显设备、机床、工位、夹具或仪器名称不能作为顶层工序。",
                target=name,
                suggested_action="保留为 equipment 证据，重新抽取或人工确认真实工序名。",
            )
    return result


def validate_merged_route(route_items: list[dict[str, Any]]) -> HarnessValidationResult:
    result = HarnessValidationResult()
    seen_sequences: dict[int, str] = {}
    for item in route_items:
        name = _operation_name(item)
        raw_sequence = item.get("sequence", item.get("seq"))
        try:
            sequence = int(raw_sequence)
        except (TypeError, ValueError):
            result.add(
                level="error",
                code="INVALID_ROUTE_SEQUENCE",
                message="母路线 sequence 必须是有效整数。",
                target=name or _as_text(raw_sequence),
                suggested_action="重新编号母路线后再保存。",
            )
            continue

        if sequence <= 0:
            result.add(
                level="error",
                code="INVALID_ROUTE_SEQUENCE",
                message="母路线 sequence 必须大于 0。",
                target=name or str(sequence),
                suggested_action="重新编号母路线后再保存。",
            )
            continue

        if sequence in seen_sequences:
            result.add(
                level="error",
                code="DUPLICATE_ROUTE_SEQUENCE",
                message="母路线 sequence 不能重复。",
                target=f"{seen_sequences[sequence]} / {name}",
                suggested_action="为重复槽位重新分配稳定顺序号。",
            )
            continue

        seen_sequences[sequence] = name
    return result


def validate_factor_rules(
    rule_items: list[dict[str, Any]],
    *,
    coverage_by_operation: dict[str, tuple[int, int]] | None = None,
) -> HarnessValidationResult:
    result = HarnessValidationResult()
    coverage_by_operation = coverage_by_operation or {}

    for item in rule_items:
        op_name = _operation_name(item)
        factors = item.get("factors") or []
        if not isinstance(factors, list):
            result.add(
                level="error",
                code="INVALID_FACTOR_LIST",
                message="因素规则 factors 必须是数组。",
                target=op_name,
                suggested_action="重新生成因素规则或人工修复 JSON 结构。",
            )
            continue

        coverage_count, sample_count = coverage_by_operation.get(op_name, (0, 0))
        is_non_full_coverage = sample_count > 0 and coverage_count < sample_count

        for factor in factors:
            if not isinstance(factor, dict):
                result.add(
                    level="error",
                    code="INVALID_FACTOR_ITEM",
                    message="单条因素规则必须是对象。",
                    target=op_name,
                    suggested_action="重新生成因素规则或人工修复 JSON 结构。",
                )
                continue

            factor_name = _as_text(factor.get("name"))
            evidence = _as_text(factor.get("evidence"))
            if not evidence:
                result.add(
                    level="warning",
                    code="MISSING_FACTOR_EVIDENCE",
                    message="因素规则缺少 evidence，后续审核和回放会缺少依据。",
                    target=op_name or factor_name,
                    suggested_action="补充样本覆盖、反例边界或人工判断依据。",
                )

            if is_non_full_coverage and factor_name.lower().replace(" ", "") == "always=true":
                result.add(
                    level="warning",
                    code="NON_FULL_COVERAGE_ALWAYS_TRUE",
                    message="非全覆盖工序不能直接设置 always=true。",
                    target=op_name,
                    suggested_action="已自动降级为 WEAK，并进入人工追问或补充例外/数据问题说明。",
                )

    return result


def _question_text(row: dict[str, Any]) -> str:
    return _as_text(row.get("question_text") or row.get("prompt"))


def _looks_like_yes_no_question(text: str) -> bool:
    normalized = _as_text(text)
    if not normalized:
        return False
    return any(pattern in normalized for pattern in YES_NO_QUESTION_PATTERNS)


def _payload_route_question_keys(payload: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for item in payload.get("questions") or []:
        if isinstance(item, dict):
            key = _as_text(item.get("question_key") or item.get("key"))
            if key:
                keys.add(key)
    return keys


def _payload_param_question_keys(payload: dict[str, Any]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for item in payload.get("questions") or []:
        if not isinstance(item, dict):
            continue
        current = item.get("current_question") if isinstance(item.get("current_question"), dict) else {}
        operation_key = _as_text(item.get("operation_key"))
        factor_key = _as_text(current.get("factor_key"))
        question_type = _as_text(current.get("question_type"))
        if operation_key and factor_key and question_type:
            keys.add((operation_key, factor_key, question_type))
    return keys


def _payload_param_option_values(payload: dict[str, Any]) -> dict[tuple[str, str, str], set[str]]:
    options_by_key: dict[tuple[str, str, str], set[str]] = {}
    for item in payload.get("questions") or []:
        if not isinstance(item, dict):
            continue
        current = item.get("current_question") if isinstance(item.get("current_question"), dict) else {}
        key = (
            _as_text(item.get("operation_key")),
            _as_text(current.get("factor_key")),
            _as_text(current.get("question_type")),
        )
        if not all(key):
            continue
        options_by_key[key] = {
            _as_text(option.get("value"))
            for option in current.get("options") or []
            if isinstance(option, dict) and _as_text(option.get("value"))
        }
    return options_by_key


def validate_route_followup_questions(
    *,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> HarnessValidationResult:
    """Validate LLM rewrites for third-step route/weak-interview questions.

    The route follow-up model may only rewrite existing question text. It must
    not invent question keys or turn the prompt into a yes/no existence check.
    """
    result = HarnessValidationResult()
    expected_keys = _payload_route_question_keys(payload)
    for row in rows:
        if not isinstance(row, dict):
            result.add(
                level="error",
                code="QUESTION_ROW_NOT_OBJECT",
                message="第三步追问模型返回的 question 必须是对象。",
                suggested_action="忽略本次模型改写，使用系统模板题。",
            )
            continue
        question_key = _as_text(row.get("question_key") or row.get("key"))
        if question_key not in expected_keys:
            result.add(
                level="error",
                code="QUESTION_KEY_NOT_IN_PAYLOAD",
                message="第三步追问模型只能改写系统已给出的问题 key。",
                target=question_key,
                suggested_action="忽略本次模型改写，使用系统模板题。",
            )
        text = _question_text(row)
        if _looks_like_yes_no_question(text):
            result.add(
                level="error",
                code="QUESTION_TEXT_YES_NO_STYLE",
                message="第三步问题不能停留在是否存在、是否需要或要不要的口头判断。",
                target=text,
                suggested_action="改为询问工序存在条件依赖哪类因素或具体边界。",
            )
    return result


def validate_param_followup_questions(
    *,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> HarnessValidationResult:
    """Validate LLM rewrites for param-operation question prompts/options."""
    result = HarnessValidationResult()
    expected_keys = _payload_param_question_keys(payload)
    option_values_by_key = _payload_param_option_values(payload)
    for row in rows:
        if not isinstance(row, dict):
            result.add(
                level="error",
                code="QUESTION_ROW_NOT_OBJECT",
                message="第三步参数追问模型返回的 question 必须是对象。",
                suggested_action="忽略本次模型改写，使用系统模板题。",
            )
            continue
        key = (
            _as_text(row.get("operation_key")),
            _as_text(row.get("factor_key")),
            _as_text(row.get("question_type")),
        )
        if key not in expected_keys:
            result.add(
                level="error",
                code="QUESTION_KEY_NOT_IN_PAYLOAD",
                message="第三步参数追问模型只能改写系统已给出的当前题。",
                target="/".join(key),
                suggested_action="忽略本次模型改写，使用系统模板题。",
            )
            continue
        text = _question_text(row)
        if _looks_like_yes_no_question(text):
            result.add(
                level="error",
                code="QUESTION_TEXT_YES_NO_STYLE",
                message="第三步问题不能停留在是否存在、是否需要或要不要的口头判断。",
                target=text,
                suggested_action="改为询问工序存在条件依赖哪类因素或具体边界。",
            )
        allowed_values = option_values_by_key.get(key, set())
        recommended_values = row.get("recommended_option_values")
        if isinstance(recommended_values, list):
            for value in recommended_values:
                clean_value = _as_text(value)
                if clean_value and clean_value not in allowed_values:
                    result.add(
                        level="error",
                        code="QUESTION_OPTION_VALUE_NOT_IN_PAYLOAD",
                        message="第三步参数追问模型不能推荐系统候选项之外的 option value。",
                        target=clean_value,
                        suggested_action="忽略本次模型选项排序，保持系统原始候选项。",
                    )
    return result


def validate_followup_answer(
    *,
    selected_values: list[str],
    allowed_values: list[str] | None = None,
    note: str = "",
    final_rule: str = "",
    can_continue: bool = False,
) -> HarnessValidationResult:
    """Validate whether a third-step answer is usable as rule evidence.

    This check is intentionally domain-neutral: it verifies answer shape and
    traceability, not whether a specific process/material decision is correct.
    """
    result = HarnessValidationResult()
    clean_values = [_as_text(value) for value in selected_values if _as_text(value)]
    allowed = {_as_text(value) for value in (allowed_values or []) if _as_text(value)}
    note_text = _as_text(note)

    if not clean_values and not note_text:
        result.add(
            level="error",
            code="ANSWER_MISSING_SELECTION_OR_NOTE",
            message="回答保存前必须选择有效选项，或填写补充说明。",
            suggested_action="选择当前题候选项；如果选项不适用，请填写补充说明。",
        )

    for value in clean_values:
        if allowed and value not in allowed:
            result.add(
                level="error",
                code="ANSWER_VALUE_NOT_IN_OPTIONS",
                message="回答值不属于当前题候选项。",
                target=value,
                suggested_action="重新选择当前题提供的候选项。",
            )

    selected_other = any(value == "other" or value.endswith("::other") or value.endswith("::other_manual") for value in clean_values)
    if selected_other and not note_text:
        result.add(
            level="error",
            code="OTHER_ANSWER_MISSING_NOTE",
            message="选择其他时必须填写具体说明。",
            target="other",
            suggested_action="补充这道工序的具体边界、条件或例外原因。",
        )

    if note_text:
        compact_note = note_text.replace(" ", "")
        if len(compact_note) < 6 or compact_note in LOW_INFORMATION_ANSWER_PATTERNS:
            level: ValidationLevel = "warning" if clean_values and not selected_other else "error"
            result.add(
                level=level,
                code="ANSWER_NOTE_TOO_SHORT",
                message="补充说明过短，难以作为可复用规则依据。",
                target=note_text,
                suggested_action="补充条件、边界、例外或证据来源，避免只写“是/否/需要”。",
            )
        elif any(pattern in note_text for pattern in UNCERTAIN_ANSWER_PATTERNS):
            result.add(
                level="warning",
                code="ANSWER_NOTE_UNCERTAIN",
                message="补充说明包含不确定表达，规则定稿前需要继续澄清。",
                target=note_text,
                suggested_action="把不确定表达改成可判断的条件，或标记为样本/数据需核查。",
            )

    if any(value in {"unsure", "data_issue"} or value.endswith("::uncertain") or value.endswith("::unknown") for value in clean_values):
        result.add(
            level="warning",
            code="ANSWER_NEEDS_FOLLOWUP_OR_AUDIT",
            message="当前回答表示暂不确定或数据待核查，不能直接沉淀为稳定规则。",
            target=", ".join(clean_values),
            suggested_action="继续追问、补充资料，或在规则定稿阶段标记为待核查。",
        )

    rule_text = _as_text(final_rule)
    has_rule_sentence = rule_text.startswith("当") and "时" in rule_text and ("保留" in rule_text or "纳入" in rule_text)
    if not has_rule_sentence:
        result.add(
            level="warning",
            code="ANSWER_SAVED_WITHOUT_RULE_SENTENCE" if not can_continue else "ANSWER_SAVED_NEEDS_FOLLOWUP",
            message="当前回答还不足以沉淀为标准规则句。",
            target=rule_text,
            suggested_action="继续追问到具体条件，或补充能写成“当 xxx 成立时，这个工序保留”的边界。",
        )
    return result


def validate_finalized_rules(
    *,
    compiled_rules: list[dict[str, Any]],
) -> HarnessValidationResult:
    """Validate rule drafts before they are treated as finalized rules."""
    result = HarnessValidationResult()
    if not compiled_rules:
        result.add(
            level="warning",
            code="FINAL_RULE_EMPTY",
            message="当前没有可定稿的规则草案。",
            suggested_action="先完成规则编译或第三步问答，再进入规则定稿。",
        )
        return result

    uncertain_tokens = ("unsure", "unknown", "data_issue", "uncertain", "待核查", "不确定", "说不清")
    for index, item in enumerate(compiled_rules, start=1):
        if not isinstance(item, dict):
            result.add(
                level="error",
                code="FINAL_RULE_ITEM_NOT_OBJECT",
                message="规则草案必须是对象。",
                target=str(index),
                suggested_action="重新编译规则，或人工修复规则 JSON。",
            )
            continue

        stage = _as_text(item.get("stage"))
        step_name = _as_text(item.get("step_name"))
        include_when = _as_text(item.get("include_when"))
        strength = _as_text(item.get("strength")).upper()
        evidence = _as_text(item.get("evidence"))
        why_not_stable = _as_text(item.get("why_not_stable"))
        candidate_factors = item.get("candidate_factors") or []
        target = f"{stage}/{step_name}" if stage or step_name else str(index)

        if not stage or not step_name or not include_when:
            result.add(
                level="error",
                code="FINAL_RULE_MISSING_REQUIRED_FIELD",
                message="规则定稿必须包含阶段、工序和存在条件。",
                target=target,
                suggested_action="补齐 stage、step_name 和 include_when 后再定稿。",
            )
            continue

        if include_when != "always=true" and len(include_when.replace(" ", "")) < 5:
            result.add(
                level="error",
                code="FINAL_RULE_CONDITION_TOO_THIN",
                message="规则存在条件过短，无法形成可执行判断。",
                target=f"{target}: {include_when}",
                suggested_action="补充具体参数、比较关系、枚举值或组合条件。",
            )

        if include_when == "always=true" and strength not in {"STRONG", "STABLE"}:
            result.add(
                level="warning",
                code="FINAL_RULE_ALWAYS_TRUE_NOT_STRONG",
                message="全量保留规则应有强证据支撑。",
                target=target,
                suggested_action="确认该工序确实在全部样本中稳定出现，或改成条件规则。",
            )

        if include_when != "always=true" and not evidence:
            result.add(
                level="warning",
                code="FINAL_RULE_MISSING_EVIDENCE",
                message="条件规则缺少证据说明，定稿后难以审计。",
                target=target,
                suggested_action="补充样本覆盖、反例边界或人工确认来源。",
            )

        if strength in {"WEAK", "MEDIUM"} and not why_not_stable:
            result.add(
                level="warning",
                code="FINAL_RULE_WEAK_WITHOUT_UNSTABLE_REASON",
                message="非强规则需要说明未判稳原因。",
                target=target,
                suggested_action="补充 why_not_stable，说明缺少哪些条件或反例边界。",
            )

        condition_text = " ".join([
            include_when,
            evidence,
            why_not_stable,
            " ".join(str(value) for value in candidate_factors if value is not None)
            if isinstance(candidate_factors, list) else _as_text(candidate_factors),
        ])
        if any(token in condition_text for token in uncertain_tokens):
            result.add(
                level="warning",
                code="FINAL_RULE_CONTAINS_UNRESOLVED_MARKER",
                message="规则草案包含不确定或待核查标记，不能直接当稳定规则定稿。",
                target=target,
                suggested_action="继续追问、补充资料，或在定稿报告中标记为待核查。",
            )

        if include_when != "always=true" and isinstance(candidate_factors, list) and not candidate_factors:
            result.add(
                level="warning",
                code="FINAL_RULE_MISSING_CANDIDATE_FACTORS",
                message="条件规则缺少候选因素列表，后续问答回放会缺少锚点。",
                target=target,
                suggested_action="把 include_when 中的关键条件同步到 candidate_factors。",
            )

    return result


def merge_validation_results(*results: HarnessValidationResult) -> HarnessValidationResult:
    merged = HarnessValidationResult()
    for result in results:
        merged.issues.extend(result.issues)
    return merged


def format_validation_errors(result: HarnessValidationResult) -> str:
    return "；".join(
        f"{issue.code}: {issue.message}"
        + (f" target={issue.target}" if issue.target else "")
        + (f" action={issue.suggested_action}" if issue.suggested_action else "")
        for issue in result.errors
    )


def raise_for_harness_errors(result: HarnessValidationResult, *, stage: str) -> None:
    if result.ok:
        return
    raise HarnessValidationError(stage=stage, result=result)
