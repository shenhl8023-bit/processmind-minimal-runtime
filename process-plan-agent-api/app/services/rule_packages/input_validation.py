"""Input validation shared by embedded tests and the simulation API."""

from __future__ import annotations

from typing import Any

from app.services.rule_packages.contracts import InputSchemaV2, ValidationIssue
from app.services.rule_packages.expression_engine import MISSING, resolve_field


def _present(value: Any) -> bool:
    if value is MISSING or value is None or value == "":
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def validate_inputs(schema: InputSchemaV2, inputs: dict[str, Any]) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []

    def add(code: str, field_key: str, message: str) -> None:
        errors.append(ValidationIssue(code=code, path=f"inputs.{field_key}", message=message))

    for field in schema.fields:
        value = resolve_field(inputs, field.key)
        if not _present(value):
            if field.required:
                add("required_input_missing", field.key, f"必填输入 {field.label} 未填写")
            continue

        if field.type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                add("input_type_mismatch", field.key, f"输入 {field.label} 必须是数值")
                continue
            if field.validation and field.validation.min is not None and value < field.validation.min:
                add("input_below_min", field.key, f"输入 {field.label} 不能小于 {field.validation.min:g}")
            if field.validation and field.validation.max is not None and value > field.validation.max:
                add("input_above_max", field.key, f"输入 {field.label} 不能大于 {field.validation.max:g}")
        elif field.type == "boolean":
            if not isinstance(value, bool):
                add("input_type_mismatch", field.key, f"输入 {field.label} 必须是布尔值")
        elif field.type == "multi_select":
            if not isinstance(value, list):
                add("input_type_mismatch", field.key, f"输入 {field.label} 必须是数组")
                continue
            if any(not isinstance(item, str) for item in value):
                add("input_type_mismatch", field.key, f"输入 {field.label} 的每个选项都必须是字符串")
                continue
        elif not isinstance(value, str):
            add("input_type_mismatch", field.key, f"输入 {field.label} 必须是字符串")
            continue

        if field.type in {"single_select", "multi_select"} and field.options and not field.allow_custom:
            allowed = {option.value.strip().casefold() for option in field.options}
            for option in field.options:
                allowed.update(alias.strip().casefold() for alias in option.aliases)
            actual_values = value if isinstance(value, list) else [value]
            invalid = [str(item) for item in actual_values if str(item).strip().casefold() not in allowed]
            if invalid:
                add("input_option_invalid", field.key, f"输入 {field.label} 包含未允许值：{', '.join(invalid)}")

        if field.validation and isinstance(value, (str, list)):
            if field.validation.min_length is not None and len(value) < field.validation.min_length:
                add("input_too_short", field.key, f"输入 {field.label} 长度不能小于 {field.validation.min_length}")
            if field.validation.max_length is not None and len(value) > field.validation.max_length:
                add("input_too_long", field.key, f"输入 {field.label} 长度不能大于 {field.validation.max_length}")

    return errors
