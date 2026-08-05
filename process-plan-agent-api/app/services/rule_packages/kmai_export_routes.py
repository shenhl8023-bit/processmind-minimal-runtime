"""Route catalog and rule artifacts for KmAI V1 compatibility exports."""

from __future__ import annotations

import re
from typing import Any, Callable

from app.services.rule_packages.contracts import (
    ConditionNode,
    KmaiCompatibilityIssue,
    RulePackageV2,
    ValidationIssue,
)
from app.services.rule_packages.kmai_export_conditions import (
    KMAI_MAX_COMBINATIONS_ENV,
    KMAI_MAX_CONDITION_OBJECTS_ENV,
    StandardFactorExportError,
)
from app.services.rule_packages.kmai_export_context import (
    ArtifactBuildResult,
    ConditionBudget,
    FactorRegistry,
)
from app.services.rule_packages.kmai_export_factors import LegacyFactorAdapterEntry


def _issue(
    code: str,
    message: str,
    path: str = "",
    **details: Any,
) -> KmaiCompatibilityIssue:
    return KmaiCompatibilityIssue(code=code, path=path, message=message, **details)


def _process_stage(phase: str, name: str) -> str:
    text = f"{phase} {name}"
    if any(token in name for token in ("\u9633\u6781\u5316", "\u9540\u94dc", "\u9664\u94dc", "\u6e17\u6c2e", "\u949d\u5316")):
        return "surface_treatment"
    if any(token in text for token in ("\u8c03\u8d28", "\u6b63\u5e38\u5316", "\u6dec\u706b", "\u70ed\u5904\u7406", "\u53bb\u5e94\u529b", "\u56de\u706b")):
        return "heat_treatment"
    if any(token in text for token in ("\u4e13\u9879\u68c0\u67e5", "\u7ec8\u68c0", "\u68c0\u9a8c", "\u68c0\u67e5")):
        return "inspection"
    if any(token in text for token in ("\u653e\u884c", "\u5305\u88c5")):
        return "package"
    if any(token in text for token in ("\u70ed\u540e", "\u7cbe\u52a0\u5de5", "\u78e8", "\u7814", "\u73e9")):
        return "finish"
    if any(token in text for token in ("\u51c6\u5907", "\u4e0b\u6599", "\u5907\u6599")):
        return "prepare"
    if any(token in text for token in ("\u8f85\u52a9", "\u6e05\u6d17", "\u53bb\u6bdb\u523a")):
        return "auxiliary"
    return "rough_machining"


