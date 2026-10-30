"""Project-owned group-template persistence with optimistic revisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GeneratedRoute, Project, ProjectGroupTemplate
from app.services.group_template_xml import (
    GroupTemplateParseResult,
    is_feature_mapping_target,
    normalize_name,
)


REVISION_CONFLICT_DETAIL = "分组模板已在其他页面更新，请重新加载。"


@dataclass
class ProjectGroupMapping:
    source_operation_id: int
    alias: str
    template_group_key: str = ""
    template_group_id: str = ""
    template_group_name: str = ""
    template_group_path: list[str] = field(default_factory=list)
    feature_selections: list[str] = field(default_factory=list)


@dataclass
class ProjectGroupStepMapping:
    source_operation_id: int
    source_operation_name: str
    source_step_key: str
    source_step_order: int
    source_step_name: str
    source_step_text_hash: str
    scope_template_group_path: list[str] = field(default_factory=list)
    template_group_path: list[str] = field(default_factory=list)
    candidate_features: list[str] = field(default_factory=list)
    match_mode: str = "any"
    status: str = "confirmed"
    confidence: float = 1.0
    source: str = "user_confirmed"
    template_group_key: str = ""
    template_group_name: str = ""
    final_targets: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ProjectTemplateSnapshot:
    project_id: int
    original_filename: str
    source_encoding: str
    part_filename: str
    content_hash: str
    feature_dictionary_version: str
    tree: list[dict[str, object]]
    validation_issues: list[dict[str, object]]
    mappings: list[ProjectGroupMapping]
    step_mappings: list[ProjectGroupStepMapping]
    mapping_output: list[dict[str, object]]
    template_revision: int
    group_count: int
    feature_selection_count: int
    created_at: Any = None
    updated_at: Any = None


@dataclass
class TemplateCommitResult(ProjectTemplateSnapshot):
    kept_source_operation_ids: list[int] = field(default_factory=list)
    invalidated: list[ProjectGroupMapping] = field(default_factory=list)
    kept_source_step_keys: list[str] = field(default_factory=list)
    invalidated_step_mappings: list[ProjectGroupStepMapping] = field(default_factory=list)


def stable_step_key(operation_id: int, step_order: int) -> str:
    return f"op_{int(operation_id)}_s{int(step_order):02d}"


def step_text_hash(value: object) -> str:
    normalized = normalize_name(value)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _canonical_path(path: list[str]) -> str:
    normalized_path = [normalize_name(part) for part in path]
    return json.dumps(normalized_path, ensure_ascii=False, separators=(",", ":"))


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_list(value: str) -> list[Any]:
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def _mapping_value(mapping: object, key: str, default: object = None) -> object:
    if isinstance(mapping, dict):
        return mapping.get(key, default)
    return getattr(mapping, key, default)


MACHINING_PROCESS_PATTERN = re.compile(
    r"车削|车外|车端|粗车|精车|车槽|铣|钻|镗|铰|攻丝|攻螺纹|磨|研|珩|"
    r"切槽|挖槽|倒角|倒圆|成形|割型|打型|电火花|线切割|平端面|端面加工"
)
AUXILIARY_PROCESS_PATTERN = re.compile(
    r"下料|备料|锻造|铸造|热处理|调质|正火|正常化|淬火|回火|退火|去应力|"
    r"时效|渗氮|渗碳|镀|钝化|喷涂|清洗|除油|检验|检查|探伤|测量|标印|"
    r"标记|打标|包装|装配"
)


def _operation_id(operation: object) -> int:
    value = _mapping_value(operation, "operation_id", _mapping_value(operation, "source_operation_id", 0))
    return int(value or 0)


def _operation_name(operation: object) -> str:
    return normalize_name(_mapping_value(operation, "operation_name", _mapping_value(operation, "name", "")))


def _process_type(operation_name: str, steps: list[str]) -> str:
    step_text = " ".join(steps)
    if MACHINING_PROCESS_PATTERN.search(operation_name) or MACHINING_PROCESS_PATTERN.search(step_text):
        if AUXILIARY_PROCESS_PATTERN.search(operation_name) and not MACHINING_PROCESS_PATTERN.search(step_text):
            return "辅助工序"
        return "加工工序"
    return "辅助工序"


def _precision_label(operation_name: str, steps: list[str]) -> str:
    text_value = " ".join([operation_name, *steps])
    if re.search(r"半精", text_value):
        return "半精加工"
    if re.search(r"精", text_value):
        return "精加工"
    if re.search(r"粗", text_value):
        return "粗加工"
    return ""


def _mapping_candidates(mappings: list[ProjectGroupStepMapping]) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    for mapping in mappings:
        if mapping.status != "confirmed" or not mapping.template_group_path:
            continue
        key = "/".join(mapping.template_group_path)
        if not key:
            continue
        values = candidates.setdefault(key, [])
        for feature in mapping.candidate_features:
            if feature and feature not in values:
                values.append(feature)
    return candidates


def _source_step_refs(step: object) -> list[tuple[int, int, str]]:
    refs = _mapping_value(step, "source_steps", [])
    values = list(refs) if isinstance(refs, list) and refs else [step]
    result: list[tuple[int, int, str]] = []
    for value in values:
        operation_id = int(_mapping_value(value, "source_operation_id", 0) or 0)
        order = int(_mapping_value(value, "source_step_order", 0) or 0)
        name = normalize_name(_mapping_value(value, "source_step_name", ""))
        if operation_id > 0 and order > 0 and name:
            ref = (operation_id, order, name)
            if ref not in result:
                result.append(ref)
    return result


def _mapping_final_targets(mapping: object) -> list[dict[str, str]] | None:
    targets = _mapping_value(mapping, "final_targets", None)
    if targets is None:
        return None
    return [{"process_id": normalize_name(_mapping_value(target, "process_id", "")),
             "step_id": normalize_name(_mapping_value(target, "step_id", ""))}
            for target in targets]


def _final_mapping_targets(operations: list[object]) -> dict[tuple[int, int, str], list[dict[str, str]]]:
    targets: dict[tuple[int, int, str], list[dict[str, str]]] = {}
    seen_ids: set[str] = set()
    for operation in operations:
        process_id = normalize_name(_mapping_value(operation, "process_id", ""))
        if not process_id or process_id in seen_ids:
            raise HTTPException(422, "最终路线工序 ID 缺失或重复，请重新加载规则分析结果。")
        if not _operation_name(operation):
            raise HTTPException(422, "最终路线工序名称不能为空，请填写名称后再保存映射。")
        seen_ids.add(process_id)
        steps = _mapping_value(operation, "steps", []) or []
        process_type = normalize_name(_mapping_value(operation, "process_type", "")) or _process_type(
            _operation_name(operation), [normalize_name(_mapping_value(step, "step_name", "")) for step in steps],
        )
        for step in steps:
            step_id = normalize_name(_mapping_value(step, "step_id", ""))
            if not step_id or step_id in seen_ids:
                raise HTTPException(422, "最终路线工步 ID 缺失或重复，请重新加载规则分析结果。")
            if not normalize_name(_mapping_value(step, "step_name", "")):
                raise HTTPException(422, "最终路线工步名称不能为空，请填写名称后再保存映射。")
            seen_ids.add(step_id)
            if process_type != "加工工序":
                continue
            for ref in _source_step_refs(step):
                targets.setdefault(ref, []).append({"process_id": process_id, "step_id": step_id})
    return targets


def _legacy_operations(operations: list[object] | None, mappings: list[ProjectGroupStepMapping]) -> list[object]:
    result = list(operations or [])
    # Older clients omitted the complete final route. This fallback is deliberately
    # isolated from the explicit final-tree contract, which never adds source nodes.
    if not result:
        for operation_id in dict.fromkeys(mapping.source_operation_id for mapping in mappings):
            operation_mappings = [mapping for mapping in mappings if mapping.source_operation_id == operation_id]
            names_by_order = {mapping.source_step_order: mapping.source_step_name for mapping in operation_mappings}
            result.append({
                "operation_id": operation_id,
                "operation_name": operation_mappings[0].source_operation_name,
                "step_items": [names_by_order.get(order, "") for order in range(1, max(names_by_order, default=0) + 1)],
            })
    return result


def _build_mapping_output(operations: list[object] | None, mappings: list[ProjectGroupStepMapping]) -> list[dict[str, object]]:
    explicit_final_tree = any(_mapping_value(operation, "process_id", "") for operation in operations or [])
    operations = list(operations or []) if explicit_final_tree else _legacy_operations(operations, mappings)
    if explicit_final_tree:
        _final_mapping_targets(operations)
    mappings_by_source: dict[tuple[int, int, str], list[ProjectGroupStepMapping]] = {}
    for mapping in mappings:
        key = (mapping.source_operation_id, mapping.source_step_order, normalize_name(mapping.source_step_name))
        mappings_by_source.setdefault(key, []).append(mapping)

    output: list[dict[str, object]] = []
    seen_process_ids: set[str] = set()
    for operation in operations:
        operation_id = _operation_id(operation)
        operation_name = _operation_name(operation)
        process_id = normalize_name(_mapping_value(operation, "process_id", "")) or f"op_{operation_id}"
        if operation_id <= 0 or not operation_name or process_id in seen_process_ids:
            continue
        seen_process_ids.add(process_id)
        if explicit_final_tree:
            source_steps = list(_mapping_value(operation, "steps", []) or [])
        else:
            raw_steps = _mapping_value(operation, "step_items", []) or []
            source_steps = [{
                "step_id": stable_step_key(operation_id, order),
                "step_name": normalize_name(name),
                "source_operation_id": operation_id,
                "source_step_order": order,
                "source_step_name": normalize_name(name),
            } for order, name in enumerate(raw_steps, start=1) if normalize_name(name)]
        step_names = [normalize_name(_mapping_value(step, "step_name", "")) for step in source_steps]
        process_type = normalize_name(_mapping_value(operation, "process_type", "")) or _process_type(operation_name, step_names)
        if process_type not in {"加工工序", "辅助工序"}:
            raise HTTPException(422, "最终路线工序类型必须为加工工序或辅助工序。")
        precision = normalize_name(_mapping_value(operation, "precision", ""))
        if not precision:
            precision = "辅助工序" if process_type == "辅助工序" else (
                "" if explicit_final_tree else _precision_label(operation_name, step_names)
            )
        steps: list[dict[str, object]] = []
        if process_type == "加工工序":
            for step in source_steps:
                target = {"process_id": process_id, "step_id": normalize_name(_mapping_value(step, "step_id", ""))}
                step_mappings = [mapping for ref in _source_step_refs(step)
                                 for mapping in mappings_by_source.get(ref, [])
                                 if not mapping.final_targets or target in mapping.final_targets]
                steps.append({
                    "step_name": normalize_name(_mapping_value(step, "step_name", "")),
                    "candidates": _mapping_candidates(step_mappings),
                    "step_id": normalize_name(_mapping_value(step, "step_id", "")),
                })
        output.append({
            "process_name": operation_name,
            "process_type": process_type,
            "precision": precision,
            "steps": steps,
            "process_id": process_id,
        })
    return output


def _restore_mapping_operations(
    output: list[object], mappings: list[ProjectGroupStepMapping],
) -> list[object]:
    """Restore final IDs and provenance; never infer current sources from names."""
    if any(_mapping_value(process, "process_id", "") for process in output):
        operations: list[object] = []
        for index, process in enumerate(output, start=1):
            process_id = normalize_name(_mapping_value(process, "process_id", ""))
            steps: list[dict[str, object]] = []
            for step in _mapping_value(process, "steps", []) or []:
                step_id = normalize_name(_mapping_value(step, "step_id", ""))
                refs = [{
                    "source_operation_id": mapping.source_operation_id,
                    "source_step_order": mapping.source_step_order,
                    "source_step_name": mapping.source_step_name,
                } for mapping in mappings if {"process_id": process_id, "step_id": step_id} in mapping.final_targets]
                # Legacy op IDs already encode their source identity, unlike final IDs.
                if not refs and re.fullmatch(r"op_[0-9]+", process_id) and re.fullmatch(r"op_[0-9]+_s[0-9]+", step_id):
                    refs = [{"source_operation_id": int(process_id[3:]),
                             "source_step_order": int(step_id.rsplit("_s", 1)[1]),
                             "source_step_name": _mapping_value(step, "step_name", "")}]
                steps.append({"step_id": step_id, "step_name": _mapping_value(step, "step_name", ""),
                              "source_steps": refs})
            operations.append({
                "operation_id": index,
                "process_id": process_id,
                "operation_name": _mapping_value(process, "process_name", ""),
                "process_type": _mapping_value(process, "process_type", ""),
                "precision": _mapping_value(process, "precision", ""),
                "steps": steps,
            })
        return operations

    # Migrate pre-ID snapshots once. Exact old candidates disambiguate duplicate
    # source names, but candidates are rebuilt exclusively from valid mappings.
    mappings_by_operation: dict[int, list[ProjectGroupStepMapping]] = {}
    for mapping in mappings:
        mappings_by_operation.setdefault(mapping.source_operation_id, []).append(mapping)
    used_ids: set[int] = set()
    next_id = max(mappings_by_operation, default=0) + 1
    operations = []
    for process in output:
        name = normalize_name(_mapping_value(process, "process_name", ""))
        raw_steps = _mapping_value(process, "steps", [])
        steps = [normalize_name(_mapping_value(step, "step_name", "")) for step in raw_steps] if isinstance(raw_steps, list) else []
        matching_ids = [operation_id for operation_id, operation_mappings in mappings_by_operation.items()
                        if operation_id not in used_ids
                        and all(mapping.source_operation_name == name and 0 < mapping.source_step_order <= len(steps)
                                and steps[mapping.source_step_order - 1] == mapping.source_step_name for mapping in operation_mappings)
                        and all(_mapping_value(step, "candidates", {}) == _mapping_candidates([
                            mapping for mapping in operation_mappings if mapping.source_step_order == step_order
                        ]) for step_order, step in enumerate(raw_steps, start=1))]
        operation_id = matching_ids[0] if matching_ids else next_id
        if not matching_ids:
            next_id += 1
        used_ids.add(operation_id)
        operations.append({"operation_id": operation_id, "operation_name": name, "step_items": steps})
    return operations


def _mapping_snapshot(mapping: object) -> ProjectGroupMapping:
    path = _mapping_value(mapping, "template_group_path", [])
    features = _mapping_value(mapping, "feature_selections", [])
    return ProjectGroupMapping(
        source_operation_id=int(_mapping_value(mapping, "source_operation_id", 0) or 0),
        alias=str(_mapping_value(mapping, "alias", "") or ""),
        template_group_key=str(_mapping_value(mapping, "template_group_key", "") or ""),
        template_group_id=str(_mapping_value(mapping, "template_group_id", "") or ""),
        template_group_name=str(_mapping_value(mapping, "template_group_name", "") or ""),
        template_group_path=[str(part) for part in path] if isinstance(path, list) else [],
        feature_selections=[str(item) for item in features] if isinstance(features, list) else [],
    )


def _step_mapping_snapshot(mapping: object) -> ProjectGroupStepMapping:
    operation_id = int(_mapping_value(mapping, "source_operation_id", 0) or 0)
    step_order = int(_mapping_value(mapping, "source_step_order", 0) or 0)
    step_name = normalize_name(_mapping_value(mapping, "source_step_name", ""))
    scope_path = _mapping_value(mapping, "scope_template_group_path", [])
    target_path = _mapping_value(mapping, "template_group_path", [])
    features = _mapping_value(mapping, "candidate_features", [])
    return ProjectGroupStepMapping(
        source_operation_id=operation_id,
        source_operation_name=normalize_name(_mapping_value(mapping, "source_operation_name", "")),
        source_step_key=str(
            _mapping_value(mapping, "source_step_key", stable_step_key(operation_id, step_order))
        ),
        source_step_order=step_order,
        source_step_name=step_name,
        source_step_text_hash=str(
            _mapping_value(mapping, "source_step_text_hash", step_text_hash(step_name))
        ),
        scope_template_group_path=[normalize_name(item) for item in scope_path]
        if isinstance(scope_path, list)
        else [],
        template_group_path=[normalize_name(item) for item in target_path]
        if isinstance(target_path, list)
        else [],
        candidate_features=[normalize_name(item) for item in features]
        if isinstance(features, list)
        else [],
        match_mode=str(_mapping_value(mapping, "match_mode", "any")),
        status=str(_mapping_value(mapping, "status", "confirmed")),
        confidence=float(_mapping_value(mapping, "confidence", 1.0) or 0.0),
        source=str(_mapping_value(mapping, "source", "user_confirmed")),
        template_group_key=str(_mapping_value(mapping, "template_group_key", "")),
        template_group_name=str(_mapping_value(mapping, "template_group_name", "")),
        final_targets=_mapping_final_targets(mapping) or [],
    )


def _path_index(tree: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}

    def visit(nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            path = node.get("path", [])
            if isinstance(path, list):
                index[_canonical_path([str(part) for part in path])] = node
            children = node.get("children", [])
            if isinstance(children, list):
                visit(children)

    visit(tree)
    return index


def _resolve_mapping(mapping: object, index: dict[str, dict[str, object]]) -> ProjectGroupMapping | None:
    requested_path = _mapping_value(mapping, "template_group_path", [])
    if not isinstance(requested_path, list):
        return None
    path = [str(part) for part in requested_path]
    node = index.get(_canonical_path(path))
    if node is None:
        return None
    node_path = node.get("path", [])
    node_features = node.get("feature_selections", [])
    key = str(node.get("key", ""))
    return ProjectGroupMapping(
        source_operation_id=int(_mapping_value(mapping, "source_operation_id", 0) or 0),
        alias=str(_mapping_value(mapping, "alias", "") or ""),
        template_group_key=key,
        template_group_id=key,
        template_group_name=str(node.get("name", "")),
        template_group_path=[str(part) for part in node_path] if isinstance(node_path, list) else [],
        feature_selections=[str(item) for item in node_features] if isinstance(node_features, list) else [],
    )


def _resolve_step_mapping(
    mapping: object,
    index: dict[str, dict[str, object]],
) -> ProjectGroupStepMapping:
    operation_id = int(_mapping_value(mapping, "source_operation_id", 0) or 0)
    operation_name = normalize_name(_mapping_value(mapping, "source_operation_name", ""))
    step_order = int(_mapping_value(mapping, "source_step_order", 0) or 0)
    step_name = normalize_name(_mapping_value(mapping, "source_step_name", ""))
    status = str(_mapping_value(mapping, "status", "confirmed"))
    confidence = float(_mapping_value(mapping, "confidence", 1.0) or 0.0)
    source = str(_mapping_value(mapping, "source", "user_confirmed"))
    key = stable_step_key(operation_id, step_order)
    text_hash = step_text_hash(step_name)
    final_targets = _step_mapping_snapshot(mapping).final_targets

    if status == "not_applicable":
        return ProjectGroupStepMapping(
            source_operation_id=operation_id,
            source_operation_name=operation_name,
            source_step_key=key,
            source_step_order=step_order,
            source_step_name=step_name,
            source_step_text_hash=text_hash,
            status=status,
            confidence=confidence,
            source=source,
            final_targets=final_targets,
        )

    requested_path = _mapping_value(mapping, "template_group_path", [])
    if not isinstance(requested_path, list):
        raise HTTPException(422, "工步正式映射必须指向具有合法特征的叶子分组。")
    target = index.get(_canonical_path([str(item) for item in requested_path]))
    if target is None or not is_feature_mapping_target(target):
        raise HTTPException(422, "工步正式映射必须指向具有合法特征的叶子分组。")

    requested_features_raw = _mapping_value(mapping, "candidate_features", [])
    requested_features = {
        normalize_name(item)
        for item in requested_features_raw
        if normalize_name(item)
    } if isinstance(requested_features_raw, list) else set()
    node_features = [
        normalize_name(item)
        for item in target.get("feature_selections", [])
        if normalize_name(item)
    ]
    if not requested_features or not requested_features.issubset(set(node_features)):
        raise HTTPException(422, "候选特征不属于目标叶子分组。")

    scope_path_raw = _mapping_value(mapping, "scope_template_group_path", [])
    scope_path = (
        [normalize_name(item) for item in scope_path_raw]
        if isinstance(scope_path_raw, list)
        else []
    )
    target_path = [normalize_name(item) for item in target.get("path", [])]
    if scope_path and target_path[:len(scope_path)] != scope_path:
        raise HTTPException(422, "目标叶子不在所选父分组范围内。")

    return ProjectGroupStepMapping(
        source_operation_id=operation_id,
        source_operation_name=operation_name,
        source_step_key=key,
        source_step_order=step_order,
        source_step_name=step_name,
        source_step_text_hash=text_hash,
        scope_template_group_path=scope_path,
        template_group_path=target_path,
        candidate_features=[item for item in node_features if item in requested_features],
        match_mode="any",
        status="confirmed",
        confidence=confidence,
        source=source,
        template_group_key=str(target.get("key", "")),
        template_group_name=str(target.get("name", "")),
        final_targets=final_targets,
    )


def _mapping_dicts(mappings: list[ProjectGroupMapping]) -> list[dict[str, object]]:
    return [asdict(mapping) for mapping in mappings]


def _step_mapping_dicts(mappings: list[ProjectGroupStepMapping]) -> list[dict[str, object]]:
    return [asdict(mapping) for mapping in mappings]


def _merge_group_mappings(
    current: list[ProjectGroupMapping],
    incoming: list[ProjectGroupMapping],
) -> list[ProjectGroupMapping]:
    """Apply an incremental legacy save without dropping sibling group mappings."""
    merged: list[ProjectGroupMapping] = []
    positions: dict[tuple[int, str], int] = {}
    for mapping in current:
        key = (mapping.source_operation_id, _canonical_path(mapping.template_group_path))
        positions.setdefault(key, len(merged))
        merged.append(mapping)
    for mapping in incoming:
        key = (mapping.source_operation_id, _canonical_path(mapping.template_group_path))
        if key in positions:
            merged[positions[key]] = mapping
        else:
            positions[key] = len(merged)
            merged.append(mapping)
    return merged


def _step_mapping_targets_key(mapping: object) -> tuple[tuple[str, str], ...]:
    targets = _mapping_value(mapping, "final_targets", []) or []
    return tuple(sorted(
        (
            normalize_name(_mapping_value(target, "process_id", "")),
            normalize_name(_mapping_value(target, "step_id", "")),
        )
        for target in targets
        if normalize_name(_mapping_value(target, "process_id", ""))
        and normalize_name(_mapping_value(target, "step_id", ""))
    ))


def _step_mapping_scope_key(mapping: object) -> tuple[str, tuple[tuple[str, str], ...]]:
    operation_id = int(_mapping_value(mapping, "source_operation_id", 0) or 0)
    step_order = int(_mapping_value(mapping, "source_step_order", 0) or 0)
    source_key = str(_mapping_value(mapping, "source_step_key", "") or "") or stable_step_key(
        operation_id, step_order,
    )
    return source_key, _step_mapping_targets_key(mapping)


def _step_mapping_path_key(mapping: object) -> str:
    path = _mapping_value(mapping, "template_group_path", [])
    return _canonical_path(path if isinstance(path, list) else [])


def _merge_step_mappings(
    current: list[ProjectGroupStepMapping],
    incoming: list[ProjectGroupStepMapping],
) -> list[ProjectGroupStepMapping]:
    """Merge added decisions without making a later partial save destructive.

    A confirmed mapping replaces the same source/target/group entry and clears a
    prior ``not_applicable`` decision for that source/target.  A not-applicable
    decision clears all entries for that source/target.  Other confirmed groups
    remain available for the same source step.
    """
    merged = list(current)
    for candidate in incoming:
        candidate_scope = _step_mapping_scope_key(candidate)
        candidate_path = _step_mapping_path_key(candidate)
        if candidate.status == "not_applicable":
            merged = [
                mapping for mapping in merged
                if _step_mapping_scope_key(mapping) != candidate_scope
            ]
        else:
            previous_features: list[str] = []
            for mapping in merged:
                if (
                    mapping.status == "confirmed"
                    and _step_mapping_scope_key(mapping) == candidate_scope
                    and _step_mapping_path_key(mapping) == candidate_path
                ):
                    previous_features.extend(mapping.candidate_features)
            merged = [
                mapping for mapping in merged
                if _step_mapping_scope_key(mapping) != candidate_scope
                or (
                    mapping.status != "not_applicable"
                    and _step_mapping_path_key(mapping) != candidate_path
                )
            ]
            candidate.candidate_features = list(dict.fromkeys(
                [*previous_features, *candidate.candidate_features]
            ))
        merged.append(candidate)
    return merged


def serialize_project_group_template(row: ProjectGroupTemplate) -> ProjectTemplateSnapshot:
    return ProjectTemplateSnapshot(
        project_id=int(row.project_id),
        original_filename=row.original_filename,
        source_encoding=row.source_encoding,
        part_filename=row.part_filename,
        content_hash=row.content_hash,
        feature_dictionary_version=row.feature_dictionary_version,
        tree=_json_list(row.tree_json),
        validation_issues=_json_list(row.validation_json),
        mappings=[_mapping_snapshot(mapping) for mapping in _json_list(row.mappings_json)],
        step_mappings=[
            _step_mapping_snapshot(mapping)
            for mapping in _json_list(getattr(row, "step_mappings_json", "[]"))
        ],
        mapping_output=_json_list(getattr(row, "mapping_output_json", "[]")),
        template_revision=int(row.template_revision),
        group_count=int(row.group_count),
        feature_selection_count=int(row.feature_selection_count),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_project_group_template(
    db: AsyncSession,
    project_id: int,
) -> ProjectGroupTemplate | None:
    return (
        await db.execute(
            select(ProjectGroupTemplate).where(ProjectGroupTemplate.project_id == project_id)
        )
    ).scalar_one_or_none()


def _conflict() -> HTTPException:
    return HTTPException(409, REVISION_CONFLICT_DETAIL)


def _parsed_values(parsed: GroupTemplateParseResult) -> dict[str, object]:
    return {
        "original_filename": parsed.original_filename,
        "source_encoding": parsed.source_encoding,
        "part_filename": parsed.part_filename,
        "content_hash": parsed.content_hash,
        "feature_dictionary_version": parsed.feature_dictionary_version,
        "source_xml": parsed.source_xml,
        "tree_json": _json_dump(parsed.tree),
        "validation_json": _json_dump([asdict(issue) for issue in parsed.issues]),
        "group_count": parsed.group_count,
        "feature_selection_count": parsed.feature_selection_count,
    }


async def _fresh_snapshot(db: AsyncSession, project_id: int) -> ProjectTemplateSnapshot:
    row = (
        await db.execute(
            select(ProjectGroupTemplate)
            .where(ProjectGroupTemplate.project_id == project_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return serialize_project_group_template(row)


async def _invalidate_template_dependent_outputs(db: AsyncSession, project_id: int) -> None:
    from app.services.rule_packages.lifecycle import supersede_published_rule_packages

    await supersede_published_rule_packages(project_id, db)
    await db.execute(delete(GeneratedRoute).where(GeneratedRoute.project_id == project_id))
    await db.flush()


async def commit_project_group_template(
    db: AsyncSession,
    project_id: int,
    parsed: GroupTemplateParseResult,
    expected_revision: int,
) -> TemplateCommitResult:
    values = _parsed_values(parsed)
    current = await get_project_group_template(db, project_id)
    if current is None:
        if expected_revision != 0:
            raise _conflict()
        params = {"project_id": project_id, **values}
        inserted = (
            await db.execute(
                text("""
                    INSERT OR IGNORE INTO project_group_templates (
                        project_id, original_filename, source_encoding, part_filename,
                        content_hash, feature_dictionary_version, source_xml, tree_json,
                        validation_json, mappings_json, step_mappings_json, mapping_output_json,
                        template_revision, group_count, feature_selection_count
                    )
                    SELECT :project_id, :original_filename, :source_encoding, :part_filename,
                           :content_hash, :feature_dictionary_version, :source_xml, :tree_json,
                           :validation_json, '[]', '[]', '[]', 1, :group_count, :feature_selection_count
                    FROM projects WHERE id = :project_id
                    RETURNING id
                """),
                params,
            )
        ).scalar_one_or_none()
        if inserted is None:
            project_exists = (
                await db.execute(select(Project.id).where(Project.id == project_id))
            ).scalar_one_or_none()
            if project_exists is None:
                raise HTTPException(404, "任务不存在")
            raise _conflict()
        await _invalidate_template_dependent_outputs(db, project_id)
        snapshot = await _fresh_snapshot(db, project_id)
        return TemplateCommitResult(**snapshot.__dict__)

    if int(current.template_revision) != expected_revision:
        raise _conflict()
    new_index = _path_index(parsed.tree)
    migrated: list[ProjectGroupMapping] = []
    invalidated: list[ProjectGroupMapping] = []
    for old_mapping in _json_list(current.mappings_json):
        resolved = _resolve_mapping(old_mapping, new_index)
        if resolved is None:
            invalidated.append(_mapping_snapshot(old_mapping))
        else:
            migrated.append(resolved)
    migrated_steps: list[ProjectGroupStepMapping] = []
    invalidated_steps: list[ProjectGroupStepMapping] = []
    old_step_mappings = _json_list(current.step_mappings_json)
    for old_mapping in old_step_mappings:
        try:
            migrated_steps.append(_resolve_step_mapping(old_mapping, new_index))
        except HTTPException:
            invalidated_steps.append(_step_mapping_snapshot(old_mapping))
    source_operations = _restore_mapping_operations(
        _json_list(current.mapping_output_json),
        [_step_mapping_snapshot(mapping) for mapping in old_step_mappings],
    )
    mapping_output = _build_mapping_output(source_operations, migrated_steps)

    revision = (
        await db.execute(
            text("""
                UPDATE project_group_templates
                SET original_filename = :original_filename,
                    source_encoding = :source_encoding,
                    part_filename = :part_filename,
                    content_hash = :content_hash,
                    feature_dictionary_version = :feature_dictionary_version,
                    source_xml = :source_xml,
                    tree_json = :tree_json,
                    validation_json = :validation_json,
                    mappings_json = :mappings_json,
                    step_mappings_json = :step_mappings_json,
                    mapping_output_json = :mapping_output_json,
                    group_count = :group_count,
                    feature_selection_count = :feature_selection_count,
                    template_revision = template_revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = :project_id AND template_revision = :expected_revision
                RETURNING template_revision
            """),
            {
                "project_id": project_id,
                "expected_revision": expected_revision,
                "mappings_json": _json_dump(_mapping_dicts(migrated)),
                "step_mappings_json": _json_dump(_step_mapping_dicts(migrated_steps)),
                "mapping_output_json": _json_dump(mapping_output),
                **values,
            },
        )
    ).scalar_one_or_none()
    if revision is None:
        raise _conflict()
    await _invalidate_template_dependent_outputs(db, project_id)
    snapshot = await _fresh_snapshot(db, project_id)
    return TemplateCommitResult(
        **snapshot.__dict__,
        kept_source_operation_ids=[mapping.source_operation_id for mapping in migrated],
        invalidated=invalidated,
        kept_source_step_keys=sorted({mapping.source_step_key for mapping in migrated_steps}),
        invalidated_step_mappings=invalidated_steps,
    )


async def replace_project_group_mappings(
    db: AsyncSession,
    project_id: int,
    mappings: list[object],
    expected_revision: int,
    replace_all: bool = True,
) -> ProjectTemplateSnapshot:
    current = await get_project_group_template(db, project_id)
    if current is None or int(current.template_revision) != expected_revision:
        raise _conflict()
    index = _path_index(_json_list(current.tree_json))
    resolved: list[ProjectGroupMapping] = []
    for mapping in mappings:
        server_mapping = _resolve_mapping(mapping, index)
        if server_mapping is None:
            raise HTTPException(422, "映射的分组路径不存在于当前模板。")
        resolved.append(server_mapping)
    if not replace_all:
        current_mappings = [
            _mapping_snapshot(mapping)
            for mapping in _json_list(current.mappings_json)
        ]
        resolved = _merge_group_mappings(current_mappings, resolved)

    revision = (
        await db.execute(
            text("""
                UPDATE project_group_templates
                SET mappings_json = :mappings_json,
                    template_revision = template_revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = :project_id AND template_revision = :expected_revision
                RETURNING template_revision
            """),
            {
                "project_id": project_id,
                "expected_revision": expected_revision,
                "mappings_json": _json_dump(_mapping_dicts(resolved)),
            },
        )
    ).scalar_one_or_none()
    if revision is None:
        raise _conflict()
    await _invalidate_template_dependent_outputs(db, project_id)
    return await _fresh_snapshot(db, project_id)


async def replace_project_group_step_mappings(
    db: AsyncSession,
    project_id: int,
    mappings: list[object],
    expected_revision: int,
    operations: list[object] | None = None,
    replace_all: bool = True,
) -> ProjectTemplateSnapshot:
    current = await get_project_group_template(db, project_id)
    if current is None or int(current.template_revision) != expected_revision:
        raise _conflict()
    index = _path_index(_json_list(current.tree_json))
    resolved: list[ProjectGroupStepMapping] = []
    seen_targets: set[tuple[str, tuple[tuple[str, str], ...], str]] = set()
    explicit_final_tree = any(_mapping_value(operation, "process_id", "") for operation in operations or [])
    saved_output = _json_list(current.mapping_output_json)
    saved_output_mode = str(getattr(current, "mapping_output_mode", "unknown") or "unknown")
    saved_final_tree = any(
        _mapping_value(mapping, "final_targets", [])
        for mapping in _json_list(current.step_mappings_json)
    ) or any(
        not re.fullmatch(r"op_[0-9]+", str(_mapping_value(process, "process_id", "")))
        for process in saved_output
    ) or saved_output_mode == "final_tree"
    if saved_final_tree and not explicit_final_tree:
        raise HTTPException(422, "当前映射已关联最终工艺树，请提交完整最终路线后再保存，不能改用旧版来源工序。")
    if saved_output and saved_output_mode != "legacy" and not explicit_final_tree:
        raise HTTPException(422, "当前保存路线格式无法判定，请重新加载并提交完整最终路线后再保存映射。")
    final_targets = _final_mapping_targets(list(operations or [])) if explicit_final_tree else {}
    if not replace_all and explicit_final_tree and saved_output:
        if saved_output_mode != "final_tree":
            raise HTTPException(422, "当前路线快照格式无法用于增量升级，请使用全量替换提交完整最终路线。")
        saved_process_ids = {
            normalize_name(_mapping_value(process, "process_id", ""))
            for process in saved_output
            if normalize_name(_mapping_value(process, "process_id", ""))
        }
        incoming_process_ids = {
            normalize_name(_mapping_value(operation, "process_id", ""))
            for operation in operations or []
            if normalize_name(_mapping_value(operation, "process_id", ""))
        }
        missing_process_ids = saved_process_ids - incoming_process_ids
        if missing_process_ids:
            raise HTTPException(422, "增量保存的最终路线必须包含当前已保存的全部工序，请提交完整最终路线。")
    for mapping in mappings:
        source_ref = (int(_mapping_value(mapping, "source_operation_id", 0) or 0),
                      int(_mapping_value(mapping, "source_step_order", 0) or 0),
                      normalize_name(_mapping_value(mapping, "source_step_name", "")))
        requested_targets = _mapping_final_targets(mapping)
        allowed_targets = final_targets.get(source_ref, [])
        if requested_targets is not None:
            if not explicit_final_tree or not requested_targets or any(
                target not in allowed_targets for target in requested_targets
            ):
                raise HTTPException(422, "映射目标必须是当前来源工步对应的最终加工工步，请重新加载模板映射。")
        elif explicit_final_tree and not allowed_targets:
            continue
        server_mapping = _resolve_step_mapping(mapping, index)
        if explicit_final_tree:
            server_mapping.final_targets = requested_targets if requested_targets is not None else allowed_targets
        target_ids = tuple(sorted((target["process_id"], target["step_id"]) for target in server_mapping.final_targets))
        target_key = _canonical_path(server_mapping.template_group_path)
        dedupe_key = (server_mapping.source_step_key, target_ids, target_key)
        if dedupe_key in seen_targets:
            continue
        seen_targets.add(dedupe_key)
        resolved.append(server_mapping)

    if not replace_all:
        current_mappings = [
            _step_mapping_snapshot(mapping)
            for mapping in _json_list(current.step_mappings_json)
        ]
        if explicit_final_tree:
            retained_mappings = []
            for mapping in current_mappings:
                source_ref = (mapping.source_operation_id, mapping.source_step_order,
                              normalize_name(mapping.source_step_name))
                allowed_targets = final_targets.get(source_ref, [])
                retained_targets = [target for target in mapping.final_targets if target in allowed_targets]
                if not mapping.final_targets:
                    retained_targets = allowed_targets
                if retained_targets:
                    mapping.final_targets = retained_targets
                    retained_mappings.append(mapping)
            current_mappings = retained_mappings
        resolved = _merge_step_mappings(current_mappings, resolved)

    statuses: dict[tuple[str, str, str], set[str]] = {}
    for mapping in resolved:
        status_keys = [("final", target["process_id"], target["step_id"]) for target in mapping.final_targets]
        if not status_keys:
            status_keys = [("source", mapping.source_step_key, "")]
        for status_key in status_keys:
            statuses.setdefault(status_key, set()).add(mapping.status)
    if any(len(step_statuses) > 1 for step_statuses in statuses.values()):
        raise HTTPException(422, "同一工步不能同时确认映射和标记为不依赖模板特征。")

    mapping_output = _build_mapping_output(operations, resolved)
    if explicit_final_tree:
        invalid_precision = [process for process in mapping_output
                             if process["process_type"] == "加工工序"
                             and process["precision"] not in {"粗加工", "半精加工", "精加工"}]
        if invalid_precision:
            names = "、".join(str(process["process_name"]) for process in invalid_precision)
            raise HTTPException(422, f"请先填写以下加工工序的精度（粗加工、半精加工或精加工）再保存映射：{names}")
        invalid_auxiliary = [process for process in mapping_output
                             if process["process_type"] == "辅助工序" and process["precision"] != "辅助工序"]
        if invalid_auxiliary:
            names = "、".join(str(process["process_name"]) for process in invalid_auxiliary)
            raise HTTPException(422, f"以下辅助工序的精度必须为辅助工序：{names}")
    revision = (
        await db.execute(
            text("""
                UPDATE project_group_templates
                SET step_mappings_json = :step_mappings_json,
                    mapping_output_json = :mapping_output_json,
                    mapping_output_mode = :mapping_output_mode,
                    template_revision = template_revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = :project_id AND template_revision = :expected_revision
                RETURNING template_revision
            """),
            {
                "project_id": project_id,
                "expected_revision": expected_revision,
                "step_mappings_json": _json_dump(_step_mapping_dicts(resolved)),
                "mapping_output_json": _json_dump(mapping_output),
                "mapping_output_mode": "final_tree" if explicit_final_tree else "legacy",
            },
        )
    ).scalar_one_or_none()
    if revision is None:
        raise _conflict()
    await _invalidate_template_dependent_outputs(db, project_id)
    return await _fresh_snapshot(db, project_id)
