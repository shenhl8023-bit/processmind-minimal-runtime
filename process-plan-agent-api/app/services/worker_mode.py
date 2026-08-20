"""
单 worker 部署约束。

ProcessMind 的提取任务运行时注册表（EXTRACTION_TASKS / EXTRACTION_RUNNING /
EXTRACTION_JOBS / EXTRACTION_QUEUE_LOCKS）保存在进程内存中，不会跨进程共享。
因此后端必须按单 worker 运行：默认即单 worker；只有显式打开多 worker 才改变
该声明，并会在启动时记录警告。

相关风险与背景见 docs/主要风险与优化修改建议.md 第 3 节。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

SINGLE_WORKER_ENV_KEY = "PROCESSMIND_SINGLE_WORKER"
# 默认单 worker。后端当前只在进程内维护提取任务注册表，多 worker 会互相看不到
# 彼此的 asyncio.Task，导致任务状态不可靠。
DEFAULT_SINGLE_WORKER = True

# uvicorn / 常见 WSGI 服务器约定的 worker 数环境变量，用于提示部署人员没有显式
# 关闭单 worker 却横向扩展的配置错误。
_WORKER_COUNT_ENV_KEYS = ("UVICORN_WORKERS", "WEB_CONCURRENCY")


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}


def single_worker_enabled() -> bool:
    """是否声明为单 worker 模式。

    默认返回 True；通过 `PROCESSMIND_SINGLE_WORKER=false` 可显式放开。
    """
    raw = os.getenv(SINGLE_WORKER_ENV_KEY)
    if raw is None:
        return DEFAULT_SINGLE_WORKER
    return _env_truthy(raw)


def _configured_worker_count() -> int | None:
    configured_counts: list[int] = []
    for key in _WORKER_COUNT_ENV_KEYS:
        raw = os.getenv(key)
        if raw is None:
            continue
        try:
            configured_counts.append(int(raw))
        except ValueError:
            logger.warning("忽略无效的 %s=%r worker 数配置。", key, raw)
    return max(configured_counts) if configured_counts else None


class MultiWorkerConfiguredError(RuntimeError):
    """声明单 worker 却检测到多 worker 配置时抛出，阻止 API 启动。"""


def check_single_worker() -> None:
    """启动时校验 worker 模式。

    声明单 worker（默认）时，若环境变量显式给出多 worker（``UVICORN_WORKERS`` /
    ``WEB_CONCURRENCY`` > 1），抛出 ``MultiWorkerConfiguredError`` 阻止启动——
    后台提取任务注册表只在进程内存，多 worker 会互相看不到彼此的任务状态。

    注意：uvicorn 的 ``--workers`` CLI 参数不经过环境变量，应用层无法探测；实际
    worker 数由启动脚本里的 ``--workers 1`` 与本检查共同保证。``PROCESSMIND_SINGLE_WORKER``
    是部署声明值，不等于事实。
    """
    if not single_worker_enabled():
        logger.warning(
            "PROCESSMIND_SINGLE_WORKER 已被显式关闭：后端将以多 worker 假设运行。"
            "提取任务注册表只存在于进程内存，多 worker 下任务状态不可靠，"
            "请勿在生产使用多 worker。"
        )
        return

    count = _configured_worker_count()
    if count is None or count <= 1:
        logger.info("ProcessMind API 以单 worker 模式运行（提取任务为进程内状态）。")
        return

    raise MultiWorkerConfiguredError(
        f"检测到多 worker 配置（worker 数={count}），但提取任务注册表只在进程内存中，"
        "多 worker 会互相看不到彼此的 asyncio.Task，导致任务状态不可靠。"
        "请以单一 uvicorn worker 运行（--workers 1），或显式设置 "
        "PROCESSMIND_SINGLE_WORKER=false 以确认你接受该风险。"
    )
