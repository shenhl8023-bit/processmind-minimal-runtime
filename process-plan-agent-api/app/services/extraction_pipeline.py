"""
第二步提炼任务编排服务。

这一层负责：
- 提炼任务启动与排队
- 后台 pipeline 编排
- 任务状态回传

避免这些运行时编排逻辑继续堆在 extract.py 的路由层。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Operation, Project
from app.services.extraction_lifecycle import (
    clear_project_extraction_results,
)
from app.services.extraction_tasks import (
    EXTRACTION_JOBS,
    EXTRACTION_RUNNING,
    EXTRACTION_TASKS,
    LEASE_RENEW_SECONDS,
    WORKER_ID,
    cancel_extraction_task,
    claim_task_lease,
    complete_task_if_not_running,
    fail_stale_task_state,
    get_extraction_queue_lock,
    is_lease_fresh,
    is_stale_task_state,
    load_extraction_task_state,
    renew_task_lease,
    set_extraction_task_state,
    task_status_from_project_status,
    update_task_state_owned,
    update_running_task_state_owned,
)

logger = logging.getLogger(__name__)
from app.services.llm_service import get_llm_config
from app.services.harness_validators import HarnessValidationError
from app.services.project_workflow_lifecycle import invalidate_project_workflow


AsyncSessionFactory = Callable[[], object]
AsyncProjectExtractor = Callable[[AsyncSession, int], Awaitable[object]]
AsyncSaveOps = Callable[[AsyncSession, int, object], Awaitable[None]]


def _has_active_local_job(project_id: int) -> bool:
    job = EXTRACTION_JOBS.get(project_id)
    return bool(
        project_id in EXTRACTION_RUNNING
        and job is not None
        and not job.done()
    )


async def _renew_lease_periodically(
    project_id: int,
    async_session_factory: AsyncSessionFactory,
    pipeline_task: asyncio.Task,
) -> None:
    """后台续租心跳：执行期间定时在数据库中刷新租约过期时间。"""
    try:
        while True:
            await asyncio.sleep(LEASE_RENEW_SECONDS)
            async with async_session_factory() as db:
                ok = await renew_task_lease(db, project_id, WORKER_ID)
                await db.commit()
            if not ok:
                logger.warning(
                    "Extraction task %s lost its lease; cancelling local pipeline",
                    project_id,
                )
                pipeline_task.cancel()
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Failed to renew extraction task lease for project %s", project_id)
        pipeline_task.cancel()


async def _commit_failed_task_state_owned(
    db: AsyncSession,
    *,
    project_id: int,
    owner: str,
    message: str,
    error: str,
    force_reextract: bool,
    harness: dict[str, object] | None = None,
) -> bool:
    """以 owner fencing 原子提交失败终态与项目状态，并重试 SQLite 锁冲突。"""
    for attempt in range(3):
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        committed = await update_task_state_owned(
            db,
            project_id,
            owner,
            task_status="failed",
            stage="failed",
            message=message,
            error=error,
            harness=harness,
            progress=100,
            project_status="EXTRACT_ERROR",
            force_reextract=force_reextract,
        )
        if not committed:
            await db.rollback()
            return False
        if project:
            project.status = "EXTRACT_ERROR"
        try:
            await db.commit()
            return True
        except OperationalError:
            await db.rollback()
            if attempt >= 2:
                raise
            await asyncio.sleep(0.3 * (attempt + 1))
    return False


async def run_extraction_pipeline(
    *,
    project_id: int,
    force_reextract: bool,
    async_session_factory: AsyncSessionFactory,
    extract_route_set_with_llm: AsyncProjectExtractor,
    save_ops: AsyncSaveOps,
) -> None:
    heartbeat_task: asyncio.Task | None = None
    # 本进程的任务租约 owner。完成/失败路径必须按此 owner 做条件终态写入，
    # 旧 owner 在恢复后无法覆盖新 owner 的状态。
    owner = WORKER_ID
    try:
        async with async_session_factory() as db:
            project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
            if not project:
                set_extraction_task_state(
                    project_id,
                    task_status="failed",
                    stage="failed",
                    message="任务不存在",
                    error="任务不存在",
                    progress=100,
                )
                return

            owned = await update_running_task_state_owned(
                db,
                project_id,
                owner,
                stage="extracting_operations",
                message="正在提取工艺路线全集...",
                error=None,
                progress=10,
                finished_at=None,
                harness=None,
                project_status="EXTRACTING",
                force_reextract=force_reextract,
            )
            if not owned:
                await db.rollback()
                owned = await claim_task_lease(
                    db,
                    project_id,
                    owner,
                    project_status="EXTRACTING",
                    force_reextract=force_reextract,
                )
            if not owned:
                await db.rollback()
                logger.warning(
                    "Extraction task %s did not acquire a lease at pipeline start",
                    project_id,
                )
                return
            await db.commit()
            heartbeat_task = asyncio.create_task(
                _renew_lease_periodically(
                    project_id,
                    async_session_factory,
                    asyncio.current_task(),
                )
            )

            await clear_project_extraction_results(
                db,
                project_id,
                preserve_document_details=not force_reextract,
            )
            # 释放 SQLite 写锁，保证独立心跳会话可以在耗时提取期间续租。下游结果
            # 已在接受任务时失效，因此这里的清理提交不代表提取成功。
            await db.commit()

            config = await get_llm_config()
            api_key = config["key"]
            use_llm = bool(api_key and api_key != "your-api-key-here")
            if not use_llm:
                raise HTTPException(400, "未配置大模型 API，第二步工艺路线全集提取必须依赖大模型。")

            ops_data = await extract_route_set_with_llm(db, project_id)
            if not ops_data:
                raise HTTPException(502, "大模型未返回可解析的工艺路线全集结果。")

            # LLM 调用可能超过一个租约周期。写业务结果前先做一次 owner + 新鲜租约
            # fencing，避免已被接管的旧 worker 写入任何工序数据。
            owned = await update_running_task_state_owned(
                db,
                project_id,
                owner,
                stage="extracting_operations",
                message="正在保存工艺路线全集...",
                progress=90,
                project_status="EXTRACTING",
            )
            if not owned:
                await db.rollback()
                logger.warning(
                    "Extraction task %s lost its lease before saving results",
                    project_id,
                )
                return
            await save_ops(db, project_id, ops_data)
            project.status = "ROUTE_SET_READY"

            # 工序、项目状态和终态 owner fencing 共用当前事务；条件写失败时回滚
            # 全部业务结果，不允许旧 worker 留下部分提交。
            committed = await update_task_state_owned(
                db,
                project_id,
                owner,
                task_status="completed",
                stage="route_set_ready",
                message="工艺路线全集已生成，可进入路线归并。",
                progress=100,
                error=None,
                project_status="ROUTE_SET_READY",
                force_reextract=force_reextract,
            )
            if not committed:
                logger.warning(
                    "Extraction task %s lease was taken over before completion; "
                    "skipping terminal write",
                    project_id,
                )
                await db.rollback()
                return
            await db.commit()
    except asyncio.CancelledError:
        logger.warning("Extraction task %s local pipeline was cancelled", project_id)
        return
    except HarnessValidationError as exc:
        async with async_session_factory() as db:
            try:
                committed = await _commit_failed_task_state_owned(
                    db,
                    project_id=project_id,
                    owner=owner,
                    message="第二步提炼被 Harness 校验拦截",
                    error=str(exc),
                    harness=exc.to_payload(),
                    force_reextract=force_reextract,
                )
                if not committed:
                    logger.warning(
                        "Extraction task %s lease was taken over before failure write; "
                        "skipping terminal write",
                        project_id,
                    )
            except Exception:
                await db.rollback()
    except Exception as exc:
        async with async_session_factory() as db:
            try:
                committed = await _commit_failed_task_state_owned(
                    db,
                    project_id=project_id,
                    owner=owner,
                    message="第二步提炼失败",
                    error=str(exc),
                    force_reextract=force_reextract,
                )
                if not committed:
                    logger.warning(
                        "Extraction task %s lease was taken over before failure write; "
                        "skipping terminal write",
                        project_id,
                    )
            except Exception:
                await db.rollback()
    finally:
        if heartbeat_task is not None and not heartbeat_task.done():
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        EXTRACTION_JOBS.pop(project_id, None)
        EXTRACTION_RUNNING.discard(project_id)


async def queue_extraction_job(
    *,
    project_id: int,
    force_reextract: bool,
    db: AsyncSession,
    project: Project,
    job_factory: Callable[[], asyncio.Task],
) -> dict[str, object]:
    config = await get_llm_config()
    api_key = config["key"]
    use_llm = bool(api_key and api_key != "your-api-key-here")
    if not use_llm:
        raise HTTPException(400, "未配置大模型 API，第二步工艺路线全集提取必须依赖大模型。")

    async with get_extraction_queue_lock(project_id):
        return await _queue_extraction_job_locked(
            project_id=project_id,
            force_reextract=force_reextract,
            db=db,
            project=project,
            job_factory=job_factory,
        )


async def _queue_extraction_job_locked(
    *,
    project_id: int,
    force_reextract: bool,
    db: AsyncSession,
    project: Project,
    job_factory: Callable[[], asyncio.Task],
) -> dict[str, object]:
    current_task = await load_extraction_task_state(db, project_id)
    active_local_job = _has_active_local_job(project_id)
    if active_local_job or (
        current_task
        and current_task.get("task_status") == "running"
        and is_lease_fresh(current_task)
    ):
        current = current_task or EXTRACTION_TASKS.get(project_id) or set_extraction_task_state(
            project_id,
            task_status="running",
            stage="extracting_operations",
            message="当前任务正在后台提炼，请稍候。",
            progress=10,
            project_status=project.status,
        )
        return {
            "ok": True,
            "project_id": project_id,
            "task_status": str(current.get("task_status") or "running"),
            "stage": str(current.get("stage") or "extracting_operations"),
            "message": str(current.get("message") or "当前任务正在后台提炼，请稍候。"),
            "workflow_revision": int(project.workflow_revision or 0),
        }

    if not force_reextract and (project.status or "").strip().upper() == "ROUTE_SET_READY":
        existing_operation = (
            await db.execute(select(Operation.id).where(Operation.project_id == project_id).limit(1))
        ).first()
        if existing_operation:
            workflow_revision = int(project.workflow_revision or 0)
            completed, current = await complete_task_if_not_running(
                db,
                project_id,
                message="已存在工艺路线全集，未强制重提炼。",
                project_status=project.status,
            )
            if not completed:
                await db.rollback()
                current = await load_extraction_task_state(db, project_id)
                return {
                    "ok": True,
                    "project_id": project_id,
                    "task_status": str((current or {}).get("task_status") or "running"),
                    "stage": str((current or {}).get("stage") or "extracting_operations"),
                    "message": str(
                        (current or {}).get("message")
                        or "当前任务正在由后台服务提炼，请稍候。"
                    ),
                    "workflow_revision": workflow_revision,
                }
            await db.commit()
            return {
                "ok": True,
                "project_id": project_id,
                "task_status": str(current.get("task_status") or "completed"),
                "stage": str(current.get("stage") or "route_set_ready"),
                "message": str(current.get("message") or "已存在工艺路线全集，未强制重提炼。"),
            }

    if is_stale_task_state(project, current_task) and not active_local_job:
        cancel_extraction_task(project_id)
        _, current_task = await fail_stale_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼进程已中断，请重新发起提炼。",
            error="extraction task interrupted",
            progress=100,
            project_status="EXTRACT_ERROR",
            force_reextract=bool(current_task.get("force_reextract", False)),
            owner_id=None,
            lease_expires_at=None,
            heartbeat_at=None,
        )

    now = datetime.now(timezone.utc)
    claimed = await claim_task_lease(
        db,
        project_id,
        WORKER_ID,
        now=now,
        project_status="EXTRACTING",
        force_reextract=force_reextract,
    )
    if not claimed:
        await db.rollback()
        return {
            "ok": True,
            "project_id": project_id,
            "task_status": "running",
            "stage": "extracting_operations",
            "message": "当前任务正在由后台服务提炼，请稍候。",
            "workflow_revision": int(project.workflow_revision or 0),
        }

    invalidation = await invalidate_project_workflow(
        db,
        project,
        from_step=2,
        expected_workflow_revision=int(project.workflow_revision or 0),
    )
    project.status = "EXTRACTING"
    await db.commit()

    EXTRACTION_RUNNING.add(project_id)
    try:
        EXTRACTION_JOBS[project_id] = job_factory()
    except Exception as exc:
        EXTRACTION_RUNNING.discard(project_id)
        try:
            committed = await update_task_state_owned(
                db,
                project_id,
                WORKER_ID,
                task_status="failed",
                stage="failed",
                message="后台提炼任务启动失败，请重试。",
                error=str(exc),
                progress=100,
                project_status="EXTRACT_ERROR",
                force_reextract=force_reextract,
            )
            if committed:
                project.status = "EXTRACT_ERROR"
                await db.commit()
            else:
                await db.rollback()
        except Exception:
            await db.rollback()
        raise
    return {
        "ok": True,
        "project_id": project_id,
        "task_status": "running",
        "stage": "queued",
        "message": "已进入后台提炼队列，正在准备任务...",
        "workflow_revision": invalidation.workflow_revision,
    }


async def resolve_extraction_task_status(
    *,
    project_id: int,
    project: Project,
    db: AsyncSession,
) -> dict[str, object]:
    local_task = EXTRACTION_TASKS.get(project_id)
    task = await load_extraction_task_state(db, project_id)
    active_local_job = _has_active_local_job(project_id)
    lease_valid = is_lease_fresh(task)
    local_execution_active = bool(
        active_local_job
        and task
        and task.get("owner_id") == WORKER_ID
        and lease_valid
    )
    if task and task.get("task_status") == "running" and not lease_valid and not active_local_job:
        cancel_extraction_task(project_id)
        recovered, task = await fail_stale_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼任务已超时或中断，请重新发起提炼。",
            error="extraction task stale",
            progress=100,
            project_status="EXTRACT_ERROR",
            force_reextract=bool(task.get("force_reextract", False)),
        )
        if recovered:
            project.status = "EXTRACT_ERROR"
            await db.commit()
        else:
            await db.rollback()
            await db.refresh(project)
            task = await load_extraction_task_state(db, project_id)
        lease_valid = is_lease_fresh(task)
        local_execution_active = False
    if task:
        payload = dict(task)
        if local_execution_active and local_task:
            for key in ("stage", "message", "error", "progress", "harness"):
                payload[key] = local_task.get(key, payload.get(key))
        payload["project_status"] = project.status
        payload["local_execution_active"] = local_execution_active
        payload["lease_valid"] = lease_valid
        return payload

    normalized_status = (project.status or "").strip().upper()
    if normalized_status == "EXTRACTING" and not active_local_job:
        recovered, task = await fail_stale_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼进程已中断，请重新发起提炼。",
            error="extraction task interrupted",
            progress=100,
            project_status="EXTRACT_ERROR",
        )
        if recovered:
            project.status = "EXTRACT_ERROR"
            await db.commit()
        else:
            await db.rollback()
            await db.refresh(project)
            task = await load_extraction_task_state(db, project_id)
        if task:
            lease_valid = is_lease_fresh(task)
            payload = dict(task)
            payload["project_status"] = project.status
            payload["local_execution_active"] = False
            payload["lease_valid"] = lease_valid
            return payload

    task_status, stage, message, progress = task_status_from_project_status(project.status)
    return {
        "project_id": project_id,
        "task_status": task_status,
        "stage": stage,
        "message": message,
        "progress": progress,
        "project_status": project.status,
        "local_execution_active": False,
        "lease_valid": False,
    }


__all__ = [
    "queue_extraction_job",
    "resolve_extraction_task_status",
    "run_extraction_pipeline",
]
