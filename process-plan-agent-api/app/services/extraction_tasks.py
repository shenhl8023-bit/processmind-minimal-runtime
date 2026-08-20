"""
第二步提炼任务状态机与运行时任务注册表。
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Project

EXTRACTION_TASKS: dict[int, dict[str, object]] = {}
EXTRACTION_RUNNING: set[int] = set()
EXTRACTION_JOBS: dict[int, asyncio.Task] = {}
EXTRACTION_QUEUE_LOCKS: dict[int, asyncio.Lock] = {}

# 本 worker 进程唯一标识。环境变量只作为便于排查的前缀；每次进程启动仍追加随机值，
# 避免多个进程继承同一环境时被误判为相同 owner。
_worker_id_prefix = (os.getenv("PROCESSMIND_WORKER_ID") or "worker").strip()[:48] or "worker"
WORKER_ID = f"{_worker_id_prefix}-{uuid.uuid4().hex[:12]}"

# 租约默认有效期与心跳间隔。租约过期后才允许其他 worker 接管。
LEASE_TTL_SECONDS = 60
LEASE_RENEW_SECONDS = 30


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_extraction_task_state(project_id: int, **updates: object) -> dict[str, object]:
    payload = _merge_task_payload(EXTRACTION_TASKS.get(project_id), project_id, updates)
    EXTRACTION_TASKS[project_id] = payload
    return payload


def _merge_task_payload(
    current: dict[str, object] | None,
    project_id: int,
    updates: dict[str, object],
) -> dict[str, object]:
    current = current or {}
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
        "owner_id": current.get("owner_id"),
        "lease_expires_at": current.get("lease_expires_at"),
        "heartbeat_at": current.get("heartbeat_at"),
        "attempt": int(current.get("attempt") or 0),
    }
    payload.update(updates)
    if payload.get("task_status") == "running" and not payload.get("started_at"):
        payload["started_at"] = now_iso()
    if payload.get("task_status") in {"completed", "failed"} and not payload.get("finished_at"):
        payload["finished_at"] = now_iso()
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
        "owner_id": None if payload.get("owner_id") is None else str(payload.get("owner_id")),
        "lease_expires_at": None if payload.get("lease_expires_at") is None else str(payload.get("lease_expires_at")),
        "heartbeat_at": None if payload.get("heartbeat_at") is None else str(payload.get("heartbeat_at")),
        "attempt": int(payload.get("attempt") or 0),
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
                force_reextract, owner_id, lease_expires_at, heartbeat_at, attempt
            )
            VALUES (
                :project_id, :task_status, :stage, :message, :error, :progress,
                :started_at, :updated_at, :finished_at, :project_status, :harness_json,
                :force_reextract, :owner_id, :lease_expires_at, :heartbeat_at, :attempt
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
                force_reextract = excluded.force_reextract,
                owner_id = excluded.owner_id,
                lease_expires_at = excluded.lease_expires_at,
                heartbeat_at = excluded.heartbeat_at,
                attempt = excluded.attempt
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
        "owner_id": mapping.get("owner_id"),
        "lease_expires_at": mapping.get("lease_expires_at"),
        "heartbeat_at": mapping.get("heartbeat_at"),
        "attempt": int(mapping.get("attempt") or 0),
    }
    return payload


async def load_extraction_task_state(db: AsyncSession, project_id: int) -> dict[str, object] | None:
    row = (
        await db.execute(
            text("""
                SELECT project_id, task_status, stage, message, error, progress,
                       started_at, updated_at, finished_at, project_status, harness_json,
                       force_reextract, owner_id, lease_expires_at, heartbeat_at, attempt
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


def _lease_expiry(task: dict[str, object] | None) -> datetime | None:
    if not task:
        return None
    return parse_iso_datetime(task.get("lease_expires_at"))


def is_lease_fresh(task: dict[str, object] | None) -> bool:
    """数据库租约是否仍然有效（未过期）。"""
    expiry = _lease_expiry(task)
    if expiry is None:
        return False
    now = datetime.now(expiry.tzinfo or timezone.utc)
    return now < expiry


def is_lease_expired(task: dict[str, object] | None) -> bool:
    """数据库租约是否已过期（过期后允许其他 worker 接管）。"""
    expiry = _lease_expiry(task)
    if expiry is None:
        return True
    now = datetime.now(expiry.tzinfo or timezone.utc)
    return now >= expiry