def _fallback_steps(name: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s*[/\uff0f]\s*", name) if part.strip()]
    return parts or [name]


def build_route_catalog(
    package: RulePackageV2,
) -> tuple[dict[str, Any], dict[str, str]]:
    processes: list[dict[str, Any]] = []
    process_keys: dict[str, str] = {}
    relation_requires: dict[str, set[str]] = {}
    relation_after: dict[str, set[str]] = {}
    relation_conflicts: dict[str, set[str]] = {}
    for relation in package.route_rules.process_relations:
        if not relation.enabled:
            continue
        for target_id in relation.target_process_ids:
            if relation.relation_type in {"trigger_after", "order_after", "requires"}:
                relation_after.setdefault(target_id, set()).update(relation.source_process_ids)
            if relation.relation_type == "requires":
                relation_requires.setdefault(target_id, set()).update(relation.source_process_ids)
        if relation.relation_type == "conflicts":
            for source_id in relation.source_process_ids:
                for target_id in relation.target_process_ids:
                    relation_conflicts.setdefault(source_id, set()).add(target_id)
                    relation_conflicts.setdefault(target_id, set()).add(source_id)
    for index, process in enumerate(package.route_catalog.processes, start=1):
        process_key = process.process_id
        process_keys[process.process_id] = process_key
        step_names = [step.name for step in process.steps if step.name] or _fallback_steps(process.display_name)
        processes.append(
            {
                "process_key": process_key,
                "process_id": f"P{index:03d}",
                "process_name": process.display_name,
                "template_group_aliases": [
                    alias.model_dump(mode="json")
                    for alias in process.template_group_aliases
                ],
                "process_type": "main" if process.main else "conditional",
                "stage": _process_stage(process.phase, process.display_name),
                "sequence": process.default_sequence,
                "enabled": True,
                "default_included": process.main,
                "requires_process_keys": sorted(set(process.constraints.requires) | relation_requires.get(process.process_id, set())),
                "must_run_after_process_keys": sorted(set(process.constraints.must_run_after) | relation_after.get(process.process_id, set())),
                "must_run_before_process_keys": sorted(process.constraints.must_run_before),
                "conflicts_with_process_keys": sorted(set(process.constraints.conflicts_with) | relation_conflicts.get(process.process_id, set())),
                "steps": [
                    {
                        "step_key": f"{process_key}_s{step_index:02d}",
                        "step_name": step_name,
                        "step_order": step_index,
                    }
                    for step_index, step_name in enumerate(step_names, start=1)
                ],
            }
        )
    relation_payload = [
        {
            "relation_id": relation.relation_id,
            "relation_type": relation.relation_type,
            "source_match": relation.source_match,
            "source_process_keys": relation.source_process_ids,
            "target_process_keys": relation.target_process_ids,
            "enabled": relation.enabled,
            "note": relation.reason,
        }
        for relation in package.route_rules.process_relations
    ]
    post_stage_bundles = [
        {
            "bundle_id": relation.relation_id,
            "trigger_mode": relation.source_match,
            "trigger_process_keys": relation.source_process_ids,
            "include_process_keys": relation.target_process_ids,
            "must_run_after_process_keys": relation.source_process_ids,
            "enabled": relation.enabled,
            "note": relation.reason,
        }
        for relation in package.route_rules.process_relations
        if relation.enabled and relation.relation_type == "trigger_after"
    ]
    return (
        {
            "schema_version": "1.0",
            "dataset_id": f"processmind_project_{package.manifest.project_id}_route_catalog",
            "dataset_name": f"{package.manifest.package_name} - KmAI \u5de5\u5e8f\u76ee\u5f55",
            "description": "\u7531 ProcessMind V2 route_catalog.json \u81ea\u52a8\u8f6c\u6362\u3002",
            "post_stage_bundles": post_stage_bundles,
            "process_relations": relation_payload,
            "processes": processes,
        },
        process_keys,
    )


def build_route_rules(
    package: RulePackageV2,
    process_keys: dict[str, str],
    registry: FactorRegistry,
    budget: ConditionBudget,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
    *,
    condition_dnf_fn: Callable[..., list[list[dict[str, Any]]]],
    condition_expansion_size_fn: Callable[[ConditionNode], tuple[int, int]],
) -> ArtifactBuildResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    rules: list[dict[str, Any]] = []
    for rule_index, rule in enumerate(package.route_rules.rules):
        path = f"route_rules.rules[{rule_index}]"
        try:
            combination_count, condition_object_count = condition_expansion_size_fn(rule.when)
        except ValueError as exc:
            errors.append(_issue("kmai_condition_unsupported", str(exc), f"{path}.when"))
            continue
        projected_count, projected_condition_object_count = budget.project(
            combination_count,
            condition_object_count,
        )
        if (
            combination_count > budget.max_combinations
            or projected_count > budget.max_combinations
        ):
            errors.append(
                _issue(
                    "kmai_combination_limit_exceeded",
                    (
                        f"\u89c4\u5219 {rule.rule_id} \u7684 all/any \u6761\u4ef6\u5c06\u5c55\u5f00\u4e3a {combination_count} \u4e2a\u7ec4\u5408\uff0c"
                        f"\u7d2f\u8ba1\u7ec4\u5408\u6570\u4e3a {projected_count}\uff0c\u8d85\u8fc7\u4e0a\u9650 {budget.max_combinations}\u3002"
                        f"\u8bf7\u7f29\u5c0f\u6761\u4ef6\u8303\u56f4\u6216\u8c03\u6574 {KMAI_MAX_COMBINATIONS_ENV}\u3002"
                    ),
                    f"{path}.when",
                )
            )
            continue
        if (
            condition_object_count > budget.max_condition_objects
            or projected_condition_object_count > budget.max_condition_objects
        ):
            errors.append(
                _issue(
                    "kmai_condition_object_limit_exceeded",
                    (
                        f"\u89c4\u5219 {rule.rule_id} \u7684 all/any \u6761\u4ef6\u5c55\u5f00\u540e\u5305\u542b {condition_object_count} \u4e2a\u6761\u4ef6\u5bf9\u8c61\uff0c"
                        f"\u7d2f\u8ba1\u6761\u4ef6\u5bf9\u8c61\u6570\u4e3a {projected_condition_object_count}\uff0c"
                        f"\u8d85\u8fc7\u4e0a\u9650 {budget.max_condition_objects}\u3002"
                        f"\u8bf7\u7f29\u5c0f\u6761\u4ef6\u8303\u56f4\u6216\u8c03\u6574 {KMAI_MAX_CONDITION_OBJECTS_ENV}\u3002"
                    ),
                    f"{path}.when",
                )
            )
            continue
        try:
            clauses = condition_dnf_fn(
                package,
                rule.when,
                registry,
                warnings,
                f"{path}.when",
                legacy_adapters,
            )
        except StandardFactorExportError as exc:
            errors.append(_issue(exc.code, str(exc), f"{path}.when"))
            continue
        except ValueError as exc:
            errors.append(_issue("kmai_condition_unsupported", str(exc), f"{path}.when"))
            continue
        budget.record(clauses)
        include_keys = [process_keys[item] for item in rule.then.include_process_ids if item in process_keys]
        exclude_keys = [process_keys[item] for item in rule.then.exclude_process_ids if item in process_keys]
        missing_ids = [
            item
            for item in (*rule.then.include_process_ids, *rule.then.exclude_process_ids)
            if item not in process_keys
        ]
        if missing_ids:
            errors.append(
                _issue(
                    "kmai_process_reference_missing",
                    f"\u89c4\u5219 {rule.rule_id} \u5f15\u7528\u4e86\u4e0d\u5b58\u5728\u7684\u5de5\u5e8f\uff1a{', '.join(missing_ids)}",
                    f"{path}.then",
                )
            )
            continue
        for clause_index, clause in enumerate(clauses, start=1):
            suffix = f".{clause_index}" if len(clauses) > 1 else ""
            rules.append(
                {
                    "rule_id": f"{rule.rule_id}{suffix}",
                    "enabled": rule.enabled,
                    "priority": rule.priority,
                    "when": {"all": clause},
                    "then": {
                        "include_process_keys": include_keys,
                        "exclude_process_keys": exclude_keys,
                    },
                    "confidence": "high",
                    "note": rule.then.reason,
                }
            )
    return ArtifactBuildResult(
        payload={
            "schema_version": "1.0",
            "dataset_id": f"processmind_project_{package.manifest.project_id}_route_rules",
            "dataset_name": f"{package.manifest.package_name} - KmAI \u8def\u7ebf\u89c4\u5219",
            "description": "\u7531 ProcessMind V2 route_rules.json \u81ea\u52a8\u8f6c\u6362\u3002",
            "rules": rules,
        },
        errors=errors,
        warnings=warnings,
    )
