import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from io import BytesIO
import threading
from typing import List, Tuple

import pytest
from fastapi import HTTPException, UploadFile
import fitz
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import (
    Document,
    DocumentOperationDetail,
    ExecutableRuleRevision,
    FinalizedRulePackage,
    GeneratedRoute,
    KnowledgeEvidenceSnapshot,
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
)
from app.routers import documents as documents_router
from app.routers import projects as projects_router
from app.services import settings_store
from app.services.extraction_tasks import save_extraction_task_state
from app.services.extraction_tasks import cancel_extraction_task
from app.services.extraction_pipeline import resolve_extraction_task_status


@pytest.fixture
def upload_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'uploads.db'}")
    configure_sqlite_engine(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())


def test_upload_rejects_invalid_content_and_cleans_partial_files(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await documents_router._stage_uploads([
                UploadFile(filename="disguised.pdf", file=BytesIO(b"not a pdf")),
            ])
        assert exc_info.value.status_code == 415

    asyncio.run(run())
    assert list(upload_dir.iterdir()) == []


def _pdf_bytes(pages: List[Tuple[str, bool]]) -> bytes:
    document = fitz.open()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
    pixmap.clear_with(220)
    image = pixmap.tobytes("png")
    for text_value, image_only in pages:
        page = document.new_page(width=300, height=300)
        if text_value:
            page.insert_text((30, 40), text_value)
        if image_only:
            page.insert_image(fitz.Rect(0, 0, 300, 300), stream=image)
    payload = document.tobytes()
    document.close()
    pixmap = None
    return payload


def _encrypted_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((30, 40), "Readable process document")
    payload = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-password",
        user_pw="user-password",
    )
    document.close()
    return payload


