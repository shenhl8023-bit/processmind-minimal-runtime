"""Template-local decisions; neither waiver nor hiding creates a binding."""

from __future__ import annotations

from fastapi import HTTPException

from app.services.group_template_xml import is_feature_mapping_target, normalize_name


def resolve_waived_group_paths(tree: list, paths: list, *, strict: bool = True) -> list[list[str]]:
    leaves = {}

    def visit(nodes):
        for node in nodes:
            if is_feature_mapping_target(node):
                leaves[tuple(normalize_name(part) for part in node.get("path", []))] = node
            visit(node.get("children", []))

    visit(tree)
    resolved: list[list[str]] = []
    for path in paths:
        valid_shape = isinstance(path, list) and bool(path) and all(
            isinstance(part, str) and normalize_name(part) for part in path)
        node = leaves.get(tuple(normalize_name(part) for part in path)) if valid_shape else None
        if node is None:
            if strict:
                raise HTTPException(422, "豁免必须指向当前模板中具有合法特征的具体叶子分组。")
            continue
        canonical = list(node["path"])
        if canonical not in resolved:
            resolved.append(canonical)
    return resolved


def filter_hidden_mapping_steps(output: list[dict], hidden_step_keys: list[str]) -> list[dict]:
    hidden = set(hidden_step_keys)
    return [{**process, "steps": [step for step in process.get("steps", [])
                                 if step.get("step_id") not in hidden]} for process in output]
