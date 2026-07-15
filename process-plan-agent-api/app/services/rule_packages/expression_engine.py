"""Deterministic evaluator for rule package V2 condition trees."""

from __future__ import annotations

from typing import Any

from app.services.rule_packages.contracts import ConditionNode, ConditionTrace


MISSING = object()


def resolve_field(inputs: dict[str, Any], field: str) -> Any:
    if field in inputs:
        return inputs[field]

    current: Any = inputs
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current


def _is_present(value: Any) -> bool:
    if value is MISSING or value is None or value == "":
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _normalized_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def _equals(actual: Any, expected: Any) -> bool:
    if (
        not isinstance(actual, bool)
        and not isinstance(expected, bool)
        and isinstance(actual, (int, float))
        and isinstance(expected, (int, float))
    ):
        return abs(float(actual) - float(expected)) < 1e-9
    return _normalized_scalar(actual) == _normalized_scalar(expected)


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str):
        return str(expected).strip().casefold() in actual.strip().casefold()
    if isinstance(actual, (list, tuple, set)):
        return any(_equals(item, expected) for item in actual)
    if isinstance(actual, dict):
        return str(expected) in actual
    return False


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _evaluate_leaf(node: ConditionNode, inputs: dict[str, Any]) -> ConditionTrace:
    field = str(node.field or "")
    op = str(node.op or "")
    actual = resolve_field(inputs, field)
    expected = node.value

    if op == "exists":
        matched = _is_present(actual)
    elif op == "not_exists":
        matched = not _is_present(actual)
    elif actual is MISSING:
        matched = False
    elif op == "eq":
        matched = _equals(actual, expected)
    elif op == "neq":
        matched = not _equals(actual, expected)
    elif op == "in":
        matched = any(_equals(actual, item) for item in expected)
    elif op == "contains":
        matched = _contains(actual, expected)
    elif op == "contains_any":
        matched = any(_contains(actual, item) for item in expected)
    elif op == "contains_all":
        matched = all(_contains(actual, item) for item in expected)
    else:
        actual_number = _number(actual)
        if op == "between":
            low = _number(expected[0])
            high = _number(expected[1])
            matched = (
                actual_number is not None
                and low is not None
                and high is not None
                and low <= actual_number <= high
            )
        else:
            expected_number = _number(expected)
            if actual_number is None or expected_number is None:
                matched = False
            elif op == "gt":
                matched = actual_number > expected_number
            elif op == "gte":
                matched = actual_number >= expected_number
            elif op == "lt":
                matched = actual_number < expected_number
            elif op == "lte":
                matched = actual_number <= expected_number
            else:
                matched = False

    if actual is MISSING:
        reason = f"missing_field:{field}"
        trace_actual = None
    else:
        reason = f"{field} {op} {'matched' if matched else 'did_not_match'}"
        trace_actual = actual
    return ConditionTrace(
        kind="leaf",
        matched=matched,
        reason=reason,
        field=field,
        op=op,
        actual=trace_actual,
        expected=expected,
    )


def evaluate_condition(node: ConditionNode, inputs: dict[str, Any]) -> ConditionTrace:
    if node.all_conditions is not None:
        children = [evaluate_condition(child, inputs) for child in node.all_conditions]
        matched = all(child.matched for child in children)
        return ConditionTrace(
            kind="all",
            matched=matched,
            reason="all conditions matched" if matched else "one or more conditions did not match",
            children=children,
        )
    if node.any_conditions is not None:
        children = [evaluate_condition(child, inputs) for child in node.any_conditions]
        matched = any(child.matched for child in children)
        return ConditionTrace(
            kind="any",
            matched=matched,
            reason="at least one condition matched" if matched else "no condition matched",
            children=children,
        )
    if node.not_condition is not None:
        child = evaluate_condition(node.not_condition, inputs)
        missing_field = any(
            trace.reason.startswith("missing_field:")
            for trace in _walk_traces(child)
        )
        return ConditionTrace(
            kind="not",
            matched=False if missing_field else not child.matched,
            reason="nested condition used a missing field" if missing_field else "nested condition was negated",
            children=[child],
        )
    return _evaluate_leaf(node, inputs)


def _walk_traces(trace: ConditionTrace):
    yield trace
    for child in trace.children:
        yield from _walk_traces(child)


def iter_condition_fields(node: ConditionNode):
    if node.field:
        yield node.field
    for child in node.all_conditions or []:
        yield from iter_condition_fields(child)
    for child in node.any_conditions or []:
        yield from iter_condition_fields(child)
    if node.not_condition is not None:
        yield from iter_condition_fields(node.not_condition)
