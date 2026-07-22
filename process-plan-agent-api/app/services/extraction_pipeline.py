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
from datetime import datetime, timedelta, timezone
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Document, Project
from app.services.extraction_lifecycle import (
    clear_project_extraction_results,
    try_commit_project_status,
)
from app.services.extraction_tasks import (
    EXTRACTION_JOBS,
    EXTRACTION_RUNNING,
    EXTRACTION_TASKS,
    cancel_extraction_task,
    is_stale_task_state,
    set_extraction_task_state,
    task_status_from_project_status,
)
from app.services.llm_service import get_llm_config
from app.services.harness_validators import HarnessValidationError


AsyncSessionFactory = Callable[[], object]
AsyncProjectExtractor = Callable[[AsyncSession, int], Awaitable[object]]
AsyncSaveOps = Callable[[AsyncSession, int, object], Awaitable[None]]


async def run_extraction_pipeline(
    *,
    project_id: int,
    force_reextract: bool,
    async_session_factory: AsyncSessionFactory,
    extract_route_set_with_llm: AsyncProjectExtractor,
    save_ops: AsyncSaveOps,
) -> None:
    del force_reextract  # 当前仍按整轮重跑处理
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

            set_extraction_task_state(
                project_id,
                task_status="running",
                stage="extracting_operations",
                message="正在提取工艺路线全集...",
                error=None,
                progress=10,
                finished_at=None,
                harness=None,
                project_status="EXTRACTING",
            )
            await try_commit_project_status(db, project, "EXTRACTING")

            await clear_project_extraction_results(
                db,
                project_id,
                preserve_document_details=True,
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
            set_extraction_task_state(
                project_id,
                task_status="running",
                stage="extracting_operations",
                message="正在保存工艺路线全集...",
                progress=90,
                project_status="EXTRACTING",
            )
            await try_commit_project_status(db, project, "ROUTE_SET_READY")

            set_extraction_task_state(
                project_id,
                task_status="completed",
                stage="route_set_ready",
                message="工艺路线全集已生成，可进入路线归并。",
                progress=100,
                error=None,
                project_status="ROUTE_SET_READY",
            )
    except HarnessValidationError as exc:
        async with async_session_factory() as db:
            project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
            if project:
                project.status = "EXTRACT_ERROR"
                try:
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

    current_task = EXTRACTION_TASKS.get(project_id)
    if is_stale_task_state(project, current_task):
        cancel_extraction_task(project_id)

    if project_id in EXTRACTION_RUNNING:
        current = EXTRACTION_TASKS.get(project_id) or set_extraction_task_state(
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
        }
    await db.commit()

    EXTRACTION_RUNNING.add(project_id)
    set_extraction_task_state(
        project_id,
        task_status="running",
        stage="queued",
        message="已进入后台提炼队列，正在准备任务...",
        error=None,
        progress=5,
        finished_at=None,
        project_status=project_status,
    )
    EXTRACTION_JOBS[project_id] = job_factory()
    return {
        "ok": True,
        "project_id": project_id,
        "task_status": "running",
        "stage": "queued",
        "message": "已进入后台提炼队列，正在准备任务...",
    }


async def resolve_extraction_task_status(
    *,
    project_id: int,
    project: Project,
    db: AsyncSession,
) -> dict[str, object]:
    task = EXTRACTION_TASKS.get(project_id)
    if is_stale_task_state(project, task):
        cancel_extraction_task(project_id)
        task = None
    if task:
        payload = dict(task)
        payload["project_status"] = project.status
        return payload

    normalized_status = (project.status or "").strip().upper()
    if normalized_status == "EXTRACTING" and project_id not in EXTRACTION_RUNNING:
        updated_at = project.updated_at
        timestamp = updated_at.replace(tzinfo=timezone.utc) if updated_at and updated_at.tzinfo is None else updated_at
        now = datetime.now(timestamp.tzinfo or timezone.utc) if timestamp else datetime.now(timezone.utc)
        age = now - timestamp if timestamp else timedelta.max
        if age <= timedelta(minutes=10):
            return {
                "project_id": project_id,
                "task_status": "running",
                "stage": "extracting_operations",
                "message": "后台提炼任务仍在运行或等待恢复。",
                "progress": 10,
                "project_status": project.status,
            }
        docs = (await db.execute(select(Document.id).where(Document.project_id == project_id))).all()
        fallback_status = "UPLOADED" if docs else "CREATED"
        await try_commit_project_status(db, project, fallback_status)
        task_status, stage, message, progress = task_status_from_project_status(project.status)
        return {
            "project_id": project_id,
            "task_status": task_status,
            "stage": stage,
            "message": message,
            "progress": progress,
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
