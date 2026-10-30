from fastapi.testclient import TestClient

from app.main import app


def test_catalog_lists_all_knowledge_without_model_or_database(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('catalog must not call a model')
    monkeypatch.setattr('app.routers.knowledge.generate_local_knowledge_answer', forbidden)
    with TestClient(app) as client:
        response = client.get('/api/knowledge/catalog', params={'section': 'knowledge'})
    assert response.status_code == 200
    body = response.json()
    assert body['total'] == 875
    assert len(body['items']) == 20
    assert body['page_size'] == 20
    assert {x['value']: x['count'] for x in body['categories']} == {'process_guidance': 117, 'typical_route': 9, 'capability': 749}


def test_catalog_filters_topic_search_and_keeps_warning_details():
    with TestClient(app) as client:
        body = client.get('/api/knowledge/catalog', params={'section': 'knowledge', 'category': 'process_guidance', 'topic': 'allowance', 'q': '内孔', 'page_size': 2}).json()
        assert body['total'] > 2
        assert len(body['items']) == 2
        assert all(x['category'] == 'process_guidance' for x in body['items'])
        detail = client.get('/api/knowledge/catalog/record', params={'record_id': body['items'][0]['id']})
    assert detail.status_code == 200
    item = detail.json()
    assert item['guidance']['kind'] == 'allowance'
    assert item['guidance']['conditions']
    assert item['fields']
    assert item['sources'][0]['document_name']
    assert item['source_kind'] == 'process_document'


def test_catalog_resources_deduplicate_keep_sources_and_paginate():
    with TestClient(app) as client:
        first = client.get('/api/knowledge/catalog', params={'section': 'resources', 'category': 'equipment', 'page_size': 3}).json()
        second = client.get('/api/knowledge/catalog', params={'section': 'resources', 'category': 'equipment', 'page_size': 3, 'page': 2}).json()
        assert first['raw_count'] == 370
        assert first['total'] == 290
        assert len(first['items']) == len(second['items']) == 3
        assert {x['id'] for x in first['items']}.isdisjoint(x['id'] for x in second['items'])
        item = client.get('/api/knowledge/catalog/record', params={'record_id': first['items'][0]['id']}).json()
        assert item['sources']
        assert item['source_kind'] == 'handbook'
        assert item['source_label'] == '手册参考'


def test_catalog_preserves_invalid_ranges_and_zero_values():
    with TestClient(app) as client:
        item = client.get('/api/knowledge/catalog/record', params={'record_id': 'CP-636'}).json()
        assert item['fields']['Ra下限_μm'] == 32
        assert item['fields']['Ra上限_μm'] == 6.3
        assert item['data_warnings']
        first = client.get('/api/knowledge/catalog/record', params={'record_id': 'gauge-2'}).json()
        assert first['fields']['测量范围下限_mm'] == 0


def test_catalog_validation_and_empty_results():
    with TestClient(app) as client:
        for params in ({'section': 'bad'}, {'page': 0}, {'page_size': 101}, {'category': 'history'}, {'sort': 'bad'}, {'section': 'knowledge', 'category': 'equipment'}):
            assert client.get('/api/knowledge/catalog', params=params).status_code == 422
        assert client.get('/api/knowledge/catalog/record', params={'record_id': 'J/RT145-13-01:工序0'}).status_code == 404
        assert client.get('/api/knowledge/catalog/record', params={'record_id': 'missing'}).status_code == 404
        empty = client.get('/api/knowledge/catalog', params={'q': '绝对不存在XYZ999'}).json()
        assert empty['total'] == 0 and empty['items'] == []


def test_catalog_preserves_special_ids_conflict_and_parameter_variants(monkeypatch):
    from app.services.knowledge import catalog
    records = [
        {'id': 'WD/01:第3节', 'category': 'process_guidance', 'title': '零值余量',
         'fields': {'下限': 0}, 'source': {'document_name': '规程.docx', 'identity': '第三节'},
         'guidance': {'kind': 'allowance', 'verification_status': 'conflict', 'conditions': '单边'}},
    ]
    for identifier, diameter, source_row in [('e/1', 20, 2), ('e/2', 20, 3), ('e/3', 30, 4)]:
        records.append({'id': identifier, 'category': 'equipment', 'title': '车床',
                        'fields': {'设备ID': identifier, '设备名称': '车床', '设备型号': 'A1', '最大工件直径_mm': diameter},
                        'source': {'document_name': '手册.xlsx', 'row_no': source_row}})
    monkeypatch.setattr(catalog, '_load_records', lambda: tuple(records))
    with TestClient(app) as client:
        body = client.get('/api/knowledge/catalog', params={'section': 'resources'}).json()
        assert body['total'] == 2 and body['raw_count'] == 3
        originals = [client.get('/api/knowledge/catalog/record', params={'record_id': row['id']}).json() for row in body['items']]
        assert sorted(len(row['sources']) for row in originals) == [1, 2]
        assert sorted(len(row['original_records']) for row in originals) == [1, 2]
        detail = client.get('/api/knowledge/catalog/record', params={'record_id': 'WD/01:第3节'}).json()
        assert detail['verification_status'] == 'conflict'
        assert detail['fields']['下限'] == 0
        assert any('冲突' in warning for warning in detail['data_warnings'])


def test_catalog_stable_sort_and_page_bounds():
    with TestClient(app) as client:
        asc = client.get('/api/knowledge/catalog', params={'sort': 'title_asc', 'page_size': 100}).json()
        desc = client.get('/api/knowledge/catalog', params={'sort': 'title_desc', 'page_size': 100}).json()
        assert asc['items'][0]['title'] <= asc['items'][-1]['title']
        assert desc['items'][0]['title'] >= desc['items'][-1]['title']
        assert client.get('/api/knowledge/catalog', params={'page': 999}).json()['items'] == []
        assert client.get('/api/knowledge/catalog', params={'topic': 'invalid'}).status_code == 422
        assert client.get('/api/knowledge/catalog', params={'section': 'resources', 'topic': 'allowance'}).status_code == 422


def test_catalog_flags_reversed_spindle_bounds_without_changing_source_values():
    with TestClient(app) as client:
        detail = client.get('/api/knowledge/catalog/record', params={'record_id': 'equipment-78'}).json()
        assert detail['fields']['主轴转速下限_r_min'] == 1000
        assert detail['fields']['主轴转速上限_r_min'] == 700
        assert any('主轴转速' in warning and '异常' in warning for warning in detail['data_warnings'])
        listing = client.get('/api/knowledge/catalog', params={'section': 'resources', 'category': 'equipment', 'q': 'TK6411'}).json()
        assert any('主轴转速' in warning for item in listing['items'] for warning in item['data_warnings'])


def test_catalog_topics_are_scoped_to_the_selected_category(monkeypatch):
    from app.services.knowledge import catalog
    records = [
        {'id': 'process-1', 'category': 'process_guidance', 'title': '加工余量',
         'fields': {}, 'source': {'document_name': '工艺.docx', 'identity': '§1'},
         'guidance': {'kind': 'allowance', 'verification_status': 'verified'}},
        {'id': 'route-1', 'category': 'typical_route', 'title': '典型路线',
         'fields': {}, 'source': {'document_name': '路线.docx', 'identity': '§2'},
         'guidance': {'kind': 'stage_overview', 'verification_status': 'pending'}},
    ]
    monkeypatch.setattr(catalog, '_load_records', lambda: tuple(records))
    with TestClient(app) as client:
        body = client.get('/api/knowledge/catalog', params={
            'section': 'knowledge', 'category': 'process_guidance',
        }).json()
    counts = {item['value']: item['count'] for item in body['topics']}
    assert counts['allowance'] == 1
    assert counts['stage_overview'] == 0


def test_catalog_resource_variants_keep_their_own_detail_records(monkeypatch):
    from app.services.knowledge import catalog
    records = [
        {'id': 'equipment-20', 'category': 'equipment', 'title': '车床',
         'fields': {'设备ID': 'E-1', '设备名称': '车床', '设备型号': 'A1', '最大工件直径_mm': 20},
         'source': {'document_name': '手册.xlsx', 'row_no': 2}},
        {'id': 'equipment-30', 'category': 'equipment', 'title': '车床',
         'fields': {'设备ID': 'E-1', '设备名称': '车床', '设备型号': 'A1', '最大工件直径_mm': 30},
         'source': {'document_name': '手册.xlsx', 'row_no': 3}},
    ]
    monkeypatch.setattr(catalog, '_load_records', lambda: tuple(records))
    with TestClient(app) as client:
        listing = client.get('/api/knowledge/catalog', params={'section': 'resources'}).json()
        assert listing['total'] == 2
        assert len({row['id'] for row in listing['items']}) == 2
        details = [client.get('/api/knowledge/catalog/record', params={'record_id': row['id']}).json()
                   for row in listing['items']]
    assert {detail['fields']['最大工件直径_mm'] for detail in details} == {20, 30}


def test_catalog_marks_same_source_guidance_values_as_conflict(monkeypatch):
    from app.services.knowledge import catalog
    def record(identifier, value):
        return {
            'id': identifier, 'category': 'process_guidance',
            'title': '同一来源粗糙度', 'fields': {},
            'source': {'document_id': 'DOC-1', 'document_name': '结构图.docx', 'identity': 'image1.png'},
            'guidance': {
                'kind': 'reference', 'part_family': '组件', 'typical_part': 'RT34(03)-100',
                'materials': [], 'topics': ['局部表面粗糙度'], 'conditions': '仅适用于结构图示',
                'conclusion': '%s μm' % value,
                'metrics': [{'name': '局部表面粗糙度', 'min': value, 'max': value, 'unit': 'μm'}],
                'verification_status': 'verified',
            },
        }
    monkeypatch.setattr(catalog, '_load_records', lambda: tuple([record('roughness-16', 0.16), record('roughness-32', 0.32)]))
    with TestClient(app) as client:
        listing = client.get('/api/knowledge/catalog', params={'section': 'knowledge'}).json()
        details = [client.get('/api/knowledge/catalog/record', params={'record_id': row['id']}).json()
                   for row in listing['items']]
    assert all(detail['verification_status'] == 'conflict' for detail in details)
    assert all(detail['guidance']['verification_status'] == 'conflict' for detail in details)
    assert all(any('同一来源' in warning or '冲突' in warning for warning in detail['data_warnings'])
               for detail in details)
