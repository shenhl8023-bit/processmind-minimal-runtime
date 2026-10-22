from __future__ import annotations

from dataclasses import dataclass, field
import unicodedata
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DocumentOperationDetail
from app.services.process_tree_builder import build_superset_process_tree
from app.services.project_group_templates import get_project_group_template, serialize_project_group_template
from app.services.rule_packages.contracts import RulePackageV2


@dataclass(frozen=True)
class TemplateMappingBlocker:
    code: str
    message: str
    process_id: str = ""
    process_name: str = ""
    severity: str = "blocking"
    required_by: list[str] = field(default_factory=list)
    required_by_labels: list[str] = field(default_factory=list)


def _alias_operation_ids(aliases) -> set[int]:
    result: set[int] = set()
    for alias in aliases or []:
        try:
            result.add(int(alias.source_operation_id))
        except (TypeError, ValueError, AttributeError):
            continue
    return result


def _source_operation_ids(process) -> set[int]:
    result: set[int] = set()
    for operation_id in getattr(process, "source_operation_ids", []) or []:
        try:
            parsed = int(operation_id)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            result.add(parsed)
    return result


async def _load_source_step_items(db: AsyncSession, project_id: int) -> dict[int, list[str]]:
    # Rebuild only the deterministic source identities; publication never calls a model.
    details = (await db.execute(
        select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == project_id)
        .order_by(DocumentOperationDetail.document_id.asc(), DocumentOperationDetail.operation_seq.asc(),
                  DocumentOperationDetail.page_no.asc(), DocumentOperationDetail.id.asc())
    )).scalars().all()
    sources = build_superset_process_tree(operations=[], detail_rows=details, sample_count=0)
    return {int(source['id']): [*list(source.get('step_items') or []),
                               *list(source.get('attached_step_items') or [])] for source in sources}


async def validate_rule_package_template_mapping(
    db: AsyncSession,
    package: RulePackageV2,
) -> list[TemplateMappingBlocker]:
    template_row = await get_project_group_template(db, package.manifest.project_id)
    if template_row is None:
        return [TemplateMappingBlocker(
            code="group_template_missing",
            message="请先完成分组模板映射。",
        )]

    template = serialize_project_group_template(template_row)
    def path_key(path):
        return tuple(unicodedata.normalize("NFC", str(part)).strip() for part in path)

    nodes = {}

    def visit(tree):
        for node in tree:
            nodes[path_key(node.get("path", []))] = node
            visit(node.get("children", []))

    visit(template.tree)
    required_paths = {
        path_key(node.get("path", [])): node
        for node in nodes.values()
        if not node.get("children") and node.get("feature_selections")
    }
    if not required_paths:
        return [TemplateMappingBlocker(
            code="group_template_mapping_missing",
            message="分组模板中没有包含特征的叶子分组，无法建立工艺映射。",
        )]
    covered_paths = set()
    processes = package.route_catalog.processes
    operation_ids = set().union(*(
        _source_operation_ids(process) | _alias_operation_ids(process.template_group_aliases)
        for process in processes
    ))
    for mapping in template.mappings:
        mapping_path = path_key(mapping.template_group_path)
        node = required_paths.get(mapping_path)
        mapped_features = set(getattr(mapping, "feature_selections", []) or [])
        if (mapping.source_operation_id in operation_ids and node
                and mapped_features.intersection(node.get("feature_selections", []))):
            covered_paths.add(mapping_path)

    source_steps = await _load_source_step_items(db, package.manifest.project_id) if template.step_mappings else {}
    processes_by_id = {process.process_id: process for process in processes}
    mapped_steps = {
        (process.get("process_id"), step.get("step_id")): step
        for process in getattr(template, "mapping_output", [])
        if process.get("process_type") != "辅助工序"
        for step in process.get("steps", [])
    }
    for mapping in template.step_mappings:
        if mapping.status != "confirmed" or mapping.source_operation_id not in operation_ids:
            continue
        node = nodes.get(path_key(mapping.template_group_path))
        if not node or node.get("children") or not mapping.candidate_features:
            continue
        if not set(mapping.candidate_features).issubset(set(node.get("feature_selections", []))):
            continue
        steps = source_steps.get(mapping.source_operation_id, [])
        position = mapping.source_step_order - 1
        if position < 0 or position >= len(steps):
            continue
        if unicodedata.normalize('NFC', steps[position]).strip() != unicodedata.normalize('NFC', mapping.source_step_name).strip():
            continue
        final_targets = getattr(mapping, "final_targets", [])
        if final_targets:
            valid_target = False
            for target in final_targets:
                process = processes_by_id.get(target.get("process_id"))
                if process is None or mapping.source_operation_id not in _source_operation_ids(process):
                    continue
                if target.get("step_id") not in {step.step_id for step in process.steps}:
                    continue
                step = mapped_steps.get((process.process_id, target.get("step_id")), {})
                path = "/".join(path_key(mapping.template_group_path))
                candidates = step.get("candidates", {}).get(path, [])
                if set(mapping.candidate_features).issubset(set(candidates)):
                    valid_target = True
                    break
            if not valid_target:
                continue
        covered_paths.add(path_key(mapping.template_group_path))

    missing_paths = [path for path in required_paths if path not in covered_paths]
    if not missing_paths:
        return []
    missing_labels = [" / ".join(map(str, required_paths[path].get("path", []))) for path in missing_paths]
    return [TemplateMappingBlocker(
        code="group_template_mapping_missing",
        message="以下模板分组尚未关联任何有效特征映射，请至少为每个有特征的分组关联一个特征：" + "、".join(missing_labels),
    )]