def lease_stamp(now: datetime | None = None) -> str:
    """当前时间戳（租约字段统一使用 UTC ISO 字符串）。"""
    return (now or datetime.now(timezone.utc)).isoformat()


def lease_expiry_stamp(now: datetime | None = None) -> str:
    """租约过期时间：当前时间 + TTL。"""
    base = now or datetime.now(timezone.utc)
    return (base + timedelta(seconds=LEASE_TTL_SECONDS)).isoformat()


async def claim_task_lease(
    db: AsyncSession,
    project_id: int,
    owner_id: str | None = None,
    now: datetime | None = None,
    *,
    stage: str = "queued",
    message: str = "已进入后台提炼队列，正在准备任务...",
    progress: int = 5,
    project_status: str | None = None,
    force_reextract: bool = False,
) -> bool:
    """抢占任务级租约（原子条件更新）。

    仅当任务行满足以下任一条件时才写入新 owner：非 running、无 owner、本进程
    已是 owner、或现有租约已过期。两个进程真正并发抢占时，数据库的条件更新 +
    ``rowcount`` 保证只有一个进程拿到租约。成功时更新本进程缓存。
    """
    owner = owner_id or WORKER_ID
    stamp = lease_stamp(now)
    expiry = lease_expiry_stamp(now)
    result = await db.execute(
        text("""
            INSERT INTO extraction_task_states (
                project_id, task_status, stage, message, error, progress,
                started_at, updated_at, finished_at, project_status, harness_json,
                force_reextract, owner_id, lease_expires_at, heartbeat_at, attempt
            ) VALUES (
                :project_id, 'running', :stage, :message, NULL, :progress,
                :now_iso, :now_iso, NULL, :project_status, NULL,
                :force_reextract, :owner_id, :lease_expires_at, :heartbeat_at, 1
            )
            ON CONFLICT(project_id) DO UPDATE SET
                task_status = 'running',
                stage = excluded.stage,
                message = excluded.message,
                error = NULL,
                progress = excluded.progress,
                started_at = excluded.started_at,
                updated_at = excluded.updated_at,
                finished_at = NULL,
                project_status = excluded.project_status,
                harness_json = NULL,
                force_reextract = excluded.force_reextract,
                owner_id = excluded.owner_id,
                lease_expires_at = excluded.lease_expires_at,
                heartbeat_at = excluded.heartbeat_at,
                attempt = extraction_task_states.attempt + 1
            WHERE extraction_task_states.task_status <> 'running'
               OR extraction_task_states.owner_id IS NULL
               OR extraction_task_states.owner_id = :owner_id
               OR extraction_task_states.lease_expires_at IS NULL
               OR extraction_task_states.lease_expires_at <= :now_iso
        """),
        {
            "project_id": project_id,
            "owner_id": owner,
            "lease_expires_at": expiry,
            "heartbeat_at": stamp,
            "now_iso": stamp,
            "stage": stage,
            "message": message,
            "progress": int(progress),
            "project_status": project_status,
            "force_reextract": bool(force_reextract),
        },
    )
    if not result.rowcount:
        # 被他人持有新鲜租约：抢占失败，不污染本进程缓存。
        return False
    await load_extraction_task_state(db, project_id)
    return True


async def complete_task_if_not_running(
    db: AsyncSession,
    project_id: int,
    *,
    message: str,
    project_status: str | None,
) -> tuple[bool, dict[str, object] | None]:
    """已有结果快捷返回：仅在不存在新鲜 running 租约时写入 completed。"""
    stamp = now_iso()
    result = await db.execute(
        text("""
            INSERT INTO extraction_task_states (
                project_id, task_status, stage, message, error, progress,
                started_at, updated_at, finished_at, project_status, harness_json,
                force_reextract, owner_id, lease_expires_at, heartbeat_at, attempt
            ) VALUES (
                :project_id, 'completed', 'route_set_ready', :message, NULL, 100,
                NULL, :now_iso, :now_iso, :project_status, NULL,
                0, NULL, NULL, NULL, 0
            )
            ON CONFLICT(project_id) DO UPDATE SET
                task_status = 'completed',
                stage = 'route_set_ready',
                message = excluded.message,
                error = NULL,
                progress = 100,
                updated_at = excluded.updated_at,
                finished_at = excluded.finished_at,
                project_status = excluded.project_status,
                harness_json = NULL,
                force_reextract = 0,
                owner_id = NULL,
                lease_expires_at = NULL,
                heartbeat_at = NULL
            WHERE extraction_task_states.task_status <> 'running'
               OR extraction_task_states.lease_expires_at IS NULL
               OR extraction_task_states.lease_expires_at <= :now_iso
        """),
        {
            "project_id": project_id,
            "message": message,
            "project_status": project_status,
            "now_iso": stamp,
        },
    )
    if not result.rowcount:
        return False, await load_extraction_task_state(db, project_id)
    return True, await load_extraction_task_state(db, project_id)


