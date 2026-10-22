"""Deterministic adapter for the three public tables consumed by the CAD Demo.

V2 remains the authoring model.  This module is the publication boundary: it
never asks a model to invent bindings and never recovers node identity by name.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math
import re
from typing import Any

from app.services.rule_packages.contracts import ConditionNode, RulePackageV2
from app.services.rule_packages.expression_engine import evaluate_condition


class DemoTableError(ValueError):
    """A publication failure with locations suitable for the existing precheck."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("；".join(issue["message"] for issue in issues))


_SOURCE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)*\Z")
_TYPES = {"bool", "int", "number", "string", "enum", "multi_enum"}
_OPS = {"eq", "neq", "in", "contains", "exists", "gt", "gte", "lt", "lte"}
_PROCESS_KEYS = {"process_name", "process_type", "precision", "steps", "process_id"}
_STEP_KEYS = {"step_name", "candidates", "step_id"}
_MACHINING_PRECISIONS = {"粗加工", "半精加工", "精加工"}


def _issue(issues, code, path, message):
    issues.append({"code": code, "path": path, "message": message})


def _fail(code, path, message):
    raise DemoTableError([{"code": code, "path": path, "message": message}])


def _exact_keys(value, required, optional, path, issues):
    if not isinstance(value, dict):
        _issue(issues, "invalid_object", path, f"{path} 必须是对象")
        return False
    if set(value) - required - optional:
        _issue(issues, "unexpected_fields", path, f"{path} 包含协议之外的字段：{', '.join(sorted(set(value) - required - optional))}")
    if required - set(value):
        _issue(issues, "missing_fields", path, f"{path} 缺少字段：{', '.join(sorted(required - set(value)))}")
        return False
    return True


def _value_ok(kind, value):
    if not isinstance(kind, str):
        return False
    if value is None:
        return True
    if kind == "bool":
        return type(value) is bool
    if kind == "int":
        return type(value) is int
    if kind == "number":
        return type(value) in (int, float) and math.isfinite(value)
    if kind in {"string", "enum"}:
        return isinstance(value, str)
    if kind == "multi_enum":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return False


def _validate_condition(c, factors, processes, path, issues):
    if type(c) is bool:
        return set()
    if not isinstance(c, dict):
        _issue(issues, "invalid_condition", path, f"{path} 条件必须是布尔值或对象")
        return set()
    branches = set(c) & {"all", "any", "not", "some"}
    if branches:
        if len(c) != 1 or len(branches) != 1:
            _issue(issues, "invalid_condition", path, f"{path} 条件只能包含一个组合运算符")
            return set()
        branch = next(iter(branches))
        if branch in {"all", "any"}:
            if not isinstance(c[branch], list) or not c[branch]:
                _issue(issues, "invalid_condition", path, f"{branch} 必须是非空条件数组")
                return set()
            deps = set()
            for i, child in enumerate(c[branch]):
                deps.update(_validate_condition(child, factors, processes, f"{path}.{branch}[{i}]", issues))
            return deps
        return _validate_condition(c[branch], factors, processes, f"{path}.{branch}", issues)
    if not _exact_keys(c, {"field", "op", "value"}, set(), path, issues):
        return set()
    field, op, value = c["field"], c["op"], c["value"]
    if not isinstance(op, str) or op not in _OPS:
        _issue(issues, "invalid_operator", path, f"{path} 不支持运算符 {op}")
        return set()
    if field == "selected_processes":
        if op != "contains" or not isinstance(value, str) or value not in processes:
            _issue(issues, "unknown_process_dependency", path, f"{path} 引用了不存在或非法的工序依赖 {value}")
            return set()
        return {value}
    if not isinstance(field, str) or field not in factors:
        _issue(issues, "unknown_factor", path, f"{path} 引用了未定义因素 {field}")
        return set()
    f = factors[field]
    kind = f.get("type")
    if not isinstance(kind, str):
        _issue(issues, "invalid_condition_type", path, f"因素 {field} 类型非法，不能用于条件")
        return set()
    valid = True
    if op == "exists":
        valid = type(value) is bool
    elif op in {"gt", "gte", "lt", "lte"}:
        valid = kind in {"int", "number"} and type(value) in (int, float) and math.isfinite(value)
    elif op == "in":
        valid = isinstance(value, list) and kind != "multi_enum" and all(_value_ok(kind, x) and x is not None for x in value)
    elif op == "contains":
        valid = kind in {"string", "enum", "multi_enum"} and isinstance(value, str)
    elif op in {"eq", "neq"}:
        # Scalar eq on a multi_enum uses the engine's any-element semantics.
        valid = isinstance(value, str) if kind == "multi_enum" else _value_ok(kind, value)
    if not valid:
        _issue(issues, "invalid_condition_type", path, f"{path} 的 {op} 条件值与因素 {field} 类型 {kind} 不匹配")
    return set()


