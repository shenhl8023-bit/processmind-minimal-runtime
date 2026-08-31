import asyncio
import time
from pathlib import Path

import fitz
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import Document, DocumentOperationDetail, Project
from app.services.document_operation_pdf_parser import extract_pdf_operation_rows
from app.services.route_rules_aggregation import _collect_candidate_summary
from app.services.route_rules_document_details_runtime import (
    ensure_document_operation_details,
    extract_document_operation_details,
)
from app.services.route_rules_parsing import _normalize_operation_name


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
async def test_extract_document_details_uses_stable_serial_pdf_parsing_by_default(tmp_path, monkeypatch):
    from app.services import route_rules_document_details_runtime as details_runtime

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

    active = 0
    max_active = 0

    def slow_details(filepath, *, max_workers=None):
        nonlocal active, max_active
        del filepath, max_workers
        active += 1
        max_active = max(max_active, active)
        try:
            time.sleep(0.15)
            return []
        finally:
            active -= 1

    monkeypatch.setattr(details_runtime, "extract_pdf_operation_details", slow_details)
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

    await asyncio.gather(parse(), tick())
    assert tick_at
    assert tick_at[0] < 0.2
    assert max_active == 1
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
