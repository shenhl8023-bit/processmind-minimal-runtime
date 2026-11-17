"""Deterministic V2 lowering shared with featureInputProjection.ts.

Only the source audit may authorize this representation: it first validates the
saved authored candidate, then derives fields and expressions from that candidate.
No client-supplied originals or projection claims are used.
"""

from __future__ import annotations

from copy import deepcopy
import re

from app.services.rule_packages.condition_contracts import CanonicalConditionField, RuleConditionCandidate
from app.services.rule_packages.contracts import InputField
from app.services.rule_packages.project_conditions import PROJECT_ACTUAL_IT_GRADES


_OPERATION_FIELD = re.compile(r"^(project_factor\.operation_[^.]+)\.(features|direction|it|ra)$")
SHARED_FEATURE_FIELD = re.compile(r"^(project_factor\.feature_[^.]+)\.(present|direction|it|ra)$")


def feature_input_scope(name: str) -> str:
    return "project_factor.feature_" + "_".join(format(ord(char), "x") for char in name)


def _combine(kind, nodes):
    return nodes[0] if len(nodes) == 1 else {kind: nodes}


def _field_keys(node):
    if not node:
        return []
    if "field" in node:
        return [node["field"]]
    if "not" in node:
        return _field_keys(node["not"])
    return [key for child in node.get("all", node.get("any", [])) for key in _field_keys(child)]


def _scope_of(node):
    if "field" in node:
        match = _OPERATION_FIELD.fullmatch(node["field"])
        return match.group(1) if match else None
    if "not" in node:
        return None
    scopes = {_scope_of(child) for child in node.get("all", node.get("any", []))}
    return next(iter(scopes)) if len(scopes) == 1 else None


def _flatten(node):
    return [item for child in node["all"] for item in _flatten(child)] if "all" in node else [node]


def _is_ab_direction(node):
    children = node.get("any", [])
    return (len(children) == 2
            and all("field" in child and child["field"].endswith(".direction")
                    and child["op"] == "eq" and child.get("value") in ("A侧", "B侧") for child in children)
            and {child["value"] for child in children} == {"A侧", "B侧"})


def _read_condition_node(node):
    """Match ruleConditionShape.ts for backend JSON with inactive null branches."""
    if not isinstance(node, dict):
        return None
    branches = [node.get("all") is not None, node.get("any") is not None,
                node.get("not") is not None, node.get("field") is not None or node.get("op") is not None]
    if sum(branches) != 1:
        return None
    for kind in ("all", "any"):
        if node.get(kind) is not None:
            if not isinstance(node[kind], list):
                return None
            children = [_read_condition_node(child) for child in node[kind]]
            return None if any(child is None for child in children) else {kind: children}
    if node.get("not") is not None:
        child = _read_condition_node(node["not"])
        return {"not": child} if child is not None else None
    if not all(isinstance(node.get(key), str) and node[key].strip() for key in ("field", "op")):
        return None
    return {key: node[key] for key in ("field", "op", "value") if key in node}


def _input_field(raw):
    return InputField.model_validate({key: value for key, value in raw.items() if key in InputField.model_fields})


def _actual_input_definition(field):
    """Match the known IT authoring-domain normalization in the TS builder."""
    validation = field.get("validation")
    options = field.get("options") or []
    standard_options = all(
        option.get("value") in [str(grade) for grade in range(-1, 19)]
        and option.get("label") == ("IT01" if option["value"] == "-1" else "IT" + option["value"])
        for option in options)
    if (field.get("type") != "number" or field.get("unit") != "IT" or not validation or not standard_options
            or any(value is not None and key not in ("min", "max") for key, value in validation.items())
            or validation.get("min") not in (-1, 1, PROJECT_ACTUAL_IT_GRADES[0])
            or validation.get("max") not in (18, PROJECT_ACTUAL_IT_GRADES[-1])):
        return field
    return {**field, "validation": {"min": PROJECT_ACTUAL_IT_GRADES[0], "max": PROJECT_ACTUAL_IT_GRADES[-1]}, "options": []}