def validate_demo_tables(tables: dict) -> None:
    """Validate exact public shape, typed expressions and cross-table references."""
    issues = []
    if not _exact_keys(tables, {"factor_table", "full_route_table", "rule_table"}, set(), "tables", issues):
        raise DemoTableError(issues)
    for key in ("factor_table", "full_route_table", "rule_table"):
        if not isinstance(tables[key], list):
            _issue(issues, "invalid_table", key, f"{key} 顶层必须是数组")
    if issues:
        raise DemoTableError(issues)
    factors = {}
    for i, f in enumerate(tables["factor_table"]):
        path = f"factor_table[{i}]"
        if not _exact_keys(f, {"key", "label", "type", "source", "visible"}, {"options", "required", "default"}, path, issues):
            continue
        key = f["key"]
        if not isinstance(key, str) or not key.strip():
            _issue(issues, "invalid_factor_key", path, f"{path} 因素 key 必须是非空字符串")
            continue
        if key == "selected_processes":
            _issue(issues, "reserved_factor", path, "selected_processes 是保留系统因素，不能在因素表声明")
        if key in factors:
            _issue(issues, "duplicate_factor", path, f"因素 key 重复：{key}")
        factors[key] = f
        if not isinstance(f["type"], str) or f["type"] not in _TYPES:
            _issue(issues, "invalid_factor_type", path, f"因素 {key} 类型不属于 Demo 协议")
        if not isinstance(f["label"], str) or not f["label"].strip():
            _issue(issues, "invalid_factor_label", path, f"因素 {key} label 必须是非空字符串")
        if type(f["visible"]) is not bool or type(f.get("required", False)) is not bool:
            _issue(issues, "invalid_factor_flags", path, f"因素 {key} visible/required 必须是布尔值")
        source = f["source"]
        if not isinstance(source, str) or not _SOURCE.fullmatch(source) or (f["visible"] is True and "[]" in source):
            _issue(issues, "invalid_factor_source", path, f"因素 {key} source 必须是有效取值路径，可见因素不能遍历数组")
        if "options" in f:
            options = f["options"]
            if f["type"] not in ("enum", "multi_enum") or not isinstance(options, list) or not all(isinstance(x, str) for x in options) or len(set(options)) != len(options):
                _issue(issues, "invalid_factor_options", path, f"因素 {key} options 必须是枚举的唯一字符串数组")
        if "default" in f:
            default = f["default"]
            if not _value_ok(f["type"], default):
                _issue(issues, "invalid_factor_default", path, f"因素 {key} default 类型不正确")
            elif f["type"] in ("enum", "multi_enum") and isinstance(f.get("options"), list) and default is not None:
                defaults = default if isinstance(default, list) else ([default] if default else [])
                if any(x not in f["options"] for x in defaults):
                    _issue(issues, "invalid_factor_default", path, f"因素 {key} default 不在选项内")
    nodes, processes, parents = set(), set(), {}
    for i, p in enumerate(tables["full_route_table"]):
        path = f"full_route_table[{i}]"
        if not _exact_keys(p, _PROCESS_KEYS, set(), path, issues):
            continue
        pid = p["process_id"]
        if not isinstance(pid, str) or not pid.strip():
            _issue(issues, "invalid_node_id", path, f"{path} process_id 必须是非空字符串")
            continue
        if pid in nodes:
            _issue(issues, "duplicate_node_id", path, f"节点 ID 重复：{pid}")
        nodes.add(pid)
        processes.add(pid)
        if p["process_type"] not in ("加工工序", "辅助工序"):
            _issue(issues, "invalid_process_type", path, f"工序 {pid} process_type 必须是加工工序或辅助工序")
        if not isinstance(p["process_name"], str) or not p["process_name"].strip():
            _issue(issues, "invalid_process_value", path, f"工序 {pid} process_name 必须是非空字符串")
        precision = p["precision"]
        if not isinstance(precision, str) or not precision.strip():
            _issue(
                issues,
                "missing_process_precision" if p["process_type"] == "加工工序" else "invalid_auxiliary_precision",
                path,
                f"工序“{p['process_name']}”（{pid}）的加工精度必须在模板映射阶段确认" if p["process_type"] == "加工工序"
                else f"辅助工序“{p['process_name']}”（{pid}）precision 必须为辅助工序",
            )
        elif p["process_type"] == "加工工序" and precision not in _MACHINING_PRECISIONS:
            _issue(issues, "invalid_process_precision", path, f"加工工序“{p['process_name']}”（{pid}）precision 必须是粗加工、半精加工或精加工")
        elif p["process_type"] == "辅助工序" and precision != "辅助工序":
            _issue(issues, "invalid_auxiliary_precision", path, f"辅助工序“{p['process_name']}”（{pid}）precision 必须为辅助工序")
        if not isinstance(p["steps"], list):
            _issue(issues, "invalid_steps", path, f"工序 {pid} steps 必须是数组")
            continue
        if p["process_type"] == "辅助工序" and p["steps"]:
            _issue(issues, "auxiliary_steps", path, f"辅助工序 {pid} steps 必须为空数组")
        for j, s in enumerate(p["steps"]):
            spath = f"{path}.steps[{j}]"
            if not _exact_keys(s, _STEP_KEYS, set(), spath, issues):
                continue
            sid = s["step_id"]
            if not isinstance(sid, str) or not sid.strip():
                _issue(issues, "invalid_node_id", spath, "step_id 必须是非空字符串")
                continue
            if sid in nodes:
                _issue(issues, "duplicate_node_id", spath, f"节点 ID 重复：{sid}")
            nodes.add(sid)
            parents[sid] = pid
            if not isinstance(s["step_name"], str) or not s["step_name"].strip():
                _issue(issues, "invalid_step_name", spath, f"工步 {sid} 名称必须是非空字符串")
            candidates = s["candidates"]
            if not isinstance(candidates, dict) or any(not isinstance(k, str) or not k.strip() or "\\" in k or k.endswith("/") or not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v) or len(set(v)) != len(v) for k, v in candidates.items()):
                _issue(issues, "invalid_candidates", spath, f"工步 {sid} candidates 必须是规范路径到唯一特征名数组的映射")
    targets, dependencies = set(), {pid: set() for pid in processes}
    for i, r in enumerate(tables["rule_table"]):
        path = f"rule_table[{i}]"
        if not _exact_keys(r, {"target"}, {"required", "when"}, path, issues):
            continue
        target = r["target"]
        if not isinstance(target, str) or target not in nodes:
            _issue(issues, "unknown_target", path, f"规则引用不存在的 target：{target}")
            continue
        if target in targets:
            _issue(issues, "duplicate_target", path, f"同一 target 只能有一条规则：{target}")
        targets.add(target)
        if type(r.get("required", False)) is not bool or (not r.get("required") and "when" not in r):
            _issue(issues, "invalid_rule", path, f"规则 {target} 需要 when 或 required=true")
        if "when" in r:
            deps = _validate_condition(r["when"], factors, processes, f"{path}.when", issues)
            dependencies[parents.get(target, target)].update(deps)
    visited, active = set(), set()

    def visit(pid):
        if pid in active:
            _issue(issues, "dependency_cycle", "rule_table", f"工序依赖存在循环：{pid}")
            return
        if pid in visited:
            return
        active.add(pid)
        for dep in dependencies[pid]:
            visit(dep)
        active.remove(pid)
        visited.add(pid)

    for pid in dependencies:
        visit(pid)
    if issues:
        raise DemoTableError(issues)


