import asyncio
import os
import time
from pathlib import Path

import fitz
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.core.compat import run_in_thread
from app.models.models import Document, DocumentOperationDetail, Project
from sqlalchemy import select
from app.services.document_operation_pdf_parser import extract_pdf_operation_rows
from app.services.route_rules_aggregation import _collect_candidate_summary
from app.services.route_rules_document_details_runtime import (
    ensure_document_operation_details,
    extract_document_operation_details,
)
from app.services.route_rules_parsing import _normalize_operation_name


def _hold_pdf_worker(started_path, release_path):
    Path(started_path).write_text(str(os.getpid()))
    deadline = time.monotonic() + 10
    while not Path(release_path).exists():
        if time.monotonic() > deadline:
            raise TimeoutError("worker was not released")
        time.sleep(0.01)
    return os.getpid()


@pytest.mark.asyncio
async def test_pdf_worker_isolated_from_parent_and_reusable_after_parse_error(monkeypatch):
    from app.services import extraction_parallel as parallel

    monkeypatch.setenv("PROCESSMIND_EXTRACT_MAX_WORKERS", "1")
    try:
        pid = await parallel.run_pdf_extraction_cpu(os.getpid)
        assert pid != os.getpid()
        with pytest.raises(ValueError):
            await parallel.run_pdf_extraction_cpu(int, "invalid")
        assert await parallel.run_pdf_extraction_cpu(os.getpid) == pid
    finally:
        if hasattr(parallel, "shutdown_pdf_extraction_pool"):
            await run_in_thread(parallel.shutdown_pdf_extraction_pool)
    assert await parallel.run_pdf_extraction_cpu(os.getpid) != pid
    await run_in_thread(parallel.shutdown_pdf_extraction_pool)


@pytest.mark.asyncio
async def test_crashed_pdf_worker_does_not_disable_later_extractions(monkeypatch):
    from concurrent.futures.process import BrokenProcessPool
    from app.services import extraction_parallel as parallel

    monkeypatch.setenv("PROCESSMIND_EXTRACT_MAX_WORKERS", "1")
    try:
        with pytest.raises(BrokenProcessPool):
            await parallel.run_pdf_extraction_cpu(os._exit, 1)
        assert await parallel.run_pdf_extraction_cpu(int, "42") == 42
    finally:
        await run_in_thread(parallel.shutdown_pdf_extraction_pool)


@pytest.mark.asyncio
async def test_cancelling_pdf_waiter_does_not_release_running_worker_capacity(tmp_path, monkeypatch):
    from app.services import extraction_parallel as parallel

    monkeypatch.setenv("PROCESSMIND_EXTRACT_MAX_WORKERS", "1")
    started = tmp_path / "started"
    release = tmp_path / "release"
    task = None
    try:
        task = asyncio.create_task(parallel.run_pdf_extraction_cpu(_hold_pdf_worker, str(started), str(release)))
        for _ in range(500):
            if started.exists():
                break
            await asyncio.sleep(0.01)
        assert started.exists()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        next_task = asyncio.create_task(parallel.run_pdf_extraction_cpu(os.getpid))
        await asyncio.sleep(0.05)
        assert not next_task.done()
        release.touch()
        assert await next_task == int(started.read_text())
    finally:
        release.touch()
        if task is not None and not task.done():
            task.cancel()
        if hasattr(parallel, "shutdown_pdf_extraction_pool"):
            await run_in_thread(parallel.shutdown_pdf_extraction_pool)


def _write_card_pdf(path: Path, page_count: int) -> None:
    doc = fitz.open()
    for index in range(page_count):
        page = doc.new_page()
        seq = (index + 1) * 10
        page.insert_text(
            (50, 50),
            (
                f"工序卡片\n"
                f"工序号 {seq}\n"
                f"工序名称 车削{seq}\n"
                f"1. 检验外圆至{seq}mm\n"
            ),
            fontname="china-ss",
        )
    doc.save(path)
    doc.close()


def test_pdf_page_parallel_matches_serial(tmp_path):
    pdf_path = tmp_path / "cards.pdf"
    _write_card_pdf(pdf_path, page_count=8)
    serial = extract_pdf_operation_rows(str(pdf_path), max_workers=1)
    parallel = extract_pdf_operation_rows(str(pdf_path), max_workers=4)
    assert serial == parallel
    assert [row.process_no for row in serial] == [10, 20, 30, 40, 50, 60, 70, 80]


