"""
第二步路线归并推荐配置。

业务规则放在 knowledge/route_merge/route_merge_rules.json 中维护；
这一层只负责加载配置并转换为运行时需要的数据结构。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROUTE_MERGE_ALGO_VERSION = "v32"

ROUTE_MERGE_RULES_PATH = (
    Path(__file__).resolve().parents[3]
    / "knowledge"
    / "route_merge"
    / "route_merge_rules.json"
)

SET_FIELDS = {
    "required_names",
    "child_names",
    "parent_names",
    "required_parent_steps",
}


def _coerce_rule_sets(rule: dict[str, Any]) -> dict[str, Any]:
    next_rule = dict(rule)
    for field in SET_FIELDS:
        if isinstance(next_rule.get(field), list):
            next_rule[field] = set(str(item) for item in next_rule[field])
    return next_rule


def _load_route_merge_rules() -> dict[str, Any]:
    with ROUTE_MERGE_RULES_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


_RULE_CONFIG = _load_route_merge_rules()

AUXILIARY_OPERATION_NAMES = set(
    str(item) for item in _RULE_CONFIG.get("auxiliary_operation_names", [])
)

DIRECT_MERGE_RULES: list[dict[str, Any]] = [
    _coerce_rule_sets(rule)
    for rule in _RULE_CONFIG.get("direct_merge_rules", [])
]

ABSORB_INTO_PARENT_RULES: list[dict[str, Any]] = [
    _coerce_rule_sets(rule)
    for rule in _RULE_CONFIG.get("absorb_into_parent_rules", [])
]

KEEP_SEPARATE_RULES: list[dict[str, Any]] = [
    _coerce_rule_sets(rule)
    for rule in _RULE_CONFIG.get("keep_separate_rules", [])
]

POST_BRANCH_STAGE_ORDER: dict[str, int] = {
    str(name): int(rank)
    for name, rank in _RULE_CONFIG.get("post_branch_stage_order", {}).items()
}

TERMINAL_RELEASE_ORDER: dict[str, int] = {
    str(name): int(rank)
    for name, rank in _RULE_CONFIG.get("terminal_release_order", {}).items()
}
