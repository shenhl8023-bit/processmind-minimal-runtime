"""Cross-reference, dependency, conflict, and executable test validation."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from app.services.rule_packages.contracts import (
    RulePackageV2,
    RulePackageValidationReport,
    TestCaseResult,
    ValidationIssue,
)
from app.services.rule_packages.expression_engine import iter_condition_fields
from app.services.rule_packages.input_validation import validate_inputs
from app.services.rule_packages.planner import RoutePlanningError, plan_route


def _duplicates(values: list[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _dependency_cycle(processes, relations=()) -> list[str]:
    process_ids = {process.process_id for process in processes}
    edges: dict[str, set[str]] = {process_id: set() for process_id in process_ids}
    for process in processes:
        for before_id in [*process.constraints.requires, *process.constraints.must_run_after]:
            if before_id in process_ids:
                edges[before_id].add(process.process_id)
        for after_id in process.constraints.must_run_before:
            if after_id in process_ids:
                edges[process.process_id].add(after_id)
    for relation in relations:
        if not relation.enabled or relation.relation_type == "conflicts":
            continue
        for source_id in relation.source_process_ids:
            for target_id in relation.target_process_ids:
                if source_id in process_ids and target_id in process_ids:
                    edges[source_id].add(target_id)

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(process_id: str) -> list[str]:
        if process_id in visiting:
            start = stack.index(process_id)
            return [*stack[start:], process_id]
        if process_id in visited:
            return []
        visiting.add(process_id)
        stack.append(process_id)
        for next_id in sorted(edges[process_id]):
            cycle = visit(next_id)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(process_id)
        visited.add(process_id)
        return []

    for process_id in sorted(process_ids):
        cycle = visit(process_id)
        if cycle:
            return cycle
    return []


def validate_rule_package(package: RulePackageV2) -> RulePackageValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    tests: list[TestCaseResult] = []

    def error(code: str, message: str, path: str = "") -> None:
        errors.append(ValidationIssue(code=code, path=path, message=message))

    def warning(code: str, message: str, path: str = "") -> None:
        warnings.append(ValidationIssue(code=code, path=path, message=message))

    field_keys = [field.key for field in package.input_schema.fields]
    process_ids = [process.process_id for process in package.route_catalog.processes]
    rule_ids = [rule.rule_id for rule in package.route_rules.rules]
    relation_ids = [relation.relation_id for relation in package.route_rules.process_relations]
    case_ids = [case.case_id for case in package.test_cases]
    field_set = set(field_keys)
    process_set = set(process_ids)
    process_map = {process.process_id: process for process in package.route_catalog.processes}

    for field_key in sorted(_duplicates(field_keys)):
        error("duplicate_field", f"输入字段重复：{field_key}", "input_schema.fields")
    for process_id in sorted(_duplicates(process_ids)):
        error("duplicate_process", f"工序 ID 重复：{process_id}", "route_catalog.processes")
    for rule_id in sorted(_duplicates(rule_ids)):
        error("duplicate_rule", f"规则 ID 重复：{rule_id}", "route_rules.rules")
    for relation_id in sorted(_duplicates(relation_ids)):
        error("duplicate_process_relation", f"工序关系 ID 重复：{relation_id}", "route_rules.process_relations")
    for case_id in sorted(_duplicates(case_ids)):
        error("duplicate_test_case", f"测试用例 ID 重复：{case_id}", "test_cases")

    if not package.input_schema.fields:
        error("empty_input_schema", "规则包至少需要一个输入字段", "input_schema.fields")
    if not package.route_catalog.processes:
        error("empty_process_catalog", "规则包至少需要一个工序", "route_catalog.processes")
    elif not any(process.main for process in package.route_catalog.processes):
        error("missing_main_process", "规则包至少需要一个主线工序", "route_catalog.processes")
    if package.manifest.project_id != int(package.manifest.scope.key):
        error("scope_project_mismatch", "manifest.scope.key 必须与 project_id 一致", "manifest.scope.key")

    for index, process in enumerate(package.route_catalog.processes):
        path = f"route_catalog.processes[{index}]"
        relation_ids = [
            *process.constraints.requires,
            *process.constraints.must_run_after,
            *process.constraints.must_run_before,
            *process.constraints.conflicts_with,
        ]
        for referenced_id in relation_ids:
            if referenced_id not in process_set:
                error("unknown_process_reference", f"工序 {process.process_id} 引用了不存在的工序 {referenced_id}", path)
            if referenced_id == process.process_id:
                error("self_process_reference", f"工序 {process.process_id} 不能引用自身", path)
        step_ids = [step.step_id for step in process.steps]
        for step_id in sorted(_duplicates(step_ids)):
            error("duplicate_step", f"工序 {process.process_id} 的工步 ID 重复：{step_id}", f"{path}.steps")

    cycle = _dependency_cycle(package.route_catalog.processes, package.route_rules.process_relations)
    if cycle:
        error("dependency_cycle", f"工序依赖存在环：{' -> '.join(cycle)}", "route_catalog.processes")

    opposing_actions: dict[tuple[int, str], dict[str, list[str]]] = defaultdict(lambda: {"include": [], "exclude": []})
    for index, rule in enumerate(package.route_rules.rules):
        path = f"route_rules.rules[{index}]"
        if rule.source == "user_confirmed":
            if not rule.source_segment_id or not rule.source_text:
                error("missing_user_rule_audit", f"用户规则 {rule.rule_id} 缺少来源工序或原始条件", path)
            if not rule.confirmed_by or not rule.confirmed_at:
                error("missing_user_rule_confirmation", f"用户规则 {rule.rule_id} 缺少确认人或确认时间", path)
        for field_name in iter_condition_fields(rule.when):
            if field_name not in field_set:
                error("unknown_input_field", f"规则 {rule.rule_id} 引用了未定义字段 {field_name}", f"{path}.when")
        for process_id in rule.then.include_process_ids:
            if process_id not in process_set:
                error("unknown_process_action", f"规则 {rule.rule_id} 引用了不存在的工序 {process_id}", f"{path}.then")
            if rule.enabled:
                opposing_actions[(rule.priority, process_id)]["include"].append(rule.rule_id)
        for process_id in rule.then.exclude_process_ids:
            if process_id not in process_set:
                error("unknown_process_action", f"规则 {rule.rule_id} 引用了不存在的工序 {process_id}", f"{path}.then")
            elif process_map[process_id].main:
                error("exclude_main_process", f"规则 {rule.rule_id} 不能排除主线工序 {process_id}", f"{path}.then")
            if rule.enabled:
                opposing_actions[(rule.priority, process_id)]["exclude"].append(rule.rule_id)

    for index, relation in enumerate(package.route_rules.process_relations):
        path = f"route_rules.process_relations[{index}]"
        if relation.source == "user_confirmed":
            if not relation.source_segment_id or not relation.source_text:
                error("missing_relation_audit", f"用户工序关系 {relation.relation_id} 缺少来源工序或原始条件", path)
            if not relation.confirmed_by or not relation.confirmed_at:
                error("missing_relation_confirmation", f"用户工序关系 {relation.relation_id} 缺少确认人或确认时间", path)
        for process_id in [*relation.source_process_ids, *relation.target_process_ids]:
            if process_id not in process_set:
                error("unknown_relation_process", f"工序关系 {relation.relation_id} 引用了不存在的工序 {process_id}", path)
        if relation.relation_type == "conflicts":
            for source_id in relation.source_process_ids:
                for target_id in relation.target_process_ids:
                    if source_id in process_map and target_id in process_map and process_map[source_id].main and process_map[target_id].main:
                        error("main_process_relation_conflict", f"两个主线工序不能互斥：{source_id} / {target_id}", path)
        elif relation.relation_type == "trigger_after":
            for target_id in relation.target_process_ids:
                if target_id in process_map and process_map[target_id].main:
                    warning("redundant_main_trigger", f"主线工序 {target_id} 无需再由工序关系触发", path)

    for index, case in enumerate(package.test_cases):
        for issue in validate_inputs(package.input_schema, case.input):
            error(
                "invalid_test_input",
                f"测试用例 {case.case_id} 输入无效：{issue.message}",
                f"test_cases[{index}].{issue.path}",
            )
        overlap = set(case.expect.included_process_ids) & set(case.expect.excluded_process_ids)
        if overlap:
            error(
                "test_expectation_conflict",
                f"测试用例 {case.case_id} 同时期望包含和排除：{', '.join(sorted(overlap))}",
                f"test_cases[{index}].expect",
            )
        for process_id in [*case.expect.included_process_ids, *case.expect.excluded_process_ids]:
            if process_id not in process_set:
                error(
                    "unknown_test_process",
                    f"测试用例 {case.case_id} 引用了不存在的工序 {process_id}",
                    f"test_cases[{index}].expect",
                )

    for (priority, process_id), actions in opposing_actions.items():
        if actions["include"] and actions["exclude"]:
            error(
                "same_priority_action_conflict",
                f"优先级 {priority} 对工序 {process_id} 同时存在 include 和 exclude 规则",
                "route_rules.rules",
            )

    user_rules = [rule for rule in package.route_rules.rules if rule.enabled and rule.source == "user_confirmed"]
    system_rules = [rule for rule in package.route_rules.rules if rule.enabled and rule.source == "system_static"]
    for user_rule in user_rules:
        user_condition = json.dumps(user_rule.when.model_dump(mode="json", by_alias=True), sort_keys=True, ensure_ascii=False)
        for system_rule in system_rules:
            system_condition = json.dumps(system_rule.when.model_dump(mode="json", by_alias=True), sort_keys=True, ensure_ascii=False)
            if user_condition != system_condition:
                continue
            conflicts = (
                set(user_rule.then.include_process_ids) & set(system_rule.then.exclude_process_ids)
            ) | (
                set(user_rule.then.exclude_process_ids) & set(system_rule.then.include_process_ids)
            )
            if conflicts and user_rule.priority > system_rule.priority:
                warning(
                    "user_rule_overrides_system",
                    f"用户规则 {user_rule.rule_id} 将覆盖系统规则 {system_rule.rule_id}：{', '.join(sorted(conflicts))}",
                    "route_rules.rules",
                )

    if not package.test_cases:
        warning("missing_test_cases", "规则包尚未定义可执行测试用例，后续不应允许发布", "test_cases")

    if not errors:
        for case in package.test_cases:
            try:
                plan = plan_route(package, case.input)
                selected = set(plan.selected_process_ids)
                missing = sorted(set(case.expect.included_process_ids) - selected)
                unexpected = sorted(set(case.expect.excluded_process_ids) & selected)
                if missing or unexpected:
                    details = []
                    if missing:
                        details.append(f"缺少预期工序：{', '.join(missing)}")
                    if unexpected:
                        details.append(f"包含应排除工序：{', '.join(unexpected)}")
                    tests.append(TestCaseResult(case_id=case.case_id, passed=False, message="；".join(details)))
                    error("test_case_failed", f"测试用例 {case.case_id} 失败：{'；'.join(details)}", "test_cases")
                else:
                    tests.append(TestCaseResult(case_id=case.case_id, passed=True))
            except RoutePlanningError as exc:
                tests.append(TestCaseResult(case_id=case.case_id, passed=False, message=str(exc)))
                error("test_case_planning_failed", f"测试用例 {case.case_id} 无法规划：{exc}", "test_cases")

    return RulePackageValidationReport(valid=not errors, errors=errors, warnings=warnings, test_results=tests)
