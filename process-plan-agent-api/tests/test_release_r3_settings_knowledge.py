"""Isolated regressions for the settings and enterprise knowledge audit."""
import asyncio
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine, get_db
from app.models.models import (
    KnowledgeEvidenceSnapshot,
    KnowledgeRuleSuggestion,
    NormalizedRouteVersion,
    Project,
)
from app.routers import knowledge as knowledge_router, settings as settings_router
from app.schemas.schemas import KnowledgeRuleSuggestionUpdate
from app.services import settings_store
from app.services.knowledge import suggestions


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    for key, _, _ in settings_store.SETTING_DEFINITIONS:
        monkeypatch.delenv(key, raising=False)
        for alias in settings_store.ENV_ALIASES.get(key, ()):
            monkeypatch.delenv(alias, raising=False)
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE_PATH', path)
    return path


def test_partial_settings_file_keeps_defaults_and_explicitly_cleared_values(isolated_settings):
    isolated_settings.write_text(json.dumps([
        {'key': 'LLM_API_KEY', 'value': 'synthetic-key'},
        {'key': 'KNOWLEDGE_SEARCH_API_KEY', 'value': ''},
    ]), encoding='utf-8')
    app = FastAPI()
    app.include_router(settings_router.router)
    with TestClient(app) as client:
        response = client.get('/api/settings')
    assert response.status_code == 200
    values = {item['key']: item for item in response.json()}
    assert values['LLM_API_URL']['value'] == 'https://integrate.api.nvidia.com/v1/chat/completions'
    assert values['LLM_MODEL']['value'] == 'meta/llama-3.1-70b-instruct'
    assert values['KNOWLEDGE_SEARCH_PROVIDER']['value'] == 'tavily'
    assert values['KNOWLEDGE_SEARCH_API_URL']['value'] == 'https://api.tavily.com/search'
    assert values['LLM_API_KEY']['is_configured'] is True
    assert values['LLM_API_KEY']['value'] == ''
    assert settings_store.get_llm_settings_map()['LLM_API_KEY'] == 'synthetic-key'
    assert settings_store.get_llm_settings_map()['KNOWLEDGE_SEARCH_API_KEY'] == ''


@pytest.fixture
def knowledge_store(tmp_path):
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'knowledge.db'))
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(Project(id=1, name='Isolated audit'))
            await db.flush()
            db.add(NormalizedRouteVersion(
                id=11, project_id=1, version=1,
                route_json='[{"id":"op-40","normalized_step_name":"淬火"}]',
            ))
            await db.flush()
            db.add(KnowledgeEvidenceSnapshot(
                id=101, project_id=1, route_version_id=11, segment_id='op-40',
                query='硬度', item_id='test-chunk', content='硬度不低于56 HRC', snapshot_hash='e' * 64,
            ))
            await db.flush()
            db.add(KnowledgeRuleSuggestion(
                id=201, project_id=1, route_version_id=11, segment_id='op-40',
                title='硬度要求', suggestion_text='硬度不低于56 HRC', evidence_ids_json='[101]',
            ))
            await db.commit()

    asyncio.run(setup())
    app = FastAPI()
    app.include_router(knowledge_router.router)

    async def override_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, sessions
    finally:
        asyncio.run(engine.dispose())


@pytest.mark.parametrize('field', ['query', 'item_id', 'content'])
def test_blank_evidence_cannot_be_saved_as_review_support(knowledge_store, field):
    client, _ = knowledge_store
    payload = {
        'project_id': 1, 'route_version_id': 11, 'segment_id': 'op-40',
        'query': '硬度', 'item_id': 'new-chunk', 'content': '硬度不低于56 HRC',
    }
    payload[field] = ' \n\t '
    response = client.post('/api/knowledge/evidence', json=payload)
    assert response.status_code == 422, response.text
    saved = client.get('/api/knowledge/evidence', params={'project_id': 1})
    assert [item['id'] for item in saved.json()] == [101]


@pytest.mark.parametrize('race', ['edit_after_confirmation', 'confirm_after_rejection'])
def test_concurrent_suggestion_update_cannot_overwrite_review(knowledge_store, monkeypatch, race):
    _, sessions = knowledge_store
    validate_evidence = suggestions._validate_evidence_ids
    interleaved = False

    async def interleave_review(db, **kwargs):
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            async with sessions() as reviewer:
                if race == 'edit_after_confirmation':
                    await suggestions.update_suggestion(
                        reviewer, 201, KnowledgeRuleSuggestionUpdate(status='pending_review'),
                    )
                    await suggestions.update_suggestion(
                        reviewer, 201, KnowledgeRuleSuggestionUpdate(status='confirmed'),
                    )
                else:
                    await suggestions.update_suggestion(
                        reviewer, 201, KnowledgeRuleSuggestionUpdate(status='rejected'),
                    )
        return await validate_evidence(db, **kwargs)

    async def exercise():
        if race == 'confirm_after_rejection':
            async with sessions() as db:
                await suggestions.update_suggestion(
                    db, 201, KnowledgeRuleSuggestionUpdate(status='pending_review'),
                )
        monkeypatch.setattr(suggestions, '_validate_evidence_ids', interleave_review)
        async with sessions() as stale_request:
            payload = (
                KnowledgeRuleSuggestionUpdate(suggestion_text='未经审核的新条件', evidence_ids=[101])
                if race == 'edit_after_confirmation'
                else KnowledgeRuleSuggestionUpdate(status='confirmed')
            )
            with pytest.raises(HTTPException) as error:
                await suggestions.update_suggestion(stale_request, 201, payload)
            assert error.value.status_code == 409
        async with sessions() as db:
            row = await db.scalar(select(KnowledgeRuleSuggestion).where(KnowledgeRuleSuggestion.id == 201))
            assert row.status == ('confirmed' if race == 'edit_after_confirmation' else 'rejected')
            assert row.suggestion_text == '硬度不低于56 HRC'

    asyncio.run(exercise())


def test_legacy_second_precision_timestamp_can_be_updated_without_conflict(knowledge_store):
    client, sessions = knowledge_store

    async def seed_legacy_timestamp():
        async with sessions() as db:
            # Older DDL used SQLite's CURRENT_TIMESTAMP default, without fractional seconds.
            await db.execute(text(
                "UPDATE knowledge_rule_suggestions SET updated_at = '2026-11-02 04:00:00' WHERE id = 201"
            ))
            await db.commit()

    asyncio.run(seed_legacy_timestamp())
    response = client.patch('/api/knowledge/suggestions/201', json={"title": "旧版建议更新"})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "旧版建议更新"
