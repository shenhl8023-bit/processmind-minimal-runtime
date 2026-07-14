"""
工艺路线生成结果的兜底构造与输出组装。
"""

from __future__ import annotations

import json

from app.schemas.schemas import RouteStep


def build_minimal_fallback_steps(
    inputs: dict[str, object],
    *,
    to_bool,
    to_float,
) -> list[RouteStep]:
    steps = [
        RouteStep(name="下料 / 锻造", op_type="MAIN", reason="规则库为空，使用默认主线"),
        RouteStep(name="粗车外圆", op_type="MAIN", reason="规则库为空，使用默认主线"),
    ]
    if to_bool(inputs.get("has_hole")):
        steps.append(RouteStep(name="钻深孔", op_type="BRANCH", reason="因勾选「需要打孔」触发"))
    if str(inputs.get("hardness", "")).upper() == "HIGH":
        steps.append(RouteStep(name="调质处理", op_type="BRANCH", reason="高硬度要求触发"))
    if to_bool(inputs.get("has_spline")):
        steps.append(RouteStep(name="拉花键", op_type="BRANCH", reason="因勾选「有花键/键槽」触发"))
    roughness = to_float(inputs.get("roughness"))
    if roughness is not None and roughness <= 0.8:
        steps.append(RouteStep(name="外圆精磨", op_type="BRANCH", reason=f"Ra <= {roughness}"))
    steps.append(RouteStep(name="最终检验", op_type="MAIN", reason="规则库为空，使用默认收尾"))
    return steps


def build_generate_output_json(project_id: int, output_mode: str, steps: list[RouteStep]) -> str:
    return json.dumps(
        {
            "project_id": project_id,
            "route_source": output_mode,
            "route": [
                {
                    "process_id": step.process_id,
                    "sequence": step.sequence or index * 10,
                    "process_name": step.name,
                    "process_steps": step.process_steps,
                }
                for index, step in enumerate(steps, start=1)
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_generate_summary(steps: list[RouteStep], source_summary: str) -> str:
    return f"共命中 {len(steps)} 条工序规则，{source_summary}"


__all__ = [
    "build_generate_output_json",
    "build_generate_summary",
    "build_minimal_fallback_steps",
]