async def renew_task_lease(
    db: AsyncSession,
    project_id: int,
    owner_id: str | None = None,
    now: datetime | None = None,
) -> bool:
    """续租：仅当仍持有该租约（owner 匹配）时更新过期时间与心跳。"""
    owner = owner_id or WORKER_ID
    stamp = lease_stamp(now)
    result = await db.execute(
        text("""
            UPDATE extraction_task_states
            SET lease_expires_at = :lease_expires_at,
                heartbeat_at = :heartbeat_at
            WHERE project_id = :project_id
              AND owner_id = :owner_id
              AND task_status = 'running'
              AND lease_expires_at > :heartbeat_at
        """),
        {
            "project_id": project_id,
            "owner_id": owner,
            "lease_expires_at": lease_expiry_stamp(now),
            "heartbeat_at": stamp,
        },
    )
    if not result.rowcount:
        return False
    task = EXTRACTION_TASKS.get(project_id) or set_extraction_task_state(project_id)
    EXTRACTION_TASKS[project_id] = set_extraction_task_state(
        project_id,
        lease_expires_at=lease_expiry_stamp(now),
        heartbeat_at=stamp,
        owner_id=owner,
    )
    return True


async def update_running_task_state_owned(
    db: AsyncSession,
    project_id: int,
    owner_id: str | None,
    **updates: object,
) -> bool:
    """仅由当前租约 owner 更新运行态，不改变租约期限。"""
    owner = owner_id or WORKER_ID
    current = await load_extraction_task_state(db, project_id)
    payload = _merge_task_payload(current, project_id, updates)
    params = _task_db_params(payload)
    params["owner_id"] = owner
    params["now_iso"] = now_iso()
    result = await db.execute(
        text("""
            UPDATE extraction_task_states
            SET stage = :stage,
                message = :message,
                error = :error,
                progress = :progress,
                started_at = :started_at,
                updated_at = :updated_at,
                finished_at = :finished_at,
                project_status = :project_status,
                harness_json = :harness_json,
                force_reextract = :force_reextract
            WHERE project_id = :project_id
              AND owner_id = :owner_id
              AND task_status = 'running'
              AND lease_expires_at > :now_iso
        """),
        params,
    )
    if not result.rowcount:
        return False
    payload["owner_id"] = owner
    EXTRACTION_TASKS[project_id] = payload
    return True


async def update_task_state_owned(
    db: AsyncSession,
    project_id: int,
    owner_id: str | None,
    **updates: object,
) -> bool:
    """仅当 owner 仍持有租约时条件写入任务终态。

    用于完成/失败等终态写入：WHERE 限定 ``owner_id = :owner AND task_status = 'running'``，
    旧 owner 在恢复后（任务已被新 owner 接管或已终态）无法覆盖。终态写入同时释放
    租约（``owner_id = NULL``、lease/heartbeat 清空）。被接管时返回 False，调用方应
    跳过项目结果提交。
    """
    owner = owner_id or WORKER_ID
    task = await load_extraction_task_state(db, project_id)
    payload = _merge_task_payload(task, project_id, updates)
    payload.update(
        owner_id=None,
        lease_expires_at=None,
        heartbeat_at=None,
    )
    params = _task_db_params(payload)
    params["expected_owner_id"] = owner
    params["now_iso"] = now_iso()
    result = await db.execute(
        text("""
            UPDATE extraction_task_states
            SET task_status = :task_status,
                stage = :stage,
                message = :message,
                error = :error,
                progress = :progress,
                started_at = :started_at,
                updated_at = :updated_at,
                finished_at = :finished_at,
                project_status = :project_status,
                harness_json = :harness_json,
                force_reextract = :force_reextract,
                owner_id = NULL,
                lease_expires_at = NULL,
                heartbeat_at = NULL
            WHERE project_id = :project_id
              AND owner_id = :expected_owner_id
              AND task_status = 'running'
              AND lease_expires_at > :now_iso
        """),
        params,
    )
    if not result.rowcount:
        return False
    EXTRACTION_TASKS[project_id] = payload
    return True


