"""Saved object reuse must not leave later accepted rules bound to old facts."""
import json

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion
from app.services.analysis_drafts import AnalysisRuleDraft
from app.services.route_analysis import save_segment_rule_review_record


def trail(direction='A侧', source=None):
    values = [('guided_mode', 'condition'), ('guided_basis', 'precision'), ('guided_it', '6')]
    if source:
        values.append(('__object_reuse', json.dumps({'schema_version': 1,
            'features': {'values': ['通孔'], 'source_segment_ids': [source]},
            'direction': {'value': direction, 'source_segment_ids': [source]}})))
    else:
        values += [('guided_features', '通孔'), ('guided_direction', direction)]
    return [{'nodeId': key, 'value': value, 'label': value} for key, value in values]


@pytest.mark.asyncio
@pytest.mark.parametrize('change, expected', [('direction', ['hone', 'polish']), ('precision', []), ('basis', ['hone', 'polish'])])
async def test_source_object_edit_invalidates_only_object_dependents_transitively(change, expected):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        ids = ['grind', 'hone', 'polish', 'independent']
        session.add(NormalizedRouteVersion(id=3, project_id=7, version=1,
            route_json=json.dumps([{'id': key, 'export_process_id': key, 'normalized_step_name': key} for key in ids])))
        for key, source in [('grind', None), ('hone', 'grind'), ('polish', 'hone'), ('independent', None)]:
            session.add(NormalizedRouteSegmentRuleReview(project_id=7, route_version_id=3, segment_id=key,
                decision='accepted', question_trail_json=json.dumps(trail(source=source)),
                condition_status='confirmed', condition_confirmed_json='{}', analysis_draft_json=json.dumps({
                    'scope': '当前工序', 'object': '通孔', 'condition_text': '原条件', 'status': 'confirmed',
                    'missing': [], 'provenance': [], 'candidate': None})))
        await session.commit()
        new_trail = trail('B侧' if change == 'direction' else 'A侧')
        if change == 'precision':
            new_trail[2]['value'] = '7'
        if change == 'basis':
            new_trail[1]['value'] = 'material'
        draft = AnalysisRuleDraft(scope='当前工序', object='通孔', condition_text='更新条件', status='confirmed', candidate={
            'kind': 'process_configuration', 'configuration': {'process_id': 'grind', 'occurrence': 'always', 'when': None, 'relations': []}, 'preview': '更新条件',
        })
        response = await save_segment_rule_review_record(project_id=7, route_id=3, segment_id='grind',
            decision='accepted', note='', summary_lines=[], question_trail=new_trail, analysis_draft=draft, db=session)
        assert response.invalidated_segment_ids == expected
        rows = {row.segment_id: row for row in (await session.execute(select(NormalizedRouteSegmentRuleReview))).scalars()}
        assert rows['independent'].decision == 'accepted'
        for key in expected:
            assert rows[key].decision == 'pending'
            assert rows[key].condition_confirmed_json is None
            assert rows[key].condition_status == 'draft'
            assert json.loads(rows[key].analysis_draft_json)['status'] == 'incomplete'
            assert json.loads(rows[key].question_trail_json) == trail(source='grind' if key == 'hone' else 'hone')
    await engine.dispose()


def object_draft(key, direction='A侧', feature='通孔'):
    scope = 'project_factor.' + key
    return AnalysisRuleDraft(scope='当前工序', object=feature, condition_text='已确认的对象条件', status='confirmed', candidate={
        'kind': 'process_configuration', 'configuration': {'process_id': key, 'occurrence': 'conditional',
            'when': {'all': [
                {'field': scope + '.features', 'op': 'contains_any', 'value': [feature]},
                {'field': scope + '.direction', 'op': 'eq', 'value': direction},
                {'field': scope + '.it', 'op': 'lte', 'value': 6}]}, 'relations': []},
        'field_definitions': [
            {'key': scope + '.features', 'label': '特征', 'type': 'multi_select', 'category': '加工', 'operators': ['contains_any'], 'options': [{'value': feature, 'label': feature}]},
            {'key': scope + '.direction', 'label': '方位', 'type': 'single_select', 'category': '加工', 'operators': ['eq'], 'options': [{'value': side, 'label': side} for side in ['A侧', 'B侧']]},
            {'key': scope + '.it', 'label': '精度', 'type': 'number', 'category': '加工', 'operators': ['lte']}],
        'preview': '已确认的对象条件'})


