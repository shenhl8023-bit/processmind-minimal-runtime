"""第二步提炼中 CPU 密集解析的并发控制。

工艺规程 PDF 的文本抽取和表格识别会长时间占用 CPU。若直接在
asyncio 事件循环里跑，状态轮询、租约心跳和进度更新都会被堵住，
页面就会一直停在“正在提取工艺路线全集...”。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_SEM: asyncio.Semaphore | None = None


def extraction_cpu_workers() -> int:
    raw = (os.getenv("PROCESSMIND_EXTRACT_MAX_WORKERS") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return max(1, min(int(raw), 16))
    cpu = os.cpu_count() or 2
    return min(8, max(2, cpu))


def reset_extraction_cpu_semaphore_for_tests() -> None:
    global _SEM
    _SEM = None


def get_extraction_cpu_semaphore() -> asyncio.Semaphore:
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(extraction_cpu_workers())
    return _SEM


async def run_extraction_cpu(func: Callable[..., T], /, *args: object, **kwargs: object) -> T:
    async with get_extraction_cpu_semaphore():
        return await asyncio.to_thread(func, *args, **kwargs)


__all__ = [
    "extraction_cpu_workers",
    "get_extraction_cpu_semaphore",
    "reset_extraction_cpu_semaphore_for_tests",
    "run_extraction_cpu",
]