def test_primary_upload_accepts_readable_text_pdf(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        staged = await documents_router._stage_uploads([
            UploadFile(filename="route.pdf", file=BytesIO(_pdf_bytes([("Process: turning", False)]))),
        ])
        assert len(staged) == 1
        assert staged[0].extension == "pdf"
        assert staged[0].path.is_file()
        return staged

    staged = asyncio.run(run())
    assert (upload_dir / staged[0].path.name).read_bytes().startswith(b"%PDF-")


def test_primary_upload_rejects_non_pdf_even_when_content_is_valid(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await documents_router._stage_uploads([
                UploadFile(filename="route.json", file=BytesIO(b"{}")),
            ])
        assert exc_info.value.status_code == 415

    asyncio.run(run())
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "payload", "message"),
    [
        ("corrupt.pdf", b"%PDF-1.7\nbroken", "无法读取"),
        ("encrypted.pdf", _encrypted_pdf_bytes(), "密码"),
        ("scanned.pdf", _pdf_bytes([("", True)]), "第1页"),
        ("mixed.pdf", _pdf_bytes([("Process: turning", False), ("", True)]), "第2页"),
    ],
    ids=["corrupt", "encrypted", "image-only", "mixed-image-page"],
)
def test_primary_upload_rejects_unreadable_pdf_pages_with_page_feedback(
    tmp_path, monkeypatch, filename, payload, message,
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await documents_router._stage_uploads([
                UploadFile(filename=filename, file=BytesIO(payload)),
            ])
        assert exc_info.value.status_code in {415, 422}
        assert message in str(exc_info.value.detail)

    asyncio.run(run())
    assert list(upload_dir.iterdir()) == []


def test_reference_routes_and_legacy_tables_are_removed_without_touching_evidence(
    tmp_path, monkeypatch,
):
    from app.services import db_schema_maintenance

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(db_schema_maintenance, "UPLOAD_DIR", upload_dir, raising=False)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reference-migration.db'}")
    configure_sqlite_engine(engine)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("INSERT INTO projects (id, name) VALUES (1, 'keep')"))
            await conn.execute(text(
                "INSERT INTO documents (id, project_id, filename, original_name, file_type) "
                "VALUES (1, 1, 'process.pdf', 'process.pdf', 'pdf')"
            ))
            await conn.execute(text("""
                CREATE TABLE "references" (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER,
                    title VARCHAR(255) NOT NULL,
                    content TEXT,
                    ref_type VARCHAR(20),
                    filename VARCHAR(255),
                    document_id INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            await conn.execute(text("""
                CREATE TABLE reference_id_sequence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT
                )
            """))
            await conn.execute(text(
                "INSERT INTO knowledge_evidence_snapshots "
                "(project_id, query, item_id, content, retrieval_method, snapshot_hash, retrieved_at, created_at) "
                "VALUES (1, 'query', 'evidence-1', 'keep evidence', 'hybrid', 'hash-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            await conn.execute(text(
                "INSERT INTO \"references\" (id, project_id, title, ref_type, filename) "
                "VALUES (1, 1, 'uploaded-only', 'uploaded', 'reference.bin'), "
                "(2, 1, 'uploaded-shared', 'uploaded', 'process.pdf'), "
                "(3, 1, 'written', 'written', NULL)"
            ))
            await conn.execute(text("INSERT INTO reference_id_sequence (id) VALUES (2)"))
            (upload_dir / "reference.bin").write_bytes(b"reference")
            (upload_dir / "process.pdf").write_bytes(b"primary")
            await db_schema_maintenance.ensure_project_schema(conn)
            await db_schema_maintenance.ensure_project_schema(conn)
            tables = {
                row[0] for row in (await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ))).all()
            }
            assert "references" not in tables
            assert "reference_id_sequence" not in tables
            assert (await conn.execute(text("SELECT COUNT(*) FROM documents"))).scalar_one() == 1
            assert (await conn.execute(text("SELECT COUNT(*) FROM knowledge_evidence_snapshots"))).scalar_one() == 1

    try:
        asyncio.run(run())
    finally:
        asyncio.run(engine.dispose())

    assert not (upload_dir / "reference.bin").exists()
    assert (upload_dir / "process.pdf").read_bytes() == b"primary"
    assert not any("/references" in getattr(route, "path", "") for route in documents_router.router.routes)


def test_clean_database_migration_does_not_require_reference_tables(tmp_path):
    from app.services import db_schema_maintenance

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'clean-migration.db'}")
    configure_sqlite_engine(engine)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await db_schema_maintenance.ensure_project_schema(conn)
            await db_schema_maintenance.ensure_project_schema(conn)
            tables = {
                row[0] for row in (await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ))).all()
            }
            assert "references" not in tables
            assert "reference_id_sequence" not in tables

    try:
        asyncio.run(run())
    finally:
        asyncio.run(engine.dispose())


def test_upload_limits_file_count_and_size(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(documents_router, "MAX_UPLOAD_FILES", 1)

    async def too_many():
        with pytest.raises(HTTPException) as exc_info:
            await documents_router._stage_uploads([
                UploadFile(filename="a.json", file=BytesIO(b"{}")),
                UploadFile(filename="b.json", file=BytesIO(b"{}")),
            ])
        assert exc_info.value.status_code == 413

    asyncio.run(too_many())
    monkeypatch.setattr(documents_router, "MAX_UPLOAD_FILES", 20)
    monkeypatch.setattr(documents_router, "MAX_UPLOAD_FILE_BYTES", 4)

    async def too_large():
        with pytest.raises(HTTPException) as exc_info:
            await documents_router._stage_uploads([
                UploadFile(
                    filename="large.pdf",
                    file=BytesIO(_pdf_bytes([("Process: turning", False)])),
                ),
            ])
        assert exc_info.value.status_code == 413

    asyncio.run(too_large())
    assert list(upload_dir.iterdir()) == []


def test_upload_database_failure_removes_file_and_rolls_back(
    upload_db,
    tmp_path,
    monkeypatch,
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def fail_invalidation(*_args, **_kwargs):
        raise RuntimeError("invalidation failed")

    monkeypatch.setattr(
        documents_router,
        "invalidate_project_document_derived_state",
        fail_invalidation,
    )

    async def run():
        async with upload_db() as db:
            db.add(Project(id=1, name="upload-test"))
            await db.commit()

            with pytest.raises(RuntimeError, match="invalidation failed"):
                await documents_router.upload_documents(
                    files=[
                        UploadFile(
                            filename="route.pdf",
                            file=BytesIO(_pdf_bytes([("工序：车外圆", False)])),
                        )
                    ],
                    project_id=1,
                    db=db,
                )

            documents = (await db.execute(select(Document))).scalars().all()
            assert documents == []

    asyncio.run(run())
    assert list(upload_dir.iterdir()) == []


def test_upload_starts_document_detail_cache_prewarm_after_commit(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def no_op_invalidation(*_args, **_kwargs):
        return {}

    started: list[int] = []
    canceled: list[int] = []

    def fake_start(project_id: int) -> bool:
        started.append(project_id)
        return True

    def fake_cancel(project_id: int) -> bool:
        canceled.append(project_id)
        return True

    monkeypatch.setattr(
        documents_router,
        "invalidate_project_document_derived_state",
        no_op_invalidation,
    )
    monkeypatch.setattr(
        documents_router,
        "start_document_detail_cache_prewarm",
        fake_start,
        raising=False,
    )
    monkeypatch.setattr(
        documents_router,
        "cancel_document_detail_cache_prewarm",
        fake_cancel,
        raising=False,
    )

    async def run():
        async with upload_db() as db:
            db.add(Project(id=1, name="prewarm-upload"))
            await db.commit()

            uploaded = await documents_router.upload_documents(
                files=[
                    UploadFile(
                        filename="route.pdf",
                        file=BytesIO(_pdf_bytes([("工序：车外圆", False)])),
                    )
                ],
                project_id=1,
                db=db,
            )

            assert len(uploaded) == 1

    asyncio.run(run())
    assert canceled == [1]
    assert started == [1]


def test_delete_document_clears_dependents_before_file(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def no_op_invalidation(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(
        documents_router,
        "invalidate_project_document_derived_state",
        no_op_invalidation,
    )
    canceled: list[int] = []

    def fake_cancel(project_id: int) -> bool:
        canceled.append(project_id)
        return True

    monkeypatch.setattr(
        documents_router,
        "cancel_document_detail_cache_prewarm",
        fake_cancel,
        raising=False,
    )

    async def run():
        async with upload_db() as db:
            project = Project(id=1, name="delete-test", status="UPLOADED")
            document = Document(
                id=1,
                project_id=1,
                filename="delete.pdf",
                original_name="delete.pdf",
                file_type="pdf",
                file_size=10,
            )
            detail = DocumentOperationDetail(
                id=1,
                project_id=1,
                document_id=1,
                pdf_name="delete.pdf",
                operation_name="工序",
            )
            db.add_all([project, document, detail])
            await db.commit()
            (upload_dir / "delete.pdf").write_bytes(b"%PDF-1.4\n")

            await documents_router.delete_document(1, db=db, project_id=1, expected_filename="delete.pdf")

            assert (await db.execute(select(Document))).scalars().all() == []
            assert (
                await db.execute(select(DocumentOperationDetail))
            ).scalars().all() == []
            assert not (upload_dir / "delete.pdf").exists()

    asyncio.run(run())
    assert canceled == [1]


def test_delete_project_removes_dependents_and_only_then_files(
    upload_db,
    tmp_path,
    monkeypatch,
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(projects_router, "UPLOAD_DIR", upload_dir)
    canceled: list[int] = []

    def fake_cancel(project_id: int) -> bool:
        canceled.append(project_id)
        return True

    monkeypatch.setattr(
        projects_router,
        "cancel_document_detail_cache_prewarm",
        fake_cancel,
        raising=False,
    )

    async def run():
        async with upload_db() as db:
            project = Project(id=1, name="delete-project", status="UPLOADED")
            document = Document(
                id=1,
                project_id=1,
                filename="document.pdf",
                original_name="document.pdf",
                file_type="pdf",
                file_size=10,
            )
            detail = DocumentOperationDetail(
                id=1,
                project_id=1,
                document_id=1,
                pdf_name="document.pdf",
                operation_name="工序",
            )
            first_package = FinalizedRulePackage(
                id=1,
                project_id=1,
                version=1,
                package_name="规则包 v1",
                status="superseded",
            )
            second_package = FinalizedRulePackage(
                id=2,
                project_id=1,
                version=2,
                package_name="规则包 v2",
                status="published",
                supersedes_id=1,
            )
            db.add_all([
                project,
                document,
                detail,
                first_package,
                second_package,
            ])
            await db.commit()
            await save_extraction_task_state(
                db,
                1,
                task_status="completed",
                stage="route_set_ready",
                progress=100,
                project_status="ROUTE_SET_READY",
            )
            await db.commit()
            (upload_dir / "document.pdf").write_bytes(b"%PDF-1.4\n")

            await projects_router.delete_project(1, db=db)

            assert (await db.execute(select(Project))).scalars().all() == []
            assert (await db.execute(select(Document))).scalars().all() == []
            assert (
                await db.execute(select(DocumentOperationDetail))
            ).scalars().all() == []
            assert (
                await db.execute(select(FinalizedRulePackage))
            ).scalars().all() == []
            task_count = (
                await db.execute(text("SELECT COUNT(*) FROM extraction_task_states"))
            ).scalar_one()
            assert task_count == 0
            assert list(upload_dir.iterdir()) == []

    asyncio.run(run())
    assert canceled == [1]


def test_delete_project_removes_executable_route_dependents_before_route_version(
    upload_db,
    monkeypatch,
):
    canceled: list[int] = []

    def fake_cancel(project_id: int) -> bool:
        canceled.append(project_id)
        return True

    monkeypatch.setattr(
        projects_router,
        "cancel_document_detail_cache_prewarm",
        fake_cancel,
        raising=False,
    )

    async def run():
        async with upload_db() as db:
            db.add_all([
                Project(id=1, name="delete-completed", status="GENERATED"),
                NormalizedRouteVersion(
                    id=1,
                    project_id=1,
                    version=1,
                    route_json='[{"segment_id":"s1"}]',
                ),
            ])
            await db.commit()
            db.add_all([
                NormalizedRouteSegmentFactorReview(
                    id=1,
                    project_id=1,
                    route_version_id=1,
                    segment_id="s1",
                    factor_name="材料",
                ),
                NormalizedRouteSegmentRuleReview(
                    id=1,
                    project_id=1,
                    route_version_id=1,
                    segment_id="s1",
                ),
                ExecutableRuleRevision(
                    id=1,
                    project_id=1,
                    route_version_id=1,
                    revision=1,
                    status="current",
                    package_json="{}",
                    normalized_route_json="[]",
                    content_hash="content",
                    source_hash="source",
                    validation_json="{}",
                ),
                GeneratedRoute(
                    id=1,
                    project_id=1,
                    executable_revision_id=1,
                    input_factors="{}",
                    result_json="{}",
                ),
                FinalizedRulePackage(
                    id=1,
                    project_id=1,
                    route_version_id=1,
                    version=1,
                    package_name="规则包 v1",
                    status="published",
                ),
            ])
            await db.commit()

            await projects_router.delete_project(1, db=db)

            for model in (
                Project,
                NormalizedRouteVersion,
                NormalizedRouteSegmentFactorReview,
                NormalizedRouteSegmentRuleReview,
                ExecutableRuleRevision,
                GeneratedRoute,
                FinalizedRulePackage,
            ):
                assert (await db.execute(select(model))).scalars().all() == []

    asyncio.run(run())
    assert canceled == [1]


def test_corrupt_settings_file_is_not_overwritten(tmp_path, monkeypatch):
    settings_path = tmp_path / "process_settings.json"
    corrupt_content = b'{"broken":'
    settings_path.write_bytes(corrupt_content)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE_PATH", settings_path)

    with pytest.raises(settings_store.SettingsStoreError):
        settings_store.load_settings()

    assert settings_path.read_bytes() == corrupt_content


def test_atomic_settings_failure_preserves_existing_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "process_settings.json"
    original_content = b'[{"key":"LLM_API_KEY","value":"existing"}]\n'
    settings_path.write_bytes(original_content)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE_PATH", settings_path)

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(settings_store.os, "replace", fail_replace)

    with pytest.raises(settings_store.SettingsStoreError):
        settings_store.save_settings([
            {"key": "LLM_API_KEY", "value": "replacement"},
        ])

    assert settings_path.read_bytes() == original_content
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("second_action", ["update", "clear"])
def test_concurrent_settings_changes_preserve_both_values(tmp_path, monkeypatch, second_action):
    monkeypatch.setattr(settings_store, "SETTINGS_FILE_PATH", tmp_path / "settings.json")
    settings_store.update_setting_value("LLM_API_KEY", "fake-existing-key")
    real_load = settings_store.load_settings
    first_loaded = threading.Event()
    second_loaded = threading.Event()

    def overlapping_load():
        rows = real_load()
        if threading.current_thread().name.endswith("_0"):
            first_loaded.set()
            second_loaded.wait(timeout=0.5)
        else:
            second_loaded.set()
        return rows

    monkeypatch.setattr(settings_store, "load_settings", overlapping_load)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="settings-race") as pool:
        first = pool.submit(settings_store.update_setting_value, "LLM_MODEL", "concurrent-model")
        assert first_loaded.wait(timeout=2)
        if second_action == "update":
            second = pool.submit(settings_store.update_setting_value, "LLM_API_URL", "https://second.test/v1")
        else:
            second = pool.submit(settings_store.clear_setting_value, "LLM_API_KEY")
        first.result(timeout=3)
        second.result(timeout=3)

    values = {row["key"]: row["value"] for row in real_load()}
    assert values["LLM_MODEL"] == "concurrent-model"
    if second_action == "update":
        assert values["LLM_API_URL"] == "https://second.test/v1"
        assert values["LLM_API_KEY"] == "fake-existing-key"
    else:
        assert values["LLM_API_KEY"] == ""


@pytest.mark.parametrize("remaining", [0, 1])
def test_delete_document_resets_completed_workflow_and_extraction_task(upload_db, tmp_path, monkeypatch, remaining):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        async with upload_db() as db:
            project = Project(id=1, name="delete-completed", status="GENERATED", workflow_revision=4)
            db.add(project)
            for doc_id in range(1, remaining + 2):
                db.add(Document(id=doc_id, project_id=1, filename=f"{doc_id}.pdf", original_name=f"{doc_id}.pdf", file_type="pdf"))
                (upload_dir / f"{doc_id}.pdf").write_bytes(_pdf_bytes([("Process: turning", False)]))
            await db.commit()
            await save_extraction_task_state(db, 1, task_status="completed", stage="route_set_ready", progress=100, project_status="ROUTE_SET_READY")
            await db.commit()

            assert await documents_router.delete_document(1, db=db, project_id=1, expected_filename="1.pdf") == {"ok": True}
            await db.refresh(project)
            assert project.status == ("UPLOADED" if remaining else "CREATED")
            assert project.workflow_revision == 5
            task = await resolve_extraction_task_status(project_id=1, project=project, db=db)
            assert task["task_status"] == "idle"
            assert task["progress"] == 0
            assert not (upload_dir / "1.pdf").exists()

    try:
        asyncio.run(run())
    finally:
        cancel_extraction_task(1)


def test_mixed_upload_batch_failure_preserves_project_and_existing_files(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    existing_path = upload_dir / "existing.pdf"
    existing_path.write_bytes(_pdf_bytes([("Process: turning", False)]))

    async def run():
        async with upload_db() as db:
            project = Project(id=1, name="atomic-upload", status="GENERATED", workflow_revision=7)
            db.add_all([project, Document(project_id=1, filename="existing.pdf", original_name="existing.pdf", file_type="pdf")])
            await db.commit()
            with pytest.raises(HTTPException) as caught:
                await documents_router.upload_documents(files=[
                    UploadFile(filename="first.pdf", file=BytesIO(_pdf_bytes([("Process: turning", False)]))),
                    UploadFile(filename="invalid.pdf", file=BytesIO(b'not a PDF')),
                ], project_id=1, db=db)
            assert caught.value.status_code == 415
            assert len((await db.execute(select(Document))).scalars().all()) == 1
            await db.refresh(project)
            assert (project.status, project.workflow_revision) == ("GENERATED", 7)
            assert list(upload_dir.iterdir()) == [existing_path]

    asyncio.run(run())


def test_new_document_upload_resets_completed_extraction_task(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(documents_router, "start_document_detail_cache_prewarm", lambda _project_id: False)

    async def run():
        async with upload_db() as db:
            project = Project(id=1, name="upload-completed", status="ROUTE_SET_READY")
            db.add(project)
            await db.commit()
            await save_extraction_task_state(db, 1, task_status="completed", stage="route_set_ready", progress=100, project_status="ROUTE_SET_READY")
            await db.commit()
            uploaded = await documents_router.upload_documents(
                files=[UploadFile(filename="route.pdf", file=BytesIO(_pdf_bytes([("Process: turning", False)])))], project_id=1, db=db,
            )
            assert len(uploaded) == 1
            task = await resolve_extraction_task_status(project_id=1, project=project, db=db)
            assert task["task_status"] == "idle"
            assert task["progress"] == 0
            assert project.status == "UPLOADED"

    try:
        asyncio.run(run())
    finally:
        cancel_extraction_task(1)


def test_upload_to_missing_project_does_not_create_files_or_rows(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        async with upload_db() as db:
            with pytest.raises(HTTPException) as caught:
                await documents_router.upload_documents(
                    files=[UploadFile(filename="route.pdf", file=BytesIO(_pdf_bytes([("Process: turning", False)])))],
                    project_id=999,
                    db=db,
                )
            assert caught.value.status_code == 404
            assert (await db.execute(select(Document))).scalars().all() == []
            assert list(upload_dir.iterdir()) == []

    asyncio.run(run())


def test_same_named_documents_keep_distinct_files_and_content(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(documents_router, "start_document_detail_cache_prewarm", lambda _project_id: False)

    async def run():
        async with upload_db() as db:
            db.add(Project(id=1, name="same-name"))
            await db.commit()
            uploaded = await documents_router.upload_documents(files=[
                UploadFile(
                    filename="same.pdf",
                    file=BytesIO(_pdf_bytes([("Process: turning 1", False)])),
                ),
                UploadFile(
                    filename="same.pdf",
                    file=BytesIO(_pdf_bytes([("Process: turning 2", False)])),
                ),
            ], project_id=1, db=db)
            assert [item.original_name for item in uploaded] == ["same.pdf", "same.pdf"]
            assert len({item.filename for item in uploaded}) == 2
            assert all((upload_dir / item.filename).read_bytes().startswith(b"%PDF-") for item in uploaded)
            assert len((await db.execute(select(Document))).scalars().all()) == 2

    asyncio.run(run())


@pytest.mark.parametrize("filename,content,want_status", [
    ("empty.pdf", b"", 400),
    ("script.exe", b"MZ", 415),
    ("bad.json", b"{", 415),
    ("wrong.doc", b"plain text", 415),
    ("wrong.xlsx", b"plain text", 415),
])
def test_invalid_upload_formats_leave_no_files(tmp_path, monkeypatch, filename, content, want_status):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        with pytest.raises(HTTPException) as caught:
            await documents_router._stage_uploads([UploadFile(filename=filename, file=BytesIO(content))])
        assert caught.value.status_code == want_status

    asyncio.run(run())
    assert list(upload_dir.iterdir()) == []


def test_optional_prewarm_failure_does_not_erase_committed_upload(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    def unavailable_prewarm(_project_id):
        raise RuntimeError("background worker unavailable")

    monkeypatch.setattr(documents_router, "start_document_detail_cache_prewarm", unavailable_prewarm)

    async def run():
        async with upload_db() as db:
            db.add(Project(id=1, name="prewarm-unavailable"))
            await db.commit()
            uploaded = await documents_router.upload_documents(
                files=[UploadFile(filename="route.pdf", file=BytesIO(_pdf_bytes([("Process: turning", False)])))],
                project_id=1, db=db,
            )
            assert len(uploaded) == 1
            assert (upload_dir / uploaded[0].filename).read_bytes().startswith(b"%PDF-")
        async with upload_db() as db:
            saved = (await db.execute(select(Document))).scalars().all()
            assert len(saved) == 1
            assert (upload_dir / saved[0].filename).is_file()

    asyncio.run(run())


@pytest.mark.parametrize("cancel_at", ["read", "close"])
def test_cancelled_upload_batch_removes_staged_files_and_closes_inputs(tmp_path, monkeypatch, cancel_at):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    existing = upload_dir / "existing.pdf"
    existing.write_bytes(_pdf_bytes([("Existing process", False)]))

    async def run():
        reached = asyncio.Event()
        files = [UploadFile(filename=name, file=BytesIO(_pdf_bytes([("Process: turning", False)])))
                 for name in ("first.pdf", "second.pdf", "third.pdf")]
        second = files[1]
        original_read = second.read
        original_close = second.close
        close_paused = False

        async def controlled_read(size):
            chunk = await original_read(size)
            if not chunk:
                reached.set()
                await asyncio.Event().wait()
            return chunk

        async def controlled_close():
            nonlocal close_paused
            await original_close()
            if not close_paused:
                close_paused = True
                reached.set()
                await asyncio.Event().wait()

        monkeypatch.setattr(second, cancel_at, controlled_read if cancel_at == "read" else controlled_close)
        task = asyncio.create_task(documents_router._stage_uploads(files))
        try:
            await asyncio.wait_for(reached.wait(), 2)
            assert len(list(upload_dir.glob("*.pdf"))) == (2 if cancel_at == "read" else 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            assert list(upload_dir.iterdir()) == [existing]
            assert all(upload.file.closed for upload in files)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            for upload in files:
                await upload.close()

    asyncio.run(run())


@pytest.mark.parametrize("cancel_at", ["lock", "flush"])
def test_upload_cancellation_before_commit_rolls_back_and_preserves_existing_pdf(
    upload_db, tmp_path, monkeypatch, cancel_at,
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    existing = upload_dir / "existing.pdf"
    existing.write_bytes(_pdf_bytes([("Existing process", False)]))

    async def run():
        reached = asyncio.Event()
        lock = asyncio.Lock()
        if cancel_at == "lock":
            await lock.acquire()

        def controlled_lock(_project_id):
            reached.set()
            return lock

        monkeypatch.setattr(documents_router, "get_route_merge_project_lock", controlled_lock)
        async with upload_db() as db:
            db.add_all([
                Project(id=1, name="cancel-before-commit", status="GENERATED", workflow_revision=7),
                Document(project_id=1, filename=existing.name, original_name=existing.name, file_type="pdf"),
            ])
            await db.commit()
            if cancel_at == "flush":
                original_flush = db.flush

                async def controlled_flush(*args, **kwargs):
                    await original_flush(*args, **kwargs)
                    reached.set()
                    await asyncio.Event().wait()

                monkeypatch.setattr(db, "flush", controlled_flush)
                # This case must wait for the actual INSERT, not lock acquisition.
                monkeypatch.setattr(documents_router, "get_route_merge_project_lock", lambda _id: lock)
            task = asyncio.create_task(documents_router.upload_documents(
                files=[UploadFile(filename="new.pdf", file=BytesIO(_pdf_bytes([("New process", False)])))],
                project_id=1, db=db,
            ))
            try:
                await asyncio.wait_for(reached.wait(), 2)
                assert len(list(upload_dir.glob("*.pdf"))) == 2
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
                assert list(upload_dir.iterdir()) == [existing]
                assert [doc.filename for doc in (await db.execute(select(Document))).scalars()] == [existing.name]
                project = await db.get(Project, 1)
                assert (project.status, project.workflow_revision) == ("GENERATED", 7)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await db.rollback()
                if lock.locked():
                    lock.release()

    asyncio.run(run())


@pytest.mark.parametrize("commit_outcome", [
    "pending_success", "committed_success", "pending_failure", "repeated_cancel_success",
])
def test_cancelled_upload_settles_commit_before_deciding_file_ownership(
    upload_db, tmp_path, monkeypatch, commit_outcome,
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(documents_router, "start_document_detail_cache_prewarm", lambda _id: False)

    async def run():
        reached = asyncio.Event()
        release_commit = asyncio.Event()
        commit_finished = asyncio.Event()
        async with upload_db() as db:
            db.add(Project(id=1, name="commit-cancellation"))
            await db.commit()
            original_commit = db.commit

            async def controlled_commit():
                if commit_outcome == "committed_success":
                    await original_commit()
                reached.set()
                await release_commit.wait()
                if commit_outcome == "pending_failure":
                    raise RuntimeError("synthetic commit failure")
                if commit_outcome in {"pending_success", "repeated_cancel_success"}:
                    await original_commit()
                commit_finished.set()

            monkeypatch.setattr(db, "commit", controlled_commit)
            task = asyncio.create_task(documents_router.upload_documents(
                files=[UploadFile(filename="route.pdf", file=BytesIO(_pdf_bytes([("Process: turning", False)])))],
                project_id=1, db=db,
            ))
            try:
                await asyncio.wait_for(reached.wait(), 2)
                task.cancel()
                if commit_outcome == "repeated_cancel_success":
                    await asyncio.sleep(0)  # Deliver the first cancellation before requesting another.
                    task.cancel()
                release_commit.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
                if commit_outcome != "pending_failure":
                    assert commit_finished.is_set(), "request exited before commit settled"
            finally:
                release_commit.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        async with upload_db() as db:
            saved = (await db.execute(select(Document))).scalars().all()
            if commit_outcome == "pending_failure":
                assert saved == []
                assert list(upload_dir.iterdir()) == []
                assert (await db.get(Project, 1)).status == "CREATED"
            else:
                assert len(saved) == 1
                assert list(upload_dir.iterdir()) == [upload_dir / saved[0].filename]
                assert (upload_dir / saved[0].filename).read_bytes().startswith(b"%PDF-")
                assert (await db.get(Project, 1)).status == "UPLOADED"

    asyncio.run(run())


def test_upload_cancelled_on_lock_exit_keeps_committed_pdf(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        reached = asyncio.Event()

        @asynccontextmanager
        async def controlled_lock(_project_id):
            yield
            reached.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(documents_router, "get_route_merge_project_lock", controlled_lock)
        async with upload_db() as db:
            db.add(Project(id=1, name="cancel-after-commit"))
            await db.commit()
            task = asyncio.create_task(documents_router.upload_documents(
                files=[UploadFile(filename="route.pdf", file=BytesIO(_pdf_bytes([("Process: turning", False)])))],
                project_id=1, db=db,
            ))
            try:
                await asyncio.wait_for(reached.wait(), 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        async with upload_db() as db:
            saved = (await db.execute(select(Document))).scalars().all()
            assert len(saved) == 1
            assert (upload_dir / saved[0].filename).is_file()

    asyncio.run(run())
