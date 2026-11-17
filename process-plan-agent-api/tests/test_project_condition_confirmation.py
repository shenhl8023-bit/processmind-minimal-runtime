"""Current project wildcard semantics at the real confirmation API boundaries."""

import json

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.routers.rule_packages import router
from app.services.rule_packages.condition_contracts import RuleConditionCandidate
from app.services.rule_packages.condition_reviews import condition_source_hash
from app.services.rule_packages.contracts import ConditionNode, RulePackageV2
from app.services.rule_packages.expression_engine import evaluate_condition, iter_condition_fields
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.project_conditions import project_condition_fields


SOURCE = 'A侧或B侧存在盲孔时安排钻孔。'
FEATURE = 'project_factor.operation_1a78c49e.features'
DIRECTION = 'project_factor.operation_1a78c49e.direction'
PATHS = [('confirm', 'condition'), ('confirm', 'process_configuration'), ('configuration', 'process_configuration')]


def candidate_for(kind, *, wildcard_only=False, nested=False):
    fields = {field.key: field for field in project_condition_fields('drill', '钻孔')}
    direction = {'field': DIRECTION, 'op': 'eq', 'value': '所有方位'}
    when = direction if wildcard_only else {'all': [
        {'field': FEATURE, 'op': 'contains_any', 'value': ['孔(盲孔)']}, direction,
    ]}
    if nested:
        when = {'all': [when]}
    payload = {'kind': kind, 'preview': '盲孔且方位等于所有方位时生成钻孔', 'evidence': SOURCE,
               'field_definitions': [fields[key].model_dump() for key in ([DIRECTION] if wildcard_only else [FEATURE, DIRECTION])]}
    if kind == 'condition':
        payload.update(when=when, then={'include_process_ids': ['drill']})
    else:
        payload['configuration'] = {'process_id': 'drill', 'occurrence': 'conditional', 'relations': [], 'when': when}
    return RuleConditionCandidate.model_validate(payload)


@pytest_asyncio.fixture
async def api():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all([Project(id=7, name='隔离方位确认回归'), NormalizedRouteVersion(
            id=1, project_id=7, version=1,
            route_json='[{"id":"prepare","normalized_step_name":"准备"},{"id":"drill","normalized_step_name":"钻孔"}]',
        )])
        await db.commit()
        app = FastAPI()
        app.include_router(router)

        async def test_db():
            yield db

        app.dependency_overrides[get_db] = test_db
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            yield client, db
    await engine.dispose()


