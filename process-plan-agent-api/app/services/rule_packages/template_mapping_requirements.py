from __future__ import annotations

from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession

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


def _referenced_process_ids(package: RulePackageV2) -> set[str]:
    selected: set[str] = set()
    for process in package.route_catalog.processes:
        if process.main:
            selected.add(process.process_id)
    for rule in package.route_rules.rules:
        if not rule.enabled:
            continue
        selected.update(rule.then.include_process_ids)
        selected.update(rule.then.exclude_process_ids)
    for relation in package.route_rules.process_relations or []:
        if not relation.enabled:
            continue
        selected.update(relation.source_process_ids)
        selected.update(relation.target_process_ids)
    return selected


def _required_by(package: RulePackageV2) -> dict[str, tuple[list[str], list[str]]]:
    reasons: dict[str, tuple[list[str], list[str]]] = {}

    def add(process_id: str, code: str, label: str) -> None:
        codes, labels = reasons.setdefault(process_id, ([], []))
        if code not in codes:
            codes.append(code)
        if label not in labels:
            labels.append(label)

    for process in package.route_catalog.processes:
        if process.main:
            add(process.process_id, "mainline", "主线工序")
    for rule in package.route_rules.rules:
        if not rule.enabled:
            continue
        for process_id in rule.then.include_process_ids:
            add(process_id, "rule_include", "规则包含引用")
        for process_id in rule.then.exclude_process_ids:
            add(process_id, "rule_exclude", "规则排除引用")
    for relation in package.route_rules.process_relations or []:
        if not relation.enabled:
            continue
        for process_id in relation.source_process_ids:
            add(process_id, "relation_source", "工序关系来源")
        for process_id in relation.target_process_ids:
            add(process_id, "relation_target", "工序关系目标")
    return reasons


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
    if not template.mappings:
        return [TemplateMappingBlocker(
            code="group_template_mapping_missing",
            message="请先完成分组模板映射。",
        )]

    mapped_operation_ids = {mapping.source_operation_id for mapping in template.mappings}
    blockers: list[TemplateMappingBlocker] = []
    referenced_process_ids = _referenced_process_ids(package)
    required_by = _required_by(package)
    for process in package.route_catalog.processes:
        aliases = _alias_operation_ids(process.template_group_aliases)
        if process.process_id not in referenced_process_ids:
            continue
        if aliases and aliases & mapped_operation_ids:
            continue
        reason_codes, reason_labels = required_by.get(process.process_id, ([], []))
        blockers.append(TemplateMappingBlocker(
            code="group_template_mapping_missing",
            message="请先完成分组模板映射。",
            process_id=process.process_id,
            process_name=process.display_name,
            required_by=reason_codes,
            required_by_labels=reason_labels,
        ))
    return blockers
