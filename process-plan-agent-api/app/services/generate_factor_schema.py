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
from app.services.generate_factor_schema_attributes import (
    extract_document_body,
    parse_document_attributes,
)

__all__ = [
    "BOOLEAN_FIELD_LABELS",
    "FIELD_LABELS",
    "GROUP_ORDER",
    "STANDARD_FACTOR_BLUEPRINT",
    "build_factor_schema",
    "build_standard_factor_schema",
    "display_label_for_key",
    "extract_document_body",
    "group_for_factor_key",
    "material_options_from_operations",
    "merge_schema_fields",
    "parse_document_attributes",
    "stringify_option_value",
]
