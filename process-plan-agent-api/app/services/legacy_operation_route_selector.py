"""
旧版 Operation/Factor 规则库路线选择器。

第5步优先使用第4步定稿规则包；当项目还没有规则包时，
这里负责根据 Operation.factors 做兼容路线生成。
"""
from __future__ import annotations

from app.models.models import Operation
from app.schemas.schemas import RouteStep
from app.services.harness_validators import is_harness_warning_factor_name
from app.services.param_rule_expression import canonicalize_factor_name, matches_factor_condition


MAIN_OP_PREFERRED_ORDER = [
    "下料", "调质", "车外圆", "车端面", "钻孔", "车外形",
    "铣槽", "铣扁", "磨外圆", "去毛刺", "清洗", "检验",
]

BRANCH_OP_PRIORITY = {
    "去应力": 10,
    "淬火": 20,
    "真空淬火": 30,
    "研顶尖孔": 40,
    "研顶尖": 50,
    "研孔": 60,
    "车螺纹": 70,
    "车槽": 80,
    "车端面B": 90,
    "车端面镗孔": 100,
    "钻铰孔": 110,
    "攻螺纹": 120,
    "攻螺纹钻孔": 130,
    "钻镗孔": 140,
    "割扁、割型孔": 150,
    "磨孔": 160,
    "倒角": 170,
    "车削中心": 180,
    "铰刀": 190,
}

MUTEX_GROUPS = {
    "预备热处理": {"调质", "正常化"},
    "热处理": {"淬火", "真空淬火"},
    "孔精加工": {"研孔", "磨孔", "铰刀"},
    "孔复合加工": {"钻孔", "钻铰孔", "钻镗孔", "车端面镗孔", "攻螺纹钻孔"},
    "外形加工": {"车外圆", "车外形"},
}


def group_for_operation(op_name: str) -> str | None:
    for group_name, names in MUTEX_GROUPS.items():
        if op_name in names:
            return group_name
    return None


def branch_priority(op_name: str) -> int:
    return BRANCH_OP_PRIORITY.get(op_name, 999)


def generic_quality_gate_kind(op_name: str) -> str | None:
    name = (op_name or "").strip()
    if "清洗" in name:
        return "clean"
    if "检验" in name and not any(token in name for token in ("磁粉", "烧伤", "探伤")):
        return "inspect"
    return None


def collapse_redundant_quality_gates(steps: list[RouteStep]) -> list[RouteStep]:
    collapsed: list[RouteStep] = []
    seen_clean = False
    seen_inspect = False

    for step in steps:
        gate_kind = generic_quality_gate_kind(step.name)
        if gate_kind is None:
            collapsed.append(step)
            seen_clean = False
            seen_inspect = False
            continue

        if gate_kind == "clean":
            if seen_clean or seen_inspect:
                continue
            seen_clean = True
            collapsed.append(step)
            continue

        if gate_kind == "inspect":
            if seen_inspect:
                continue
            seen_inspect = True
            collapsed.append(step)

    return collapsed


def operation_matches(op: Operation, inputs: dict[str, object]) -> tuple[bool, list[str]]:
    effective_factors = [factor for factor in op.factors if not is_harness_warning_factor_name(factor.name)]
    if not effective_factors:
        return op.op_type == "MAIN", ["命中规则：主线工序"]

    reasons: list[str] = []
    strong_total = 0
    strong_matched = 0
    weak_matched = 0
    has_always = False
    for factor in effective_factors:
        matched, reason = matches_factor_condition(factor.name, inputs, op.name)
        if canonicalize_factor_name(factor.name) == "always=true":
            has_always = True
        if factor.strength == "STRONG":
            strong_total += 1
        if matched:
            reasons.append(reason or f"命中规则：{factor.name}")
            if factor.strength == "STRONG":
                strong_matched += 1
            else:
                weak_matched += 1

    if has_always and op.op_type == "MAIN":
        return True, reasons or ["命中规则：基础主线工序"]

    if strong_total > 0:
        return strong_matched == strong_total, reasons if strong_matched == strong_total else []

    return weak_matched > 0, reasons


def select_best_operations(operations: list[Operation], inputs: dict[str, object]) -> list[RouteStep]:
    matched_main: list[tuple[int, RouteStep]] = []
    matched_branch: list[tuple[int, RouteStep, str | None]] = []

    for op in operations:
        matched, reasons = operation_matches(op, inputs)
        if not matched:
            continue

        step = RouteStep(
            name=op.name,
            op_type="MAIN" if op.op_type == "MAIN" else "BRANCH",
            reason="；".join(reasons),
        )

        if op.op_type == "MAIN":
            matched_main.append((op.sequence, step))
        else:
            matched_branch.append((op.sequence, step, group_for_operation(op.name)))

    matched_main.sort(
        key=lambda item: (
            item[0],
            MAIN_OP_PREFERRED_ORDER.index(item[1].name) if item[1].name in MAIN_OP_PREFERRED_ORDER else 999,
            item[1].name,
        )
    )

    selected_steps: list[RouteStep] = [item[1] for item in matched_main]
    chosen_groups: set[str] = set()

    for _, step, group_name in sorted(matched_branch, key=lambda item: (item[0], branch_priority(item[1].name), item[1].name)):
        if group_name and group_name in chosen_groups:
            continue
        selected_steps.append(step)
        if group_name:
            chosen_groups.add(group_name)

    return collapse_redundant_quality_gates(selected_steps)
