"""
参数规则条件表达式解析、匹配与人读化工具。

第4步导出的规则包和第5步路线生成都应复用这里的表达式语义，
避免同一个条件在不同流程里被解释成不同含义。
"""
from __future__ import annotations

import re
from typing import Any


def canonicalize_factor_name(factor_name: str) -> str:
    factor = (factor_name or "").strip()
    if not factor:
        return ""

    if factor in {"通用基础工序相关", "外形特征相关", "检验要求相关", "外形与关键尺寸相关", "通用质量收尾相关"}:
        return "always=true"
    if factor in {"孔类结构相关"}:
        return "has_hole=true"
    if factor in {"槽类/键/花键结构相关"}:
        return "has_spline=true"
    if factor in {"精度公差相关", "精度与表面要求相关"}:
        return "roughness<=0.8"
    if factor in {"材料与热处理相关"}:
        return "hardness=HIGH"
    if factor in {"part_type=活门类", "structure_type=活门类"}:
        return "structure_type=活门类"
    if factor in {"part_type=衬套类", "structure_type=衬套类"}:
        return "structure_type=衬套类"

    material_match = re.fullmatch(r"材料\s*[=：:]\s*([A-Za-z0-9_.-]+)", factor)
    if material_match:
        return f"material={material_match.group(1)}"

    if re.fullmatch(r"硬度要求\s*[><=]+\s*HRC\d+", factor):
        return "hardness=HIGH"

    return factor


def parse_factor_condition(factor_name: str) -> dict | None:
    factor = canonicalize_factor_name(factor_name)
    if not factor:
        return None

    if factor == "always=true":
        return {"operator": "always", "key": "always", "value": True}

    not_empty_match = re.fullmatch(r"([A-Za-z_][\w]*)!=空", factor)
    if not_empty_match:
        key = not_empty_match.group(1)
        return {"operator": "not_empty", "key": key, "value": None}

    compare_match = re.fullmatch(r"([A-Za-z_][\w]*)(<=|>=|=|~=)(.+)", factor)
    if compare_match:
        key, operator, raw_value = compare_match.groups()
        value: object = raw_value.strip()
        if str(value).lower() in {"true", "false"}:
            value = str(value).lower() == "true"
        elif re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", str(value)):
            value = float(str(value))
        return {"operator": operator, "key": key, "value": value}

    return {"operator": "raw", "key": factor, "value": factor}


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是"}
    return False


def to_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        text = (
            text.replace("°", "")
            .replace("度", "")
            .replace("mm", "")
            .replace("MM", "")
            .replace(",", "")
            .strip()
        )
        matched = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if matched:
            text = matched.group(0)
        try:
            return float(text)
        except ValueError:
            return None
    return None


def matches_factor_condition(factor_name: str, inputs: dict[str, object], op_name: str = "") -> tuple[bool, str]:
    parsed = parse_factor_condition(factor_name)
    if not parsed:
        return False, ""

    operator = parsed["operator"]
    key = parsed["key"]
    expected = parsed["value"]

    if operator == "always":
        return True, "命中规则：基础主线工序"

    actual = inputs.get(key)

    if operator == "not_empty":
        matched = actual not in (None, "")
        return matched, f"命中规则：{key} 已填写" if matched else ""

    if operator == "=" and isinstance(expected, bool):
        matched = to_bool(actual) == expected
        return matched, f"命中规则：{key}={'是' if expected else '否'}" if matched else ""

    if operator == "=":
        actual_number = to_float(actual)
        expected_number = to_float(expected)
        if actual_number is not None and expected_number is not None:
            matched = abs(actual_number - expected_number) < 1e-6
        else:
            matched = str(actual or "").strip().lower() == str(expected).strip().lower()
        return matched, f"命中规则：{key}={expected}" if matched else ""

    if operator == "~=":
        matched = str(expected).strip().lower() in str(actual or "").strip().lower()
        return matched, f"命中规则：{key} 包含 {expected}" if matched else ""

    if operator == "<=":
        actual_number = to_float(actual)
        threshold = to_float(expected)
        matched = actual_number is not None and threshold is not None and actual_number <= threshold
        return matched, f"命中规则：{key}<={threshold}" if matched else ""

    if operator == ">=":
        actual_number = to_float(actual)
        threshold = to_float(expected)
        matched = actual_number is not None and threshold is not None and actual_number >= threshold
        return matched, f"命中规则：{key}>={threshold}" if matched else ""

    return False, ""


