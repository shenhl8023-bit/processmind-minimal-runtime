"""Project-owned group-template persistence with optimistic revisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Project, ProjectGroupTemplate
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


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text_value = normalize_name(item)
        if not text_value or text_value in seen:
            continue
        seen.add(text_value)
        result.append(text_value)
    return result


def _operation_id(operation: object) -> int:
    value = _mapping_value(operation, "operation_id", _mapping_value(operation, "source_operation_id", 0))
    return int(value or 0)


def _operation_name(operation: object) -> str:
    return normalize_name(_mapping_value(operation, "operation_name", _mapping_value(operation, "name", "")))


def _operation_steps(operation: object) -> list[str]:
    return _text_list(_mapping_value(operation, "step_items", []))


def _operation_requirements(operation: object) -> list[str]:
    return _text_list([
        *_text_list(_mapping_value(operation, "rule_evidence", [])),
        *_text_list(_mapping_value(operation, "rule_reasons", [])),
    ])


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


def _mapping_feature_keys(mapping: ProjectGroupStepMapping) -> set[str]:
    if mapping.status != "confirmed" or not mapping.template_group_path:
        return set()
    path_key = "/".join(mapping.template_group_path)
    return {f"{path_key}\u0000{feature}" for feature in mapping.candidate_features if feature}


def _build_mapping_output(operations: list[object] | None, mappings: list[ProjectGroupStepMapping]) -> list[dict[str, object]]:
    mappings_by_step: dict[tuple[int, int], list[ProjectGroupStepMapping]] = {}
    for mapping in mappings:
        mappings_by_step.setdefault((mapping.source_operation_id, mapping.source_step_order), []).append(mapping)

    normalized_operations: list[dict[str, object]] = []
    seen_operations: set[int] = set()
    for operation in operations or []:
        operation_id = _operation_id(operation)
        operation_name = _operation_name(operation)
        if operation_id <= 0 or not operation_name or operation_id in seen_operations:
            continue
        seen_operations.add(operation_id)
        normalized_operations.append({
            "operation_id": operation_id,
            "operation_name": operation_name,
            "step_items": _operation_steps(operation),
            "technical_requirements": _operation_requirements(operation),
        })

    for operation_id in sorted({mapping.source_operation_id for mapping in mappings} - seen_operations):
        operation_mappings = [mapping for mapping in mappings if mapping.source_operation_id == operation_id]
        operation_name = operation_mappings[0].source_operation_name if operation_mappings else ""
        normalized_operations.append({
            "operation_id": operation_id,
            "operation_name": operation_name,
            "step_items": [mapping.source_step_name for mapping in sorted(operation_mappings, key=lambda item: item.source_step_order)],
            "technical_requirements": [],
        })

    output: list[dict[str, object]] = []
    for operation in normalized_operations:
        operation_id = int(operation["operation_id"])
        operation_name = str(operation["operation_name"])
        steps = [str(step) for step in operation.get("step_items", []) if str(step).strip()]
        last_feature_step: dict[str, int] = {}
        for (mapped_operation_id, step_order), step_mappings in mappings_by_step.items():
            if mapped_operation_id != operation_id:
                continue
            for mapping in step_mappings:
                for feature_key in _mapping_feature_keys(mapping):
                    last_feature_step[feature_key] = max(last_feature_step.get(feature_key, 0), step_order)

        step_output: list[dict[str, object]] = []
        for step_order, step_name in enumerate(steps, start=1):
            step_mappings = mappings_by_step.get((operation_id, step_order), [])
            feature_keys = set().union(*[_mapping_feature_keys(mapping) for mapping in step_mappings]) if step_mappings else set()
            candidates = _mapping_candidates(step_mappings)
            step_output.append({
                "step_name": step_name,
                "candidates": candidates,
                "is_last": bool(feature_keys) and all(last_feature_step.get(key) == step_order for key in feature_keys),
            })

        output.append({
            "process_name": operation_name,
            "process_type": _process_type(operation_name, steps),
            "precision": _precision_label(operation_name, steps),
            "technical_requirements": list(operation.get("technical_requirements", [])),
            "steps": step_output,
        })

    return output


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
    )


def _mapping_dicts(mappings: list[ProjectGroupMapping]) -> list[dict[str, object]]:
    return [asdict(mapping) for mapping in mappings]


def _step_mapping_dicts(mappings: list[ProjectGroupStepMapping]) -> list[dict[str, object]]:
    return [asdict(mapping) for mapping in mappings]


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
    for old_mapping in _json_list(current.step_mappings_json):
        try:
            migrated_steps.append(_resolve_step_mapping(old_mapping, new_index))
        except HTTPException:
            invalidated_steps.append(_step_mapping_snapshot(old_mapping))

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
                    mapping_output_json = '[]',
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
                **values,
            },
        )
    ).scalar_one_or_none()
    if revision is None:
        raise _conflict()
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

    revision = (
        await db.execute(
            text("""
                UPDATE project_group_templates
                SET mappings_json = :mappings_json,
                    mapping_output_json = '[]',
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
    return await _fresh_snapshot(db, project_id)


async def replace_project_group_step_mappings(
    db: AsyncSession,
    project_id: int,
    mappings: list[object],
    expected_revision: int,
    operations: list[object] | None = None,
) -> ProjectTemplateSnapshot:
    current = await get_project_group_template(db, project_id)
    if current is None or int(current.template_revision) != expected_revision:
        raise _conflict()
    index = _path_index(_json_list(current.tree_json))
    resolved: list[ProjectGroupStepMapping] = []
    seen_targets: set[tuple[str, str]] = set()
    statuses: dict[str, set[str]] = {}
    for mapping in mappings:
        server_mapping = _resolve_step_mapping(mapping, index)
        statuses.setdefault(server_mapping.source_step_key, set()).add(server_mapping.status)
        target_key = _canonical_path(server_mapping.template_group_path)
        dedupe_key = (server_mapping.source_step_key, target_key)
        if dedupe_key in seen_targets:
            continue
        seen_targets.add(dedupe_key)
        resolved.append(server_mapping)

    if any(len(step_statuses) > 1 for step_statuses in statuses.values()):
        raise HTTPException(422, "同一工步不能同时确认映射和标记为不依赖模板特征。")

    mapping_output = _build_mapping_output(operations, resolved)
    revision = (
        await db.execute(
            text("""
                UPDATE project_group_templates
                SET step_mappings_json = :step_mappings_json,
                    mapping_output_json = :mapping_output_json,
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
            },
        )
    ).scalar_one_or_none()
    if revision is None:
        raise _conflict()
    return await _fresh_snapshot(db, project_id)
