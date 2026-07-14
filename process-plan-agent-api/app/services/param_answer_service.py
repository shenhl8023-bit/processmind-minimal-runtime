"""
参数规则问答的答案归一化与展示工具。

这里保持为纯函数，避免路由层夹杂答案显示、存储语义和规则表达式格式化。
"""
from typing import Any


PARAM_ANSWER_FIELD_MAP = {
    "material": "material",
    "material_basis": "material_basis",
    "heat": "heat_treatment",
    "precision": "precision_requirement",
    "slot": "slot_family",
    "slot_detail": "slot_feature",
    "hole": "hole_family",
    "hole_detail": "hole_feature",
    "mfg": "manufacturability",
    "risk": "risk_factor",
    "generic": "primary_driver",
    "coverage_reason": "coverage_reason",
    "size": "size_driver",
    "size_boundary": "size_boundary",
    "blank": "blank_driver",
    "blank_need": "blank_need",
    "requirement": "requirement_driver",
    "requirement_need": "requirement_need",
    "multi": "multi_factor_driver",
    "multi_primary": "multi_primary",
    "missing": "missing_info",
    "structure": "structure_family",
}


def normalize_param_answer_kind(selected_value: str, note: str = "") -> str:
    value = (selected_value or "").strip()
    if value == "data_issue":
        return "data_issue"
    if value == "unsure":
        return "unsure"
    if value == "other":
        return "custom" if (note or "").strip() else "unsure"
    return "selected"


def param_driver_factor_key(factor_key: str, layer: str = "reason") -> str:
    return f"__driver__::{layer}::{factor_key}"


def param_driver_storage_key(
    *,
    factor_key: str,
    question_type: str,
    selected_value: str,
    answer_kind: str,
) -> str:
    if answer_kind != "selected":
        return factor_key
    if question_type == "merge_name_select":
        return param_driver_factor_key("__merge__", "name")
    if question_type == "generic_reason_select" and (
        selected_value.startswith("generic::") or selected_value.startswith("coverage_reason::")
    ):
        return param_driver_factor_key(factor_key, "reason")
    if question_type == "material_select" and selected_value.startswith("material_basis::"):
        return param_driver_factor_key(factor_key, "material")
    if question_type == "multi_factor_select" and selected_value.startswith("multi::"):
        return param_driver_factor_key(factor_key, "multi")
    if question_type == "hole_structure_select" and selected_value.startswith("hole::"):
        return param_driver_factor_key(factor_key, "hole")
    if question_type == "slot_structure_select" and selected_value.startswith("slot::"):
        return param_driver_factor_key(factor_key, "slot")
    return factor_key


def param_answer_display_text(answer: Any | None) -> str:
    if answer is None:
        return ""
    note_text = str(getattr(answer, "note", "") or "").strip()
    label_text = str(getattr(answer, "selected_label", "") or "").strip()
    value_text = str(getattr(answer, "selected_value", "") or "").strip()
    if note_text:
        return note_text
    if label_text:
        return label_text
    return value_text


def param_answer_expression(answer: Any | None, factor_label: str = "") -> str:
    if answer is None:
        return ""
    value = str(getattr(answer, "selected_value", "") or "").strip()
    answer_kind = str(getattr(answer, "answer_kind", "") or "").strip()
    display = param_answer_display_text(answer)
    if answer_kind == "custom":
        return display
    if answer_kind == "unsure":
        return f"{factor_label or '该因素'}=暂不确定"
    if answer_kind == "data_issue":
        return f"{factor_label or '该因素'}=样本/数据需核查"
    if "::" in value:
        prefix, actual = value.split("::", 1)
        field_name = PARAM_ANSWER_FIELD_MAP.get(prefix, factor_label or prefix)
        return f"{field_name}={display or actual}"
    return display or value
