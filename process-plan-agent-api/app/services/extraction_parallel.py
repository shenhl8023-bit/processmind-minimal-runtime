"""第二步提炼中 CPU 密集解析的并发控制。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from functools import partial
import multiprocessing
import os
from typing import Callable, TypeVar

from app.core.compat import run_in_thread

T = TypeVar("T")

_SEM: asyncio.Semaphore | None = None
_PDF_POOL: ProcessPoolExecutor | None = None


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
        return await run_in_thread(func, *args, **kwargs)


async def run_pdf_extraction_cpu(func: Callable[..., T], /, *args: object, **kwargs: object) -> T:
    """Keep PyMuPDF out of concurrent threads, with one global worker limit.

    Only importable pure functions and plain arguments may cross this boundary.
    The executor owns capacity even when an asyncio waiter is cancelled: a
    still-running parse must not release a slot for another process.
    """
    global _PDF_POOL
    if _PDF_POOL is None:
        _PDF_POOL = ProcessPoolExecutor(
            max_workers=min(4, extraction_cpu_workers()),
            mp_context=multiprocessing.get_context("spawn"),
        )
    pool = _PDF_POOL
    try:
        return await asyncio.get_running_loop().run_in_executor(pool, partial(func, *args, **kwargs))
    except BrokenProcessPool:
        # A malformed PDF can terminate a native worker. Do not retry that
        # document, but let later requests create a healthy replacement pool.
        if _PDF_POOL is pool:
            _PDF_POOL = None
        pool.shutdown(wait=False)
        raise


def shutdown_pdf_extraction_pool() -> None:
    """Drain workers at application shutdown; also permits a later restart."""
    global _PDF_POOL
    pool, _PDF_POOL = _PDF_POOL, None
    if pool is not None:
        pool.shutdown(wait=True)


__all__ = [
    "extraction_cpu_workers",
    "get_extraction_cpu_semaphore",
    "reset_extraction_cpu_semaphore_for_tests",
    "run_extraction_cpu",
    "run_pdf_extraction_cpu",
    "shutdown_pdf_extraction_pool",
]
