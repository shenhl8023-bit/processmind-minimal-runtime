import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import Operation, Project
from app.services import extraction_pipeline
from app.services.extraction_tasks import (
    EXTRACTION_JOBS,
    EXTRACTION_RUNNING,
    EXTRACTION_TASKS,
    cancel_extraction_task,
)


def test_cancelled_extraction_keeps_replacement_running(tmp_path, monkeypatch):
    """Uploading then restarting must not let the old job hide the new one."""
    async def configured_model():
        return {"key": "isolated-test-key"}

    monkeypatch.setattr(extraction_pipeline, "get_llm_config", configured_model)

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'replacement.db'}")
        configure_sqlite_engine(engine)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        started = [asyncio.Event(), asyncio.Event()]
        finish = asyncio.Event()
        jobs = []

        async def save_ops(db, project_id, _ops):
            db.add(Operation(project_id=project_id, name="新任务工序", sequence=10))

        def start_job(index):
            async def extract(_db, _project_id):
                started[index].set()
                await finish.wait()
                return [{"name": "新任务工序"}]

            job = asyncio.create_task(extraction_pipeline.run_extraction_pipeline(
                project_id=1,
                force_reextract=True,
                async_session_factory=sessions,
                extract_route_set_with_llm=extract,
                save_ops=save_ops,
            ))
            EXTRACTION_JOBS[1] = job
            EXTRACTION_RUNNING.add(1)
            jobs.append(job)
            return job

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with sessions() as db:
                db.add(Project(id=1, name="replacement", status="UPLOADED"))
                await db.commit()

            old = start_job(0)
            await asyncio.wait_for(started[0].wait(), timeout=5)
            cancel_extraction_task(1)
            replacement = start_job(1)
            with pytest.raises(asyncio.CancelledError):
                await old
            await asyncio.wait_for(started[1].wait(), timeout=5)

            async with sessions() as db:
                project = await db.get(Project, 1)
                status = await extraction_pipeline.resolve_extraction_task_status(
                    project_id=1, project=project, db=db,
                )
                assert status["task_status"] == "running"
                assert project.status == "EXTRACTING"
            assert EXTRACTION_JOBS.get(1) is replacement
            assert 1 in EXTRACTION_RUNNING
            finish.set()
            await asyncio.wait_for(replacement, timeout=5)
            async with sessions() as db:
                project = await db.get(Project, 1)
                status = await extraction_pipeline.resolve_extraction_task_status(
                    project_id=1, project=project, db=db,
                )
                assert status["task_status"] == "completed"
                assert project.status == "ROUTE_SET_READY"
            assert 1 not in EXTRACTION_JOBS
            assert 1 not in EXTRACTION_RUNNING
        finally:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            EXTRACTION_JOBS.pop(1, None)
            EXTRACTION_RUNNING.discard(1)
            EXTRACTION_TASKS.pop(1, None)
            await engine.dispose()

    asyncio.run(run())
