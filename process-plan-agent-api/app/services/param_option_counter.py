"""
参数问答候选项计数工具。

这里集中处理样本属性字段的计数、分类命中和特征细化选项生成，
让 generate.py 只负责编排问答流程。
"""
from __future__ import annotations

import re
from collections import Counter

from app.schemas.schemas import ParamConfirmOptionOut, ParamReviewedFactorOut


def count_attr_values_by_keys(rows: list[dict[str, str]], keys: list[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for attrs in rows:
        for key in keys:
            value = str(attrs.get(key, "")).strip()
            if value:
                counter[value] += 1
    return counter


def count_attr_values_by_key_tokens(rows: list[dict[str, str]], include_tokens: tuple[str, ...]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for attrs in rows:
        for key, raw_value in attrs.items():
            if not any(token in key for token in include_tokens):
                continue
            value = str(raw_value or "").strip()
            if not value or value in {"是", "否"}:
                continue
            counter[value] += 1
    return counter


def count_positive_attr_labels(rows: list[dict[str, str]], include_tokens: tuple[str, ...]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for attrs in rows:
        for key, raw_value in attrs.items():
            if not any(token in key for token in include_tokens):
                continue
            value = str(raw_value or "").strip()
            if value in {"是", "true", "True", "TRUE", "1"}:
                counter[key] += 1
    return counter


def count_category_matches(
    rows: list[dict[str, str]],
    mapping: dict[str, tuple[str, ...]],
    *,
    positive_only: bool = False,
) -> Counter[str]:
    counter: Counter[str] = Counter()
    positive_values = {"是", "true", "True", "TRUE", "1"}
    for attrs in rows:
        for key, raw_value in attrs.items():
            label = str(key or "").strip()
            if not label:
                continue
            value = str(raw_value or "").strip()
            if positive_only and value not in positive_values:
                continue
            haystack = f"{label} {value}"
            for category, tokens in mapping.items():
                if any(token in haystack for token in tokens):
                    counter[category] += 1
                    break
    return counter


def count_feature_attr_labels(
    rows: list[dict[str, str]],
    include_tokens: tuple[str, ...],
    exclude_tokens: tuple[str, ...] = (),
) -> Counter[str]:
    counter: Counter[str] = Counter()
    negative_values = {"否", "false", "False", "FALSE", "0", ""}
    for attrs in rows:
        for key, raw_value in attrs.items():
            label = str(key or "").strip()
            if not label:
                continue
            if not any(token in label for token in include_tokens):
                continue
            if exclude_tokens and any(token in label for token in exclude_tokens):
                continue
            value = str(raw_value or "").strip()
            if value in negative_values:
                continue
            counter[label] += 1
    return counter


def top_counter_options(counter: Counter[str], value_prefix: str = "", limit: int = 5) -> list[ParamConfirmOptionOut]:
    options: list[ParamConfirmOptionOut] = []
    for value, count in counter.most_common(limit):
        normalized_value = f"{value_prefix}{value}" if value_prefix else value
        options.append(ParamConfirmOptionOut(value=normalized_value, label=value, count=count))
    return options


def build_feature_detail_options(
    rows: list[dict[str, str]],
    include_tokens: tuple[str, ...],
    exclude_tokens: tuple[str, ...],
    fallback_labels: list[str],
    value_prefix: str,
) -> list[ParamConfirmOptionOut]:
    counter = count_feature_attr_labels(rows, include_tokens, exclude_tokens)
    options = top_counter_options(counter, value_prefix=value_prefix)
    if options:
        return options
    return [
        ParamConfirmOptionOut(value=f"{value_prefix}{label}", label=label, count=0)
        for label in fallback_labels
    ]


def build_feature_detail_options_with_snapshot_fallback(
    *,
    rows: list[dict[str, str]],
    target_factor: ParamReviewedFactorOut,
    include_tokens: tuple[str, ...],
    exclude_tokens: tuple[str, ...],
    fallback_labels: list[str],
    value_prefix: str,
    snapshot_include_tokens: tuple[str, ...] | None = None,
) -> list[ParamConfirmOptionOut]:
    options = build_feature_detail_options(
        rows=rows,
        include_tokens=include_tokens,
        exclude_tokens=exclude_tokens,
        fallback_labels=fallback_labels,
        value_prefix=value_prefix,
    )
    if any(option.count > 0 for option in options):
        return options
    snapshot_options = build_snapshot_detail_options(
        target_factor=target_factor,
        include_tokens=snapshot_include_tokens or include_tokens,
        exclude_tokens=exclude_tokens,
        value_prefix=value_prefix,
    )
    if snapshot_options:
        return snapshot_options
    return options


def build_snapshot_detail_options(
    target_factor: ParamReviewedFactorOut,
    include_tokens: tuple[str, ...],
    exclude_tokens: tuple[str, ...],
    value_prefix: str,
) -> list[ParamConfirmOptionOut]:
    texts = [
        str(target_factor.factor_key or "").strip(),
        str(target_factor.factor_label or "").strip(),
        str(target_factor.expected_value or "").strip(),
        str(target_factor.reason_text or "").strip(),
    ]
    labels: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        parts = re.split(r"[=,，;；/\\s]+", text)
        for raw in parts:
            item = raw.strip()
            if not item:
                continue
            if exclude_tokens and any(token in item for token in exclude_tokens):
                continue
            if not any(token in item for token in include_tokens):
                continue
            if item in seen:
                continue
            seen.add(item)
            labels.append(item)
    return [
        ParamConfirmOptionOut(value=f"{value_prefix}{label}", label=label, count=0)
        for label in labels[:5]
    ]