async def submit(api, endpoint, candidate, existing_row=None):
    client, db = api
    row = existing_row or NormalizedRouteSegmentRuleReview(
        project_id=7, route_version_id=1, segment_id='drill', decision='accepted',
        condition_source_text=SOURCE, condition_source_hash=condition_source_hash(SOURCE),
        condition_status='pending_confirmation', condition_candidate_json=candidate.model_dump_json(by_alias=True),
    )
    if existing_row is None:
        db.add(row)
        await db.commit()
    body = {'project_id': 7, 'route_id': 1, 'segment_id': 'drill', 'source_text': SOURCE,
            'candidate': candidate.model_dump(mode='json', by_alias=True),
            'processes': [{'process_id': 'prepare', 'display_name': '准备', 'main': True},
                          {'process_id': 'drill', 'display_name': '钻孔'}]}
    body.update({'source_hash': row.condition_source_hash} if endpoint == 'confirm' else {'process_id': 'drill'})
    response = await client.post('/api/extract/finalized-rule-packages/rule-conditions/' + endpoint, json=body)
    await db.refresh(row)
    return response, row


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint,kind', PATHS)
@pytest.mark.parametrize('nested', [False, True])
async def test_confirmed_all_directions_keeps_a_b_range_and_definition(api, endpoint, kind, nested):
    candidate = candidate_for(kind, nested=nested)
    original = candidate.model_dump(mode='json', by_alias=True)
    response, row = await submit(api, endpoint, candidate)
    assert response.status_code == 200, response.text
    saved = RuleConditionCandidate.model_validate(json.loads(row.condition_confirmed_json))
    when = saved.configuration.when if saved.configuration else saved.when
    for direction in ['A侧', 'B侧']:
        assert evaluate_condition(when, {FEATURE: ['孔(盲孔)'], DIRECTION: direction}).matched
    for direction in ['中间', '周边']:
        assert not evaluate_condition(when, {FEATURE: ['孔(盲孔)'], DIRECTION: direction}).matched
    assert not evaluate_condition(when, {FEATURE: ['孔'], DIRECTION: '周边'}).matched
    assert set(iter_condition_fields(when)) == {FEATURE, DIRECTION}
    assert [field.key for field in saved.field_definitions] == [FEATURE, DIRECTION]
    assert '所有方位' not in saved.preview
    assert saved.evidence == SOURCE
    assert row.condition_candidate_json == row.condition_confirmed_json
    assert response.json()['review']['confirmed'] == json.loads(row.condition_confirmed_json)
    assert candidate.model_dump(mode='json', by_alias=True) == original

    rules = {'process_configurations': [saved.configuration.model_dump(by_alias=True)]} if saved.configuration else {
        'rules': [{'rule_id': 'drill', 'when': when.model_dump(by_alias=True), 'then': saved.then.model_dump()}],
    }
    package = RulePackageV2.model_validate({
        'manifest': {'package_name': '方位确认执行', 'project_id': 7, 'scope': {'key': '7'}},
        'input_schema': {'fields': [{'key': FEATURE, 'label': '钻孔特征', 'type': 'multi_select'}, {'key': DIRECTION, 'label': '方位', 'type': 'single_select'}]},
        'route_catalog': {'processes': [{'process_id': 'prepare', 'display_name': '准备', 'main': True},
                                        {'process_id': 'drill', 'display_name': '钻孔'}]},
        'route_rules': rules,
    })
    # The new A/B choice is a real range, not a wildcard.
    assert set(plan_route(package, {FEATURE: ['孔(盲孔)'], DIRECTION: 'A侧'}).selected_process_ids) == {'prepare', 'drill'}
    assert set(plan_route(package, {FEATURE: ['孔(盲孔)'], DIRECTION: '周边'}).selected_process_ids) == {'prepare'}
    assert set(plan_route(package, {FEATURE: ['孔'], DIRECTION: 'B侧'}).selected_process_ids) == {'prepare'}


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint,kind', PATHS)
@pytest.mark.parametrize('nested', [False, True])
async def test_all_directions_alone_confirms_a_nonempty_a_b_range(api, endpoint, kind, nested):
    response, row = await submit(api, endpoint, candidate_for(kind, wildcard_only=True, nested=nested))
    assert response.status_code == 200, response.text
    saved = RuleConditionCandidate.model_validate_json(row.condition_confirmed_json)
    when = saved.configuration.when if saved.configuration else saved.when
    assert evaluate_condition(when, {DIRECTION: 'A侧'}).matched
    assert not evaluate_condition(when, {DIRECTION: '周边'}).matched


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint,kind', PATHS)
async def test_normalized_a_b_choice_can_be_saved_again_with_its_frozen_domain(api, endpoint, kind):
    candidate = candidate_for(kind)
    candidate.field_definitions[1].options = [{'value': '所有方位', 'label': '所有方位'}]
    response, row = await submit(api, endpoint, candidate)
    assert response.status_code == 200, response.text
    saved = RuleConditionCandidate.model_validate_json(row.condition_confirmed_json)
    # Reopening a saved range must not discard it or invent A/B candidate options.
    response, row = await submit(api, endpoint, saved, existing_row=row)
    assert response.status_code == 200, response.text
    saved_again = RuleConditionCandidate.model_validate_json(row.condition_confirmed_json)
    assert saved_again == saved


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint,kind', PATHS)
async def test_concrete_project_direction_remains_a_required_condition(api, endpoint, kind):
    candidate = candidate_for(kind)
    when = candidate.configuration.when if candidate.configuration else candidate.when
    when.all_conditions[1].value = '周边'
    response, row = await submit(api, endpoint, candidate)
    assert response.status_code == 200, response.text
    saved = RuleConditionCandidate.model_validate(json.loads(row.condition_confirmed_json))
    when = saved.configuration.when if saved.configuration else saved.when
    assert list(iter_condition_fields(when)) == [FEATURE, DIRECTION]
    assert [field.key for field in saved.field_definitions] == [FEATURE, DIRECTION]
    assert evaluate_condition(when, {FEATURE: ['孔(盲孔)'], DIRECTION: '周边'}).matched
    assert not evaluate_condition(when, {FEATURE: ['孔(盲孔)'], DIRECTION: 'A侧'}).matched


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['confirm', 'configuration'])
@pytest.mark.parametrize('invalid', ['frozen-domain', 'different-object'])
async def test_wildcard_normalization_does_not_bypass_candidate_validation(api, endpoint, invalid):
    candidate = candidate_for('process_configuration')
    if invalid == 'frozen-domain':
        candidate.field_definitions[1].options = [{'value': '周边', 'label': '冻结候选'}]
    else:
        candidate.configuration.when.all_conditions[1].field = 'project_factor.operation_other.direction'
        candidate.field_definitions[1].key = 'project_factor.operation_other.direction'
    response, row = await submit(api, endpoint, candidate)
    assert response.status_code == 422, response.text
    assert row.condition_confirmed_json is None


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['confirm', 'configuration'])
async def test_generic_dynamic_direction_keeps_its_literal_eq_on_confirmation(api, endpoint):
    candidate = candidate_for('process_configuration', wildcard_only=True)
    candidate.configuration.when.field = 'project_factor.delivery_direction'
    candidate.field_definitions[0].key = 'project_factor.delivery_direction'
    response, row = await submit(api, endpoint, candidate)
    assert response.status_code == 200, response.text
    saved = RuleConditionCandidate.model_validate(json.loads(row.condition_confirmed_json))
    assert saved.configuration.when.value == '所有方位'
    assert not evaluate_condition(saved.configuration.when, {'project_factor.delivery_direction': '周边'}).matched


def test_historical_project_direction_eq_keeps_literal_execution_semantics():
    when = ConditionNode(field=DIRECTION, op='eq', value='所有方位')
    assert not evaluate_condition(when, {DIRECTION: '周边'}).matched
    assert evaluate_condition(when, {DIRECTION: '所有方位'}).matched
