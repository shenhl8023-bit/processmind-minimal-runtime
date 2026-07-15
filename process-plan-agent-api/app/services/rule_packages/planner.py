"""Deterministic route planning from a validated rule package V2."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any

from app.services.rule_packages.contracts import (
    PlannedRouteStep,
    RoutePlan,
    RuleExecutionTrace,
    RulePackageV2,
)
from app.services.rule_packages.expression_engine import evaluate_condition


class RoutePlanningError(ValueError):
    pass


@dataclass(frozen=True)
class _Decision:
    action: str
    priority: int
    rule_id: str
    reason: str


def _apply_decision(decisions: dict[str, _Decision], process_id: str, decision: _Decision) -> None:
    existing = decisions.get(process_id)
    if existing is None or decision.priority > existing.priority:
        decisions[process_id] = decision
        return
    if decision.priority == existing.priority and decision.action != existing.action:
        raise RoutePlanningError(
            f"同优先级规则对工序 {process_id} 产生冲突：{existing.rule_id} / {decision.rule_id}"
        )


def _expand_required_processes(
    selected: set[str],
    decisions: dict[str, _Decision],
    process_map: dict[str, Any],
    reasons: dict[str, str],
) -> None:
    pending = list(selected)
    while pending:
        process_id = pending.pop()
        process = process_map[process_id]
        for required_id in process.constraints.requires:
            required_decision = decisions.get(required_id)
            if required_decision and required_decision.action == "exclude":
                raise RoutePlanningError(
                    f"工序 {process_id} 依赖 {required_id}，但后者被规则 {required_decision.rule_id} 排除"
                )
            if required_id not in selected:
                selected.add(required_id)
                reasons[required_id] = f"工序 {process_id} 的前置依赖"
                pending.append(required_id)


def _assert_no_selected_conflicts(selected: set[str], process_map: dict[str, Any]) -> None:
    for process_id in sorted(selected):
        conflicts = selected & set(process_map[process_id].constraints.conflicts_with)
        if conflicts:
            other = sorted(conflicts)[0]
            raise RoutePlanningError(f"工序 {process_id} 与 {other} 不能同时进入路线")


def _topological_process_order(selected: set[str], process_map: dict[str, Any]) -> list[str]:
    edges: dict[str, set[str]] = {process_id: set() for process_id in selected}
    indegree = {process_id: 0 for process_id in selected}

    def add_edge(before: str, after: str) -> None:
        if before == after or before not in selected or after not in selected:
            return
        if after not in edges[before]:
            edges[before].add(after)
            indegree[after] += 1

    for process_id in selected:
        constraints = process_map[process_id].constraints
        for required_id in constraints.requires:
            add_edge(required_id, process_id)
        for before_id in constraints.must_run_after:
            add_edge(before_id, process_id)
        for after_id in constraints.must_run_before:
            add_edge(process_id, after_id)

    ready: list[tuple[int, str]] = []
    for process_id, degree in indegree.items():
        if degree == 0:
            process = process_map[process_id]
            heapq.heappush(ready, (process.default_sequence, process_id))

    ordered: list[str] = []
    while ready:
        _, process_id = heapq.heappop(ready)
        ordered.append(process_id)
        for after_id in sorted(edges[process_id]):
            indegree[after_id] -= 1
            if indegree[after_id] == 0:
                process = process_map[after_id]
                heapq.heappush(ready, (process.default_sequence, after_id))

    if len(ordered) != len(selected):
        remaining = sorted(process_id for process_id, degree in indegree.items() if degree > 0)
        raise RoutePlanningError(f"工序依赖存在环：{', '.join(remaining)}")
    return ordered


def plan_route(package: RulePackageV2, inputs: dict[str, Any]) -> RoutePlan:
    process_map = {process.process_id: process for process in package.route_catalog.processes}
    selected = {process.process_id for process in package.route_catalog.processes if process.main}
    reasons = {process_id: "主线工序" for process_id in selected}
    decisions: dict[str, _Decision] = {}
    traces: list[RuleExecutionTrace] = []

    for rule in sorted(package.route_rules.rules, key=lambda item: (-item.priority, item.rule_id)):
        if not rule.enabled:
            continue
        condition_trace = evaluate_condition(rule.when, inputs)
        traces.append(
            RuleExecutionTrace(
                rule_id=rule.rule_id,
                priority=rule.priority,
                matched=condition_trace.matched,
                condition=condition_trace,
            )
        )
        if not condition_trace.matched:
            continue
        reason = rule.then.reason or f"规则 {rule.rule_id} 命中"
        for process_id in rule.then.include_process_ids:
            _apply_decision(decisions, process_id, _Decision("include", rule.priority, rule.rule_id, reason))
        for process_id in rule.then.exclude_process_ids:
            _apply_decision(decisions, process_id, _Decision("exclude", rule.priority, rule.rule_id, reason))

    for process_id, decision in decisions.items():
        if decision.action == "include":
            selected.add(process_id)
            reasons[process_id] = decision.reason
        elif not process_map[process_id].main:
            selected.discard(process_id)
            reasons.pop(process_id, None)

    _expand_required_processes(selected, decisions, process_map, reasons)
    _assert_no_selected_conflicts(selected, process_map)
    ordered_ids = _topological_process_order(selected, process_map)

    steps = []
    for index, process_id in enumerate(ordered_ids, start=1):
        process = process_map[process_id]
        steps.append(
            PlannedRouteStep(
                process_id=process_id,
                sequence=index,
                name=process.display_name,
                op_type="MAIN" if process.main else "BRANCH",
                reason=reasons.get(process_id, "规则包依赖命中"),
                process_steps=[step.name for step in process.steps],
            )
        )

    return RoutePlan(steps=steps, traces=traces, selected_process_ids=ordered_ids)
