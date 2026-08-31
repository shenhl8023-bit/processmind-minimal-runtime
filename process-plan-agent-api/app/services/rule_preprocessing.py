"""Persistent background recognition for Step 4 rule candidates."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services.project_workflow_lifecycle import acquire_workflow_revision
from app.services.rule_packages.condition_contracts import (
    ParseRuleConditionRequest,
    RuleConditionProcessOption,
    RulePreprocessItem,
    RulePreprocessStartRequest,
    RulePreprocessStatusResponse,
)
from app.services.rule_packages.condition_registry import FIELD_REGISTRY_VERSION
from app.services.rule_packages.condition_reviews import (
    _active_condition_parser_context,
    parse_condition_review,
)


RULE_PREPROCESS_JOBS: dict[tuple[int, int], asyncio.Task] = {}
RULE_PREPROCESS_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}


def _key(project_id: int, route_id: int) -> tuple[int, int]:
    return int(project_id), int(route_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload(
    project_id: int,
    route_id: int,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = row or {}
    return {
        "project_id": int(project_id),
        "route_id": int(route_id),
        "workflow_revision": int(row.get("workflow_revision") or 0),
        "task_status": str(row.get("task_status") or "idle"),
        "total_count": int(row.get("total_count") or 0),
        "completed_count": int(row.get("completed_count") or 0),
        "failed_count": int(row.get("failed_count") or 0),
        "current_segment_id": str(row.get("current_segment_id") or ""),
        "message": str(row.get("message") or ""),
        "error": str(row.get("error") or ""),
        "input_hash": str(row.get("input_hash") or ""),
        "started_at": str(row.get("started_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "finished_at": str(row.get("finished_at") or ""),
        "items_json": str(row.get("items_json") or "[]"),
        "processes_json": str(row.get("processes_json") or "[]"),
    }


async def _load_state(db: AsyncSession, project_id: int, route_id: int) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text("""
                SELECT project_id, route_version_id, workflow_revision, task_status,
                       total_count, completed_count, failed_count, current_segment_id,
                       message, error, input_hash, items_json, processes_json,
                       started_at, updated_at, finished_at
                FROM rule_preprocess_task_states
                WHERE project_id = :project_id AND route_version_id = :route_id
            """),
            {"project_id": project_id, "route_id": route_id},
        )
    ).mappings().one_or_none()
    return _payload(project_id, route_id, dict(row) if row else None) if row else None


async def _save_state(
    db: AsyncSession,
    project_id: int,
    route_id: int,
    **updates: Any,
) -> dict[str, Any]:
    current = await _load_state(db, project_id, route_id) or _payload(project_id, route_id)
    current.update(updates)
    current["updated_at"] = _now()
    await db.execute(
        text("""
            INSERT INTO rule_preprocess_task_states (
                project_id, route_version_id, workflow_revision, task_status,
                total_count, completed_count, failed_count, current_segment_id,
                message, error, input_hash, items_json, processes_json,
                started_at, updated_at, finished_at
            )
            VALUES (
                :project_id, :route_id, :workflow_revision, :task_status,
                :total_count, :completed_count, :failed_count, :current_segment_id,
                :message, :error, :input_hash, :items_json, :processes_json,
                :started_at, :updated_at, :finished_at
            )
            ON CONFLICT(project_id, route_version_id) DO UPDATE SET
                workflow_revision = excluded.workflow_revision,
                task_status = excluded.task_status,
                total_count = excluded.total_count,
                completed_count = excluded.completed_count,
                failed_count = excluded.failed_count,
                current_segment_id = excluded.current_segment_id,
                message = excluded.message,
                error = excluded.error,
                input_hash = excluded.input_hash,
                items_json = excluded.items_json,
                processes_json = excluded.processes_json,
                started_at = excluded.started_at,
                updated_at = excluded.updated_at,
                finished_at = excluded.finished_at
        """),
        {
            "project_id": project_id,
            "route_id": route_id,
            "workflow_revision": int(current.get("workflow_revision") or 0),
            "task_status": current["task_status"],
            "total_count": int(current.get("total_count") or 0),
            "completed_count": int(current.get("completed_count") or 0),
            "failed_count": int(current.get("failed_count") or 0),
            "current_segment_id": current.get("current_segment_id") or "",
            "message": current.get("message") or "",
            "error": current.get("error") or "",
            "input_hash": current.get("input_hash") or "",
            "items_json": current.get("items_json") or "[]",
            "processes_json": current.get("processes_json") or "[]",
            "started_at": current.get("started_at") or "",
            "updated_at": current.get("updated_at") or "",
            "finished_at": current.get("finished_at") or "",
        },
    )
    return current


def _input_hash(items: list[RulePreprocessItem], processes: list[RuleConditionProcessOption]) -> str:
    payload = {
        "items": [item.model_dump(mode="json") for item in items],
        "processes": [process.model_dump(mode="json") for process in processes],
        "field_registry_version": FIELD_REGISTRY_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _deserialize_items(raw: str | None) -> list[RulePreprocessItem]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [RulePreprocessItem.model_validate(item) for item in payload if isinstance(item, dict)]


def _deserialize_processes(raw: str | None) -> list[RuleConditionProcessOption]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [RuleConditionProcessOption.model_validate(item) for item in payload if isinstance(item, dict)]


def _response(state: dict[str, Any]) -> RulePreprocessStatusResponse:
    fields = set(RulePreprocessStatusResponse.model_fields)
    return RulePreprocessStatusResponse(**{key: value for key, value in state.items() if key in fields})


async def _review_is_current(
    db: AsyncSession,
    project_id: int,
    route_id: int,
    item: RulePreprocessItem,
    parser_version: str,
) -> bool:
    review = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.project_id == project_id,
                NormalizedRouteSegmentRuleReview.route_version_id == route_id,
                NormalizedRouteSegmentRuleReview.segment_id == item.segment_id,
            )
        )
    ).scalar_one_or_none()
    if not review:
        return False
    if str(review.condition_source_text or "").strip() != item.source_text.strip():
        return False
    if str(review.condition_status or "") not in {"pending_confirmation", "confirmed"}:
        return False
    if not review.condition_candidate_json:
        return False
    if str(review.condition_parser_version or "") == "manual":
        return True
    return (
        str(review.condition_parser_version or "") == parser_version
        and str(review.condition_field_registry_version or "") == FIELD_REGISTRY_VERSION
    )


async def _run_job(
    *,
    project_id: int,
    route_id: int,
    workflow_revision: int,
    items: list[RulePreprocessItem],
    processes: list[RuleConditionProcessOption],
) -> None:
    key = _key(project_id, route_id)
    completed = 0
    failed = 0
    failures: list[str] = []
    cursor = 0
    cursor_lock = asyncio.Lock()
    progress_lock = asyncio.Lock()
    parser_version, _ = await _active_condition_parser_context()

    async def next_item() -> RulePreprocessItem | None:
        nonlocal cursor
        async with cursor_lock:
            if cursor >= len(items):
                return None
            item = items[cursor]
            cursor += 1
            return item

    async def worker() -> None:
        nonlocal completed, failed
        while True:
            item = await next_item()
            if item is None:
                return
            async with async_session() as db:
                try:
                    project = (
                        await db.execute(select(Project).where(Project.id == project_id))
                    ).scalar_one_or_none()
                    route = (
                        await db.execute(
                            select(NormalizedRouteVersion).where(
                                NormalizedRouteVersion.id == route_id,
                                NormalizedRouteVersion.project_id == project_id,
                            )
                        )
                    ).scalar_one_or_none()
                    if not project or not route:
                        raise RuntimeError("规则预处理依赖的任务或路线版本不存在。")
                    if int(project.workflow_revision or 0) != int(workflow_revision):
                        raise RuntimeError("工作流版本已变化，请重新发起规则预处理。")
                    if await _review_is_current(db, project_id, route_id, item, parser_version):
                        pass
                    else:
                        await parse_condition_review(
                            ParseRuleConditionRequest(
                                project_id=project_id,
                                route_id=route_id,
                                expected_workflow_revision=workflow_revision,
                                segment_id=item.segment_id,
                                source_text=item.source_text,
                                process_id=item.process_id,
                                process_name=item.process_name,
                                processes=processes,
                            ),
                            db,
                        )
                    await db.commit()
                    async with progress_lock:
                        completed += 1
                        await _save_state(
                            db,
                            project_id,
                            route_id,
                            workflow_revision=workflow_revision,
                            task_status="running",
                            total_count=len(items),
                            completed_count=completed,
                            failed_count=failed,
                            current_segment_id=item.segment_id,
                            message=f"正在准备规则候选：{completed}/{len(items)}",
                            error="\n".join(failures),
                        )
                        await db.commit()
                except Exception as exc:
                    await db.rollback()
                    async with progress_lock:
                        failed += 1
                        failures.append(f"{item.segment_id}: {exc}")
                        await _save_state(
                            db,
                            project_id,
                            route_id,
                            workflow_revision=workflow_revision,
                            task_status="running",
                            total_count=len(items),
                            completed_count=completed,
                            failed_count=failed,
                            current_segment_id=item.segment_id,
                            message=f"规则候选准备中，已有 {failed} 条失败",
                            error="\n".join(failures),
                        )
                        await db.commit()

    try:
        await asyncio.gather(*(worker() for _ in range(min(3, max(1, len(items))))))
        async with async_session() as db:
            message = (
                f"规则候选已准备 {completed}/{len(items)} 条"
                if not failed
                else f"规则候选已准备 {completed}/{len(items)} 条，{failed} 条需要重试"
            )
            await _save_state(
                db,
                project_id,
                route_id,
                workflow_revision=workflow_revision,
                task_status="completed",
                total_count=len(items),
                completed_count=completed,
                failed_count=failed,
                current_segment_id="",
                message=message,
                error="\n".join(failures),
                finished_at=_now(),
            )
            await db.commit()
    except Exception as exc:
        async with async_session() as db:
            await _save_state(
                db,
                project_id,
                route_id,
                workflow_revision=workflow_revision,
                task_status="failed",
                total_count=len(items),
                completed_count=completed,
                failed_count=failed,
                message="规则预处理失败，请重试。",
                error=str(exc),
                finished_at=_now(),
            )
            await db.commit()
    finally:
        RULE_PREPROCESS_JOBS.pop(key, None)


async def start_rule_preprocessing(
    body: RulePreprocessStartRequest,
    db: AsyncSession,
) -> RulePreprocessStatusResponse:
    key = _key(body.project_id, body.route_id)
    lock = RULE_PREPROCESS_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
        route = (
            await db.execute(
                select(NormalizedRouteVersion).where(
                    NormalizedRouteVersion.id == body.route_id,
                    NormalizedRouteVersion.project_id == body.project_id,
                )
            )
        ).scalar_one_or_none()
        if not route:
            raise ValueError("规则预处理依赖的路线版本不存在。")

        input_hash = _input_hash(body.items, body.processes)
        current = await _load_state(db, body.project_id, body.route_id)
        active = RULE_PREPROCESS_JOBS.get(key)
        if active and not active.done() and current:
            return _response(current)
        if (
            current
            and current.get("task_status") == "completed"
            and int(current.get("failed_count") or 0) == 0
            and current.get("input_hash") == input_hash
            and int(current.get("workflow_revision") or 0) == int(body.expected_workflow_revision)
        ):
            return _response(current)

        items_json = json.dumps([item.model_dump(mode="json") for item in body.items], ensure_ascii=False)
        processes_json = json.dumps([item.model_dump(mode="json") for item in body.processes], ensure_ascii=False)
        state = await _save_state(
            db,
            body.project_id,
            body.route_id,
            workflow_revision=body.expected_workflow_revision,
            task_status="queued",
            total_count=len(body.items),
            completed_count=0,
            failed_count=0,
            current_segment_id="",
            message="已进入规则预处理队列。",
            error="",
            input_hash=input_hash,
            items_json=items_json,
            processes_json=processes_json,
            started_at=_now(),
            finished_at="",
        )
        await db.commit()
        if not body.items:
            state = await _save_state(
                db,
                body.project_id,
                body.route_id,
                task_status="completed",
                message="当前没有需要预处理的条件或关联规则。",
                finished_at=_now(),
            )
            await db.commit()
            return _response(state)
        RULE_PREPROCESS_JOBS[key] = asyncio.create_task(
            _run_job(
                project_id=body.project_id,
                route_id=body.route_id,
                workflow_revision=body.expected_workflow_revision,
                items=body.items,
                processes=body.processes,
            )
        )
        state["task_status"] = "running"
        state["message"] = "正在后台准备规则候选。"
        return _response(state)


async def get_rule_preprocessing_status(
    project_id: int,
    route_id: int,
    db: AsyncSession,
) -> RulePreprocessStatusResponse:
    state = await _load_state(db, project_id, route_id)
    if not state:
        return RulePreprocessStatusResponse(
            project_id=project_id,
            route_id=route_id,
            workflow_revision=0,
            task_status="idle",
        )
    active = RULE_PREPROCESS_JOBS.get(_key(project_id, route_id))
    if state["task_status"] == "running" and (not active or active.done()):
        state = await _save_state(
            db,
            project_id,
            route_id,
            task_status="failed",
            message="后台规则预处理已中断，请重试。",
            error=state.get("error") or "preprocessing task interrupted",
            finished_at=_now(),
        )
        await db.commit()
    return _response(state)


__all__ = [
    "RULE_PREPROCESS_JOBS",
    "get_rule_preprocessing_status",
    "start_rule_preprocessing",
]