# Explicit semantic bindings.  Registry descriptions such as "CAD/PLM" are
# not data paths.  Unsupported CAD-derived categories become visible manual
# parameters; no fictitious geometry/roughness fields are added to CAD input.
_BINDINGS = {
    "material.grade": ("material", "manual_defaults.material_grade", True),
    "material": ("material", "manual_defaults.material_grade", True),
    "part_type": ("part_type", "manual_defaults.part_type", True),
    "heat_treatment": ("heat_treatment", "manual_defaults.heat_treatment", True),
    "surface_treatments": ("surface_treatments", "manual_defaults.surface_treatments", True),
    "inspection_items": ("inspection_items", "manual_defaults.inspection_items", True),
    "marking_methods": ("marking_methods", "manual_defaults.marking_methods", True),
    "shaped_hole_or_cut_flat": ("shaped_hole_or_cut_flat", "manual_defaults.special_process_flags.shaped_hole_or_cut_flat", True),
    "post_stage_added_hole": ("post_stage_added_hole", "manual_defaults.special_process_flags.post_stage_added_hole", True),
    # The authoring field is a CAD feature collection.  Its registry source
    # is intentionally descriptive ("CAD"), so bind it to the real repeated
    # input path used by the downstream engine instead of exposing a manual
    # text control.
    "cad.features": ("feature_type", "input_json[].features[].feature_select", False),
    "group_path": ("group_path", "input_json[].group_path", False),
    "feature_type": ("feature_type", "input_json[].features[].feature_select", False),
    "feature_rank": ("feature_rank", "input_json[].features[].feat_rank", False),
}


