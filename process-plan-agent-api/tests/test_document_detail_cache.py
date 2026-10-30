from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import Document, DocumentOperationDetail, Project
from app.services.route_rules_document_details_runtime import ensure_document_operation_details


@asynccontextmanager
async def detail_cache_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'detail-cache.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(Project(id=1, name="工步缓存"))
            await db.commit()
        yield sessions
    finally:
        await engine.dispose()


def document(document_id, *, file_type="pdf"):
    return Document(
        id=document_id, project_id=1, filename=f"{document_id}.{file_type}",
        original_name=f"工艺规程{document_id}.{file_type}", file_type=file_type,
    )


def detail(document_id):
    return DocumentOperationDetail(
        project_id=1, document_id=document_id, pdf_name=f"工艺规程{document_id}.pdf",
        operation_seq=10, operation_name="车削", normalized_name="车削",
        operation_content="1. 平端面；2. 车外圆", page_no=1,
    )


async def unexpected_extraction(db, project_id, *, docs):
    raise AssertionError("已有缓存或缺少源文件时，不应重新提取")


@pytest.mark.asyncio
async def test_missing_pdf_keeps_existing_document_details_after_reload(tmp_path, monkeypatch):
    from app.services import route_rules_document_details_runtime as runtime

    monkeypatch.setattr(runtime, "UPLOAD_DIR", tmp_path)
    async with detail_cache_db(tmp_path) as sessions:
        async with sessions() as db:
            db.add(document(1))
            db.add(detail(1))
            await db.commit()
            rows = await ensure_document_operation_details(
                db, 1, extract_document_operation_details_fn=unexpected_extraction,
            )
            assert [(row.document_id, row.operation_content) for row in rows] == [
                (1, "1. 平端面；2. 车外圆"),
            ]
            await db.commit()

        async with sessions() as db:
            rows = (await db.execute(select(DocumentOperationDetail))).scalars().all()
            assert [(row.document_id, row.operation_content) for row in rows] == [
                (1, "1. 平端面；2. 车外圆"),
            ]


@pytest.mark.asyncio
@pytest.mark.parametrize("document_state", ["deleted", "non_pdf"])
async def test_deleted_or_non_pdf_documents_still_remove_cached_details(tmp_path, monkeypatch, document_state):
    from app.services import route_rules_document_details_runtime as runtime

    monkeypatch.setattr(runtime, "UPLOAD_DIR", tmp_path)
    async with detail_cache_db(tmp_path) as sessions:
        async with sessions() as db:
            if document_state == "non_pdf":
                db.add(document(1, file_type="txt"))
            db.add(detail(1))
            await db.commit()
            rows = await ensure_document_operation_details(
                db, 1, extract_document_operation_details_fn=unexpected_extraction,
            )
            assert rows == []

        async with sessions() as db:
            assert (await db.execute(select(DocumentOperationDetail))).scalars().all() == []


@pytest.mark.asyncio
async def test_only_available_pdf_without_cache_is_extracted(tmp_path, monkeypatch):
    from app.services import route_rules_document_details_runtime as runtime

    monkeypatch.setattr(runtime, "UPLOAD_DIR", tmp_path)
    (tmp_path / "1.pdf").write_bytes(b"%PDF")
    (tmp_path / "2.pdf").write_bytes(b"%PDF")
    extracted_document_ids = []

    async def extract(db, project_id, *, docs):
        rows = []
        for doc in docs:
            extracted_document_ids.append(doc.id)
            row = detail(doc.id)
            db.add(row)
            rows.append(row)
        await db.flush()
        return rows

    async with detail_cache_db(tmp_path) as sessions:
        async with sessions() as db:
            db.add_all([document(1), document(2), document(3), document(4)])
            db.add_all([detail(1), detail(3)])
            await db.commit()
            rows = await ensure_document_operation_details(
                db, 1, extract_document_operation_details_fn=extract,
            )
            assert extracted_document_ids == [2]
            assert [row.document_id for row in rows] == [1, 2, 3]

        async with sessions() as db:
            rows = (await db.execute(
                select(DocumentOperationDetail).order_by(DocumentOperationDetail.document_id),
            )).scalars().all()
            assert [row.document_id for row in rows] == [1, 2, 3]
