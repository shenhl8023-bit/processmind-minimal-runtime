"""Project-owned group-template persistence with optimistic revisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Project, ProjectGroupTemplate
from app.services.group_template_xml import GroupTemplateParseResult, normalize_name


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
    template_revision: int
    group_count: int
    feature_selection_count: int
    created_at: Any = None
    updated_at: Any = None


@dataclass
class TemplateCommitResult(ProjectTemplateSnapshot):
    kept_source_operation_ids: list[int] = field(default_factory=list)
    invalidated: list[ProjectGroupMapping] = field(default_factory=list)


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


def _mapping_dicts(mappings: list[ProjectGroupMapping]) -> list[dict[str, object]]:
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
                        validation_json, mappings_json, template_revision, group_count,
                        feature_selection_count
                    )
                    SELECT :project_id, :original_filename, :source_encoding, :part_filename,
                           :content_hash, :feature_dictionary_version, :source_xml, :tree_json,
                           :validation_json, '[]', 1, :group_count, :feature_selection_count
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
