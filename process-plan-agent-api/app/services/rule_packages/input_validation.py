"""Input validation shared by embedded tests and the simulation API."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import Field

from app.services.rule_packages.contracts import InputField, InputSchemaV2, ValidationIssue
from app.services.rule_packages.expression_engine import MISSING, resolve_field


class InputValidationIssue(ValidationIssue):
    """A field-level input error suitable for returning from API endpoints."""

    field: str
    reason: str
    allowed_values: list[Any] = Field(default_factory=list)


def _present(value: Any) -> bool:
    if value is MISSING or value is None or value == "":
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _allowed_values(field: InputField) -> list[Any]:
    if field.type == "boolean":
        return [True, False]
    return [option.value for option in field.options]


def _input_leaf_paths(
    value: Any,
    *,
    known_fields: set[str],
    prefix: str = "",
):
    if prefix in known_fields:
        yield prefix
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            next_prefix = f"{prefix}.{key_text}" if prefix else key_text
            yield from _input_leaf_paths(item, known_fields=known_fields, prefix=next_prefix)
        return
    if prefix:
        yield prefix


def _set_field(inputs: dict[str, Any], field_key: str, value: Any) -> None:
    if field_key in inputs:
        inputs[field_key] = value
        return
    current: dict[str, Any] = inputs
    parts = field_key.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _canonical_option_value(field: InputField, value: Any) -> Any:
    if not isinstance(value, str) or not field.options:
        return value
    canonical_values = {
        option.value.strip().casefold(): option.value
        for option in field.options
    }
    aliases = {
        alias.strip().casefold(): option.value
        for option in field.options
        for alias in option.aliases
    }
    normalized = value.strip().casefold()
    return canonical_values.get(normalized, aliases.get(normalized, value))


def _unknown_input_issue(field_key: str) -> InputValidationIssue:
    message = f"输入包含规则包未定义字段：{field_key}"
    return InputValidationIssue(
        code="unknown_input_field",
        path=f"inputs.{field_key}",
        message=message,
        field=field_key,
        reason=message,
    )


def _metadata_issue(code: str, field: InputField, message: str) -> InputValidationIssue:
    return InputValidationIssue(
        code=code,
        path=f"inputs.{field.key}",
        message=message,
        field=field.key,
        reason=message,
        allowed_values=_allowed_values(field),
    )


def canonicalize_inputs(
    schema: InputSchemaV2,
    inputs: dict[str, Any],
) -> tuple[dict[str, Any], list[InputValidationIssue]]:
    """Return planner-ready values and errors for unsupported input paths."""
    normalized = deepcopy(inputs or {})
    fields_by_key = {field.key: field for field in schema.fields}
    errors = [
        _unknown_input_issue(path)
        for path in _input_leaf_paths(normalized, known_fields=set(fields_by_key))
        if path not in fields_by_key
    ]
    for field in schema.fields:
        value = resolve_field(normalized, field.key)
        if value is MISSING:
            continue
        if field.type == "multi_select" and isinstance(value, list):
            _set_field(
                normalized,
                field.key,
                [_canonical_option_value(field, item) for item in value],
            )
        else:
            _set_field(normalized, field.key, _canonical_option_value(field, value))
    return normalized, errors


def validate_inputs(schema: InputSchemaV2, inputs: dict[str, Any]) -> list[InputValidationIssue]:
    normalized_inputs, errors = canonicalize_inputs(schema, inputs)

    def add(code: str, field: InputField, message: str) -> None:
        errors.append(
            InputValidationIssue(
                code=code,
                path=f"inputs.{field.key}",
                message=message,
                field=field.key,
                reason=message,
                allowed_values=_allowed_values(field),
            )
        )

    for field in schema.fields:
        value = resolve_field(normalized_inputs, field.key)
        if not _present(value):
            if field.required:
                add("required_input_missing", field, f"必填输入 {field.label} 未填写")
            continue

        if field.type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                add("input_type_mismatch", field, f"输入 {field.label} 必须是数值")
                continue
            if field.validation and field.validation.min is not None and value < field.validation.min:
                add("input_below_min", field, f"输入 {field.label} 不能小于 {field.validation.min:g}")
            if field.validation and field.validation.max is not None and value > field.validation.max:
                add("input_above_max", field, f"输入 {field.label} 不能大于 {field.validation.max:g}")
        elif field.type == "boolean":
            if not isinstance(value, bool):
                add("input_type_mismatch", field, f"输入 {field.label} 必须是布尔值")
        elif field.type == "multi_select":
            if not isinstance(value, list):
                add("input_type_mismatch", field, f"输入 {field.label} 必须是数组")
                continue
            if any(not isinstance(item, str) for item in value):
                add("input_type_mismatch", field, f"输入 {field.label} 的每个选项都必须是字符串")
                continue
        elif not isinstance(value, str):
            add("input_type_mismatch", field, f"输入 {field.label} 必须是字符串")
            continue

        if field.type in {"single_select", "multi_select"} and field.options and not field.allow_custom:
            allowed = {option.value.strip().casefold() for option in field.options}
            for option in field.options:
                allowed.update(alias.strip().casefold() for alias in option.aliases)
            actual_values = value if isinstance(value, list) else [value]
            invalid = [str(item) for item in actual_values if str(item).strip().casefold() not in allowed]
            if invalid:
                add("input_option_invalid", field, f"输入 {field.label} 包含未允许值：{', '.join(invalid)}")

        if field.validation and isinstance(value, (str, list)):
            if field.validation.min_length is not None and len(value) < field.validation.min_length:
                add("input_too_short", field, f"输入 {field.label} 长度不能小于 {field.validation.min_length}")
            if field.validation.max_length is not None and len(value) > field.validation.max_length:
                add("input_too_long", field, f"输入 {field.label} 长度不能大于 {field.validation.max_length}")

    return errors


def validate_input_metadata(
    schema: InputSchemaV2,
    inputs: dict[str, Any],
    input_metadata: dict[str, Any] | None,
) -> list[InputValidationIssue]:
    metadata = input_metadata or {}
    fields_by_key = {field.key: field for field in schema.fields}
    errors = [
        _unknown_input_issue(field_key)
        for field_key in metadata
        if field_key not in fields_by_key
    ]
    for field in schema.fields:
        value = resolve_field(inputs, field.key)
        if not _present(value):
            continue
        entry = metadata.get(field.key)
        if entry is None:
            errors.append(_metadata_issue(
                "input_origin_missing",
                field,
                f"输入 {field.label} 缺少值来源，请人工确认或提供提取依据后再生成",
            ))
            continue
        origin = getattr(entry, "origin", None)
        if origin is None and isinstance(entry, dict):
            origin = entry.get("origin")
        if origin not in {"manual", "extracted"}:
            code = "example_input_not_confirmed" if origin == "example" else "input_origin_unconfirmed"
            message = (
                f"输入 {field.label} 仍是示例值，请人工确认后再生成"
                if origin == "example"
                else f"输入 {field.label} 尚未确认来源，请人工确认或提供提取依据后再生成"
            )
            errors.append(_metadata_issue(code, field, message))
        evidence = getattr(entry, "evidence", None)
        if evidence is None and isinstance(entry, dict):
            evidence = entry.get("evidence")
        if origin == "extracted" and not any(str(item).strip() for item in (evidence or [])):
            errors.append(_metadata_issue(
                "extracted_input_missing_evidence",
                field,
                f"提取输入 {field.label} 缺少来源证据，不能用于生成路线",
            ))
        unit = getattr(entry, "unit", None)
        if unit is None and isinstance(entry, dict):
            unit = entry.get("unit")
        if field.type == "number" and field.unit and unit not in {None, "", field.unit}:
            errors.append(_metadata_issue(
                "input_unit_mismatch",
                field,
                f"输入 {field.label} 的单位必须是 {field.unit}",
            ))
    return errors


def input_validation_error_detail(errors: list[InputValidationIssue]) -> list[dict[str, Any]]:
    return [issue.model_dump(mode="json") for issue in errors]
