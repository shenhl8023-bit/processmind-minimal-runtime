"""
工艺路线生成结果的兜底构造与输出组装。
"""

from __future__ import annotations

import json

from app.schemas.schemas import RouteStep


def build_generate_output_json(
    project_id: int,
    output_mode: str,
    steps: list[RouteStep],
    *,
    full_route_structure: list[dict[str, object]] | None = None,
    input_factors: dict[str, object] | None = None,
    input_metadata: dict[str, object] | None = None,
) -> str:
    return json.dumps(
        {
            "project_id": project_id,
            "route_source": output_mode,
            "input_factors": input_factors or {},
            "input_metadata": input_metadata or {},
            "full_route_structure": full_route_structure or [],
            "route": [
                {
                    "process_id": step.process_id,
                    "sequence": step.sequence or index * 10,
                    "process_name": step.name,
                    "phase": step.phase,
                    "process_steps": step.process_steps,
                    "template_group_aliases": [alias.model_dump() for alias in step.template_group_aliases],
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
]