def test_pdf_default_parser_uses_stable_serial_result(tmp_path):
    pdf_path = tmp_path / "cards.pdf"
    _write_card_pdf(pdf_path, page_count=8)

    assert extract_pdf_operation_rows(str(pdf_path)) == extract_pdf_operation_rows(str(pdf_path), max_workers=1)


@pytest.mark.asyncio
async def test_collect_candidate_summary_does_not_block_event_loop(tmp_path, monkeypatch):
    from app.services import route_rules_aggregation as aggregation

    monkeypatch.setattr(aggregation, "UPLOAD_DIR", str(tmp_path))

    def slow_extract(filepath, file_type=None, max_chars=None):
        del filepath, file_type, max_chars
        time.sleep(0.25)
        return "工序号 10\n工序名称 车削\n"

    monkeypatch.setattr(aggregation, "extract_text", slow_extract)
    monkeypatch.setattr(aggregation, "run_pdf_extraction_cpu", run_in_thread, raising=False)
    docs = [
        Document(id=1, project_id=1, filename="a.pdf", original_name="甲.pdf", file_type="pdf"),
        Document(id=2, project_id=1, filename="b.pdf", original_name="乙.pdf", file_type="pdf"),
    ]
    (tmp_path / "a.pdf").write_bytes(b"a")
    (tmp_path / "b.pdf").write_bytes(b"b")

    started = time.perf_counter()
    tick_at: list[float] = []

    async def tick():
        await asyncio.sleep(0.05)
        tick_at.append(time.perf_counter() - started)

    await asyncio.gather(_collect_candidate_summary(docs), tick())
    assert tick_at
    assert tick_at[0] < 0.2