def _join(branch, expressions):
    values = []
    identity = branch == "all"
    for expression in expressions:
        if type(expression) is bool:
            if expression != identity:
                return not identity
            continue
        children = expression[branch] if set(expression) == {branch} else [expression]
        for child in children:
            if child not in values:
                values.append(child)
    if not values:
        return identity
    if len(values) == 1:
        return values[0]
    return {branch: values}


def _negate(c):
    if type(c) is bool:
        return not c
    return c["not"] if set(c) == {"not"} else {"not": c}


def _condition_nodes(node):
    yield node
    for child in (node.all_conditions or []) + (node.any_conditions or []):
        yield from _condition_nodes(child)
    if node.not_condition is not None:
        yield from _condition_nodes(node.not_condition)


def _fields(node):
    return (child.field for child in _condition_nodes(node) if child.field)


def _compile_condition(node, key_map):
    if node.all_conditions is not None:
        return _join("all", [_compile_condition(c, key_map) for c in node.all_conditions])
    if node.any_conditions is not None:
        return _join("any", [_compile_condition(c, key_map) for c in node.any_conditions])
    if node.not_condition is not None:
        return _negate(_compile_condition(node.not_condition, key_map))
    if node.field not in key_map:
        _fail("unknown_factor", "route_rules", f"条件因素 {node.field} 未定义")
    field, op, value = key_map[node.field], node.op, deepcopy(node.value)
    def leaf(operator, wanted):
        return {"field": field, "op": operator, "value": wanted}
    if op in {"contains_any", "contains_all"}:
        return _join("any" if op == "contains_any" else "all", [leaf("contains", item) for item in value])
    if op == "between":
        return _join("all", [leaf("gte", value[0]), leaf("lte", value[1])])
    if op in {"exists", "not_exists"}:
        return leaf("exists", op == "exists")
    return leaf(op, value)


def _exclusive(a, b):
    """Prove disjointness for exact leaf domains; otherwise refuse to guess."""
    if not a.field or a.field != b.field:
        return False
    def same(left, right):
        node = ConditionNode.model_validate({"field": "value", "op": "eq", "value": right})
        return evaluate_condition(node, {"value": left}).matched
    if a.op == "eq" and b.op == "eq":
        return not same(a.value, b.value)
    if a.op == "eq" and b.op == "neq":
        return same(a.value, b.value)
    if a.op == "neq" and b.op == "eq":
        return same(a.value, b.value)
    if a.op in {"eq", "in"} and b.op in {"eq", "in"}:
        left = a.value if a.op == "in" else [a.value]
        right = b.value if b.op == "in" else [b.value]
        return not any(same(x, y) for x in left for y in right)
    return False


