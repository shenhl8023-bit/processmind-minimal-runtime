"""Project a validated authoring snapshot into executable, mapped CAD tables."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.demo_tables import DemoTableError, _join, _negate, validate_demo_tables


PUBLICATION_COMPILER_VERSION = "demo-three-table/5"
PROJECTED_COMPILER_VERSIONS = frozenset({"demo-three-table/3", "demo-three-table/4", PUBLICATION_COMPILER_VERSION})


def _rewrite(condition, removed_processes):
    if type(condition) is bool:
        return condition
    for branch in ("all", "any"):
        if branch in condition:
            return _join(branch, [_rewrite(child, removed_processes) for child in condition[branch]])
    if "not" in condition:
        return _negate(_rewrite(condition["not"], removed_processes))
    if "some" in condition:
        child = _rewrite(condition["some"], removed_processes)
        # some(true) still requires an input row; only false can collapse.
        return False if child is False else {"some": child}
    if condition["field"] == "selected_processes" and condition["value"] in removed_processes:
        return False
    return deepcopy(condition)


def _condition_fields(value):
    if isinstance(value, dict):
        if isinstance(value.get("field"), str) and value["field"] != "selected_processes":
            yield value["field"]
        for child in value.values():
            yield from _condition_fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from _condition_fields(child)


def project_publication_tables(tables: dict, package: RulePackageV2) -> tuple[dict, dict]:
    """Keep mapped machining, preserve auxiliaries, and close over live dependencies.

    The caller compiles and validates the full saved route first. This function
    never changes authoring identities or invents feature aliases or input data.
    """
    validate_demo_tables(tables)
    output = deepcopy(tables)
    route, excluded_steps, excluded_processes = [], [], []
    for process in output["full_route_table"]:
        if process["process_type"] == "加工工序":
            mapped = []
            for step in process["steps"]:
                if any(step["candidates"].values()):
                    mapped.append(step)
                else:
                    excluded_steps.append({"process_id": process["process_id"], "process_name": process["process_name"],
                                           "step_id": step["step_id"], "step_name": step["step_name"],
                                           "reason": "加工工步没有有效特征映射"})
            process["steps"] = mapped
            if not mapped:
                excluded_processes.append({"process_id": process["process_id"], "process_name": process["process_name"],
                                           "reason": "加工工序没有可导出的已映射工步"})
                continue
        route.append(process)
    if not route:
        raise DemoTableError([{"code": "empty_export_route", "path": "full_route_table",
                               "message": "没有可交付的工序，请先为加工工步保存有效特征映射；辅助工序按其规则保留。"}])
    output["full_route_table"] = route
    retained = {process["process_id"] for process in route}
    removed = {process["process_id"] for process in tables["full_route_table"]} - retained
    retained_nodes = retained | {step["step_id"] for process in route for step in process["steps"]}
    machining = {process["process_id"] for process in route if process["process_type"] == "加工工序"}
    catalog = {process.process_id: process for process in package.route_catalog.processes}
    prerequisites = defaultdict(list)
    issues = []

    def require(sources, targets):
        targets = [target for target in targets if target in retained]
        if not targets:
            return
        available = [source for source in sources if source in retained]
        missing = [source for source in sources if source not in retained]
        if missing:
            for target in targets:
                issues.append({"code": "unmapped_required_process", "path": f"route_catalog.{target}.constraints",
                               "process_id": target, "process_name": catalog[target].display_name,
                               "prerequisite_process_ids": missing,
                               "prerequisite_process_names": [catalog[source].display_name for source in missing],
                               "message": f"工序“{catalog[target].display_name}”需要的前置加工工序没有有效映射，无法交付；请补充前置工序映射或修正规则。"})
            return
        gate = _join("all", [{"field": "selected_processes", "op": "contains", "value": source}
                             for source in available])
        for target in targets:
            prerequisites[target].append(gate)

    for process in package.route_catalog.processes:
        if process.constraints.requires:
            require(process.constraints.requires, [process.process_id])
    relations = [relation for relation in package.route_rules.process_relations if relation.enabled]
    relations.extend(relation for configuration in package.route_rules.process_configurations if configuration.enabled
                     for relation in configuration.relations)
    for relation in relations:
        if relation.relation_type == "requires":
            # requires means every prerequisite in the planner and editor.
            # source_match only changes trigger semantics.
            require(relation.source_process_ids, relation.target_process_ids)
    if issues:
        raise DemoTableError(issues)

    rules = []
    for rule in output["rule_table"]:
        target = rule["target"]
        if target not in retained_nodes:
            continue
        condition = True if rule.get("required") else _rewrite(rule["when"], removed)
        gates = prerequisites.get(target, [])
        # KMAI keeps required processes even when every step fails to bind.
        # when:true retains priority while allowing the usual empty-step pruning.
        if target in machining or gates or not rule.get("required"):
            rule = {"target": target, "when": _join("all", [condition, *gates])}
        rules.append(rule)

    # Propagate proven-false process conditions through the acyclic dependency
    # graph. Unknown input conditions stay conditional; do not guess their value.
    process_rules = {rule["target"]: rule for rule in rules if rule["target"] in retained}
    impossible = retained - process_rules.keys()
    while True:
        disabled = {target for target, rule in process_rules.items()
                    if not rule.get("required") and _rewrite(rule["when"], impossible) is False}
        if disabled <= impossible:
            break
        impossible.update(disabled)
    for rule in rules:
        if "when" in rule:
            rule["when"] = _rewrite(rule["when"], impossible)
    if retained <= impossible:
        raise DemoTableError([{"code": "empty_export_route", "path": "rule_table",
                               "message": "映射筛选后，所有工序的启用条件都不可能满足，请补充映射或修正规则。"}])
    output["rule_table"] = rules
    formerly_used = set(_condition_fields(tables["rule_table"]))
    still_used = set(_condition_fields(rules))
    unused = formerly_used - still_used
    removed_factors = [factor["key"] for factor in output["factor_table"] if factor["key"] in unused]
    output["factor_table"] = [factor for factor in output["factor_table"] if factor["key"] not in unused]
    validate_demo_tables(output)
    report = {
        "original_process_count": len(tables["full_route_table"]), "exported_process_count": len(route),
        "original_step_count": sum(len(process["steps"]) for process in tables["full_route_table"]),
        "exported_step_count": sum(len(process["steps"]) for process in route),
        "excluded_processes": excluded_processes, "excluded_steps": excluded_steps,
        "removed_factor_keys": removed_factors,
    }
    return output, report
