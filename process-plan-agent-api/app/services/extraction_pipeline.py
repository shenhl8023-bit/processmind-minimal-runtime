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
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Operation, Project
from app.services.extraction_lifecycle import (
    clear_project_extraction_results,
    try_commit_project_status,
)
from app.services.extraction_tasks import (
    EXTRACTION_JOBS,
    EXTRACTION_RUNNING,
    EXTRACTION_TASKS,
    cancel_extraction_task,
    get_extraction_queue_lock,
    is_stale_task_state,
    load_extraction_task_state,
    save_extraction_task_state,
    set_extraction_task_state,
    task_status_from_project_status,
)
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


async def run_extraction_pipeline(
    *,
    project_id: int,
    force_reextract: bool,
    async_session_factory: AsyncSessionFactory,
    extract_route_set_with_llm: AsyncProjectExtractor,
    save_ops: AsyncSaveOps,
) -> None:
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

            if not force_reextract:
                existing_operation = (
                    await db.execute(select(Operation.id).where(Operation.project_id == project_id).limit(1))
                ).first()
                if existing_operation and (project.status or "").upper() == "ROUTE_SET_READY":
                    await save_extraction_task_state(
                        db,
                        project_id,
                        task_status="completed",
                        stage="route_set_ready",
                        message="已存在工艺路线全集，未强制重提炼。",
                        error=None,
                        progress=100,
                        finished_at=None,
                        harness=None,
                        project_status="ROUTE_SET_READY",
                        force_reextract=False,
                    )
                    await db.commit()
                    return

            await save_extraction_task_state(
                db,
                project_id,
                task_status="running",
                stage="extracting_operations",
                message="正在提取工艺路线全集...",
                error=None,
                progress=10,
                finished_at=None,
                harness=None,
                project_status="EXTRACTING",
                force_reextract=force_reextract,
            )
            await try_commit_project_status(db, project, "EXTRACTING")

            await clear_project_extraction_results(
                db,
                project_id,
                preserve_document_details=not force_reextract,
            )

            config = await get_llm_config()
            api_key = config["key"]
            use_llm = bool(api_key and api_key != "your-api-key-here")
            if not use_llm:
                raise HTTPException(400, "未配置大模型 API，第二步工艺路线全集提取必须依赖大模型。")

            ops_data = await extract_route_set_with_llm(db, project_id)
            if not ops_data:
                raise HTTPException(502, "大模型未返回可解析的工艺路线全集结果。")

            await save_ops(db, project_id, ops_data)
            await save_extraction_task_state(
                db,
                project_id,
                task_status="running",
                stage="extracting_operations",
                message="正在保存工艺路线全集...",
                progress=90,
                project_status="EXTRACTING",
            )
            await try_commit_project_status(db, project, "ROUTE_SET_READY")

            await save_extraction_task_state(
                db,
                project_id,
                task_status="completed",
                stage="route_set_ready",
                message="工艺路线全集已生成，可进入路线归并。",
                progress=100,
                error=None,
                project_status="ROUTE_SET_READY",
                force_reextract=force_reextract,
            )
            await db.commit()
    except HarnessValidationError as exc:
        async with async_session_factory() as db:
            project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
            if project:
                project.status = "EXTRACT_ERROR"
            try:
                await save_extraction_task_state(
                    db,
                    project_id,
                    task_status="failed",
                    stage="failed",
                    message="第二步提炼被 Harness 校验拦截",
                    error=str(exc),
                    harness=exc.to_payload(),
                    progress=100,
                    project_status="EXTRACT_ERROR",
                    force_reextract=force_reextract,
                )
                await db.commit()
            except Exception:
                await db.rollback()
        detail = str(exc)
        set_extraction_task_state(
            project_id,
            task_status="failed",
            stage="failed",
            message="第二步提炼被 Harness 校验拦截",
            error=detail,
            harness=exc.to_payload(),
            progress=100,
            project_status="EXTRACT_ERROR",
        )
    except Exception as exc:
        async with async_session_factory() as db:
            project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
            if project:
                project.status = "EXTRACT_ERROR"
            try:
                await save_extraction_task_state(
                    db,
                    project_id,
                    task_status="failed",
                    stage="failed",
                    message="第二步提炼失败",
                    error=str(exc),
                    progress=100,
                    project_status="EXTRACT_ERROR",
                    force_reextract=force_reextract,
                )
                await db.commit()
            except Exception:
                await db.rollback()
        detail = str(exc)
        set_extraction_task_state(
            project_id,
            task_status="failed",
            stage="failed",
            message="第二步提炼失败",
            error=detail,
            progress=100,
            project_status="EXTRACT_ERROR",
        )
    finally:
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
    if not force_reextract and (project.status or "").strip().upper() == "ROUTE_SET_READY":
        existing_operation = (
            await db.execute(select(Operation.id).where(Operation.project_id == project_id).limit(1))
        ).first()
        if existing_operation:
            current = await save_extraction_task_state(
                db,
                project_id,
                task_status="completed",
                stage="route_set_ready",
                message="已存在工艺路线全集，未强制重提炼。",
                error=None,
                progress=100,
                started_at=None,
                finished_at=None,
                harness=None,
                project_status=project.status,
                force_reextract=False,
            )
            await db.commit()
            return {
                "ok": True,
                "project_id": project_id,
                "task_status": str(current.get("task_status") or "completed"),
                "stage": str(current.get("stage") or "route_set_ready"),
                "message": str(current.get("message") or "已存在工艺路线全集，未强制重提炼。"),
            }

    current_task = EXTRACTION_TASKS.get(project_id) or await load_extraction_task_state(db, project_id)
    active_local_job = _has_active_local_job(project_id)
    if is_stale_task_state(project, current_task) and not active_local_job:
        cancel_extraction_task(project_id)
        current_task = None
    elif (
        current_task
        and current_task.get("task_status") == "running"
        and not active_local_job
    ):
        cancel_extraction_task(project_id)
        current_task = await save_extraction_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼进程已中断，请重新发起提炼。",
            error="extraction task interrupted",
            progress=100,
            project_status="EXTRACT_ERROR",
            force_reextract=bool(current_task.get("force_reextract", False)),
        )
        if (project.status or "").strip().upper() == "EXTRACTING":
            await try_commit_project_status(db, project, "EXTRACT_ERROR")
        else:
            await db.commit()
        current_task = None

    if active_local_job or (
        current_task and current_task.get("task_status") == "running"
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

    project_status = project.status
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=10)
    # The running set is useful for in-process progress, but this conditional
    # update is the actual cross-process lease. A second worker cannot launch a
    # destructive re-extraction while the first lease is fresh.
    claim = await db.execute(
        update(Project)
        .where(
            Project.id == project_id,
            (Project.status != "EXTRACTING") | (Project.updated_at < stale_before),
        )
        .values(status="EXTRACTING", updated_at=now)
    )
    if not claim.rowcount:
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

    await save_extraction_task_state(
        db,
        project_id,
        task_status="running",
        stage="queued",
        message="已进入后台提炼队列，正在准备任务...",
        error=None,
        progress=5,
        finished_at=None,
        project_status=project_status,
        force_reextract=force_reextract,
    )
    await db.commit()
    EXTRACTION_RUNNING.add(project_id)
    try:
        EXTRACTION_JOBS[project_id] = job_factory()
    except Exception as exc:
        EXTRACTION_RUNNING.discard(project_id)
        try:
            await save_extraction_task_state(
                db,
                project_id,
                task_status="failed",
                stage="failed",
                message="后台提炼任务启动失败，请重试。",
                error=str(exc),
                progress=100,
                project_status="EXTRACT_ERROR",
                force_reextract=force_reextract,
            )
            await try_commit_project_status(db, project, "EXTRACT_ERROR")
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
    task = EXTRACTION_TASKS.get(project_id) or await load_extraction_task_state(db, project_id)
    active_local_job = _has_active_local_job(project_id)
    if is_stale_task_state(project, task) and not active_local_job:
        cancel_extraction_task(project_id)
        task = await save_extraction_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼任务已超时或中断，请重新发起提炼。",
            error="extraction task stale",
            progress=100,
            project_status="EXTRACT_ERROR",
        )
        await try_commit_project_status(db, project, "EXTRACT_ERROR")
    elif (
        task
        and task.get("task_status") == "running"
        and not active_local_job
    ):
        cancel_extraction_task(project_id)
        task = await save_extraction_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼进程已中断，请重新发起提炼。",
            error="extraction task interrupted",
            progress=100,
            project_status="EXTRACT_ERROR",
            force_reextract=bool(task.get("force_reextract", False)),
        )
        await try_commit_project_status(db, project, "EXTRACT_ERROR")
    elif (
        task
        and task.get("task_status") == "running"
        and project_id not in EXTRACTION_RUNNING
        and project_id not in EXTRACTION_JOBS
    ):
        cancel_extraction_task(project_id)
        task = await save_extraction_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼进程已中断，请重新发起提炼。",
            error="extraction task interrupted",
            progress=100,
            project_status="EXTRACT_ERROR",
            force_reextract=bool(task.get("force_reextract", False)),
        )
        await try_commit_project_status(db, project, "EXTRACT_ERROR")
    if task:
        payload = dict(task)
        payload["project_status"] = project.status
        return payload

    normalized_status = (project.status or "").strip().upper()
    if normalized_status == "EXTRACTING" and project_id not in EXTRACTION_RUNNING:
        await save_extraction_task_state(
            db,
            project_id,
            task_status="failed",
            stage="failed",
            message="后台提炼进程已中断，请重新发起提炼。",
            error="extraction task interrupted",
            progress=100,
            project_status="EXTRACT_ERROR",
        )
        await try_commit_project_status(db, project, "EXTRACT_ERROR")
        return {
            "project_id": project_id,
            "task_status": "failed",
            "stage": "failed",
            "message": "后台提炼进程已中断，请重新发起提炼。",
            "error": "extraction task interrupted",
            "progress": 100,
            "project_status": project.status,
        }

    task_status, stage, message, progress = task_status_from_project_status(project.status)
    return {
        "project_id": project_id,
        "task_status": task_status,
        "stage": stage,
        "message": message,
        "progress": progress,
        "project_status": project.status,
    }


__all__ = [
    "queue_extraction_job",
    "resolve_extraction_task_status",
    "run_extraction_pipeline",
]
