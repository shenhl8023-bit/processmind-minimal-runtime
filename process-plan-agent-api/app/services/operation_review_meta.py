from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Document, Operation
from app.services.harness_validators import is_harness_warning_factor_name


def _split_source_names(source: str | None) -> list[str]:
    if not source:
        return []
    parts = [
        item.strip()
        for item in re.split(r"[;,；，\n]+", source)
        if item and item.strip()
    ]
    return list(dict.fromkeys(parts))


def _operation_has_user_note(op: Operation) -> bool:
    description = (op.description or "").strip()
    if "补充说明：" in description:
        return True
    return any(bool(f.confirmed) for f in op.factors if not is_harness_warning_factor_name(f.name))


def _operation_has_data_issue(op: Operation, coverage_count: int) -> bool:
    if coverage_count == 0:
        return True
    text = " ".join(filter(None, [op.description, op.source])).lower()
    issue_tokens = (
        "提取失败",
        "解析失败",
        "缺页",
        "不完整",
        "范围不一致",
        "数据问题",
        "待核查",
        "ocr",
        "识别失败",
    )
    return any(token in text for token in issue_tokens)


def build_operation_review_meta(op: Operation, sample_count: int) -> dict[str, object]:
    coverage_count = len(_split_source_names(op.source))
    has_user_note = _operation_has_user_note(op)
    effective_factors = [f for f in op.factors if not is_harness_warning_factor_name(f.name)]
    reviewed = has_user_note or any(bool(f.confirmed) for f in effective_factors)
    strong_factor_count = sum(1 for f in effective_factors if (f.strength or "").upper() == "STRONG")
    has_exception = sample_count > 0 and 0 < coverage_count < sample_count

    if _operation_has_data_issue(op, coverage_count):
        return {
            "review_status": "data_issue",
            "review_label": "数据待核查",
            "review_reason": "当前工序的来源样本或文本证据不足，建议先核查样本完整性、提取质量和分析范围。",
            "sample_count": sample_count,
            "coverage_count": coverage_count,
            "has_exception": has_exception,
            "has_user_note": has_user_note,
            "reviewed": reviewed,
        }

    if reviewed and (op.confidence or "").upper() == "STRONG":
        return {
            "review_status": "stable",
            "review_label": "稳定",
            "review_reason": "当前工序已经结合人工确认或补充说明收敛，可直接进入规则沉淀。",
            "sample_count": sample_count,
            "coverage_count": coverage_count,
            "has_exception": has_exception,
            "has_user_note": has_user_note,
            "reviewed": reviewed,
        }

    if sample_count > 0 and coverage_count == sample_count:
        return {
            "review_status": "stable",
            "review_label": "稳定",
            "review_reason": f"当前工序在 {coverage_count}/{sample_count} 份样本中稳定出现，按当前审核原则可直接视为稳定工序。",
            "sample_count": sample_count,
            "coverage_count": coverage_count,
            "has_exception": False,
            "has_user_note": has_user_note,
            "reviewed": reviewed,
        }

    if has_exception:
        return {
            "review_status": "exception",
            "review_label": "存在例外",
            "review_reason": f"当前工序在 {coverage_count}/{sample_count} 份样本中出现，但仍存在未解释例外。按当前审核原则，任何非全覆盖工序都需要先处理例外边界。",
            "sample_count": sample_count,
            "coverage_count": coverage_count,
            "has_exception": True,
            "has_user_note": has_user_note,
            "reviewed": reviewed,
        }

    if strong_factor_count > 0 or len(effective_factors) > 0 or (op.confidence or "").upper() == "STRONG":
        return {
            "review_status": "pending_confirm",
            "review_label": "待确认",
            "review_reason": "当前工序已经收敛到少量候选边界，适合继续通过结构化问题或专家审核完成确认。",
            "sample_count": sample_count,
            "coverage_count": coverage_count,
            "has_exception": has_exception,
            "has_user_note": has_user_note,
            "reviewed": reviewed,
        }

    return {
        "review_status": "evidence",
        "review_label": "证据不足",
        "review_reason": "当前样本中存在分支，但还未能稳定收敛到可执行边界，建议结合专家说明继续补证据。",
        "sample_count": sample_count,
        "coverage_count": coverage_count,
        "has_exception": has_exception,
        "has_user_note": has_user_note,
        "reviewed": reviewed,
    }


async def get_project_sample_count(db: AsyncSession, project_id: int) -> int:
    result = await db.execute(select(Document.id).where(Document.project_id == project_id))
    return len(result.all())