def _canonical_enum_condition(condition, definitions):
    """Lower V2 normalized text comparisons over a finite declared domain."""
    if type(condition) is bool:
        return condition
    for branch in ("all", "any"):
        if branch in condition:
            return _join(branch, [_canonical_enum_condition(c, definitions) for c in condition[branch]])
    if "not" in condition:
        return _negate(_canonical_enum_condition(condition["not"], definitions))
    field, op = condition["field"], condition["op"]
    definition = definitions[field]
    if definition.type not in {"single_select", "multi_select"} or op == "exists":
        return condition
    values = list(dict.fromkeys(o.value for o in definition.options))
    if definition.type == "single_select" and "" not in values:
        values.append("")
    # Evaluate the authoring condition itself, rather than approximating its
    # casefold/whitespace rules in a second expression evaluator.
    node = ConditionNode.model_validate({**condition, "op": "eq" if op == "neq" else op})
    accepted = [value for value in values if evaluate_condition(
        node, {field: [value] if definition.type == "multi_select" else value}
    ).matched]
    if definition.type == "multi_select":
        return _join("any", [{"field": field, "op": "contains", "value": value} for value in accepted])
    result = {"field": field, "op": "in", "value": accepted} if accepted else False
    return _negate(result) if op == "neq" else result


def compile_demo_tables(
    package: RulePackageV2,
    full_route_table: list[dict],
    *,
    step_states: dict[str, str] | None = None,
) -> dict:
    """Compile a single immutable public snapshot from V2 and the mapped route."""
    validate_demo_tables({"factor_table": [], "full_route_table": full_route_table, "rule_table": []})
    if not full_route_table:
        _fail("empty_full_route", "full_route_table", "映射后全集路线为空，不能发布三表")
    catalog = {p.process_id: p for p in package.route_catalog.processes}
    route_ids = [p["process_id"] for p in full_route_table]
    if len(catalog) != len(package.route_catalog.processes) or set(route_ids) != set(catalog):
        _fail("stale_catalog_identity", "full_route_table", "全集路线与规则目录的工序 ID 不一致，请刷新最终工艺树和模板映射")
    for p in full_route_table:
        expected = catalog[p["process_id"]]
        actual_steps = [s["step_id"] for s in p["steps"]]
        expected_steps = [s.step_id for s in expected.steps]
        if actual_steps != expected_steps:
            _fail("stale_catalog_identity", f"full_route_table.{p['process_id']}.steps", f"工序 {p['process_id']} 的工步身份或顺序已变化，请重新确认模板映射")
        if p["process_name"] != expected.display_name or any(s["step_name"] != e.name for s, e in zip(p["steps"], expected.steps)):
            _fail("stale_catalog_identity", f"full_route_table.{p['process_id']}", f"工序 {p['process_id']} 的最终名称与规则目录不一致，请刷新后发布")
    rules = [r for r in package.route_rules.rules if r.enabled]
    reviewed_steps = step_states or {}
    known_steps = {s["step_id"] for p in full_route_table for s in p["steps"]}
    if not isinstance(reviewed_steps, dict):
        _fail("invalid_step_review", "step_states", "工步审定状态必须按稳定工步 ID 提供")
    for sid, state in reviewed_steps.items():
        if sid not in known_steps:
            _fail("unknown_step_review", "step_states", f"工步审定证据引用已失效的工步 {sid}，请刷新模板映射")
        if state not in ("general", "pending"):
            _fail("invalid_step_review", f"step_states.{sid}", f"工步 {sid} 审定状态非法")
    # An empty feature candidate set means this step has no automatic
    # geometry filter. Keep it in the full route and let its parent process
    # rule control inclusion; do not force per-step review.
    referenced = {key for r in rules for key in _fields(r.when)}
    definitions = {f.key: f for f in package.factor_dictionary.fields}
    active_keys = list(dict.fromkeys([f.key for f in package.input_schema.fields] + sorted(referenced)))
    factors, key_map = [], {}
    for key in active_keys:
        if key not in definitions:
            _fail("unknown_factor", "factor_table", f"条件因素 {key} 未定义")
        f = definitions[key]
        binding = _BINDINGS.get(key)
        if binding:
            public_key, source, visible = binding
        elif _SOURCE.fullmatch(f.source or "") and f.source.startswith(("manual_defaults.", "input_json[].")):
            public_key, source, visible = key, f.source, "[]" not in f.source
        else:
            public_key, source, visible = key, f"manual_defaults.{key}", True
        if public_key in key_map.values():
            _fail("duplicate_factor", "factor_table", f"因素 {key} 与已有因素映射到同一 key {public_key}")
        key_map[key] = public_key
        kind = {"boolean": "bool", "single_select": "enum", "multi_select": "multi_enum"}.get(f.type, f.type)
        # Repeated CAD feature values are scalar enum items collected from
        # input rows.  The downstream Demo engine expects enum here and
        # returns a list because the source path contains [].
        if key == "cad.features" and source == "input_json[].features[].feature_select":
            kind = "enum"
        if source == "input_json[].features[].feat_rank" and kind == "number":
            kind = "int"
        factor = {"key": public_key, "label": f.label, "type": kind, "source": source, "visible": visible}
        if f.options and not f.allow_custom:
            factor["options"] = list(dict.fromkeys(o.value for o in f.options))
        if f.required:
            factor["required"] = True
        factors.append(factor)
    public_definitions = {key_map[key]: definitions[key] for key in active_keys}
    public_factors = {f["key"]: f for f in factors}
    decisions = defaultdict(list)
    manual_fields = {f.key for f in package.input_schema.fields if f.type == "boolean" and f.source == "用户直接设定" and f.key.startswith("project_factor.manual_process_")}
    for r in rules:
        for node in _condition_nodes(r.when):
            if node.field and definitions[node.field].type == "multi_select" and node.op in {"eq", "neq", "in"}:
                _fail("unsupported_collection_equality", f"route_rules.{r.rule_id}.when", f"规则 {r.rule_id} 对多选因素 {node.field} 使用整体相等比较，与 Demo 的逐元素比较不等价，请改用包含条件")
            if node.field and (definitions[node.field].type == "string" or (
                definitions[node.field].type in {"single_select", "multi_select"}
                and (not definitions[node.field].options or definitions[node.field].allow_custom)
            )) and node.op not in {"exists", "not_exists"}:
                _fail("unsupported_text_comparison", f"route_rules.{r.rule_id}.when", f"规则 {r.rule_id} 对开放文本因素“{definitions[node.field].label}”的比较会忽略大小写及首尾空白，Demo 使用精确值，不能无损转换；请先将该因素审定为有明确选项的枚举。")
            if node.field and public_factors[key_map[node.field]]["type"] == "number" and node.op in {"eq", "neq", "in"}:
                _fail("unsupported_numeric_equality", f"route_rules.{r.rule_id}.when", f"规则 {r.rule_id} 对数值因素“{definitions[node.field].label}”使用带容差的相等比较，Demo 使用精确值，不能无损转换；请改为明确的数值区间。")
        condition = _compile_condition(r.when, key_map)
        condition_issues = []
        _validate_condition(condition, {f["key"]: f for f in factors}, set(catalog), f"route_rules.{r.rule_id}.when", condition_issues)
        if condition_issues:
            raise DemoTableError(condition_issues)
        condition = _canonical_enum_condition(condition, public_definitions)
        for action, ids in (("include", r.then.include_process_ids), ("exclude", r.then.exclude_process_ids)):
            for pid in ids:
                if pid not in catalog:
                    _fail("unknown_target", f"route_rules.{r.rule_id}", f"规则 {r.rule_id} 引用了不存在的工序 {pid}")
                manual = action == "exclude" and r.source == "user_confirmed" and r.when.field in manual_fields and r.when.op == "eq" and r.when.value is False
                decisions[pid].append((r, action, condition, manual))
    expressions, manual_exclusions = {}, {}
    for pid, p in catalog.items():
        by_priority = defaultdict(list)
        for decision in decisions[pid]:
            by_priority[decision[0].priority].append(decision)
        higher, accepted, manual_rejected = False, [], []
        for priority in sorted(by_priority, reverse=True):
            group = by_priority[priority]
            for left in group:
                for right in group:
                    if left[1] != right[1] and not _exclusive(left[0].when, right[0].when):
                        _fail("same_priority_action_conflict", f"route_rules.{pid}", f"工序 {pid} 的同优先级规则 {left[0].rule_id}/{right[0].rule_id} 可能同时纳入与排除，Demo 无法表达该运行时冲突")
            for r, action, condition, manual in group:
                winner = _join("all", [condition, _negate(higher)])
                if action == "include" or (p.main and not manual):
                    accepted.append(winner)
                if manual:
                    manual_rejected.append(winner)
            higher = _join("any", [higher, *[item[2] for item in group]])
        if p.main:
            accepted.append(_negate(higher))
        expressions[pid] = True if p.main and not manual_rejected else _join("any", accepted)
        manual_exclusions[pid] = _join("any", manual_rejected)
    positions = {pid: i for i, pid in enumerate(route_ids)}
    issues = []
    def ordered(before, after, path):
        if before not in positions or after not in positions:
            _issue(issues, "unknown_process_dependency", path, f"顺序约束引用未知工序 {before}/{after}")
        elif positions[before] >= positions[after]:
            _issue(issues, "route_order_conflict", path, f"全集路线顺序必须使 {before} 位于 {after} 之前；Demo 不会自动重排")
    for pid, p in catalog.items():
        path = f"route_catalog.{pid}.constraints"
        for dependency in p.constraints.requires:
            ordered(dependency, pid, path)
            if expressions.get(dependency) is not True:
                _issue(issues, "unsupported_requires", path, f"工序 {pid} 依赖可选工序 {dependency}，其排除冲突无法无损转换为 Demo 启用条件")
        if p.constraints.conflicts_with:
            _issue(issues, "unsupported_conflicts", path, f"工序 {pid} 的互斥约束不能转为自动关闭；请先审定启用规则")
        for before in p.constraints.must_run_after:
            ordered(before, pid, path)
        for after in p.constraints.must_run_before:
            ordered(pid, after, path)
    for relation in package.route_rules.process_relations:
        if not relation.enabled:
            continue
        path = f"route_rules.process_relations.{relation.relation_id}"
        sources, targets = relation.source_process_ids, relation.target_process_ids
        if any(pid not in catalog for pid in sources + targets):
            _issue(issues, "unknown_process_dependency", path, f"关系 {relation.relation_id} 引用了未知工序")
            continue
        if relation.relation_type == "conflicts":
            _issue(issues, "unsupported_conflicts", path, f"互斥关系 {relation.relation_id} 需要运行时冲突报错，Demo 条件不能等价表达")
            continue
        for before in sources:
            for after in targets:
                ordered(before, after, path)
        if relation.relation_type == "requires":
            if any(expressions[source] is not True for source in sources):
                _issue(issues, "unsupported_requires", path, f"依赖关系 {relation.relation_id} 含可选前置工序，不能静默改为关闭目标工序")
        elif relation.relation_type == "trigger_after":
            trigger = _join("all" if relation.source_match == "all" else "any", [
                {"field": "selected_processes", "op": "contains", "value": source} for source in sources])
            for target in targets:
                if expressions[target] is True:
                    continue
                if any(action == "exclude" and not manual for _, action, _, manual in decisions[target]):
                    _issue(issues, "unsupported_trigger_exclusion", path, f"触发关系 {relation.relation_id} 的目标 {target} 含排除条件，Demo 无法表达触发与排除的运行时冲突")
                expressions[target] = _join("all", [_join("any", [expressions[target], trigger]), _negate(manual_exclusions[target])])
    if issues:
        raise DemoTableError(issues)
    output_rules = [{"target": pid, **({"required": True} if expressions[pid] is True else {"when": expressions[pid]})} for pid in route_ids]
    tables = {"factor_table": factors, "full_route_table": deepcopy(full_route_table), "rule_table": output_rules}
    validate_demo_tables(tables)
    return tables
