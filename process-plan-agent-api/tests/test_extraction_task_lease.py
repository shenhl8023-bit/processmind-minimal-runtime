"""
提取任务租约的竞态与崩溃恢复测试。

覆盖 docs/主要风险与优化修改建议.md 第 3 节 P0 的验收标准：
- 两个独立 worker 同时启动同一项目，只有一个获得任务租约。
- 持有租约的进程崩溃后，任务在租约过期后可被接管。
- 旧 owner 在恢复后不能覆盖新 owner 的状态。
- 重启 API 后，任务状态不会永久停留在 running。
"""
import asyncio
import multiprocessing
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import Operation, Project
from app.services import extraction_pipeline
from app.services.extraction_tasks import (
    EXTRACTION_JOBS,
    EXTRACTION_RUNNING,
    EXTRACTION_TASKS,
    WORKER_ID,
    claim_task_lease,
    is_lease_expired,
    is_lease_fresh,
    load_extraction_task_state,
    renew_task_lease,
    save_extraction_task_state,
    update_task_state_owned,
)
from app.services.extraction_pipeline import resolve_extraction_task_status


def _clear_runtime_task_state():
    for task in list(EXTRACTION_JOBS.values()):
        task.cancel()
    EXTRACTION_JOBS.clear()
    EXTRACTION_RUNNING.clear()
    EXTRACTION_TASKS.clear()


async def _make_env(tmp_path, name):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, sessions


def _claim_lease_in_process(db_path, owner, start_event, result_queue, now_iso=None):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        configure_sqlite_engine(engine)
        try:
            start_event.wait(timeout=10)
            async with async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )() as db:
                claimed = await claim_task_lease(
                    db,
                    1,
                    owner,
                    now=datetime.fromisoformat(now_iso) if now_iso else None,
                )
                await db.commit()
            result_queue.put((owner, claimed))
        finally:
            await engine.dispose()

    asyncio.run(run())


def _claim_lease_and_crash(db_path, owner, claimed_event, now_iso):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        configure_sqlite_engine(engine)
        async with async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )() as db:
            claimed = await claim_task_lease(
                db,
                1,
                owner,
                now=datetime.fromisoformat(now_iso),
            )
            await db.commit()
        if claimed:
            claimed_event.set()

    asyncio.run(run())
    os._exit(0)


# ---------- 租约原语 ----------

def test_lease_freshness_is_time_based():
    task = {
        "task_status": "running",
        "lease_expires_at": "2099-01-01T00:00:00+00:00",
    }
    assert is_lease_fresh(task) is True
    assert is_lease_expired(task) is False

    expired = {
        "task_status": "running",
        "lease_expires_at": "2000-01-01T00:00:00+00:00",
    }
    assert is_lease_fresh(expired) is False
    assert is_lease_expired(expired) is True

    no_lease = {"task_status": "running"}
    assert is_lease_fresh(no_lease) is False
    assert is_lease_expired(no_lease) is True


def test_worker_id_remains_unique_when_processes_share_environment():
    env = os.environ.copy()
    env["PROCESSMIND_WORKER_ID"] = "deployment"
    api_root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-c",
        (
            f"import sys; sys.path.insert(0, {str(api_root)!r}); "
            "from app.services.extraction_tasks import WORKER_ID; print(WORKER_ID)"
        ),
    ]

    worker_ids = {
        subprocess.check_output(
            command,
            text=True,
            env=env,
            cwd=api_root,
        ).strip()
        for _ in range(2)
    }

    assert len(worker_ids) == 2
    assert all(worker_id.startswith("deployment-") for worker_id in worker_ids)


