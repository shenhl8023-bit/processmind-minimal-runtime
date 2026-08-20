import asyncio

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import Document, DocumentOperationDetail, Project
from app.routers import extract as extract_router
from app.routers.extract import get_superset_route
from app.services import route_rules_document_details_runtime as details_runtime


@pytest.mark.asyncio
async def test_concurrent_detail_cache_build_is_idempotent(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'details.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add(Project(id=1, name="并发测试"))
        db.add(Document(id=1, project_id=1, filename="missing.pdf", original_name="missing.pdf", file_type="pdf"))
        await db.commit()
    (tmp_path / "missing.pdf").write_bytes(b"test")
    monkeypatch.setattr(details_runtime, "UPLOAD_DIR", str(tmp_path))
    details_runtime.DETAIL_BUILD_LOCKS.clear()

    calls = 0

    async def extract_rows(db, project_id, *, docs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        row = DocumentOperationDetail(
            project_id=project_id,
            document_id=docs[0].id,
            pdf_name=docs[0].original_name,
            operation_seq=1,
            operation_name="车削",
            operation_content="测试",
            page_no=1,
            normalized_name="车削",
        )
        db.add(row)
        await db.flush()
        return [row]

    async def run_one():
        async with session_factory() as db:
            return await details_runtime.ensure_document_operation_details(
                db,
                1,
                extract_document_operation_details_fn=extract_rows,
            )

    results = await asyncio.gather(run_one(), run_one())
    assert calls == 1
    assert all(len(rows) == 1 for rows in results)
    async with session_factory() as db:
        rows = (await db.execute(select(DocumentOperationDetail))).scalars().all()
        assert len(rows) == 1
    details_runtime.DETAIL_BUILD_LOCKS.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_uploaded_project_cannot_load_route_merge_workspace(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'guard.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add(Project(id=1, name="未提炼项目", status="UPLOADED"))
        await db.commit()
        with pytest.raises(Exception) as exc_info:
            await get_superset_route(1, db)
        assert getattr(exc_info.value, "status_code", None) == 409
    await engine.dispose()


@pytest.mark.asyncio
async def test_detail_cache_releases_write_lock_before_parsing_next_document(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'commit-per-document.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add(Project(id=1, name="提交测试"))
        db.add_all([
            Document(id=1, project_id=1, filename="one.pdf", original_name="one.pdf", file_type="pdf"),
            Document(id=2, project_id=1, filename="two.pdf", original_name="two.pdf", file_type="pdf"),
        ])
        await db.commit()
    (tmp_path / "one.pdf").write_bytes(b"one")
    (tmp_path / "two.pdf").write_bytes(b"two")
    monkeypatch.setattr(details_runtime, "UPLOAD_DIR", str(tmp_path))
    details_runtime.DETAIL_BUILD_LOCKS.clear()
    second_parse_started = asyncio.Event()
    release_second_parse = asyncio.Event()

    async def extract_rows(db, project_id, *, docs):
        doc = docs[0]
        if doc.id == 2:
            second_parse_started.set()
            await release_second_parse.wait()
        row = DocumentOperationDetail(
            project_id=project_id,
            document_id=doc.id,
            pdf_name=doc.original_name,
            operation_seq=doc.id,
            operation_name=f"工序{doc.id}",
            operation_content="测试",
            page_no=1,
            normalized_name=f"工序{doc.id}",
        )
        db.add(row)
        await db.flush()
        return [row]

    async def build_cache():
        async with session_factory() as db:
            return await details_runtime.ensure_document_operation_details(
                db,
                1,
                extract_document_operation_details_fn=extract_rows,
            )

    build_task = asyncio.create_task(build_cache())
    try:
        await asyncio.wait_for(second_parse_started.wait(), timeout=1)
        async with session_factory() as db:
            await asyncio.wait_for(
                db.execute(update(Project).where(Project.id == 1).values(name="锁已释放")),
                timeout=0.2,
            )
            await asyncio.wait_for(db.commit(), timeout=0.2)
    finally:
        release_second_parse.set()
        await build_task
        details_runtime.DETAIL_BUILD_LOCKS.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_route_merge_workspace_returns_one_complete_snapshot(tmp_path):
    get_workspace = getattr(extract_router, "get_route_merge_workspace", None)
    assert callable(get_workspace)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workspace.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add(Project(id=1, name="已提炼项目", status="ROUTE_SET_READY"))
        await db.commit()
        result = await get_workspace(1, db)
        assert result["project_id"] == 1
        assert result["superset_route"] == []
        assert result["merge_suggestions"] == []
        assert result["normalized_superset_route"] == []
    await engine.dispose()
