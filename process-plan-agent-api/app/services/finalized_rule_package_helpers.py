"""
规则定稿导出包的轻量序列化辅助。
"""

from __future__ import annotations

import json

from app.models.models import FinalizedRulePackage
from app.schemas.schemas import FinalizedRulePackageOut


def json_dumps(value: object) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def serialize_finalized_rule_package(row: FinalizedRulePackage) -> FinalizedRulePackageOut:
    return FinalizedRulePackageOut(
        id=row.id,
        project_id=row.project_id,
        route_version_id=row.route_version_id,
        version=row.version,
        package_name=row.package_name,
        input_schema=json_loads(row.input_schema_json),
        route_catalog=json_loads(row.route_catalog_json),
        route_rules=json_loads(row.route_rules_json),
        rule_report_md=row.rule_report_md or "",
        validation_report=json_loads(row.validation_report_json),
        created_by=row.created_by or "默认用户",
        created_at=row.created_at,
    )


__all__ = [
    "json_dumps",
    "json_loads",
    "serialize_finalized_rule_package",
]