async def fail_stale_task_state(
    db: AsyncSession,
    project_id: int,
    **updates: object,
) -> tuple[bool, dict[str, object] | None]:
    """仅当任务仍缺失或数据库租约仍已过期时写入失败状态。"""
    current = await load_extraction_task_state(db, project_id)
    if current and current.get("task_status") != "running":
        return False, current
    payload = _merge_task_payload(current, project_id, updates)
    payload.update(owner_id=None, lease_expires_at=None, heartbeat_at=None)
    params = _task_db_params(payload)
    params["now_iso"] = now_iso()
    if current:
        result = await db.execute(
            text("""
                UPDATE extraction_task_states
                SET task_status = :task_status,
                    stage = :stage,
                    message = :message,
                    error = :error,
                    progress = :progress,
                    started_at = :started_at,
                    updated_at = :updated_at,
                    finished_at = :finished_at,
                    project_status = :project_status,
                    harness_json = :harness_json,
                    force_reextract = :force_reextract,
                    owner_id = NULL,
                    lease_expires_at = NULL,
                    heartbeat_at = NULL
                WHERE project_id = :project_id
                  AND task_status = 'running'
                  AND (lease_expires_at IS NULL OR lease_expires_at <= :now_iso)
            """),
            params,
        )
    else:
        result = await db.execute(
            text("""
                INSERT INTO extraction_task_states (
                    project_id, task_status, stage, message, error, progress,
                    started_at, updated_at, finished_at, project_status, harness_json,
                    force_reextract, owner_id, lease_expires_at, heartbeat_at, attempt
                ) VALUES (
                    :project_id, :task_status, :stage, :message, :error, :progress,
                    :started_at, :updated_at, :finished_at, :project_status, :harness_json,
                    :force_reextract, NULL, NULL, NULL, :attempt
                )
                ON CONFLICT(project_id) DO NOTHING
            """),
            params,
        )
    if not result.rowcount:
        return False, await load_extraction_task_state(db, project_id)
    EXTRACTION_TASKS[project_id] = payload
    return True, payload


def is_stale_task_state(project: Project, task: dict[str, object] | None) -> bool:
    if not task:
        return False
    project_created_at = getattr(project, "created_at", None)
    task_started_at = parse_iso_datetime(task.get("started_at"))
    if project_created_at and getattr(project_created_at, "tzinfo", None) is None:
        project_created_at = project_created_at.replace(tzinfo=timezone.utc)
    if project_created_at and task_started_at and task_started_at < project_created_at:
        return True
    if task.get("task_status") != "running":
        return False
    # 数据库租约仍然有效 -> 视为活跃，不判定为过期。
    if is_lease_fresh(task):
        return False
    task_updated_at = parse_iso_datetime(task.get("updated_at"))
    if task_updated_at:
        now = datetime.now(task_updated_at.tzinfo or timezone.utc)
        if now - task_updated_at > timedelta(minutes=10):
            return True
    # 无租约（旧数据）或租约已过期：按运行状态视作超时中断。
    return True


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
    "WORKER_ID",
    "cancel_extraction_task",
    "claim_task_lease",
    "complete_task_if_not_running",
    "delete_extraction_task_state",
    "fail_stale_task_state",
    "get_extraction_queue_lock",
    "is_lease_expired",
    "is_lease_fresh",
    "is_stale_task_state",
    "lease_stamp",
    "load_extraction_task_state",
    "now_iso",
    "parse_iso_datetime",
    "renew_task_lease",
    "save_extraction_task_state",
    "set_extraction_task_state",
    "task_status_from_project_status",
    "update_task_state_owned",
    "update_running_task_state_owned",
]
