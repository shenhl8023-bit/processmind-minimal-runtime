"""
参数问答树配置读取工具。

这里集中处理第三步/第四步沉淀的问题树配置，避免业务路由直接读取
配置文件并手工转换选项结构。
"""
from __future__ import annotations

import json

from app.core.paths import THIRD_STEP_RULE_TREE_PATH
from app.schemas.schemas import ParamConfirmOptionOut


THIRD_STEP_RULE_TREE_CACHE: dict[str, object] | None = None


def load_third_step_rule_tree_config() -> dict[str, object]:
    global THIRD_STEP_RULE_TREE_CACHE
    if THIRD_STEP_RULE_TREE_CACHE is not None:
        return dict(THIRD_STEP_RULE_TREE_CACHE)
    if not THIRD_STEP_RULE_TREE_PATH.is_file():
        THIRD_STEP_RULE_TREE_CACHE = {}
        return {}
    try:
        payload = json.loads(THIRD_STEP_RULE_TREE_PATH.read_text(encoding="utf-8"))
    except Exception:
        THIRD_STEP_RULE_TREE_CACHE = {}
        return {}
    THIRD_STEP_RULE_TREE_CACHE = payload if isinstance(payload, dict) else {}
    return dict(THIRD_STEP_RULE_TREE_CACHE)


def get_third_step_tree_node(branch: str, node_id: str) -> dict[str, object]:
    payload = load_third_step_rule_tree_config()
    branches = payload.get("branches") if isinstance(payload, dict) else None
    branch_payload = branches.get(branch) if isinstance(branches, dict) else None
    nodes = branch_payload.get("nodes") if isinstance(branch_payload, dict) else None
    if not isinstance(nodes, list):
        return {}
    for row in nodes:
        if isinstance(row, dict) and str(row.get("node_id") or "").strip() == node_id:
            return row
    return {}


def tree_next_node_id(branch: str, node_id: str, selected_value: str = "__submit__") -> str:
    node = get_third_step_tree_node(branch, node_id)
    next_map = node.get("next_map") if isinstance(node, dict) else None
    if not isinstance(next_map, dict):
        return ""
    direct = str(next_map.get(selected_value) or "").strip()
    if direct:
        return direct
    submit_fallback = str(next_map.get("__submit__") or "").strip()
    return submit_fallback


def tree_node_question(branch: str, node_id: str, fallback: str) -> str:
    node = get_third_step_tree_node(branch, node_id)
    question = str(node.get("question") or "").strip() if isinstance(node, dict) else ""
    return question or fallback


def tree_node_question_type(branch: str, node_id: str) -> str:
    node = get_third_step_tree_node(branch, node_id)
    return str(node.get("question_type") or "").strip() if isinstance(node, dict) else ""


def tree_node_options(branch: str, node_id: str) -> list[ParamConfirmOptionOut]:
    node = get_third_step_tree_node(branch, node_id)
    raw_options = node.get("options") if isinstance(node, dict) else None
    options: list[ParamConfirmOptionOut] = []
    if not isinstance(raw_options, list):
        return options
    for row in raw_options:
        if not isinstance(row, dict):
            continue
        value = str(row.get("value") or "").strip()
        label = str(row.get("label") or "").strip()
        if not value or not label:
            continue
        options.append(
            ParamConfirmOptionOut(
                value=value,
                label=label,
                count=int(row.get("count") or 0),
            )
        )
    return options
