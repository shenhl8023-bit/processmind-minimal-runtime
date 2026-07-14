"""工艺路线生成因素 schema 的兼容导出入口。"""

from __future__ import annotations

from app.services.generate_factor_schema_constants import (
    BOOLEAN_FIELD_LABELS,
    FIELD_LABELS,
    GROUP_ORDER,
    STANDARD_FACTOR_BLUEPRINT,
)
from app.services.generate_factor_schema_operation import (
    build_factor_schema,
    build_standard_factor_schema,
    display_label_for_key,
    group_for_factor_key,
    material_options_from_operations,
    merge_schema_fields,
    stringify_option_value,
)
from app.services.generate_factor_schema_reference import (
    build_attribute_factor_schema,
    build_reference_factor_schema,
    clean_reference_line,
    collect_attribute_rows_from_texts,
    collect_reference_attribute_rows,
    extract_document_body,
    extract_reference_body,
    is_numeric_value,
    material_options_from_rows,
    parse_reference_attributes,
    reference_group_for_label,
    reference_material_options,
    reference_structure_options,
    structure_options_from_rows,
)

__all__ = [
    "BOOLEAN_FIELD_LABELS",
    "FIELD_LABELS",
    "GROUP_ORDER",
    "STANDARD_FACTOR_BLUEPRINT",
    "build_attribute_factor_schema",
    "build_factor_schema",
    "build_reference_factor_schema",
    "build_standard_factor_schema",
    "clean_reference_line",
    "collect_attribute_rows_from_texts",
    "collect_reference_attribute_rows",
    "display_label_for_key",
    "extract_document_body",
    "extract_reference_body",
    "group_for_factor_key",
    "is_numeric_value",
    "material_options_from_operations",
    "material_options_from_rows",
    "merge_schema_fields",
    "parse_reference_attributes",
    "reference_group_for_label",
    "reference_material_options",
    "reference_structure_options",
    "stringify_option_value",
    "structure_options_from_rows",
]
