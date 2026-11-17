"""
工艺路线生成页的因素 schema 组装辅助。
"""

from __future__ import annotations

from typing import Callable

from app.models.models import Operation
from app.schemas.schemas import FactorFieldOut
from app.services.generate_factor_schema import (
    build_factor_schema,
    build_standard_factor_schema,
    merge_schema_fields,
)


def build_project_factor_schema(
    operations: list[Operation],
    *,
    parse_factor_condition: Callable[[str], dict[str, object] | None],
    is_warning_factor_name: Callable[[str], bool],
) -> list[FactorFieldOut]:
    standard_schema = build_standard_factor_schema(
        operations,
        parse_factor_condition=parse_factor_condition,
        is_warning_factor_name=is_warning_factor_name,
    )
    schema = merge_schema_fields(
        standard_schema,
        build_factor_schema(
            operations,
            parse_factor_condition=parse_factor_condition,
            is_warning_factor_name=is_warning_factor_name,
        ),
    )
    return schema


__all__ = ["build_project_factor_schema"]
