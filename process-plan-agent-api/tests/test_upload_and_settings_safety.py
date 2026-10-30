import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import threading

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import (
    Document,
    DocumentOperationDetail,
    FinalizedRulePackage,
    Project,
    Reference,
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
                UploadFile(filename="large.json", file=BytesIO(b'{"a":1}')),
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
                            file=BytesIO(b"%PDF-1.4\nfixture\n%%EOF\n"),
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
                        file=BytesIO(b"%PDF-1.4\nfixture\n%%EOF\n"),
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
            reference = Reference(
                id=1,
                project_id=1,
                title="linked",
                document_id=1,
            )
            detail = DocumentOperationDetail(
                id=1,
                project_id=1,
                document_id=1,
                pdf_name="delete.pdf",
                operation_name="工序",
            )
            db.add_all([project, document, reference, detail])
            await db.commit()
            (upload_dir / "delete.pdf").write_bytes(b"%PDF-1.4\n")

            await documents_router.delete_document(1, db=db)

            assert (await db.execute(select(Document))).scalars().all() == []
            assert (
                await db.execute(select(DocumentOperationDetail))
            ).scalars().all() == []
            saved_reference = (
                await db.execute(select(Reference).where(Reference.id == 1))
            ).scalar_one()
            assert saved_reference.document_id is None
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
            reference = Reference(
                id=1,
                project_id=1,
                title="linked",
                ref_type="uploaded",
                filename="reference.json",
                document_id=1,
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
                reference,
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
            (upload_dir / "reference.json").write_text("{}", encoding="utf-8")

            await projects_router.delete_project(1, db=db)

            assert (await db.execute(select(Project))).scalars().all() == []
            assert (await db.execute(select(Document))).scalars().all() == []
            assert (await db.execute(select(Reference))).scalars().all() == []
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
                db.add(Document(id=doc_id, project_id=1, filename=f"{doc_id}.json", original_name=f"{doc_id}.json", file_type="json"))
                (upload_dir / f"{doc_id}.json").write_text("{}", encoding="utf-8")
            await db.commit()
            await save_extraction_task_state(db, 1, task_status="completed", stage="route_set_ready", progress=100, project_status="ROUTE_SET_READY")
            await db.commit()

            assert await documents_router.delete_document(1, db=db) == {"ok": True}
            await db.refresh(project)
            assert project.status == ("UPLOADED" if remaining else "CREATED")
            assert project.workflow_revision == 5
            task = await resolve_extraction_task_status(project_id=1, project=project, db=db)
            assert task["task_status"] == "idle"
            assert task["progress"] == 0
            assert not (upload_dir / "1.json").exists()

    try:
        asyncio.run(run())
    finally:
        cancel_extraction_task(1)


def test_mixed_upload_batch_failure_preserves_project_and_existing_files(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    existing_path = upload_dir / "existing.json"
    existing_path.write_text("{}", encoding="utf-8")

    async def run():
        async with upload_db() as db:
            project = Project(id=1, name="atomic-upload", status="GENERATED", workflow_revision=7)
            db.add_all([project, Document(project_id=1, filename="existing.json", original_name="existing.json", file_type="json")])
            await db.commit()
            with pytest.raises(HTTPException) as caught:
                await documents_router.upload_documents(files=[
                    UploadFile(filename="first.json", file=BytesIO(b'{}')),
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
                files=[UploadFile(filename="route.json", file=BytesIO(b'{}'))], project_id=1, db=db,
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


@pytest.mark.parametrize("reference", [False, True])
def test_upload_to_missing_project_does_not_create_files_or_rows(upload_db, tmp_path, monkeypatch, reference):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        async with upload_db() as db:
            upload = documents_router.upload_references if reference else documents_router.upload_documents
            with pytest.raises(HTTPException) as caught:
                await upload(files=[UploadFile(filename="route.json", file=BytesIO(b'{}'))], project_id=999, db=db)
            assert caught.value.status_code == 404
            assert (await db.execute(select(Document))).scalars().all() == []
            assert (await db.execute(select(Reference))).scalars().all() == []
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
                UploadFile(filename="same.json", file=BytesIO(b'{"version":1}')),
                UploadFile(filename="same.json", file=BytesIO(b'{"version":2}')),
            ], project_id=1, db=db)
            assert [item.original_name for item in uploaded] == ["same.json", "same.json"]
            assert len({item.filename for item in uploaded}) == 2
            assert [(upload_dir / item.filename).read_bytes() for item in uploaded] == [b'{"version":1}', b'{"version":2}']
            assert len((await db.execute(select(Document))).scalars().all()) == 2

    asyncio.run(run())


@pytest.mark.parametrize("filename,content,want_status", [
    ("empty.json", b"", 400),
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


def test_reference_batch_failure_removes_preceding_staged_file(upload_db, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        async with upload_db() as db:
            project = Project(id=1, name="reference-atomic", status="GENERATED")
            db.add(project)
            await db.commit()
            with pytest.raises(HTTPException) as caught:
                await documents_router.upload_references(files=[
                    UploadFile(filename="valid.md", file=BytesIO(b'notes')),
                    UploadFile(filename="invalid.json", file=BytesIO(b'{')),
                ], project_id=1, db=db)
            assert caught.value.status_code == 415
            assert (await db.execute(select(Reference))).scalars().all() == []
            await db.refresh(project)
            assert project.status == "GENERATED"
            assert list(upload_dir.iterdir()) == []

    asyncio.run(run())


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
                files=[UploadFile(filename="route.json", file=BytesIO(b'{"route":[]}'))],
                project_id=1, db=db,
            )
            assert len(uploaded) == 1
            assert (upload_dir / uploaded[0].filename).read_bytes() == b'{"route":[]}'
        async with upload_db() as db:
            saved = (await db.execute(select(Document))).scalars().all()
            assert len(saved) == 1
            assert (upload_dir / saved[0].filename).is_file()

    asyncio.run(run())
