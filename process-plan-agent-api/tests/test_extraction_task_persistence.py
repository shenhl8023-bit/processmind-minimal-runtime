import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import Project
from app.services import extraction_pipeline
from app.services.extraction_pipeline import resolve_extraction_task_status, run_extraction_pipeline
from app.services.extraction_tasks import (
    EXTRACTION_JOBS,
    EXTRACTION_RUNNING,
    EXTRACTION_TASKS,
    delete_extraction_task_state,
    load_extraction_task_state,
    save_extraction_task_state,
)


def _clear_runtime_task_state():
    for task in list(EXTRACTION_JOBS.values()):
        task.cancel()
    EXTRACTION_JOBS.clear()
    EXTRACTION_RUNNING.clear()
    EXTRACTION_TASKS.clear()


def test_extraction_task_state_survives_memory_reset(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}")
        configure_sqlite_engine(engine)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with sessions() as db:
                db.add(Project(id=1, name="persisted-task"))
                await db.commit()
                await save_extraction_task_state(
                    db,
                    1,
                    task_status="failed",
                    stage="failed",
                    message="validation failed",
                    error="bad payload",
                    progress=100,
                    harness={"valid": False, "issues": ["bad payload"]},
                    project_status="EXTRACT_ERROR",
                    force_reextract=True,
                )
                await db.commit()

            EXTRACTION_TASKS.clear()
            async with sessions() as db:
                payload = await load_extraction_task_state(db, 1)
                assert payload is not None
                assert payload["task_status"] == "failed"
                assert payload["harness"] == {"valid": False, "issues": ["bad payload"]}
                assert payload["force_reextract"] is True
                await delete_extraction_task_state(db, 1)
                await db.commit()

            EXTRACTION_TASKS.clear()
            async with sessions() as db:
                assert await load_extraction_task_state(db, 1) is None
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_persisted_running_task_without_local_job_is_interrupted(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'interrupted.db'}")
        configure_sqlite_engine(engine)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with sessions() as db:
                project = Project(id=1, name="interrupted", status="EXTRACTING")
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
                    # 模拟已崩溃的旧 worker：owner 不同且租约已过期。
                    owner_id="dead-worker",
                    lease_expires_at="2000-01-01T00:00:00+00:00",
                    heartbeat_at="2000-01-01T00:00:00+00:00",
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
                assert payload["task_status"] == "failed"
                assert payload["error"] == "extraction task stale"
                assert project.status == "EXTRACT_ERROR"
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())


def test_force_reextract_controls_document_detail_cache(tmp_path, monkeypatch):
    captured: list[bool] = []

    async def fake_config():
        return {"key": "configured"}

    async def fake_clear(_db, _project_id, preserve_document_details):
        captured.append(preserve_document_details)

    async def fake_extract(_db, _project_id):
        return [{"name": "工序一"}]

    async def fake_save_ops(_db, _project_id, _ops):
        return None

    monkeypatch.setattr(extraction_pipeline, "get_llm_config", fake_config)
    monkeypatch.setattr(extraction_pipeline, "clear_project_extraction_results", fake_clear)

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'force.db'}")
        configure_sqlite_engine(engine)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with sessions() as db:
                db.add(Project(id=1, name="force", status="UPLOADED"))
                await db.commit()

            await run_extraction_pipeline(
                project_id=1,
                force_reextract=False,
                async_session_factory=sessions,
                extract_route_set_with_llm=fake_extract,
                save_ops=fake_save_ops,
            )
            await run_extraction_pipeline(
                project_id=1,
                force_reextract=True,
                async_session_factory=sessions,
                extract_route_set_with_llm=fake_extract,
                save_ops=fake_save_ops,
            )
        finally:
            _clear_runtime_task_state()
            await engine.dispose()

    asyncio.run(run())
    assert captured == [True, False]
