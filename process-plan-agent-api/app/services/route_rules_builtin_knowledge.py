"""
工艺规程模式内置知识包缓存。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from app.core.paths import ROUTE_RULE_KNOWLEDGE_DIR


BUILTIN_KNOWLEDGE_FILES = (
    "01_通用工艺路线基础.md",
    "02_回转类规则因素与按需工序.md",
    "03_业务场景专用知识.md",
    "04_特征分类与提问词表.md",
    "05_问题生成与循环控制规则.md",
    "06_规则输出格式规范.md",
)

BUILTIN_KNOWLEDGE_CACHE: list[str] = []
BUILTIN_KNOWLEDGE_CACHE_INFO: dict[str, object] = {
    "loaded": False,
    "loaded_at": None,
    "file_count": 0,
    "block_count": 0,
    "files": [],
    "missing_files": [],
}


def _read_builtin_knowledge_blocks(
    max_chars_per_file: int = 1000,
    max_lines_per_file: int = 14,
) -> tuple[list[str], list[str], list[str]]:
    if not os.path.isdir(ROUTE_RULE_KNOWLEDGE_DIR):
        return [], [], list(BUILTIN_KNOWLEDGE_FILES)

    blocks: list[str] = []
    existing_files: list[str] = []
    missing_files: list[str] = []
    for filename in BUILTIN_KNOWLEDGE_FILES:
        filepath = os.path.join(ROUTE_RULE_KNOWLEDGE_DIR, filename)
        if not os.path.isfile(filepath):
            missing_files.append(filename)
            continue
        existing_files.append(filename)
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                text = handle.read().strip()
        except OSError:
            continue

        if not text:
            continue

        title = os.path.splitext(filename)[0]
        body_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("# "):
                title = line[2:].strip() or title
                continue
            if line.startswith("#"):
                line = line.lstrip("#").strip()
            if line.startswith(">"):
                line = line.lstrip(">").strip()
            if not line:
                continue
            body_lines.append(line)
            if len(body_lines) >= max_lines_per_file:
                break

        snippet = "\n".join(f"- {line}" for line in body_lines).strip()
        if not snippet:
            continue
        if len(snippet) > max_chars_per_file:
            snippet = snippet[:max_chars_per_file].rstrip() + "..."
        blocks.append(f"【系统内置知识包：{title}】\n{snippet}")

    return blocks, existing_files, missing_files


def preload_builtin_knowledge_cache(
    force: bool = False,
    max_chars_per_file: int = 1000,
    max_lines_per_file: int = 14,
) -> dict[str, object]:
    global BUILTIN_KNOWLEDGE_CACHE, BUILTIN_KNOWLEDGE_CACHE_INFO

    if BUILTIN_KNOWLEDGE_CACHE_INFO["loaded"] and not force:
        return dict(BUILTIN_KNOWLEDGE_CACHE_INFO)

    blocks, existing_files, missing_files = _read_builtin_knowledge_blocks(
        max_chars_per_file=max_chars_per_file,
        max_lines_per_file=max_lines_per_file,
    )
    BUILTIN_KNOWLEDGE_CACHE = blocks
    BUILTIN_KNOWLEDGE_CACHE_INFO = {
        "loaded": True,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(existing_files),
        "block_count": len(blocks),
        "files": existing_files,
        "missing_files": missing_files,
    }
    return dict(BUILTIN_KNOWLEDGE_CACHE_INFO)


def load_builtin_knowledge_blocks(
    max_chars_per_file: int = 1000,
    max_lines_per_file: int = 14,
) -> list[str]:
    if not BUILTIN_KNOWLEDGE_CACHE_INFO["loaded"]:
        preload_builtin_knowledge_cache(
            max_chars_per_file=max_chars_per_file,
            max_lines_per_file=max_lines_per_file,
        )
    return list(BUILTIN_KNOWLEDGE_CACHE)