def split_condition_terms(condition_expr: str) -> list[str]:
    expr = (condition_expr or "").strip()
    if not expr:
        return []
    parts = [part.strip() for part in re.split(r"\s+and\s+", expr, flags=re.IGNORECASE)]
    return [part for part in parts if part]


def match_rule_expr(condition_expr: str, inputs: dict[str, object]) -> tuple[bool, list[str]]:
    terms = split_condition_terms(condition_expr)
    if not terms:
        return False, []

    reasons: list[str] = []
    for term in terms:
        matched, reason = matches_factor_condition(term.replace(" ", ""), inputs, "")
        if not matched:
            space_match = re.fullmatch(r'([A-Za-z_][\w]*)\s*(<=|>=|=|!=|~=)\s*(.+)', term)
            if not space_match:
                return False, []
            key, operator, raw_value = space_match.groups()
            actual = inputs.get(key)
            raw_value = raw_value.strip().strip('"')
            if operator == "!=":
                if raw_value == "":
                    matched = actual not in (None, "")
                    reason = f"命中规则：{key} 已填写" if matched else ""
                else:
                    actual_number = to_float(actual)
                    expected_number = to_float(raw_value)
                    if actual_number is not None and expected_number is not None:
                        matched = abs(actual_number - expected_number) >= 1e-6
                    else:
                        matched = str(actual or "").strip().lower() != raw_value.lower()
                    reason = f"命中规则：{key}!={raw_value}" if matched else ""
            elif operator == "=":
                normalized = "true" if raw_value.lower() == "true" else "false" if raw_value.lower() == "false" else raw_value
                matched, reason = matches_factor_condition(f"{key}={normalized}", inputs, "")
            elif operator in {"<=", ">=", "~="}:
                matched, reason = matches_factor_condition(f"{key}{operator}{raw_value}", inputs, "")
            else:
                matched = False
                reason = ""

        if not matched:
            return False, []
        if reason:
            reasons.append(reason)
    return True, reasons


def strength_rank(strength: str) -> int:
    mapping = {
        "WEAK": 0,
        "MEDIUM": 1,
        "STRONG": 2,
    }
    return mapping.get((strength or "").upper(), 3)


def field_option_label(field: Any | None, option_value: object) -> str:
    if field is None:
        return str(option_value)
    normalized = str(option_value).strip().strip('"')
    for option in getattr(field, "options", []) or []:
        if option.value == normalized:
            return option.label
    if getattr(field, "input_type", "") == "boolean":
        return "是" if normalized.lower() == "true" else "否" if normalized.lower() == "false" else normalized
    return normalized


def humanize_param_rule_term(term: str, factor_fields: list[Any]) -> str:
    expr = (term or "").strip()
    if not expr:
        return ""
    if expr == "always=true":
        return "属于稳定主线"

    normalized = expr.replace(" ", "")
    parsed = parse_factor_condition(normalized)
    if parsed:
        key = str(parsed.get("key") or "").strip()
        operator = str(parsed.get("operator") or "").strip()
        value = parsed.get("value")
        field = next((item for item in factor_fields if item.key == key), None)
        field_label = field.label if field else key
        if operator == "not_empty":
            return f"{field_label}已填写"
        if operator == "=":
            return f"{field_label}={field_option_label(field, value)}"
        if operator == "~=":
            return f"{field_label}包含{field_option_label(field, value)}"
        if operator in {"<=", ">="}:
            return f"{field_label}{operator}{value}"

    match = re.fullmatch(r'([A-Za-z_][\w]*)\s*(<=|>=|=|!=|~=)\s*(.+)', expr)
    if not match:
        return expr

    key, operator, raw_value = match.groups()
    field = next((item for item in factor_fields if item.key == key), None)
    field_label = field.label if field else key
    value_text = field_option_label(field, raw_value)
    return f"{field_label}{operator}{value_text}"


def humanize_param_rule_expr(condition_expr: str, factor_fields: list[Any]) -> str:
    terms = split_condition_terms(condition_expr)
    if not terms:
        return condition_expr
    return " 且 ".join(filter(None, (humanize_param_rule_term(term, factor_fields) for term in terms)))


def term_expected_value_text(term: str, factor_fields: list[Any]) -> str:
    expr = (term or "").strip()
    normalized = expr.replace(" ", "")
    parsed = parse_factor_condition(normalized)
    if not parsed:
        return expr
    value = parsed.get("value")
    field = next((item for item in factor_fields if item.key == parsed.get("key")), None)
    if value is None:
        return ""
    return field_option_label(field, value)


def normalize_candidate_factor_terms(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        terms.append(text)
    return terms
