"""
第二步路线归并中的明细摘要工具。
"""

from __future__ import annotations

import re


def extract_detail_excerpt(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").replace("\u3000", " ")).strip()
    if len(normalized) <= 120:
        return normalized
    return normalized[:117] + "..."