def test_lease_fresh_task_is_not_stale():
    from datetime import datetime, timedelta, timezone

    from app.services.extraction_tasks import is_stale_task_state

    class FakeProject:
        created_at = None

    now = datetime.now(timezone.utc)
    fresh = {
        "task_status": "running",
        "started_at": now.isoformat(),
        "updated_at": (now - timedelta(minutes=30)).isoformat(),
        "owner_id": "worker-a",
        "lease_expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    # 即使 updated_at 很久以前，只要租约新鲜就不算 stale。
    assert is_stale_task_state(FakeProject(), fresh) is False


def test_expired_lease_task_is_stale():
    from datetime import datetime, timedelta, timezone

    from app.services.extraction_tasks import is_stale_task_state

    class FakeProject:
        created_at = None

    now = datetime.now(timezone.utc)
    expired = {
        "task_status": "running",
        "started_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "owner_id": "worker-dead",
        "lease_expires_at": (now - timedelta(minutes=1)).isoformat(),
    }
    assert is_stale_task_state(FakeProject(), expired) is True


# ---------- 竞态：只有一个 worker 获得租约 ----------

def test_concurrent_claim_only_one_worker_wins(tmp_path):
    """两个 worker 用各自独立的 DB 会话并发抢占同一项目的租约。

    用 ``asyncio.gather`` 让两个 ``claim_task_lease`` 真正交错执行。由于抢占是
    单条带条件的原子 UPDATE 并依据 ``rowcount``，恰好只有一个 worker 胜出。
    """
    async def run():
        engine, sessions = await _make_env(tmp_path, "race.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="race"))
                await db.commit()
                # 预置一个无 owner、过期租约的 running 行，作为抢占起点。
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="queued",
                    message="",
                    progress=5,
                    project_status="EXTRACTING",
                    owner_id=None,
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                    heartbeat_at="2000-01-01T00:00:00+00:00",
                )
                await db.commit()

            _clear_runtime_task_state()

            async def claim_as(owner: str) -> bool:
                async with sessions() as db:
                    ok = await claim_task_lease(db, 1, owner)
                    await db.commit()
                    return ok

            # 多轮、两种 owner 顺序，降低交错偶然性。
            for round_idx in range(8):
                # 每轮重置为无 owner 的 running 行，供下一轮抢占。
                async with sessions() as db:
                    await db.execute(
                        text(
                            "UPDATE extraction_task_states "
                            "SET owner_id=NULL, lease_expires_at='2000-01-01T00:00:00+00:00', "
                            "heartbeat_at='2000-01-01T00:00:00+00:00', task_status='running' "
                            "WHERE project_id=1"
                        )
                    )
                    await db.commit()
                _clear_runtime_task_state()
                owners = ("worker-a", "worker-b") if round_idx % 2 == 0 else ("worker-b", "worker-a")
                results = await asyncio.gather(claim_as(owners[0]), claim_as(owners[1]))
                winners = [o for o, ok in zip(owners, results) if ok]
                assert len(winners) == 1, (
                    f"round {round_idx}: expected exactly one winner, got {winners} (results={results})"
                )
                async with sessions() as db:
                    state = await load_extraction_task_state(db, 1)
                assert state["owner_id"] == winners[0]
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_fresh_lease_not_overwritten_by_second_worker(tmp_path):
    """worker-a 持有新鲜租约时，worker-b 即便并发也无法抢占或覆盖。"""
    async def run():
        engine, sessions = await _make_env(tmp_path, "fresh-race.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="fresh-race"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="extracting_operations",
                    message="running",
                    progress=10,
                    project_status="EXTRACTING",
                    owner_id="worker-a",
                    lease_expires_at="2099-01-01T00:00:00+00:00",
                    heartbeat_at="2099-01-01T00:00:00+00:00",
                )
                await db.commit()

            _clear_runtime_task_state()

            async def claim_as(owner: str) -> bool:
                async with sessions() as db:
                    ok = await claim_task_lease(db, 1, owner)
                    await db.commit()
                    return ok

            results = await asyncio.gather(claim_as("worker-a"), claim_as("worker-b"))
            # worker-a 已是 owner，可以"续占"成功；worker-b 必须失败。
            assert results == [True, False]
            async with sessions() as db:
                state = await load_extraction_task_state(db, 1)
            assert state["owner_id"] == "worker-a"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_old_owner_terminal_write_blocked_via_independent_session(tmp_path):
    """旧 owner 恢复后用独立会话写终态 -> 被条件 UPDATE 拦截，DB 不变。"""
    async def run():
        engine, sessions = await _make_env(tmp_path, "overwrite.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="overwrite"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="queued",
                    message="",
                    progress=5,
                    project_status="EXTRACTING",
                    owner_id="worker-b",
                    lease_expires_at="2099-01-01T00:00:00+00:00",
                    heartbeat_at="2099-01-01T00:00:00+00:00",
                    attempt=3,
                )
                await db.commit()

            _clear_runtime_task_state()
            # 模拟崩溃的旧 worker 恢复：独立会话、错误 owner 写终态。
            async with sessions() as db:
                overwritten = await update_task_state_owned(
                    db,
                    1,
                    "worker-dead",
                    task_status="failed",
                    stage="failed",
                    error="stale write",
                    progress=100,
                    project_status="EXTRACT_ERROR",
                )
                await db.commit()
                state = await load_extraction_task_state(db, 1)
            assert overwritten is False
            assert state["task_status"] == "running"
            assert state["owner_id"] == "worker-b"

            # 真正的 owner 写终态成功，并释放租约。
            async with sessions() as db:
                ok = await update_task_state_owned(
                    db,
                    1,
                    "worker-b",
                    task_status="completed",
                    stage="route_set_ready",
                    progress=100,
                    project_status="ROUTE_SET_READY",
                )
                await db.commit()
                state = await load_extraction_task_state(db, 1)
            assert ok is True
            assert state["task_status"] == "completed"
            assert state["owner_id"] is None
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_expired_lease_can_be_taken_over(tmp_path):
    async def run():
        engine, sessions = await _make_env(tmp_path, "takeover.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="takeover"))
                await db.commit()
                # 旧 worker 的租约早已过期。
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="extracting_operations",
                    message="old",
                    progress=10,
                    project_status="EXTRACTING",
                    owner_id="worker-dead",
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                    heartbeat_at="2000-01-01T00:00:00+00:00",
                )
                await db.commit()

            _clear_runtime_task_state()
            async with sessions() as db:
                claimed = await claim_task_lease(db, 1, "worker-b")
                await db.commit()
                state = await load_extraction_task_state(db, 1)
            assert claimed is True
            assert state["owner_id"] == "worker-b"
            assert is_lease_fresh(state) is True
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


# ---------- 重启恢复 ----------

def test_restart_recovers_persisted_running_task_as_failed(tmp_path):
    async def run():
        engine, sessions = await _make_env(tmp_path, "restart.db")
        try:
            async with sessions() as db:
                project = Project(id=1, name="restart", status="EXTRACTING")
                db.add(project)
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="extracting_operations",
                    message="running",
                    progress=25,
                    project_status="EXTRACTING",
                    force_reextract=True,
                    owner_id="worker-dead",
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                    heartbeat_at="2000-01-01T00:00:00+00:00",
                )
                await db.commit()

            # 模拟 API 重启：清空进程内注册表。
            _clear_runtime_task_state()
            async with sessions() as db:
                project = (
                    await db.execute(select(Project).where(Project.id == 1))
                ).scalar_one()
                payload = await resolve_extraction_task_status(
                    project_id=1,
                    project=project,
                    db=db,
                )
                assert payload["task_status"] == "failed"
                assert project.status == "EXTRACT_ERROR"
                # 重启后任务状态不再停留在 running。
                state = await load_extraction_task_state(db, 1)
                assert state["task_status"] == "failed"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_restart_does_not_break_fresh_lease_task(tmp_path):
    """重启后，若数据库仍持有新鲜租约，任务不应被误判为中断。"""
    async def run():
        engine, sessions = await _make_env(tmp_path, "fresh-restart.db")
        try:
            async with sessions() as db:
                project = Project(id=1, name="fresh", status="EXTRACTING")
                db.add(project)
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="extracting_operations",
                    message="running",
                    progress=25,
                    project_status="EXTRACTING",
                    owner_id="worker-a",
                    lease_expires_at="2099-01-01T00:00:00+00:00",
                    heartbeat_at="2099-01-01T00:00:00+00:00",
                )
                await db.commit()

            _clear_runtime_task_state()
            async with sessions() as db:
                project = (
                    await db.execute(select(Project).where(Project.id == 1))
                ).scalar_one()
                payload = await resolve_extraction_task_status(
                    project_id=1,
                    project=project,
                    db=db,
                )
                # 租约仍新鲜 -> 不应被标记为失败。
                assert payload["task_status"] == "running"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_status_recovery_does_not_overwrite_lease_created_after_initial_read(
    tmp_path,
    monkeypatch,
):
    """状态查询读到无任务行后，新 worker 的租约不能被旧查询覆盖为失败。"""

    async def run():
        engine, sessions = await _make_env(tmp_path, "missing-row-race.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="missing-row-race", status="EXTRACTING"))
                await db.commit()

            original_load = extraction_pipeline.load_extraction_task_state
            first_load = True

            async def load_with_concurrent_claim(db, project_id):
                nonlocal first_load
                if first_load:
                    first_load = False
                    async with sessions() as competing_db:
                        claimed = await claim_task_lease(
                            competing_db,
                            project_id,
                            "worker-new",
                        )
                        await competing_db.commit()
                    assert claimed is True
                    return None
                return await original_load(db, project_id)

            monkeypatch.setattr(
                extraction_pipeline,
                "load_extraction_task_state",
                load_with_concurrent_claim,
            )

            async with sessions() as db:
                project = (
                    await db.execute(select(Project).where(Project.id == 1))
                ).scalar_one()
                payload = await resolve_extraction_task_status(
                    project_id=1,
                    project=project,
                    db=db,
                )

            async with sessions() as db:
                state = await load_extraction_task_state(db, 1)
                project_status = (
                    await db.execute(select(Project.status).where(Project.id == 1))
                ).scalar_one()

            assert payload["task_status"] == "running"
            assert payload["lease_valid"] is True
            assert state["task_status"] == "running"
            assert state["owner_id"] == "worker-new"
            assert project_status == "EXTRACTING"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_status_recovery_ignores_stale_running_registry_without_live_job(tmp_path):
    async def run():
        engine, sessions = await _make_env(tmp_path, "stale-running-registry.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="stale-running-registry", status="EXTRACTING"))
                await db.commit()

            _clear_runtime_task_state()
            EXTRACTION_RUNNING.add(1)
            async with sessions() as db:
                project = (
                    await db.execute(select(Project).where(Project.id == 1))
                ).scalar_one()
                payload = await resolve_extraction_task_status(
                    project_id=1,
                    project=project,
                    db=db,
                )

            assert payload["task_status"] == "failed"
            assert payload["local_execution_active"] is False
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


# ---------- 续租 ----------

def test_renew_lease_only_extends_owner_lease(tmp_path):
    async def run():
        engine, sessions = await _make_env(tmp_path, "renew.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="renew"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="queued",
                    message="",
                    progress=5,
                    project_status="EXTRACTING",
                    owner_id="worker-a",
                    lease_expires_at="2099-01-01T00:00:00+00:00",
                    heartbeat_at="2099-01-01T00:00:00+00:00",
                )
                await db.commit()

            _clear_runtime_task_state()
            async with sessions() as db:
                # 正确 owner 续租成功，租约变新鲜。
                ok = await renew_task_lease(db, 1, "worker-a")
                await db.commit()
                state = await load_extraction_task_state(db, 1)
                assert ok is True
                assert is_lease_fresh(state) is True

                # 错误 owner 无法续租。
                ok2 = await renew_task_lease(db, 1, "intruder")
                await db.commit()
                state2 = await load_extraction_task_state(db, 1)
                assert ok2 is False
                assert state2["owner_id"] == "worker-a"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_expired_lease_cannot_be_renewed(tmp_path):
    async def run():
        engine, sessions = await _make_env(tmp_path, "renew-expired.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="renew-expired"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="queued",
                    message="",
                    progress=5,
                    project_status="EXTRACTING",
                    owner_id="worker-a",
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                    heartbeat_at="2000-01-01T00:00:00+00:00",
                )
                await db.commit()

            _clear_runtime_task_state()
            async with sessions() as db:
                renewed = await renew_task_lease(db, 1, "worker-a")
                await db.commit()
                state = await load_extraction_task_state(db, 1)

            assert renewed is False
            assert is_lease_expired(state) is True
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


# ---------- 管道集成：失败时释放租约，可再次发起 ----------

def test_pipeline_failure_releases_lease_and_restart_can_claim(tmp_path, monkeypatch):
    async def fake_config():
        return {"key": "configured"}

    async def fake_clear(_db, _project_id, preserve_document_details):
        return None

    async def fake_extract(_db, _project_id):
        raise RuntimeError("llm down")

    async def fake_save_ops(_db, _project_id, _ops):
        return None

    monkeypatch.setattr(extraction_pipeline, "get_llm_config", fake_config)
    monkeypatch.setattr(extraction_pipeline, "clear_project_extraction_results", fake_clear)

    async def run():
        engine, sessions = await _make_env(tmp_path, "pipeline-fail.db")
        try:
            async with sessions() as db:
                project = Project(id=1, name="pipeline-fail", status="UPLOADED")
                db.add(project)
                await db.commit()

            _clear_runtime_task_state()
            await extraction_pipeline.run_extraction_pipeline(
                project_id=1,
                force_reextract=True,
                async_session_factory=sessions,
                extract_route_set_with_llm=fake_extract,
                save_ops=fake_save_ops,
            )
            # 失败后任务状态为 failed，且租约被释放（owner 为空）。
            async with sessions() as db:
                state = await load_extraction_task_state(db, 1)
            assert state["task_status"] == "failed"
            assert state["owner_id"] is None

            # 新的 worker 可以重新发起并抢占租约。
            _clear_runtime_task_state()
            async with sessions() as db:
                claimed = await claim_task_lease(db, 1, "worker-c")
                await db.commit()
            assert claimed is True
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_pipeline_failure_retries_terminal_state_and_project_status_atomically(
    tmp_path,
    monkeypatch,
):
    async def fake_config():
        return {"key": "configured"}

    async def fake_clear(_db, _project_id, preserve_document_details):
        return None

    async def fake_extract(_db, _project_id):
        raise RuntimeError("llm down")

    async def fake_save_ops(_db, _project_id, _ops):
        return None

    monkeypatch.setattr(extraction_pipeline, "get_llm_config", fake_config)
    monkeypatch.setattr(extraction_pipeline, "clear_project_extraction_results", fake_clear)

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'failure-retry.db'}")
        configure_sqlite_engine(engine)
        commit_count = 0

        class FailTerminalCommitOnceSession(AsyncSession):
            async def commit(self):
                nonlocal commit_count
                commit_count += 1
                if commit_count == 3:
                    raise OperationalError("COMMIT", {}, RuntimeError("database is locked"))
                await super().commit()

        sessions = async_sessionmaker(
            engine,
            class_=FailTerminalCommitOnceSession,
            expire_on_commit=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="failure-retry", status="UPLOADED"))
                await db.commit()

            # 只统计管道内部提交：领取租约、清理结果、失败终态。
            commit_count = 0
            _clear_runtime_task_state()
            await extraction_pipeline.run_extraction_pipeline(
                project_id=1,
                force_reextract=True,
                async_session_factory=sessions,
                extract_route_set_with_llm=fake_extract,
                save_ops=fake_save_ops,
            )

            async with sessions() as db:
                state = await load_extraction_task_state(db, 1)
                project_status = (
                    await db.execute(select(Project.status).where(Project.id == 1))
                ).scalar_one()

            assert commit_count == 4
            assert state["task_status"] == "failed"
            assert state["owner_id"] is None
            assert project_status == "EXTRACT_ERROR"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_pipeline_completion_releases_lease_and_blocks_stale_owner(tmp_path, monkeypatch):
    """成功完成走条件终态写入：owner 释放为 None；旧 owner 写终态被拦截。"""
    async def fake_config():
        return {"key": "configured"}

    async def fake_clear(_db, _project_id, preserve_document_details):
        return None

    async def fake_extract(_db, _project_id):
        return [{"name": "工序一"}]

    async def fake_save_ops(_db, _project_id, _ops):
        return None

    monkeypatch.setattr(extraction_pipeline, "get_llm_config", fake_config)
    monkeypatch.setattr(extraction_pipeline, "clear_project_extraction_results", fake_clear)

    async def run():
        engine, sessions = await _make_env(tmp_path, "pipeline-ok.db")
        try:
            async with sessions() as db:
                project = Project(id=1, name="pipeline-ok", status="UPLOADED")
                db.add(project)
                await db.commit()

            _clear_runtime_task_state()
            await extraction_pipeline.run_extraction_pipeline(
                project_id=1,
                force_reextract=True,
                async_session_factory=sessions,
                extract_route_set_with_llm=fake_extract,
                save_ops=fake_save_ops,
            )
            # 完成后任务为 completed，租约释放（owner 为空）。
            async with sessions() as db:
                state = await load_extraction_task_state(db, 1)
            assert state["task_status"] == "completed"
            assert state["owner_id"] is None

            # 旧 owner 恢复后写终态 -> 条件 UPDATE 拦截（task 已非 running）。
            _clear_runtime_task_state()
            async with sessions() as db:
                ok = await update_task_state_owned(
                    db,
                    1,
                    "worker-impostor",
                    task_status="failed",
                    stage="failed",
                    error="stale",
                    progress=100,
                    project_status="EXTRACT_ERROR",
                )
                await db.commit()
                state = await load_extraction_task_state(db, 1)
            assert ok is False
            assert state["task_status"] == "completed"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_pipeline_does_not_overwrite_new_owner_after_takeover(tmp_path, monkeypatch):
    entered = asyncio.Event()
    resume = asyncio.Event()

    async def fake_config():
        return {"key": "configured"}

    async def fake_clear(_db, _project_id, preserve_document_details):
        return None

    async def paused_extract(_db, _project_id):
        entered.set()
        await resume.wait()
        return [{"name": "old-worker-result"}]

    async def fake_save_ops(db, project_id, _ops):
        db.add(Operation(project_id=project_id, name="old-worker-result", sequence=1))

    monkeypatch.setattr(extraction_pipeline, "get_llm_config", fake_config)
    monkeypatch.setattr(extraction_pipeline, "clear_project_extraction_results", fake_clear)

    async def run():
        engine, sessions = await _make_env(tmp_path, "takeover-during-run.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="takeover", status="EXTRACTING"))
                await db.commit()

            _clear_runtime_task_state()
            old_worker = asyncio.create_task(
                extraction_pipeline.run_extraction_pipeline(
                    project_id=1,
                    force_reextract=True,
                    async_session_factory=sessions,
                    extract_route_set_with_llm=paused_extract,
                    save_ops=fake_save_ops,
                )
            )
            await entered.wait()
            async with sessions() as db:
                await db.execute(text("""
                    UPDATE extraction_task_states
                    SET owner_id = 'worker-b',
                        lease_expires_at = '2099-01-01T00:00:00+00:00',
                        heartbeat_at = '2099-01-01T00:00:00+00:00'
                    WHERE project_id = 1
                """))
                await db.commit()
            resume.set()
            await old_worker

            async with sessions() as db:
                state = await load_extraction_task_state(db, 1)
                project = (
                    await db.execute(select(Project).where(Project.id == 1))
                ).scalar_one()
                operations = (
                    await db.execute(select(Operation).where(Operation.project_id == 1))
                ).scalars().all()
            assert state["task_status"] == "running"
            assert state["owner_id"] == "worker-b"
            assert project.status == "EXTRACTING"
            assert operations == []
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_terminal_fence_failure_rolls_back_business_results(tmp_path, monkeypatch):
    async def fake_config():
        return {"key": "configured"}

    async def fake_clear(_db, _project_id, preserve_document_details):
        return None

    async def fake_extract(_db, _project_id):
        return [{"name": "rejected-result"}]

    async def fake_save_ops(db, project_id, _ops):
        db.add(Operation(project_id=project_id, name="rejected-result", sequence=1))

    async def reject_terminal(*_args, **_kwargs):
        return False

    monkeypatch.setattr(extraction_pipeline, "get_llm_config", fake_config)
    monkeypatch.setattr(extraction_pipeline, "clear_project_extraction_results", fake_clear)
    monkeypatch.setattr(extraction_pipeline, "update_task_state_owned", reject_terminal)

    async def run():
        engine, sessions = await _make_env(tmp_path, "terminal-fence.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="terminal-fence", status="EXTRACTING"))
                await db.commit()

            _clear_runtime_task_state()
            await extraction_pipeline.run_extraction_pipeline(
                project_id=1,
                force_reextract=True,
                async_session_factory=sessions,
                extract_route_set_with_llm=fake_extract,
                save_ops=fake_save_ops,
            )

            async with sessions() as db:
                project = (
                    await db.execute(select(Project).where(Project.id == 1))
                ).scalar_one()
                operations = (
                    await db.execute(select(Operation).where(Operation.project_id == 1))
                ).scalars().all()
            assert project.status == "EXTRACTING"
            assert operations == []
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_expired_lease_is_claimed_from_real_queue_entrypoint(tmp_path):
    async def run():
        engine, sessions = await _make_env(tmp_path, "queue-takeover.db")
        started = False
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="queue-takeover", status="EXTRACTING"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="extracting_operations",
                    message="dead worker",
                    progress=25,
                    project_status="EXTRACTING",
                    owner_id="worker-dead",
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                    heartbeat_at="2000-01-01T00:00:00+00:00",
                )
                await db.commit()

            _clear_runtime_task_state()

            def job_factory():
                nonlocal started
                started = True
                return asyncio.create_task(asyncio.sleep(3600))

            async with sessions() as db:
                project = (
                    await db.execute(select(Project).where(Project.id == 1))
                ).scalar_one()
                payload = await extraction_pipeline._queue_extraction_job_locked(
                    project_id=1,
                    force_reextract=True,
                    db=db,
                    project=project,
                    job_factory=job_factory,
                )
                state = await load_extraction_task_state(db, 1)
            assert started is True
            assert payload["task_status"] == "running"
            assert state["owner_id"] == WORKER_ID
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_existing_results_shortcut_does_not_overwrite_concurrent_fresh_lease(
    tmp_path,
    monkeypatch,
):
    async def run():
        engine, sessions = await _make_env(tmp_path, "shortcut-race.db")
        try:
            async with sessions() as stale_db:
                project = Project(id=1, name="shortcut-race", status="ROUTE_SET_READY")
                stale_db.add(project)
                stale_db.add(Operation(project_id=1, name="existing", sequence=1))
                await stale_db.commit()

                # 首次读取返回后，另一 worker 才取得新鲜租约，复现 read/write 窗口。
                original_load = extraction_pipeline.load_extraction_task_state
                first_load = True

                async def load_then_concurrent_claim(db, project_id):
                    nonlocal first_load
                    current = await original_load(db, project_id)
                    if first_load:
                        first_load = False
                        async with sessions() as competing_db:
                            claimed = await claim_task_lease(
                                competing_db,
                                project_id,
                                "worker-new",
                                project_status="EXTRACTING",
                                force_reextract=True,
                            )
                            await competing_db.commit()
                        assert claimed is True
                    return current

                monkeypatch.setattr(
                    extraction_pipeline,
                    "load_extraction_task_state",
                    load_then_concurrent_claim,
                )

                payload = await extraction_pipeline._queue_extraction_job_locked(
                    project_id=1,
                    force_reextract=False,
                    db=stale_db,
                    project=project,
                    job_factory=lambda: asyncio.create_task(asyncio.sleep(3600)),
                )
                await stale_db.rollback()

            async with sessions() as db:
                state = await load_extraction_task_state(db, 1)

            assert payload["task_status"] == "running"
            assert state["task_status"] == "running"
            assert state["owner_id"] == "worker-new"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_two_independent_processes_only_one_claims_lease(tmp_path):
    async def prepare():
        engine, sessions = await _make_env(tmp_path, "process-race.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="process-race"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="queued",
                    message="",
                    progress=5,
                    project_status="EXTRACTING",
                    owner_id=None,
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(prepare())
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_claim_lease_in_process,
            args=(str(tmp_path / "process-race.db"), owner, start_event, result_queue),
        )
        for owner in ("worker-a", "worker-b")
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = [result_queue.get(timeout=15) for _ in processes]
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0
    assert sum(int(claimed) for _, claimed in results) == 1


def test_crashed_process_lease_can_be_claimed_after_expiry(tmp_path):
    async def prepare():
        engine, sessions = await _make_env(tmp_path, "process-restart.db")
        try:
            async with sessions() as db:
                db.add(Project(id=1, name="process-restart"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="running",
                    stage="queued",
                    message="",
                    progress=5,
                    project_status="EXTRACTING",
                    owner_id=None,
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(prepare())
    context = multiprocessing.get_context("spawn")
    claimed_event = context.Event()
    crashed = context.Process(
        target=_claim_lease_and_crash,
        args=(
            str(tmp_path / "process-restart.db"),
            "worker-dead",
            claimed_event,
            "2000-01-01T00:00:00+00:00",
        ),
    )
    crashed.start()
    assert claimed_event.wait(timeout=15)
    crashed.join(timeout=15)
    assert crashed.exitcode == 0

    async def reclaim():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'process-restart.db'}"
        )
        configure_sqlite_engine(engine)
        try:
            async with async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )() as db:
                claimed = await claim_task_lease(
                    db,
                    1,
                    "worker-new",
                    now=datetime.fromisoformat("2000-01-01T00:01:01+00:00"),
                )
                await db.commit()
                state = await load_extraction_task_state(db, 1)
            assert claimed is True
            assert state["owner_id"] == "worker-new"
        finally:
            await engine.dispose()

    asyncio.run(reclaim())
