"""Regression coverage for stale document actions and background rule jobs."""
import asyncio
from io import BytesIO
import json

import pytest
import fitz
from fastapi import FastAPI, HTTPException, UploadFile
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.database import Base, configure_sqlite_engine, get_db
from app.models.models import Document, NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.routers import documents as documents_router
from app.services import rule_preprocessing as preprocessing
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages import condition_reviews
from app.services.rule_packages.condition_contracts import ManualRuleConditionRequest, RulePreprocessStartRequest


def _pdf_bytes(text_value="Process: turning"):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((30, 40), text_value)
    payload = document.tobytes()
    document.close()
    return payload


async def create_database(path):
    engine = create_async_engine('sqlite+aiosqlite:///' + str(path))
    configure_sqlite_engine(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_project_schema(conn)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def isolate_uploads(monkeypatch, directory, stub_invalidation=True):
    directory.mkdir()
    monkeypatch.setattr(documents_router, 'UPLOAD_DIR', directory)
    monkeypatch.setattr(documents_router, 'start_document_detail_cache_prewarm', lambda *_: False)

    async def no_invalidation(*_args, **_kwargs):
        return {}

    if stub_invalidation:
        monkeypatch.setattr(documents_router, 'invalidate_project_document_derived_state', no_invalidation)


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy_table', [False, True])
async def test_deleted_document_identity_is_not_reused_after_restart(tmp_path, monkeypatch, legacy_table):
    engine, sessions = await create_database(tmp_path / 'documents.db')
    isolate_uploads(monkeypatch, tmp_path / 'uploads')
    try:
        if legacy_table:
            async with engine.begin() as conn:
                await conn.execute(text('DROP TABLE documents'))
                ddl = str(CreateTable(Document.__table__).compile(dialect=engine.dialect))
                await conn.execute(text(ddl.replace('PRIMARY KEY AUTOINCREMENT', 'PRIMARY KEY')))
                await ensure_project_schema(conn)
        async with sessions() as db:
            db.add_all([Project(id=1, name='A'), Project(id=2, name='B')])
            await db.commit()
            old = (await documents_router.upload_documents(
                [UploadFile(filename='old.pdf', file=BytesIO(_pdf_bytes()))], 1, db,
            ))[0]
            old_id = old.id
            await documents_router.delete_document(old_id, db=db, project_id=1, expected_filename=old.filename)
        # Startup schema maintenance must not reset the document high-water mark.
        async with engine.begin() as conn:
            await ensure_project_schema(conn)
        async with sessions() as db:
            new = (await documents_router.upload_documents(
                [UploadFile(filename='new.pdf', file=BytesIO(_pdf_bytes('Process: milling')))], 2, db,
            ))[0]
            assert new.id > old_id
            with pytest.raises(HTTPException) as error:
                await documents_router.delete_document(old_id, db=db)
            assert error.value.status_code == 404
            assert (tmp_path / 'uploads' / new.filename).is_file()
            assert await db.get(Document, new.id) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('expected_project,expected_filename', [
    (1, 'new.json'), (2, 'old.json'), (None, None), (2, None), (None, 'new.json'),
])
async def test_stale_delete_checks_project_and_document_identity(tmp_path, monkeypatch, expected_project, expected_filename):
    engine, sessions = await create_database(tmp_path / 'guard.db')
    isolate_uploads(monkeypatch, tmp_path / 'uploads')
    try:
        async with sessions() as db:
            db.add(Project(id=2, name='New project'))
            db.add(Document(id=17, project_id=2, filename='new.pdf', original_name='new.pdf', file_type='pdf'))
            await db.commit()
            (tmp_path / 'uploads' / 'new.pdf').write_bytes(_pdf_bytes())
            with pytest.raises(HTTPException) as error:
                await documents_router.delete_document(
                    17, db=db, project_id=expected_project, expected_filename=expected_filename,
                )
            assert error.value.status_code == 409
            assert await db.get(Document, 17) is not None
            assert (tmp_path / 'uploads' / 'new.pdf').is_file()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_document_http_actions_preserve_new_file_and_reject_stale_identity(tmp_path, monkeypatch):
    engine, sessions = await create_database(tmp_path / 'http-documents.db')
    isolate_uploads(monkeypatch, tmp_path / 'uploads', stub_invalidation=False)
    app = FastAPI()
    app.include_router(documents_router.router)

    async def override_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with sessions() as db:
            db.add_all([Project(id=1, name='A'), Project(id=2, name='B')])
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://isolated') as client:
            response = await client.post('/api/documents/upload', data={'project_id': 1},
                                         files={'files': ('old.pdf', _pdf_bytes(), 'application/pdf')})
            assert response.status_code == 200, response.text
            old = response.json()[0]
            wrong = await client.delete('/api/documents/{}'.format(old['id']),
                                        params={'project_id': 2, 'expected_filename': old['filename']})
            assert wrong.status_code == 409
            good = await client.delete('/api/documents/{}'.format(old['id']),
                                       params={'project_id': 1, 'expected_filename': old['filename']})
            assert good.status_code == 200, good.text
            response = await client.post('/api/documents/upload', data={'project_id': 2},
                                         files={'files': ('new.pdf', _pdf_bytes('Process: milling'), 'application/pdf')})
            assert response.status_code == 200, response.text
            new = response.json()[0]
            assert new['id'] != old['id']
            stale = await client.delete('/api/documents/{}'.format(old['id']))
            assert stale.status_code == 404
            assert (await client.get('/api/documents/{}/file'.format(new['id']))).status_code == 200
            assert (tmp_path / 'uploads' / new['filename']).is_file()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_seeds_allocator_from_existing_document_ids(tmp_path, monkeypatch):
    engine, sessions = await create_database(tmp_path / 'upgrade.db')
    isolate_uploads(monkeypatch, tmp_path / 'uploads')
    try:
        async with sessions() as db:
            db.add(Project(id=1, name='Existing project'))
            db.add(Document(id=77, project_id=1, filename='existing.pdf', original_name='existing.pdf', file_type='pdf'))
            await db.commit()
        async with engine.begin() as conn:
            await ensure_project_schema(conn)
        async with sessions() as db:
            await documents_router.delete_document(77, db=db, project_id=1, expected_filename='existing.pdf')
            new = (await documents_router.upload_documents(
                [UploadFile(filename='new.pdf', file=BytesIO(_pdf_bytes('Process: milling')))], 1, db,
            ))[0]
            assert new.id > 77
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('save_during_parse', [False, True])
async def test_queued_preprocessing_preserves_later_human_configuration(tmp_path, monkeypatch, save_during_parse):
    engine, sessions = await create_database(tmp_path / 'preprocess.db')
    gate = asyncio.Event()
    parse_started = asyncio.Event()
    original_job = preprocessing._run_job
    original_parser = condition_reviews.parse_rule_condition

    async def delayed_job(**kwargs):
        if not save_during_parse:
            await gate.wait()
        await original_job(**kwargs)

    async def delayed_parse(*args, **kwargs):
        parse_started.set()
        await gate.wait()
        return await original_parser(*args, **kwargs)

    async def parser_context():
        return 'regression-parser', {}

    monkeypatch.setattr(preprocessing, 'async_session', sessions)
    monkeypatch.setattr(preprocessing, '_run_job', delayed_job)
    monkeypatch.setattr(preprocessing, '_active_condition_parser_context', parser_context)
    monkeypatch.setattr(condition_reviews, '_active_condition_parser_context', parser_context)
    if save_during_parse:
        monkeypatch.setattr(condition_reviews, 'parse_rule_condition', delayed_parse)
    processes = [{'process_id': 'target', 'display_name': '检验', 'main': False}]
    new_text = '检验设为主工序，固定生成'
    task = None
    try:
        async with sessions() as db:
            db.add(Project(id=7, name='Rule race', workflow_revision=0))
            db.add(NormalizedRouteVersion(id=1, project_id=7, version=1,
                route_json=json.dumps([{'id': 'target', 'normalized_step_name': '检验'}])))
            await db.commit()
            await preprocessing.start_rule_preprocessing(RulePreprocessStartRequest(
                project_id=7, route_id=1, processes=processes,
                items=[{'segment_id': 'target', 'process_id': 'target', 'process_name': '检验',
                        'source_text': '当硬度不低于HRC58时，纳入检验工序'}],
            ), db)
            task = preprocessing.RULE_PREPROCESS_JOBS[(7, 1)]
        if save_during_parse:
            await asyncio.wait_for(parse_started.wait(), timeout=10)
        async with sessions() as db:
            saved = await condition_reviews.set_process_configuration_review(ManualRuleConditionRequest(
                project_id=7, route_id=1, segment_id='target', process_id='target',
                source_text=new_text, processes=processes,
                candidate={'kind': 'process_configuration',
                           'configuration': {'process_id': 'target', 'occurrence': 'always'}},
            ), db)
            assert saved.review.status == 'confirmed'
        gate.set()
        await asyncio.wait_for(task, timeout=10)
        async with sessions() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalar_one()
            assert row.condition_source_text == new_text
            assert row.condition_status == 'confirmed'
            assert row.condition_confirmed_json is not None
            state = await preprocessing._load_state(db, 7, 1)
            assert state['task_status'] == 'completed'
            assert state['failed_count'] == 0
    finally:
        gate.set()
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await engine.dispose()