@pytest.mark.asyncio
async def test_collect_candidate_summary_keeps_document_order(tmp_path, monkeypatch):
    from app.services import route_rules_aggregation as aggregation

    monkeypatch.setattr(aggregation, "UPLOAD_DIR", str(tmp_path))

    def fake_extract(filepath, file_type=None, max_chars=None):
        del file_type, max_chars
        name = Path(filepath).name
        if name == "a.pdf":
            time.sleep(0.05)
            return "工序号 10\n工序名称 下料\n工序号 20\n工序名称 车削\n"
        return "工序号 10\n工序名称 车削\n工序号 30\n工序名称 检验\n"

    monkeypatch.setattr(aggregation, "extract_text", fake_extract)
    monkeypatch.setattr(aggregation, "run_pdf_extraction_cpu", run_in_thread, raising=False)
    docs = [
        Document(id=1, project_id=1, filename="a.pdf", original_name="甲.pdf", file_type="pdf"),
        Document(id=2, project_id=1, filename="b.pdf", original_name="乙.pdf", file_type="pdf"),
    ]
    messages: list[str] = []
    grouped, doc_names, doc_orders = await _collect_candidate_summary(
        docs,
        progress_callback=lambda message, progress: messages.append(f"{progress}:{message}"),
    )
    assert doc_names == ["甲.pdf", "乙.pdf"]
    assert doc_orders["甲.pdf"][0] == _normalize_operation_name("下料")
    assert "车削" in grouped or _normalize_operation_name("车削") in grouped
    assert any("正在读取工艺文档" in item for item in messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    "worker_error", "worker_cancel", "parent_cancel", "parent_cancel_twice", "worker_error_then_parent_cancel",
])
async def test_candidate_summary_aborts_and_awaits_every_sibling(tmp_path, monkeypatch, failure):
    from app.services import route_rules_aggregation as aggregation

    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    workers = []
    cleaning = set()
    cleaned = set()
    progress = []

    async def controlled_worker(_function, _path, _file_type, name):
        workers.append(asyncio.current_task())
        if name == "bad.pdf":
            await started.wait()
            if failure.startswith("worker_error"):
                raise ValueError("synthetic PDF parse failure")
            if failure == "worker_cancel":
                asyncio.current_task().cancel()
                await asyncio.Event().wait()
            return name, [], []
        if len(workers) == 2:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.add(name)
            if len(cleaning) == 2:
                cleanup_started.set()
            await release_cleanup.wait()
            cleaned.add(name)

    monkeypatch.setattr(aggregation, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(aggregation, "run_pdf_extraction_cpu", controlled_worker)
    names = ["slow-a.pdf", "slow-b.pdf"]
    if not failure.startswith("parent_cancel"):
        names.append("bad.pdf")
    docs = [Document(id=index + 1, filename=name, original_name=name, file_type="pdf")
            for index, name in enumerate(names)]
    batch = asyncio.create_task(_collect_candidate_summary(
        docs, progress_callback=lambda message, _progress: progress.append(message),
    ))
    cleanup_waiter = asyncio.create_task(cleanup_started.wait())
    try:
        await asyncio.wait_for(started.wait(), 2)
        if failure.startswith("parent_cancel"):
            batch.cancel()
        done, _pending = await asyncio.wait(
            [batch, cleanup_waiter], timeout=2, return_when=asyncio.FIRST_COMPLETED,
        )
        assert cleanup_waiter in done, "batch returned without cancelling all siblings"
        assert not batch.done(), "batch returned before sibling cleanup completed"
        if failure in {"parent_cancel_twice", "worker_error_then_parent_cancel"}:
            batch.cancel()
        release_cleanup.set()
        expected_error = ValueError if failure == "worker_error" else asyncio.CancelledError
        with pytest.raises(expected_error):
            await asyncio.wait_for(batch, 2)
        assert cleaned == {"slow-a.pdf", "slow-b.pdf"}
        assert all(worker.done() for worker in workers)
        assert len(progress) == 1  # No late progress can revive a failed extraction.
    finally:
        release_cleanup.set()
        for task in [batch, cleanup_waiter] + workers:
            if not task.done():
                task.cancel()
        await asyncio.gather(batch, cleanup_waiter, *workers, return_exceptions=True)


@pytest.mark.asyncio
async def test_extract_document_details_does_not_block_event_loop(tmp_path, monkeypatch):
    from app.services import route_rules_document_details_runtime as details_runtime

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'details.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add(Project(id=1, name="并行解析"))
        db.add(Document(id=1, project_id=1, filename="slow.pdf", original_name="slow.pdf", file_type="pdf"))
        await db.commit()
    (tmp_path / "slow.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(details_runtime, "UPLOAD_DIR", str(tmp_path))

    def slow_details(filepath, *, max_workers=None):
        del filepath, max_workers
        time.sleep(0.25)
        return []

    monkeypatch.setattr(details_runtime, "extract_pdf_operation_details", slow_details)
    monkeypatch.setattr(details_runtime, "run_pdf_extraction_cpu", run_in_thread, raising=False)
    started = time.perf_counter()
    tick_at: list[float] = []

    async def tick():
        await asyncio.sleep(0.05)
        tick_at.append(time.perf_counter() - started)

    async def parse():
        async with session_factory() as db:
            return await extract_document_operation_details(
                db,
                1,
                detail_row_normalized_names=lambda name: [name],
                normalize_operation_name=lambda name: name,
            )

    await asyncio.gather(parse(), tick())
    assert tick_at
    assert tick_at[0] < 0.2
    await engine.dispose()


@pytest.mark.asyncio
async def test_document_pdfs_parse_concurrently_but_save_rows_in_input_order(tmp_path, monkeypatch):
    from app.services import route_rules_document_details_runtime as details_runtime
    from app.services.document_operation_detail_types import ExtractedOperationDetail

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'details-stable.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add(Project(id=1, name="稳定解析"))
        await db.commit()

    for filename in ("a.pdf", "b.pdf"):
        (tmp_path / filename).write_bytes(b"%PDF")
    monkeypatch.setattr(details_runtime, "UPLOAD_DIR", str(tmp_path))

    completed = []

    def slow_details(filepath, *, max_workers=None):
        del max_workers
        name = Path(filepath).name
        time.sleep(0.15 if name == "a.pdf" else 0.02)
        completed.append(name)
        return [ExtractedOperationDetail(10, "车削", name, page_no=1)]

    monkeypatch.setattr(details_runtime, "extract_pdf_operation_details", slow_details)
    monkeypatch.setattr(details_runtime, "run_pdf_extraction_cpu", run_in_thread, raising=False)
    started = time.perf_counter()
    tick_at: list[float] = []

    async def tick():
        await asyncio.sleep(0.05)
        tick_at.append(time.perf_counter() - started)

    async def parse():
        async with session_factory() as db:
            return await extract_document_operation_details(
                db,
                1,
                docs=[
                    Document(id=1, project_id=1, filename="a.pdf", original_name="甲.pdf", file_type="pdf"),
                    Document(id=2, project_id=1, filename="b.pdf", original_name="乙.pdf", file_type="pdf"),
                ],
                detail_row_normalized_names=lambda name: [name],
                normalize_operation_name=lambda name: name,
            )

    rows, _ = await asyncio.gather(parse(), tick())
    assert tick_at
    assert tick_at[0] < 0.2
    assert completed == ["b.pdf", "a.pdf"]
    assert [(row.document_id, row.operation_content) for row in rows] == [(1, "a.pdf"), (2, "b.pdf")]
    await engine.dispose()


@pytest.mark.asyncio
async def test_real_pdf_process_results_equal_serial_details(tmp_path):
    from app.services import extraction_parallel as parallel
    from app.services.document_operation_pdf_parser import extract_pdf_operation_details

    paths = [tmp_path / "first.pdf", tmp_path / "second.pdf"]
    for path in paths:
        _write_card_pdf(path, page_count=3)
    expected = [extract_pdf_operation_details(str(path)) for path in paths]
    try:
        results = await asyncio.gather(*[
            parallel.run_pdf_extraction_cpu(extract_pdf_operation_details, str(path)) for path in paths
        ])
        assert results == expected
        assert [row.operation_seq for row in results[0]] == [10, 20, 30]
    finally:
        if hasattr(parallel, "shutdown_pdf_extraction_pool"):
            await run_in_thread(parallel.shutdown_pdf_extraction_pool)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cancel", "office_error"])
async def test_aborted_document_batch_cancels_pdf_waiters_without_saving_partial_rows(tmp_path, monkeypatch, failure):
    from fastapi import HTTPException
    from app.services import route_rules_document_details_runtime as runtime

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'aborted.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked_pdf(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def invalid_office(*args):
        await started.wait()
        raise ValueError("原文缺少工步")

    monkeypatch.setattr(runtime, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(runtime, "run_pdf_extraction_cpu", blocked_pdf)
    monkeypatch.setattr(runtime, "extract_non_pdf_operation_details", invalid_office)
    docs = [Document(id=1, project_id=1, filename="one.pdf", original_name="一.pdf", file_type="pdf")]
    (tmp_path / "one.pdf").touch()
    if failure == "office_error":
        docs.append(Document(id=2, project_id=1, filename="two.docx", original_name="二.docx", file_type="docx"))
        (tmp_path / "two.docx").touch()
    try:
        async with sessions() as db:
            task = asyncio.create_task(runtime.extract_document_operation_details(
                db, 1, docs=docs, detail_row_normalized_names=lambda value: [value],
                normalize_operation_name=lambda value: value,
            ))
            await asyncio.wait_for(started.wait(), 2)
            if failure == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(HTTPException) as error:
                    await task
                assert error.value.status_code == 422
                assert "二.docx" in error.value.detail
            assert cancelled.is_set()
            await db.flush()
            assert (await db.execute(select(DocumentOperationDetail))).scalars().all() == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ensure_document_details_parses_missing_documents_in_one_parallel_batch(tmp_path, monkeypatch):
    from app.services import route_rules_document_details_runtime as details_runtime

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'details-batch.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        db.add(Project(id=1, name="批量解析"))
        db.add_all(
            [
                Document(id=1, project_id=1, filename="a.pdf", original_name="甲.pdf", file_type="pdf"),
                Document(id=2, project_id=1, filename="b.pdf", original_name="乙.pdf", file_type="pdf"),
                Document(id=3, project_id=1, filename="c.pdf", original_name="丙.pdf", file_type="pdf"),
            ]
        )
        await db.commit()

    for filename in ("a.pdf", "b.pdf", "c.pdf"):
        (tmp_path / filename).write_bytes(b"%PDF")
    monkeypatch.setattr(details_runtime, "UPLOAD_DIR", str(tmp_path))

    calls: list[list[int]] = []
    progress_messages: list[str] = []

    async def fake_extract(db, project_id, *, docs):
        calls.append([int(doc.id) for doc in docs])
        rows: list[DocumentOperationDetail] = []
        for doc in docs:
            row = DocumentOperationDetail(
                project_id=project_id,
                document_id=doc.id,
                pdf_name=doc.original_name,
                operation_seq=int(doc.id) * 10,
                operation_name=f"工序{doc.id}",
                operation_content="",
                page_no=1,
                normalized_name=f"工序{doc.id}",
                source_type="test",
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        return rows

    async with session_factory() as db:
        rows = await ensure_document_operation_details(
            db,
            1,
            extract_document_operation_details_fn=fake_extract,
            progress_callback=lambda message, progress: progress_messages.append(f"{progress}:{message}"),
        )

    assert calls == [[1, 2, 3]]
    assert [int(row.document_id) for row in rows] == [1, 2, 3]
    assert any("批量解析工序明细" in item for item in progress_messages)
    await engine.dispose()