async def save_object(session, key, direction='A侧', source=None, decision='accepted', draft_direction=None):
    return await save_segment_rule_review_record(project_id=7, route_id=3, segment_id=key,
        decision=decision, note='', summary_lines=[], question_trail=trail(direction, source),
        analysis_draft=object_draft(key, draft_direction or direction), db=session)


@pytest_asyncio.fixture
async def object_session():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(NormalizedRouteVersion(id=3, project_id=7, version=1, route_json=json.dumps([
            {'id': key, 'export_process_id': key, 'normalized_step_name': key} for key in ['grind', 'hone', 'polish']])))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_first_source_save_invalidates_existing_legacy_bindings(object_session):
    session = object_session
    session.add(NormalizedRouteSegmentRuleReview(project_id=7, route_version_id=3, segment_id='hone',
        decision='accepted', question_trail_json=json.dumps(trail(source='grind')),
        analysis_draft_json=object_draft('hone').model_dump_json()))
    await session.commit()
    result = await save_object(session, 'grind', direction='B侧')
    assert result.invalidated_segment_ids == ['hone']
    row = (await session.execute(select(NormalizedRouteSegmentRuleReview).where(
        NormalizedRouteSegmentRuleReview.segment_id == 'hone'))).scalar_one()
    assert row.decision == 'pending'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['direction', 'rejected', 'missing', 'forward', 'draft_mismatch'])
async def test_saved_reuse_rejects_unavailable_or_stale_source(object_session, change):
    from fastapi import HTTPException
    session = object_session
    if change != 'missing':
        await save_object(session, 'grind')
    if change in ['direction', 'rejected']:
        await save_object(session, 'hone', source='grind')
        response = await save_object(session, 'grind', direction='B侧' if change == 'direction' else 'A侧',
            decision='rejected' if change == 'rejected' else 'accepted')
        assert response.invalidated_segment_ids == ['hone']
    if change == 'forward':
        await save_object(session, 'polish')
    with pytest.raises(HTTPException) as error:
        await save_object(session, 'hone', source='polish' if change == 'forward' else 'grind',
            draft_direction='B侧' if change == 'draft_mismatch' else None)
    assert error.value.status_code == 409
    assert error.value.detail['code'] == 'stale_object_reuse'
    await session.rollback()
    if change in ['direction', 'rejected']:
        row = (await session.execute(select(NormalizedRouteSegmentRuleReview).where(
            NormalizedRouteSegmentRuleReview.segment_id == 'hone'))).scalar_one()
        assert row.decision == 'pending'


@pytest.mark.asyncio
async def test_current_transitive_reuse_and_explicit_manual_object_remain_valid(object_session):
    session = object_session
    await save_object(session, 'grind')
    await save_object(session, 'hone', source='grind')
    await save_object(session, 'polish', source='hone')
    invalidated = await save_object(session, 'grind', direction='B侧')
    assert invalidated.invalidated_segment_ids == ['hone', 'polish']
    manual = await save_object(session, 'hone', direction='A侧')
    assert manual.rule_review.decision == 'accepted'
    current = await save_object(session, 'polish', source='hone')
    assert current.rule_review.decision == 'accepted'


@pytest.mark.asyncio
async def test_source_graph_resolves_each_saved_object_once_per_save(object_session, monkeypatch):
    from app.services import analysis_object_dependencies as service
    session = object_session
    keys = ['object' + str(index) for index in range(14)]
    route = await session.get(NormalizedRouteVersion, 3)
    route.route_json = json.dumps([{'id': key, 'export_process_id': key, 'normalized_step_name': key} for key in keys])
    for index, key in enumerate(keys[:-1]):
        session.add(NormalizedRouteSegmentRuleReview(project_id=7, route_version_id=3, segment_id=key,
            decision='accepted', question_trail_json=json.dumps(trail(source=keys[index - 1] if index else None)),
            analysis_draft_json=object_draft(key).model_dump_json()))
    await session.commit()
    calls = 0
    original = service._trail

    def counted(raw):
        nonlocal calls
        calls += 1
        return original(raw)

    monkeypatch.setattr(service, '_trail', counted)
    result = await save_object(session, keys[-1], source=keys[-2])
    assert result.rule_review.decision == 'accepted'
    assert calls < len(keys) * 4, 'Shared feature/direction dependencies must not expand exponentially.'
