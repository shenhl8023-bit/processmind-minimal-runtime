"""工序因素规则到输入 schema 的装配。"""

from __future__ import annotations

from collections.abc import Callable

from app.models.models import Operation
from app.schemas.schemas import FactorFieldOption, FactorFieldOut
from app.services.generate_factor_schema_constants import (
    BOOLEAN_FIELD_LABELS,
    FIELD_LABELS,
    GROUP_ORDER,
    STANDARD_FACTOR_BLUEPRINT,
)


def display_label_for_key(key: str) -> str:
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    if key.startswith("has_"):
        suffix = key[4:].replace("_", " / ")
        return f"是否有 {suffix}"
    return key.replace("_", " ").strip().title()


def group_for_factor_key(key: str) -> str:
    if key in {"family", "material", "structure_type"}:
        return "基础与材料"
    if key in {"hardness", "has_final", "has_vac", "has_relief"}:
        return "热处理与性能"
    if key in {"hole_complex", "has_milling"}:
        return "结构补充"
    if key in {"need_trace", "need_mt", "need_burn_check"}:
        return "专项检查与放行"
    if key in {"roughness"}:
        return "精度与表面"
    if key.startswith("has_") or key.startswith("need_"):
        return "结构特征"
    return "其他因素"


def stringify_option_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def merge_schema_fields(base_schema: list[FactorFieldOut], extra_fields: list[FactorFieldOut]) -> list[FactorFieldOut]:
    merged = list(base_schema)
    seen = {field.key for field in merged}
    for field in extra_fields:
        if field.key in seen:
            continue
        merged.append(field)
        seen.add(field.key)
    return merged


def material_options_from_operations(
    operations: list[Operation],
    parse_factor_condition: Callable[[str], dict | None],
    is_warning_factor_name: Callable[[str], bool],
) -> list[tuple[str, str]]:
    values: set[str] = set()
    for op in operations:
        for factor in op.factors:
            if is_warning_factor_name(factor.name):
                continue
            parsed = parse_factor_condition(factor.name)
            if parsed and parsed["key"] == "material" and parsed["operator"] == "=" and isinstance(parsed["value"], str):
                values.add(parsed["value"])
    if not values:
        values.update(value for value, _ in STANDARD_FACTOR_BLUEPRINT[0]["options"])
    return [(value, value) for value in sorted(values)]


def build_standard_factor_schema(
    operations: list[Operation],
    parse_factor_condition: Callable[[str], dict | None],
    is_warning_factor_name: Callable[[str], bool],
    material_options_override: list[tuple[str, str]] | None = None,
    structure_options_override: list[str] | None = None,
) -> list[FactorFieldOut]:
    schema: list[FactorFieldOut] = []
    material_options = material_options_override or material_options_from_operations(
        operations,
        parse_factor_condition=parse_factor_condition,
        is_warning_factor_name=is_warning_factor_name,
    )

    for item in STANDARD_FACTOR_BLUEPRINT:
        options = item["options"]
        if item["key"] == "material":
            options = material_options
        elif item["key"] == "structure_type" and structure_options_override:
            options = [(value, value) for value in structure_options_override]
        schema.append(
            FactorFieldOut(
                key=item["key"],
                label=item["label"],
                group=item["group"],
                input_type=item["input_type"],
                required=item["required"],
                placeholder=item["placeholder"],
                options=[FactorFieldOption(value=value, label=label) for value, label in options],
            )
        )
    return schema


def build_factor_schema(
    operations: list[Operation],
    parse_factor_condition: Callable[[str], dict | None],
    is_warning_factor_name: Callable[[str], bool],
) -> list[FactorFieldOut]:
    standard_schema = build_standard_factor_schema(
        operations,
        parse_factor_condition=parse_factor_condition,
        is_warning_factor_name=is_warning_factor_name,
    )
    field_data: dict[str, dict] = {}

    def ensure_field(key: str) -> dict:
        field = field_data.get(key)
        if field:
            return field
        field = {
            "key": key,
            "label": display_label_for_key(key),
            "group": group_for_factor_key(key),
            "input_type": "text",
            "required": False,
            "placeholder": None,
            "options": {},
            "thresholds": set(),
            "operators": set(),
        }
        field_data[key] = field
        return field

    for op in operations:
        for factor in op.factors:
            if is_warning_factor_name(factor.name):
                continue
            parsed = parse_factor_condition(factor.name)
            if not parsed or parsed["key"] == "always" or parsed["operator"] == "raw":
                continue

            key = parsed["key"]
            operator = parsed["operator"]
            value = parsed["value"]
            field = ensure_field(key)
            field["operators"].add(operator)
            field["required"] = field["required"] or factor.strength == "STRONG"

            if operator == "not_empty":
                field["input_type"] = "text"
                field["placeholder"] = f"请输入{field['label']}"
            elif operator == "=" and isinstance(value, bool):
                field["input_type"] = "boolean"
                field["options"] = {
                    "false": BOOLEAN_FIELD_LABELS.get(key, ("否", "是"))[0],
                    "true": BOOLEAN_FIELD_LABELS.get(key, ("否", "是"))[1],
                }
            elif operator == "=":
                option_value = stringify_option_value(value)
                field["options"][option_value] = option_value
                field["input_type"] = "radio" if key == "hardness" else "select"
            elif operator in {"<=", ">="}:
                if isinstance(value, (int, float)):
                    field["thresholds"].add(float(value))
                field["input_type"] = "select" if key == "roughness" else "number"
            elif operator == "~=":
                option_value = stringify_option_value(value)
                field["options"][option_value] = option_value
                field["input_type"] = "select"

    for key, field in list(field_data.items()):
        if key == "hardness":
            field["input_type"] = "radio"
            field["options"] = {
                "LOW": "普通 (< HRC45)",
                "HIGH": "高硬度 (> HRC50)",
            }
        elif key == "roughness":
            field["input_type"] = "select"
            all_values = {3.2, 1.6, 0.8, 0.4}
            all_values.update(field["thresholds"])
            field["options"] = {
                stringify_option_value(value): f"Ra {stringify_option_value(value)}"
                for value in sorted(all_values, reverse=True)
            }
        elif key == "material" and not field["options"]:
            field["input_type"] = "text"
            field["placeholder"] = "请输入材料牌号"
        elif key == "family" and not field["options"]:
            field["input_type"] = "text"
            field["placeholder"] = "请输入零件家族"

    schema: list[FactorFieldOut] = list(standard_schema)
    existing_keys = {field.key for field in schema}
    for field in sorted(
        field_data.values(),
        key=lambda item: (GROUP_ORDER.get(item["group"], 99), item["label"]),
    ):
        if field["key"] in existing_keys:
            continue
        options = [
            FactorFieldOption(value=value, label=label)
            for value, label in field["options"].items()
        ]
        schema.append(
            FactorFieldOut(
                key=field["key"],
                label=field["label"],
                group=field["group"],
                input_type=field["input_type"],
                required=field["required"],
                placeholder=field["placeholder"],
                options=options,
            )
        )
    return schema


__all__ = [
    "build_factor_schema",
    "build_standard_factor_schema",
    "display_label_for_key",
    "group_for_factor_key",
    "material_options_from_operations",
    "merge_schema_fields",
    "stringify_option_value",
]
