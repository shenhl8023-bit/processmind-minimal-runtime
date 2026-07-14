"""
第二步提炼任务状态机与运行时任务注册表。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.models.models import Project

EXTRACTION_TASKS: dict[int, dict[str, object]] = {}
EXTRACTION_RUNNING: set[int] = set()
EXTRACTION_JOBS: dict[int, asyncio.Task] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_extraction_task_state(project_id: int, **updates: object) -> dict[str, object]:
    current = EXTRACTION_TASKS.get(project_id, {})
    payload = {
        "project_id": project_id,
        "task_status": current.get("task_status", "idle"),
        "stage": current.get("stage", "idle"),
        "message": current.get("message", ""),
        "error": current.get("error"),
        "progress": int(current.get("progress") or 0),
        "started_at": current.get("started_at"),
        "updated_at": now_iso(),
        "finished_at": current.get("finished_at"),
        "project_status": current.get("project_status"),
        "harness": current.get("harness"),
    }
    payload.update(updates)
    if payload.get("task_status") == "running" and not payload.get("started_at"):
        payload["started_at"] = now_iso()
    if payload.get("task_status") in {"completed", "failed"} and not payload.get("finished_at"):
        payload["finished_at"] = now_iso()
    EXTRACTION_TASKS[project_id] = payload
    return payload


def cancel_extraction_task(project_id: int) -> None:
    task = EXTRACTION_JOBS.pop(project_id, None)
    if task and not task.done():
        task.cancel()
    EXTRACTION_TASKS.pop(project_id, None)
    EXTRACTION_RUNNING.discard(project_id)


def parse_iso_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_stale_task_state(project: Project, task: dict[str, object] | None) -> bool:
    if not task:
        return False
    project_created_at = getattr(project, "created_at", None)
    task_started_at = parse_iso_datetime(task.get("started_at"))
    if project_created_at and getattr(project_created_at, "tzinfo", None) is None:
        project_created_at = project_created_at.replace(tzinfo=timezone.utc)
    if project_created_at and task_started_at and task_started_at < project_created_at:
        return True
    task_updated_at = parse_iso_datetime(task.get("updated_at"))
    if task.get("task_status") == "running" and task_updated_at:
        now = datetime.now(task_updated_at.tzinfo or timezone.utc)
        if now - task_updated_at > timedelta(minutes=10):
            return True
    return False


def task_status_from_project_status(project_status: str | None) -> tuple[str, str, str, int]:
    normalized = (project_status or "").strip().upper()
    if normalized == "EXTRACTING":
        return ("running", "extracting_operations", "正在提取工艺路线全集...", 25)
    if normalized in {"ROUTE_SET_READY", "BUILDING_RULE_ASSETS", "RULE_ASSETS_READY", "EXTRACTED"}:
        return ("completed", "route_set_ready", "工艺路线全集已生成，可进入路线归并。", 100)
    if normalized in {"EXTRACT_ERROR", "FAILED"}:
        return ("failed", "failed", "第二步提炼失败。", 100)
    return ("idle", "idle", "", 0)


__all__ = [
    "EXTRACTION_JOBS",
    "EXTRACTION_RUNNING",
    "EXTRACTION_TASKS",
    "cancel_extraction_task",
    "is_stale_task_state",
    "now_iso",
    "parse_iso_datetime",
    "set_extraction_task_state",
    "task_status_from_project_status",
]
