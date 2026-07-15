"""Canonical hashing for executable rule package content."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.rule_packages.contracts import RulePackageV2


NON_SEMANTIC_KEYS = {"exported_at", "compiled_at"}


def _without_non_semantic_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_non_semantic_values(item)
            for key, item in value.items()
            if key not in NON_SEMANTIC_KEYS
        }
    if isinstance(value, list):
        return [_without_non_semantic_values(item) for item in value]
    return value


def canonical_rule_package_json(package: RulePackageV2) -> str:
    payload = _without_non_semantic_values(package.model_dump(mode="json", by_alias=True))
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rule_package_content_hash(package: RulePackageV2) -> str:
    canonical = canonical_rule_package_json(package)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def legacy_rule_package_content_hash(
    *,
    package_name: str,
    input_schema: dict,
    route_catalog: dict,
    route_rules: dict,
    rule_report_md: str,
) -> str:
    payload = {
        "schema_version": "1.0",
        "package_name": package_name,
        "input_schema": input_schema,
        "route_catalog": route_catalog,
        "route_rules": route_rules,
        "rule_report": rule_report_md,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
