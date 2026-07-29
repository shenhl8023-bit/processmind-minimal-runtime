"""
第二步提炼任务状态机与运行时任务注册表。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Project

EXTRACTION_TASKS: dict[int, dict[str, object]] = {}
EXTRACTION_RUNNING: set[int] = set()
EXTRACTION_JOBS: dict[int, asyncio.Task] = {}
EXTRACTION_QUEUE_LOCKS: dict[int, asyncio.Lock] = {}


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
        "force_reextract": bool(current.get("force_reextract", False)),
    }
    payload.update(updates)
    if payload.get("task_status") == "running" and not payload.get("started_at"):
        payload["started_at"] = now_iso()
    if payload.get("task_status") in {"completed", "failed"} and not payload.get("finished_at"):
        payload["finished_at"] = now_iso()
    EXTRACTION_TASKS[project_id] = payload
    return payload


def get_extraction_queue_lock(project_id: int) -> asyncio.Lock:
    lock = EXTRACTION_QUEUE_LOCKS.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        EXTRACTION_QUEUE_LOCKS[project_id] = lock
    return lock


def _task_db_params(payload: dict[str, object]) -> dict[str, object]:
    harness = payload.get("harness")
    return {
        "project_id": int(payload.get("project_id") or 0),
        "task_status": str(payload.get("task_status") or "idle"),
        "stage": str(payload.get("stage") or "idle"),
        "message": str(payload.get("message") or ""),
        "error": None if payload.get("error") is None else str(payload.get("error")),
        "progress": int(payload.get("progress") or 0),
        "started_at": None if payload.get("started_at") is None else str(payload.get("started_at")),
        "updated_at": None if payload.get("updated_at") is None else str(payload.get("updated_at")),
        "finished_at": None if payload.get("finished_at") is None else str(payload.get("finished_at")),
        "project_status": None if payload.get("project_status") is None else str(payload.get("project_status")),
        "harness_json": None if harness is None else json.dumps(harness, ensure_ascii=False),
        "force_reextract": bool(payload.get("force_reextract", False)),
    }


async def save_extraction_task_state(
    db: AsyncSession,
    project_id: int,
    **updates: object,
) -> dict[str, object]:
    payload = set_extraction_task_state(project_id, **updates)
    await db.execute(
        text("""
            INSERT INTO extraction_task_states (
                project_id, task_status, stage, message, error, progress,
                started_at, updated_at, finished_at, project_status, harness_json,
                force_reextract
            )
            VALUES (
                :project_id, :task_status, :stage, :message, :error, :progress,
                :started_at, :updated_at, :finished_at, :project_status, :harness_json,
                :force_reextract
            )
            ON CONFLICT(project_id) DO UPDATE SET
                task_status = excluded.task_status,
                stage = excluded.stage,
                message = excluded.message,
                error = excluded.error,
                progress = excluded.progress,
                started_at = excluded.started_at,
                updated_at = excluded.updated_at,
                finished_at = excluded.finished_at,
                project_status = excluded.project_status,
                harness_json = excluded.harness_json,
                force_reextract = excluded.force_reextract
        """),
        _task_db_params(payload),
    )
    return payload


def _task_payload_from_row(row: object) -> dict[str, object]:
    mapping = dict(row)
    harness_json = mapping.pop("harness_json", None)
    harness = None
    if harness_json:
        try:
            harness = json.loads(str(harness_json))
        except json.JSONDecodeError:
            harness = None
    payload: dict[str, object] = {
        "project_id": mapping.get("project_id"),
        "task_status": mapping.get("task_status") or "idle",
        "stage": mapping.get("stage") or "idle",
        "message": mapping.get("message") or "",
        "error": mapping.get("error"),
        "progress": int(mapping.get("progress") or 0),
        "started_at": mapping.get("started_at"),
        "updated_at": mapping.get("updated_at"),
        "finished_at": mapping.get("finished_at"),
        "project_status": mapping.get("project_status"),
        "harness": harness,
        "force_reextract": bool(mapping.get("force_reextract", False)),
    }
    return payload


async def load_extraction_task_state(db: AsyncSession, project_id: int) -> dict[str, object] | None:
    row = (
        await db.execute(
            text("""
                SELECT project_id, task_status, stage, message, error, progress,
                       started_at, updated_at, finished_at, project_status, harness_json,
                       force_reextract
                FROM extraction_task_states
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        )
    ).mappings().one_or_none()
    if not row:
        return None
    payload = _task_payload_from_row(row)
    EXTRACTION_TASKS[project_id] = payload
    return payload


async def delete_extraction_task_state(db: AsyncSession, project_id: int) -> None:
    EXTRACTION_TASKS.pop(project_id, None)
    await db.execute(
        text("DELETE FROM extraction_task_states WHERE project_id = :project_id"),
        {"project_id": project_id},
    )


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
    "EXTRACTION_QUEUE_LOCKS",
    "EXTRACTION_RUNNING",
    "EXTRACTION_TASKS",
    "cancel_extraction_task",
    "delete_extraction_task_state",
    "get_extraction_queue_lock",
    "is_stale_task_state",
    "load_extraction_task_state",
    "now_iso",
    "parse_iso_datetime",
    "save_extraction_task_state",
    "set_extraction_task_state",
    "task_status_from_project_status",
]