def lower_feature_inputs(input_data: dict, *, strict_metadata: bool = False) -> dict:
    """Lower raw input without adding model defaults or mutating its arguments.

    Raw mode mirrors TS for the cross-language fixture. Source auditing also
    refuses conflicting saved metadata rather than silently accepting whichever
    definition happens to appear first.
    """
    data = deepcopy(input_data)
    definitions = {field["key"]: field for field in data["fields"]}
    shared = {}

    def register(name, suffix, old_key=None):
        key = feature_input_scope(name) + "." + suffix
        original = definitions.get(old_key)
        if original and suffix == "it":
            original = _actual_input_definition(original)
        if suffix == "present":
            definition = {"key": key, "label": name, "type": "boolean", "required": False,
                          "source": "本项目特征输入", "allow_custom": False}
        else:
            label = {"direction": "的方位", "it": "的实际尺寸精度等级", "ra": "的实际Ra要求值"}[suffix]
            definition = {**original, "key": key, "label": name + label,
                          "required": False, "source": "本项目特征输入"}
        if key not in shared:
            shared[key] = definition
        else:
            existing = shared[key]
            if strict_metadata:
                left, right = _input_field(existing), _input_field(definition)
                if left.model_dump(exclude={"options"}) != right.model_dump(exclude={"options"}):
                    raise ValueError("Conflicting saved shared-feature metadata: " + key)
                left_options = {option.value: option for option in left.options}
                if any(option.value in left_options and left_options[option.value] != option for option in right.options):
                    raise ValueError("Conflicting saved shared-feature option: " + key)
            if original and original.get("options"):
                # Dict insertion order matches JS Map: updating an exact value
                # replaces its metadata without moving its original position.
                options = {option["value"]: option for option in existing.get("options", [])}
                options.update((option["value"], deepcopy(option)) for option in original["options"])
                existing["options"] = list(options.values())
        return key

    def substitute(node, name):
        if "field" in node:
            suffix = _OPERATION_FIELD.fullmatch(node["field"]).group(2)
            if suffix == "features":
                return {"field": register(name, "present"), "op": "eq", "value": True}
            key = register(name, suffix, node["field"])
            if suffix == "direction" and node["op"] == "eq" and node.get("value") in ("A侧", "B侧", "所有方位"):
                values = ["A侧", "B侧", "所有方位"] if node["value"] == "所有方位" else [node["value"], "所有方位"]
                return {"field": key, "op": "in", "value": values}
            return {**node, "field": key}
        if "not" in node:
            return node
        kind = "all" if "all" in node else "any"
        return _combine(kind, [substitute(child, name) for child in node[kind]])

    def lower(node):
        if "not" in node:
            return node
        if "any" in node:
            return _combine("any", [lower(child) for child in node["any"]])
        nodes = _flatten(node)
        by_scope = {}
        for item in nodes:
            scope = _scope_of(item)
            if scope:
                by_scope.setdefault(scope, []).append(item)
        replacements, consumed = {}, set()
        for clauses in by_scope.values():
            selections = [item for item in clauses if "field" in item and item["field"].endswith(".features")]
            if len(selections) != 1 or selections[0]["op"] not in ("contains_any", "contains"):
                continue
            if any("field" not in item and not _is_ab_direction(item) for item in clauses):
                continue
            if any(key not in definitions for item in clauses for key in _field_keys(item)):
                continue
            value = selections[0]["value"]
            names = list(dict.fromkeys(value if isinstance(value, list) else [value]))
            if not names:
                continue
            replacements[id(clauses[0])] = _combine("any", [
                _combine("all", [substitute(item, name) for item in clauses]) for name in names])
            consumed.update(id(item) for item in clauses[1:])
        return _combine("all", [replacements[id(item)] if id(item) in replacements else
                                item if "field" in item else lower(item)
                                for item in nodes if id(item) not in consumed])

    rules = [{**rule, "when": lower(_read_condition_node(rule["when"]) or rule["when"])} for rule in data["rules"]]
    configurations = [{**config, **({"when": lower(_read_condition_node(config["when"]) or config["when"])} if config.get("when") else {})}
                      for config in data["processConfigurations"]]
    referenced = {key for item in [*rules, *configurations] for key in _field_keys(item.get("when"))}
    fields = [field for field in [*data["fields"], *shared.values()] if field["key"] in referenced]
    return {"fields": fields, "rules": rules, "processConfigurations": configurations}


def project_feature_candidate(candidate: RuleConditionCandidate) -> RuleConditionCandidate:
    """Project a previously validated, saved authored candidate for source audit."""
    payload = candidate.model_dump(by_alias=True, exclude_none=True)
    rules = [{"when": payload["when"]}] if candidate.when else []
    configurations = [payload["configuration"]] if candidate.configuration else []
    projected = lower_feature_inputs({"fields": payload["field_definitions"], "rules": rules,
                                      "processConfigurations": configurations}, strict_metadata=True)
    result = candidate.model_copy(deep=True)
    if rules:
        result.when = type(candidate.when).model_validate(projected["rules"][0]["when"])
    if configurations:
        result.configuration = type(candidate.configuration).model_validate(projected["processConfigurations"][0])
    result.field_definitions = [CanonicalConditionField.model_validate({
        "category": "本项目条件", "operators": ["eq"], **field,
    }) for field in projected["fields"]]
    return result
