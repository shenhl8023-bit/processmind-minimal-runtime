"""
第5步参数问答策略工具。

这里集中放置工序族分类、根因优先级和终止问题类型读取逻辑，
避免 generate.py 同时承担 API、规则生成、问答策略三类职责。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.paths import PARAM_QUESTION_STRATEGY_PATH

PARAM_QUESTION_STRATEGY_CACHE: dict[str, object] | None = None


class ParamQuestionStrategyError(ValueError):
    """参数问答策略配置不可用。"""


def validate_param_question_strategy(payload: object, source: Path) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ParamQuestionStrategyError(f"参数问答策略配置必须是 JSON 对象: {source}")
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ParamQuestionStrategyError(f"参数问答策略缺少非空 version: {source}")

    family_rules = payload.get("familyRules")
    if not isinstance(family_rules, list) or not family_rules:
        raise ParamQuestionStrategyError(f"参数问答策略 familyRules 必须是非空数组: {source}")
    for index, item in enumerate(family_rules):
        if not isinstance(item, dict):
            raise ParamQuestionStrategyError(f"参数问答策略 familyRules[{index}] 必须是对象: {source}")
        for key in ("family", "label"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ParamQuestionStrategyError(
                    f"参数问答策略 familyRules[{index}].{key} 必须是非空字符串: {source}"
                )
        patterns = item.get("patterns")
        if not isinstance(patterns, list) or any(not isinstance(pattern, str) for pattern in patterns):
            raise ParamQuestionStrategyError(
                f"参数问答策略 familyRules[{index}].patterns 必须是字符串数组: {source}"
            )

    priority_map = payload.get("rootReasonPriority")
    if not isinstance(priority_map, dict) or not isinstance(priority_map.get("other"), list) or not priority_map["other"]:
        raise ParamQuestionStrategyError(
            f"参数问答策略 rootReasonPriority 必须包含数组字段 other: {source}"
        )
    for family, values in priority_map.items():
        if not isinstance(family, str) or not isinstance(values, list) or not values or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise ParamQuestionStrategyError(
                f"参数问答策略 rootReasonPriority.{family} 必须是非空字符串数组: {source}"
            )

    terminal_types = payload.get("terminalQuestionTypes")
    if not isinstance(terminal_types, list) or not terminal_types or any(
        not isinstance(value, str) or not value.strip() for value in terminal_types
    ):
        raise ParamQuestionStrategyError(
            f"参数问答策略 terminalQuestionTypes 必须是非空字符串数组: {source}"
        )
    return dict(payload)

HOLE_OPERATION_HINTS = ("孔", "钻", "镗", "铰", "攻螺纹", "车螺纹")
SLOT_OPERATION_HINTS = ("槽", "扁", "键", "花键")
HEAT_TREAT_OPERATION_HINTS = ("调质", "淬火", "回火", "去应力", "热处理", "渗氮", "时效", "钝化", "氰化", "正常化")
FINISH_OPERATION_HINTS = ("磨", "研", "珩", "抛光")
END_FACE_OPERATION_HINTS = ("端面", "平端面", "车端面")
CHAMFER_OPERATION_HINTS = ("倒角", "倒圆", "孔口倒角", "车倒角")
OUTER_SURFACE_OPERATION_HINTS = ("外圆", "车外形", "车外圆", "外形")

PARAM_QUESTION_GOAL_MAP = {
    "merge_name_select": "先确认这组可无条件合并工序的统一名称",
    "generic_reason_select": "先确定这道工序未全覆盖的主要原因类型",
    "generic_structure_select": "先确认当前工序主要落在哪类结构或特征差异上",
    "structure_need_select": "先确认没有这些结构或特征时该工序是否通常不出现",
    "hole_structure_select": "先确认孔相关结构属于哪一类",
    "hole_detail_select": "把孔结构继续细化到可落规则的粒度",
    "slot_structure_select": "先确认槽相关结构属于哪一类",
    "slot_detail_select": "把槽结构继续细化到可落规则的粒度",
    "material_select": "先确认这道工序是按哪种材料信息区分的",
    "material_scope_select": "把会出现该工序的材料范围勾选出来",
    "heat_treatment_select": "先确认当前边界主要落在哪类热处理状态上",
    "precision_select": "先确认当前边界主要落在哪类加工要求上",
    "size_select": "先确认主要是哪一种尺寸或尺度边界在起作用",
    "size_boundary_select": "先确认这类尺寸边界是否已经能总结出大致分界",
    "blank_select": "先确认当前边界主要落在哪类毛坯或来料状态上",
    "blank_need_select": "先确认这种毛坯或来料状态下是否通常需要该工序",
    "requirement_select": "先确认当前边界主要落在哪类加工要求上",
    "requirement_need_select": "先确认是不是要求更高时才会增加该工序",
    "multi_factor_select": "先确认最主要的两个联合因素是什么",
    "multi_primary_select": "先确认联合因素里谁更像主因素",
    "missing_info_select": "先确认当前最缺的是哪一类信息",
    "manufacturability_select": "先确认是不是可加工性限制在驱动这道工序",
    "stress_risk_select": "先确认是不是变形或应力风险在驱动这道工序",
}

PARAM_QUESTION_TREE_META = {
    "merge_name_select": ("merge", "merge_name_root", "fixed"),
    "generic_reason_select": ("coverage", "coverage_reason_root", "fixed"),
    "material_select": ("coverage", "coverage_material_type", "fixed"),
    "material_scope_select": ("coverage", "coverage_material_list", "extracted"),
    "generic_structure_select": ("coverage", "coverage_structure_type", "fixed"),
    "structure_need_select": ("coverage", "coverage_structure_need", "fixed"),
    "hole_structure_select": ("coverage", "coverage_structure_type", "fixed"),
    "hole_detail_select": ("coverage", "coverage_structure_detail", "extracted"),
    "slot_structure_select": ("coverage", "coverage_structure_type", "fixed"),
    "slot_detail_select": ("coverage", "coverage_structure_detail", "extracted"),
    "heat_treatment_select": ("coverage", "coverage_material_type", "fixed"),
    "precision_select": ("coverage", "coverage_requirement_type", "fixed"),
    "size_select": ("coverage", "coverage_size_type", "fixed"),
    "size_boundary_select": ("coverage", "coverage_size_boundary", "fixed"),
    "blank_select": ("coverage", "coverage_blank_type", "fixed"),
    "blank_need_select": ("coverage", "coverage_blank_need", "fixed"),
    "requirement_select": ("coverage", "coverage_requirement_type", "fixed"),
    "requirement_need_select": ("coverage", "coverage_requirement_need", "fixed"),
    "multi_factor_select": ("coverage", "coverage_multi_pair", "fixed"),
    "multi_primary_select": ("coverage", "coverage_multi_primary", "fixed"),
    "missing_info_select": ("coverage", "coverage_uncertain_missing", "fixed"),
    "manufacturability_select": ("coverage", "coverage_requirement_type", "fixed"),
    "stress_risk_select": ("coverage", "coverage_requirement_type", "fixed"),
}


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in (text or "") for hint in hints)


def load_param_question_strategy(
    path: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, object]:
    global PARAM_QUESTION_STRATEGY_CACHE
    source = Path(path) if path is not None else PARAM_QUESTION_STRATEGY_PATH
    if path is None and PARAM_QUESTION_STRATEGY_CACHE is not None and not force:
        return dict(PARAM_QUESTION_STRATEGY_CACHE)
    if not source.is_file():
        raise ParamQuestionStrategyError(f"参数问答策略配置不存在: {source}")
    try:
        with source.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ParamQuestionStrategyError(f"参数问答策略无法解析 JSON: {source}") from exc
    except OSError as exc:
        raise ParamQuestionStrategyError(f"参数问答策略无法读取: {source}") from exc
    validated = validate_param_question_strategy(payload, source)
    if path is None:
        PARAM_QUESTION_STRATEGY_CACHE = validated
    return dict(validated)


def shared_param_operation_family(step_name: str) -> str:
    text = str(step_name or "").strip()
    if not text:
        return "other"
    strategy = load_param_question_strategy()
    family_rules = strategy.get("familyRules")
    if isinstance(family_rules, list):
        for item in family_rules:
            if not isinstance(item, dict):
                continue
            family = str(item.get("family") or "").strip()
            patterns = item.get("patterns")
            if not family or not isinstance(patterns, list):
                continue
            if any(str(pattern or "").strip() and str(pattern) in text for pattern in patterns):
                return family
    return "other"


def shared_prioritized_root_reason_values(step_name: str) -> list[str]:
    strategy = load_param_question_strategy()
    priority_map = strategy.get("rootReasonPriority")
    if not isinstance(priority_map, dict):
        return []
    family = shared_param_operation_family(step_name)
    values = priority_map.get(family) or priority_map.get("other") or []
    if not isinstance(values, list):
        return []
    return [str(value or "").strip() for value in values if str(value or "").strip()]


def shared_terminal_question_types() -> set[str]:
    strategy = load_param_question_strategy()
    values = strategy.get("terminalQuestionTypes")
    if not isinstance(values, list):
        return set()
    return {str(value or "").strip() for value in values if str(value or "").strip()}


def param_operation_family(step_name: str) -> str:
    if _contains_any(step_name, END_FACE_OPERATION_HINTS):
        return "end_face"
    if _contains_any(step_name, CHAMFER_OPERATION_HINTS):
        return "chamfer"
    if _contains_any(step_name, HOLE_OPERATION_HINTS):
        return "hole"
    if _contains_any(step_name, SLOT_OPERATION_HINTS):
        return "slot"
    if _contains_any(step_name, HEAT_TREAT_OPERATION_HINTS):
        return "heat"
    if _contains_any(step_name, FINISH_OPERATION_HINTS):
        return "finish"
    if _contains_any(step_name, OUTER_SURFACE_OPERATION_HINTS):
        return "outer_surface"
    return "generic"


def prioritized_root_reason_values(step_name: str) -> list[str]:
    shared = shared_prioritized_root_reason_values(step_name)
    return list(shared)


def default_param_question_meta(
    *,
    question_type: str,
    step_name: str,
    round_index: int,
    round_total_hint: int,
) -> tuple[str, str]:
    goal = PARAM_QUESTION_GOAL_MAP.get(question_type, "先确认这一轮最关键的规则边界")
    terminal_question_types = shared_terminal_question_types()

    if question_type in terminal_question_types:
        reason = f"这题答完后，工序“{step_name}”通常就可以结束这一轮确认，不再默认追加额外追问。"
        return goal, reason

    if round_index >= round_total_hint:
        reason = f"这是工序“{step_name}”本轮建议范围内的后段问题，答完后通常就可以判断是否继续细分。"
    elif round_index <= 1:
        reason = f"这题先帮系统判断工序“{step_name}”当前最值得优先确认的边界，避免一开始就问得过细。"
    else:
        reason = f"前一轮已经收敛到更小范围，这一题继续把工序“{step_name}”压到更稳定的规则边界。"
    return goal, reason


def param_question_tree_meta(question_type: str) -> tuple[str, str, str]:
    return PARAM_QUESTION_TREE_META.get(question_type, ("coverage", "", "fixed"))


def estimate_param_operation_round_limit(step_name: str) -> int:
    normalized = (step_name or "").strip()
    if any(token in normalized for token in ("线切割", "电火花", "珩", "研", "磨槽", "深孔", "冲洗")):
        return 4
    if any(token in normalized for token in ("磨", "镗", "铰", "孔", "槽", "螺纹", "去应力", "时效", "淬火", "渗氮", "钝化", "探伤", "检查")):
        return 3
    return 2


def sort_param_question_options(options: list[Any], ordered_values: list[str]) -> list[Any]:
    if not ordered_values:
        return options
    option_map = {item.value: item for item in options}
    used: set[str] = set()
    ordered: list[Any] = []
    for value in ordered_values:
        item = option_map.get(str(value))
        if item is None or item.value in used:
            continue
        ordered.append(item)
        used.add(item.value)
    tail_priority = {"other": 90, "unsure": 91, "data_issue": 92}
    remaining = [item for item in options if item.value not in used]
    remaining.sort(key=lambda item: tail_priority.get(item.value, 10))
    return [*ordered, *remaining]
