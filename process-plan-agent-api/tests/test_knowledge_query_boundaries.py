"""Knowledge query failures must keep local evidence usable."""
import asyncio

import pytest

from test_knowledge_local_api import _client
from app.database import get_db
from app.main import app


@pytest.mark.parametrize('answer', [{'answer': 'unexpected wrapper'}, ['unexpected list'], 17, True])
def test_search_degrades_non_text_model_responses_without_losing_evidence(tmp_path, monkeypatch, answer):
    client, engine = _client(tmp_path)

    async def fake_model(*args, **kwargs):
        return answer

    monkeypatch.setattr('app.services.knowledge.answer.call_llm', fake_model)
    try:
        response = client.post('/api/knowledge/search', json={'query': '9Cr18 衬套工艺', 'top_k': 3})
        assert response.status_code == 200
        payload = response.json()
        assert payload['status'] == 'llm_unavailable'
        assert payload['answer'] == ''
        assert '大模型' in payload['message']
        assert len(payload['items']) == 3
        assert all(item['source']['document_name'] for item in payload['items'])
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_search_rejects_whitespace_before_retrieving_local_records(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    retrieved = []

    def fake_search(query, top_k):
        retrieved.append(query)
        return {'items': [], 'message': '没有记录'}

    monkeypatch.setattr('app.routers.knowledge.search_local_knowledge', fake_search)
    try:
        response = client.post('/api/knowledge/search', json={'query': ' \t\n '})
        assert response.status_code == 422
        assert '问题' in str(response.json()['detail'])
        assert retrieved == []
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())
