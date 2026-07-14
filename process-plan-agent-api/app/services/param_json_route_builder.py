"""
参数 JSON 工艺路线解析与全集树合并工具。

这些函数只负责把样本 JSON 文本转换为工序/工步树结构，
并把多份样本合并成第5步可复用的全集路线。
"""
from __future__ import annotations

import json
from collections import Counter

from app.schemas.schemas import ParamJsonStageOut, ParamJsonStepOut


def read_raw_text_with_fallbacks(
    filepath: str,
    encodings: tuple[str, ...] = ("utf-8", "utf-8-sig", "gb18030", "gbk"),
) -> str:
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            with open(filepath, "r", encoding=encoding) as fp:
                return fp.read()
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return ""


def parse_top_level_json_entries(raw_text: str) -> list[tuple[str, object]]:
    text = (raw_text or "").strip()
    if not text.startswith("{"):
        return []

    decoder = json.JSONDecoder()
    entries: list[tuple[str, object]] = []
    idx = 1

    while idx < len(text):
        while idx < len(text) and text[idx] in {" ", "\n", "\r", "\t", ","}:
            idx += 1
        if idx >= len(text) or text[idx] == "}":
            break

        key, idx = decoder.raw_decode(text, idx)
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text) or text[idx] != ":":
            return []
        idx += 1
        while idx < len(text) and text[idx].isspace():
            idx += 1

        value, idx = decoder.raw_decode(text, idx)
        entries.append((str(key), value))

    return entries


def build_param_step_out(step_name: str, raw_value: object) -> ParamJsonStepOut:
    if not isinstance(raw_value, str):
        return ParamJsonStepOut(name=step_name, description=str(raw_value or ""))

    parts = [part.strip() for part in raw_value.split("&&")]
    description = parts[0] if len(parts) > 0 else ""
    machine = parts[1] if len(parts) > 1 and parts[1] != "NULL" else ""
    note = parts[2] if len(parts) > 2 and parts[2] != "NULL" else ""
    return ParamJsonStepOut(name=step_name, description=description, machine=machine, note=note)


def build_param_sample_stages(raw_text: str) -> list[ParamJsonStageOut]:
    entries = parse_top_level_json_entries(raw_text)
    stages: list[ParamJsonStageOut] = []
    occurrence_counter: Counter[str] = Counter()
    for stage_name, stage_value in entries:
        occurrence_counter[stage_name] += 1
        if isinstance(stage_value, dict):
            steps = [build_param_step_out(step_name, raw_value) for step_name, raw_value in stage_value.items()]
        else:
            steps = [build_param_step_out(stage_name, stage_value)]
        stages.append(
            ParamJsonStageOut(
                stage=stage_name,
                steps=steps,
                occurrence_index=occurrence_counter[stage_name],
                evidence_count=1,
            )
        )
    return stages


def merge_text_by_count(values: list[str]) -> str:
    cleaned = [value.strip() for value in values if value and value.strip()]
    if not cleaned:
        return ""
    counts = Counter(cleaned)
    return sorted(counts.items(), key=lambda item: (-item[1], len(item[0]), item[0]))[0][0]


def build_param_superset_stages(stage_lists: list[list[ParamJsonStageOut]]) -> list[ParamJsonStageOut]:
    stage_buckets: dict[tuple[str, int], dict[str, object]] = {}

    for stages in stage_lists:
        for position, stage in enumerate(stages, start=1):
            key = (stage.stage, stage.occurrence_index)
            bucket = stage_buckets.setdefault(
                key,
                {
                    "stage": stage.stage,
                    "occurrence_index": stage.occurrence_index,
                    "positions": [],
                    "doc_hits": 0,
                    "steps": {},
                },
            )
            bucket["positions"].append(position)
            bucket["doc_hits"] += 1
            step_buckets: dict[str, dict[str, object]] = bucket["steps"]  # type: ignore[assignment]
            for step_index, step in enumerate(stage.steps, start=1):
                step_bucket = step_buckets.setdefault(
                    step.name,
                    {
                        "name": step.name,
                        "positions": [],
                        "doc_hits": 0,
                        "descriptions": [],
                        "machines": [],
                        "notes": [],
                    },
                )
                step_bucket["positions"].append(step_index)
                step_bucket["doc_hits"] += 1
                step_bucket["descriptions"].append(step.description)
                step_bucket["machines"].append(step.machine)
                step_bucket["notes"].append(step.note)

    ordered_stage_buckets = sorted(
        stage_buckets.values(),
        key=lambda bucket: (
            sum(bucket["positions"]) / max(len(bucket["positions"]), 1),  # type: ignore[index]
            bucket["occurrence_index"],  # type: ignore[index]
            bucket["stage"],  # type: ignore[index]
        ),
    )

    result: list[ParamJsonStageOut] = []
    for bucket in ordered_stage_buckets:
        step_buckets: dict[str, dict[str, object]] = bucket["steps"]  # type: ignore[assignment]
        ordered_steps = sorted(
            step_buckets.values(),
            key=lambda item: (
                sum(item["positions"]) / max(len(item["positions"]), 1),  # type: ignore[index]
                item["name"],  # type: ignore[index]
            ),
        )
        steps = [
            ParamJsonStepOut(
                name=step_bucket["name"],  # type: ignore[index]
                description=merge_text_by_count(step_bucket["descriptions"]),  # type: ignore[arg-type]
                machine=merge_text_by_count(step_bucket["machines"]),  # type: ignore[arg-type]
                note=merge_text_by_count(step_bucket["notes"]),  # type: ignore[arg-type]
                evidence_count=step_bucket["doc_hits"],  # type: ignore[index]
            )
            for step_bucket in ordered_steps
        ]
        result.append(
            ParamJsonStageOut(
                stage=bucket["stage"],  # type: ignore[index]
                occurrence_index=bucket["occurrence_index"],  # type: ignore[index]
                evidence_count=bucket["doc_hits"],  # type: ignore[index]
                steps=steps,
            )
        )
    return result
